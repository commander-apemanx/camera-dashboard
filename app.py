#!/usr/bin/env python3
"""Four-camera RTSP/ONVIF dashboard with person detection."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse, urlunparse

import cv2
import numpy as np
from flask import (
    Flask,
    Response,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS
from flask_socketio import SocketIO, disconnect
from functools import wraps

from auth_vault import AuthVault, redact_rtsp_url, strip_rtsp_auth

# OpenCV intra-op threads fight YOLO/torch for cores and make the grid stutter.
cv2.setNumThreads(1)
try:
    cv2.ocl.setUseOpenCL(False)
except Exception:  # noqa: BLE001
    pass

app = Flask(__name__)
CORS(app, supports_credentials=True)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 14  # 14 days max cookie life

MAX_CAMERAS = 4
DETECTION_COOLDOWN_SEC = 3.0  # terminal notification throttle
DEFAULT_SNAPSHOT_DELAY_SEC = 20.0  # photo capture throttle (user-selectable)
MIN_SNAPSHOT_DELAY_SEC = 1.0
MAX_SNAPSHOT_DELAY_SEC = 600.0
JPEG_QUALITY = 70
SNAPSHOT_JPEG_QUALITY = 90
FRAME_WIDTH = 640
FRAME_HEIGHT = 360
YOLO_IMGSZ = 320
YOLO_CONF = 0.45
PROBE_TIMEOUT_SEC = 8.0
DETECT_INTERVAL_SEC = 0.4  # per-camera YOLO submit rate
BOX_TTL_SEC = 2.0  # keep last boxes so overlays do not flicker
RECONNECT_WAIT_SEC = 1.5
OPEN_FAIL_WAIT_SEC = 5.0
READ_FAIL_LIMIT = 30
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
SNAPSHOT_DIR = os.path.join(ROOT_DIR, "Data")  # person-detection photos
CAMERAS_FILE = os.path.join(DATA_DIR, "cameras.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_UNLOCK_UNTIL_REBOOT = True

# Low-latency RTSP. start.sh / Docker often set only rtsp_transport;tcp — upgrade that.
FFMPEG_CAPTURE_OPTIONS = (
    "rtsp_transport;tcp|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "max_delay;500000|"
    "stimeout;5000000"
)
_existing_ff = (os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS") or "").strip()
if not _existing_ff or _existing_ff == "rtsp_transport;tcp":
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = FFMPEG_CAPTURE_OPTIONS

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

_BLACK_JPEG: Optional[bytes] = None
_BLACK_JPEG_LOCK = threading.Lock()


def _black_jpeg() -> bytes:
    global _BLACK_JPEG
    if _BLACK_JPEG:
        return _BLACK_JPEG
    with _BLACK_JPEG_LOCK:
        if _BLACK_JPEG:
            return _BLACK_JPEG
        img = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
        _BLACK_JPEG = buf.tobytes() if ok else b""
        return _BLACK_JPEG


def _load_secret_key() -> str:
    env = (os.environ.get("SECRET_KEY") or "").strip()
    if env:
        return env
    path = os.path.join(DATA_DIR, ".secret_key")
    try:
        if os.path.isfile(path):
            stored = open(path, "r", encoding="utf-8").read().strip()
            if stored:
                return stored
        generated = uuid.uuid4().hex + uuid.uuid4().hex
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(generated)
        return generated
    except OSError:
        return uuid.uuid4().hex


app.config["SECRET_KEY"] = _load_secret_key()
vault = AuthVault(DATA_DIR)


def _safe_name(value: str) -> str:
    """Filesystem-safe token from camera name."""
    cleaned = []
    for ch in (value or "camera").strip():
        if ch.isalnum() or ch in ("-", "_"):
            cleaned.append(ch)
        elif ch.isspace():
            cleaned.append("_")
    out = "".join(cleaned).strip("._") or "camera"
    return out[:48]


PersonBox = Tuple[float, Tuple[int, int, int, int]]


def _draw_person_boxes(frame: np.ndarray, boxes: List[PersonBox]) -> np.ndarray:
    """Draw person rectangles + labels onto frame (in place)."""
    for conf, (x1, y1, x2, y2) in boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 80), 2)
        label = f"Person {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = max(0, y1 - th - 8)
        cv2.rectangle(frame, (x1, top), (x1 + tw + 4, y1), (0, 220, 80), -1)
        cv2.putText(
            frame,
            label,
            (x1 + 2, max(th + 2, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return frame


def _quote_auth(value: str) -> str:
    return quote(value or "", safe="")


def build_rtsp_url(ip: str, port: int, username: str, password: str, path: str) -> str:
    user = username or ""
    pwd = password or ""
    if user or pwd:
        auth = f"{_quote_auth(user)}:{_quote_auth(pwd)}@"
    else:
        auth = ""
    path = (path or "").strip()
    if path and not path.startswith("/"):
        path = f"/{path}"
    return f"rtsp://{auth}{ip}:{int(port or 554)}{path}"


def inject_rtsp_auth(url: str, username: str, password: str) -> str:
    """Ensure RTSP URL includes credentials when ONVIF omits them."""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.username or not (username or password):
        return url
    host = parsed.hostname or ""
    netloc = f"{_quote_auth(username)}:{_quote_auth(password)}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def _open_capture(url: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(PROBE_TIMEOUT_SEC * 1000))
    if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
    return cap


def _release_capture(cap: Optional[cv2.VideoCapture]) -> None:
    if cap is None:
        return
    try:
        cap.release()
    except Exception:  # noqa: BLE001
        pass


def resolve_onvif_rtsp(
    ip: str,
    port: int,
    username: str,
    password: str,
    profile_index: int = 0,
) -> Tuple[Optional[str], Optional[str]]:
    """Discover RTSP URI via ONVIF. Returns (rtsp_url, error)."""
    try:
        from onvif import ONVIFCamera
    except ImportError:
        return None, "onvif-zeep not installed. Re-run ./start.sh"

    ports_to_try = []
    p = int(port or 80)
    for candidate in (p, 80, 8080, 8000, 8899):
        if candidate not in ports_to_try:
            ports_to_try.append(candidate)

    last_err = "ONVIF connection failed"
    for onvif_port in ports_to_try:
        try:
            cam = ONVIFCamera(ip, onvif_port, username or "", password or "", no_cache=True)
            media = cam.create_media_service()
            profiles = media.GetProfiles()
            if not profiles:
                last_err = "ONVIF connected but no media profiles found"
                continue
            idx = max(0, min(profile_index, len(profiles) - 1))
            token = profiles[idx].token
            req = media.create_type("GetStreamUri")
            req.ProfileToken = token
            req.StreamSetup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
            result = media.GetStreamUri(req)
            uri = getattr(result, "Uri", None) or (result.get("Uri") if isinstance(result, dict) else None)
            if not uri:
                last_err = "ONVIF returned empty stream URI"
                continue
            uri = inject_rtsp_auth(str(uri), username or "", password or "")
            return uri, None
        except Exception as exc:  # noqa: BLE001
            last_err = f"ONVIF port {onvif_port}: {exc}"
            continue
    return None, last_err


def probe_rtsp(url: str, timeout_sec: float = PROBE_TIMEOUT_SEC) -> Tuple[bool, str]:
    """Open RTSP and read one frame. Returns (ok, message)."""
    if not url.lower().startswith("rtsp://"):
        return False, "URL is not an RTSP stream"

    cap = None
    deadline = time.time() + timeout_sec
    try:
        cap = _open_capture(url)
        if not cap.isOpened():
            return False, "Cannot open stream (check IP, port, path, credentials)"

        while time.time() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None and getattr(frame, "size", 0) > 0:
                h, w = frame.shape[:2]
                return True, f"Stream OK ({w}x{h})"
            time.sleep(0.1)

        return False, f"Connected but no frames within {timeout_sec:.0f}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"Probe error: {exc}"
    finally:
        _release_capture(cap)


@dataclass
class CameraConfig:
    id: str
    name: str
    ip: str
    port: int
    username: str
    password: str
    path: str
    protocol: str = "rtsp"  # rtsp | onvif
    rtsp_url: str = ""
    password_enc: str = ""
    enabled: bool = True
    last_status: str = ""
    last_message: str = ""

    def build_url(self) -> str:
        # Stored rtsp_url must be credential-free; inject live decrypted password.
        if self.rtsp_url:
            return inject_rtsp_auth(strip_rtsp_auth(self.rtsp_url), self.username, self.password)
        return build_rtsp_url(self.ip, self.port, self.username, self.password, self.path)

    def to_disk_dict(self) -> dict:
        data = asdict(self)
        data["password"] = ""
        data["rtsp_url"] = strip_rtsp_auth(self.rtsp_url or "")
        return data

    @staticmethod
    def from_dict(item: dict) -> "CameraConfig":
        allowed = {f.name for f in fields(CameraConfig)}
        data = {k: v for k, v in item.items() if k in allowed}
        data.setdefault("protocol", "rtsp")
        data.setdefault("path", "")
        data.setdefault("rtsp_url", "")
        data.setdefault("password_enc", "")
        data.setdefault("enabled", True)
        data.setdefault("last_status", "")
        data.setdefault("last_message", "")
        # Never keep plaintext password from disk into memory until vault unlock.
        if data.get("password_enc"):
            data["password"] = ""
        data["rtsp_url"] = strip_rtsp_auth(str(data.get("rtsp_url") or ""))
        return CameraConfig(**data)


@dataclass
class DetectionEvent:
    id: str
    camera_id: str
    camera_name: str
    timestamp: str
    count: int
    confidence: float
    message: str
    snapshot: str = ""


@dataclass
class DetectionResult:
    boxes: List[PersonBox]
    count: int
    confidence: float
    ts: float
    seq: int


class PersonDetector:
    """Lazy-loaded YOLOv8 person detector. Called from DetectionHub only."""

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._ready = False
        self._error: Optional[str] = None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                try:
                    import torch

                    n = os.cpu_count() or 2
                    torch.set_num_threads(max(1, min(4, n)))
                except Exception:  # noqa: BLE001
                    pass

                from ultralytics import YOLO

                weights = os.path.join(ROOT_DIR, "yolov8n.pt")
                self._model = YOLO(weights if os.path.isfile(weights) else "yolov8n.pt")
                dummy = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
                self._model.predict(
                    dummy,
                    conf=YOLO_CONF,
                    imgsz=YOLO_IMGSZ,
                    classes=[0],
                    verbose=False,
                )
                self._ready = True
                self._error = None
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)
                self._ready = False
                self._model = None

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def error(self) -> Optional[str]:
        return self._error

    def detect(self, frame: np.ndarray) -> Tuple[int, float, List[PersonBox]]:
        if not self._ready or self._model is None:
            return 0, 0.0, []

        try:
            extracted: List[PersonBox] = []
            with self._lock:
                if not self._ready or self._model is None:
                    return 0, 0.0, []
                results = self._model.predict(
                    frame,
                    conf=YOLO_CONF,
                    imgsz=YOLO_IMGSZ,
                    classes=[0],
                    verbose=False,
                )
                h, w = frame.shape[:2]
                for result in results:
                    boxes = result.boxes
                    if boxes is None:
                        continue
                    for box in boxes:
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        x1 = max(0, min(w - 1, x1))
                        y1 = max(0, min(h - 1, y1))
                        x2 = max(0, min(w - 1, x2))
                        y2 = max(0, min(h - 1, y2))
                        if x2 <= x1 or y2 <= y1:
                            continue
                        extracted.append((conf, (x1, y1, x2, y2)))

            if not extracted:
                return 0, 0.0, []

            max_conf = max(conf for conf, _ in extracted)
            return len(extracted), max_conf, extracted
        except Exception as exc:  # noqa: BLE001
            print(f"[YOLO] {exc}", flush=True)
            return 0, 0.0, []


class DetectionHub:
    """
    Single YOLO worker. Camera threads submit the latest frame (stale frames
    are dropped) so inference never blocks RTSP reads.
    """

    def __init__(self, detector: PersonDetector) -> None:
        self.detector = detector
        self._inbox: Dict[str, np.ndarray] = {}
        self._results: Dict[str, DetectionResult] = {}
        self._seqs: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="yolo-hub", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wakeup.set()

    def submit(self, camera_id: str, frame: np.ndarray) -> None:
        with self._lock:
            self._inbox[camera_id] = frame.copy()
        self._wakeup.set()

    def latest(self, camera_id: str) -> Optional[DetectionResult]:
        with self._lock:
            return self._results.get(camera_id)

    def clear(self, camera_id: str) -> None:
        with self._lock:
            self._inbox.pop(camera_id, None)
            self._results.pop(camera_id, None)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wakeup.wait(timeout=0.2)
            self._wakeup.clear()
            if not self.detector.ready:
                continue
            while not self._stop.is_set() and self.detector.ready:
                with self._lock:
                    if not self._inbox:
                        break
                    camera_id, frame = next(iter(self._inbox.items()))
                    del self._inbox[camera_id]
                count, conf, boxes = self.detector.detect(frame)
                with self._lock:
                    seq = self._seqs.get(camera_id, 0) + 1
                    self._seqs[camera_id] = seq
                    self._results[camera_id] = DetectionResult(
                        boxes=boxes,
                        count=count,
                        confidence=conf,
                        ts=time.monotonic(),
                        seq=seq,
                    )


class CameraWorker:
    """Reads RTSP on its own thread; YOLO runs in DetectionHub."""

    def __init__(self, config: CameraConfig, manager: "CameraManager") -> None:
        self.config = config
        self.manager = manager
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._status = "stopped"
        self._last_error = ""
        self._fps = 0.0
        self._person_count = 0
        self._last_detection_emit = 0.0
        self._last_snapshot_time = 0.0
        self._last_submit = 0.0
        self._last_result_seq = -1
        self._cap: Optional[cv2.VideoCapture] = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def person_count(self) -> int:
        return self._person_count

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"cam-{self.config.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        # Never release VideoCapture from another thread — that segfaults OpenCV/FFmpeg
        # while cap.read() is blocked. Signal stop and let _run() release in its finally.
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=8.0)
        self._thread = None
        self._cap = None
        self._status = "stopped"
        self._person_count = 0
        self.manager.hub.clear(self.config.id)

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def _placeholder(self, text: str) -> bytes:
        img = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        img[:] = (28, 28, 32)
        cv2.putText(img, self.config.name, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
        cv2.putText(img, text, (20, FRAME_HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 140, 255), 2)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        return buf.tobytes() if ok else b""

    def _set_jpeg(self, data: bytes) -> None:
        with self._lock:
            self._jpeg = data

    def _handle_detection(self, frame: np.ndarray, persons: int, conf: float) -> None:
        now_m = time.monotonic()
        snapshot_name = ""
        if self.manager.snapshot_enabled:
            delay = self.manager.snapshot_delay_sec
            if now_m - self._last_snapshot_time >= delay:
                snapshot_name = self.manager.save_snapshot(self.config.name, frame)
                if snapshot_name:
                    self._last_snapshot_time = now_m

        if snapshot_name or (now_m - self._last_detection_emit >= DETECTION_COOLDOWN_SEC):
            self._last_detection_emit = now_m
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = (
                f"Person detected on {self.config.name} "
                f"({persons} person{'s' if persons != 1 else ''}, conf {conf:.0%})"
            )
            if snapshot_name:
                msg += f" · saved {snapshot_name}"
            event = DetectionEvent(
                id=str(uuid.uuid4())[:8],
                camera_id=self.config.id,
                camera_name=self.config.name,
                timestamp=ts,
                count=persons,
                confidence=round(conf, 3),
                message=msg,
                snapshot=snapshot_name,
            )
            self.manager.add_detection(event)

    def _run(self) -> None:
        url = self.config.build_url()
        self.manager.hub.clear(self.config.id)
        self._set_jpeg(self._placeholder("Connecting..."))

        while not self._stop.is_set():
            try:
                self._run_session(url)
            except Exception as exc:  # noqa: BLE001
                self._status = "error"
                self._last_error = str(exc)
                print(f"[CAM {self.config.name}] {exc}", flush=True)
                self._set_jpeg(self._placeholder("Error — retrying"))
            finally:
                cap = self._cap
                self._cap = None
                _release_capture(cap)

            if not self._stop.is_set():
                self._status = "reconnecting"
                self._stop.wait(RECONNECT_WAIT_SEC)

        self._status = "stopped"

    def _run_session(self, url: str) -> None:
        self._status = "connecting"
        self._set_jpeg(self._placeholder("Connecting..."))

        cap = _open_capture(url)
        self._cap = cap
        if not cap.isOpened():
            self._status = "error"
            self._last_error = "Cannot open stream"
            self._set_jpeg(self._placeholder("Stream unavailable"))
            self._stop.wait(OPEN_FAIL_WAIT_SEC)
            return

        self._status = "live"
        self._last_error = ""
        fail = 0
        frames = 0
        last_t = time.monotonic()
        self._last_submit = 0.0
        self._last_result_seq = -1

        while not self._stop.is_set():
            ok, frame = cap.read()
            if self._stop.is_set():
                return
            if not ok or frame is None or getattr(frame, "size", 0) == 0:
                fail += 1
                if fail > READ_FAIL_LIMIT:
                    self._status = "reconnecting"
                    self._set_jpeg(self._placeholder("Reconnecting..."))
                    return
                continue

            fail = 0
            if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
                frame = cv2.resize(
                    frame,
                    (FRAME_WIDTH, FRAME_HEIGHT),
                    interpolation=cv2.INTER_AREA,
                )

            now = time.monotonic()
            if self.manager.detector.ready and (now - self._last_submit) >= DETECT_INTERVAL_SEC:
                self.manager.hub.submit(self.config.id, frame)
                self._last_submit = now

            result = self.manager.hub.latest(self.config.id)
            boxes: List[PersonBox] = []
            persons = 0
            conf = 0.0
            if result is not None and (now - result.ts) <= BOX_TTL_SEC:
                boxes = result.boxes
                persons = result.count
                conf = result.confidence
            self._person_count = persons

            if boxes:
                _draw_person_boxes(frame, boxes)

            if result is not None and result.seq != self._last_result_seq:
                self._last_result_seq = result.seq
                if persons > 0:
                    self._handle_detection(frame, persons, conf)

            cv2.rectangle(frame, (0, 0), (FRAME_WIDTH, 28), (0, 0, 0), -1)
            cv2.putText(
                frame,
                f"{self.config.name}  |  {self._status.upper()}  |  FPS {self._fps:.1f}",
                (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (180, 255, 180),
                1,
                cv2.LINE_AA,
            )

            ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if ok_enc:
                self._set_jpeg(buf.tobytes())

            frames += 1
            if now - last_t >= 1.0:
                self._fps = frames / (now - last_t)
                frames = 0
                last_t = now


class CameraManager:
    def __init__(self) -> None:
        self.detector = PersonDetector()
        self.hub = DetectionHub(self.detector)
        self.cameras: Dict[str, CameraConfig] = {}
        self.workers: Dict[str, CameraWorker] = {}
        self.detections: Deque[DetectionEvent] = deque(maxlen=500)
        self._lock = threading.RLock()
        self._order: List[str] = []  # stable slot order
        self._snapshot_delay_sec = DEFAULT_SNAPSHOT_DELAY_SEC
        self._snapshot_enabled = True
        self._unlock_until_reboot = DEFAULT_UNLOCK_UNTIL_REBOOT
        self._settings_lock = threading.Lock()
        self._legacy_plain: Dict[str, str] = {}
        self._load_settings()
        self._load()
        self.hub.start()

    @property
    def snapshot_delay_sec(self) -> float:
        return self._snapshot_delay_sec

    @property
    def snapshot_enabled(self) -> bool:
        return self._snapshot_enabled

    @property
    def unlock_until_reboot(self) -> bool:
        return self._unlock_until_reboot

    def _load_settings(self) -> None:
        if not os.path.isfile(SETTINGS_FILE):
            self._save_settings()
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            delay = float(raw.get("snapshot_delay_sec", DEFAULT_SNAPSHOT_DELAY_SEC))
            self._snapshot_delay_sec = max(MIN_SNAPSHOT_DELAY_SEC, min(MAX_SNAPSHOT_DELAY_SEC, delay))
            self._snapshot_enabled = bool(raw.get("snapshot_enabled", True))
            self._unlock_until_reboot = bool(raw.get("unlock_until_reboot", DEFAULT_UNLOCK_UNTIL_REBOOT))
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Failed to load settings.json: {exc}", flush=True)
            self._snapshot_delay_sec = DEFAULT_SNAPSHOT_DELAY_SEC
            self._snapshot_enabled = True
            self._unlock_until_reboot = DEFAULT_UNLOCK_UNTIL_REBOOT

    def _save_settings(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        payload = {
            "snapshot_delay_sec": self._snapshot_delay_sec,
            "snapshot_enabled": self._snapshot_enabled,
            "unlock_until_reboot": self._unlock_until_reboot,
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except OSError:
            pass

    def get_settings(self) -> dict:
        return {
            "snapshot_delay_sec": self._snapshot_delay_sec,
            "snapshot_enabled": self._snapshot_enabled,
            "unlock_until_reboot": self._unlock_until_reboot,
            "min_snapshot_delay_sec": MIN_SNAPSHOT_DELAY_SEC,
            "max_snapshot_delay_sec": MAX_SNAPSHOT_DELAY_SEC,
            "default_snapshot_delay_sec": DEFAULT_SNAPSHOT_DELAY_SEC,
            "snapshot_dir": "Data",
            "auth_setup": vault.is_setup,
            "vault_unlocked": vault.unlocked,
            "session_authenticated": bool(session.get("authenticated")) if has_request_context() else False,
        }

    def update_settings(
        self,
        snapshot_delay_sec: Optional[float] = None,
        snapshot_enabled: Optional[bool] = None,
        unlock_until_reboot: Optional[bool] = None,
    ) -> Tuple[bool, str, dict]:
        with self._settings_lock:
            if snapshot_delay_sec is not None:
                try:
                    val = float(snapshot_delay_sec)
                except (TypeError, ValueError):
                    return False, "snapshot_delay_sec must be a number", self.get_settings()
                if val < MIN_SNAPSHOT_DELAY_SEC or val > MAX_SNAPSHOT_DELAY_SEC:
                    return (
                        False,
                        f"Delay must be between {MIN_SNAPSHOT_DELAY_SEC:g} and {MAX_SNAPSHOT_DELAY_SEC:g} seconds",
                        self.get_settings(),
                    )
                self._snapshot_delay_sec = val
            if snapshot_enabled is not None:
                self._snapshot_enabled = bool(snapshot_enabled)
            if unlock_until_reboot is not None:
                self._unlock_until_reboot = bool(unlock_until_reboot)
            self._save_settings()
        print(
            f"[SETTINGS] snapshot_enabled={self._snapshot_enabled} delay={self._snapshot_delay_sec}s "
            f"unlock_until_reboot={self._unlock_until_reboot}",
            flush=True,
        )
        return True, "Settings updated", self.get_settings()

    def set_snapshot_delay(self, seconds: float) -> Tuple[bool, str, float]:
        ok, message, settings = self.update_settings(snapshot_delay_sec=seconds)
        return ok, message, float(settings.get("snapshot_delay_sec", self._snapshot_delay_sec))

    def save_snapshot(self, camera_name: str, frame: np.ndarray) -> str:
        """Save annotated detection frame. Returns filename or ''."""
        if not self._snapshot_enabled:
            return ""
        try:
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            cam = _safe_name(camera_name)
            filename = f"{ts}_{cam}.jpg"
            path = os.path.join(SNAPSHOT_DIR, filename)
            if os.path.exists(path):
                filename = f"{ts}_{cam}_{uuid.uuid4().hex[:4]}.jpg"
                path = os.path.join(SNAPSHOT_DIR, filename)
            ok = cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), SNAPSHOT_JPEG_QUALITY])
            if not ok:
                return ""
            print(f"[SNAPSHOT] {filename}", flush=True)
            return filename
        except Exception as exc:  # noqa: BLE001
            print(f"[SNAPSHOT ERROR] {exc}", flush=True)
            return ""

    def photo_count(self) -> int:
        try:
            return sum(1 for n in os.listdir(SNAPSHOT_DIR) if n.lower().endswith(PHOTO_EXTS))
        except OSError:
            return 0

    def list_photos(self) -> List[dict]:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        items: List[dict] = []
        try:
            names = [n for n in os.listdir(SNAPSHOT_DIR) if n.lower().endswith(PHOTO_EXTS)]
        except OSError:
            names = []

        for name in names:
            path = os.path.join(SNAPSHOT_DIR, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            base = os.path.splitext(name)[0]
            camera = ""
            parts = base.split("_")
            # expected: YYYY-MM-DD_HH-MM-SS_CameraName
            if len(parts) >= 3:
                camera = "_".join(parts[2:])
            items.append(
                {
                    "filename": name,
                    "camera": camera,
                    "url": f"/Data/{name}",
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "timestamp": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        items.sort(key=lambda x: x["mtime"], reverse=True)
        return items

    def delete_photo(self, filename: str) -> bool:
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            return False
        path = os.path.join(SNAPSHOT_DIR, filename)
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def _load(self) -> None:
        if not os.path.isfile(CAMERAS_FILE):
            return
        try:
            with open(CAMERAS_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            for item in raw:
                plain = str(item.get("password") or "")
                cfg = CameraConfig.from_dict(item)
                cfg.password = ""  # never keep disk plaintext in RAM while locked
                if plain and not cfg.password_enc:
                    self._legacy_plain[cfg.id] = plain
                self.cameras[cfg.id] = cfg
                if cfg.id not in self._order:
                    self._order.append(cfg.id)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Failed to load cameras.json: {exc}", flush=True)

    def _save(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        payload = []
        for cid in self._order:
            cfg = self.cameras.get(cid)
            if cfg:
                payload.append(cfg.to_disk_dict())
        for cid, cfg in self.cameras.items():
            if cid not in self._order:
                payload.append(cfg.to_disk_dict())
        with open(CAMERAS_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        try:
            os.chmod(CAMERAS_FILE, 0o600)
        except OSError:
            pass

    def _seal_camera_secret(self, cfg: CameraConfig) -> None:
        """Encrypt in-memory password onto password_enc when vault is unlocked."""
        if not vault.unlocked:
            return
        if cfg.password:
            cfg.password_enc = vault.encrypt(cfg.password)
        cfg.rtsp_url = strip_rtsp_auth(cfg.rtsp_url or "")

    def apply_vault_secrets(self) -> Tuple[bool, str]:
        """Decrypt password_enc into memory and migrate legacy plaintext."""
        if not vault.unlocked:
            return False, "Vault is locked"
        with self._lock:
            for cfg in self.cameras.values():
                if cfg.password_enc:
                    try:
                        cfg.password = vault.decrypt(cfg.password_enc)
                    except Exception as exc:  # noqa: BLE001
                        return False, f"Decrypt failed for camera {cfg.name}: {exc}"
                elif cfg.id in self._legacy_plain:
                    cfg.password = self._legacy_plain.pop(cfg.id)
                    cfg.password_enc = vault.encrypt(cfg.password)
                cfg.rtsp_url = strip_rtsp_auth(cfg.rtsp_url or "")
            self._legacy_plain.clear()
            self._save()
        return True, "Camera secrets unlocked"

    def clear_vault_secrets(self) -> None:
        """Wipe plaintext passwords from memory."""
        with self._lock:
            for cfg in self.cameras.values():
                cfg.password = ""

    def stop_all_workers(self) -> None:
        with self._lock:
            workers = list(self.workers.items())
            self.workers.clear()
        # Stop sequentially so RTSP teardown does not race across cameras.
        for _cid, w in workers:
            try:
                w.stop()
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] worker stop: {exc}", flush=True)

    def start_enabled_workers(self) -> None:
        if not vault.unlocked:
            return
        to_start: List[CameraConfig] = []
        with self._lock:
            for cid in list(self._order):
                cfg = self.cameras.get(cid)
                if cfg and cfg.enabled:
                    to_start.append(cfg)
        for cfg in to_start:
            self._start_worker(cfg)

    def start_all(self) -> None:
        def _load_detector() -> None:
            self.detector.load()
            socketio.emit(
                "status",
                {
                    "detector_ready": self.detector.ready,
                    "detector_error": self.detector.error,
                },
            )
            print(
                f"[DETECTOR] ready={self.detector.ready} error={self.detector.error or 'none'}",
                flush=True,
            )

        threading.Thread(target=_load_detector, name="yolo-load", daemon=True).start()
        # Camera workers start only after vault unlock (login / setup).
        if vault.unlocked:
            self.start_enabled_workers()
        else:
            print("[AUTH] Vault locked — camera streams wait until login", flush=True)

    def _start_worker(self, cfg: CameraConfig) -> None:
        if not vault.unlocked:
            return
        old = self.workers.pop(cfg.id, None)
        if old:
            old.stop()
        worker = CameraWorker(cfg, self)
        self.workers[cfg.id] = worker
        worker.start()

    def list_public(self) -> List[dict]:
        out = []
        for cid in self._order:
            cfg = self.cameras.get(cid)
            if not cfg:
                continue
            w = self.workers.get(cfg.id)
            out.append(
                {
                    "id": cfg.id,
                    "name": cfg.name,
                    "ip": cfg.ip,
                    "port": cfg.port,
                    "username": cfg.username,
                    "password": "••••••••" if (cfg.password or cfg.password_enc) else "",
                    "path": cfg.path,
                    "protocol": cfg.protocol,
                    "rtsp_url_set": bool(cfg.rtsp_url),
                    "enabled": cfg.enabled,
                    "status": w.status if w else (cfg.last_status or "stopped"),
                    "fps": round(w.fps, 1) if w else 0,
                    "person_count": w.person_count if w else 0,
                    "error": (w.last_error if w else "") or cfg.last_message,
                    "slot": len(out),
                }
            )
        return out

    def resolve_and_probe(
        self,
        protocol: str,
        ip: str,
        port: int,
        username: str,
        password: str,
        path: str,
    ) -> Tuple[Optional[str], bool, str]:
        """
        Resolve stream URL and probe it.
        Returns (rtsp_url, ok, message).
        """
        protocol = (protocol or "rtsp").lower().strip()
        ip = (ip or "").strip()
        if not ip:
            return None, False, "IP address is required"

        if protocol == "onvif":
            url, err = resolve_onvif_rtsp(ip, int(port or 80), username or "", password or "")
            if err or not url:
                return None, False, err or "ONVIF discovery failed"
            ok, msg = probe_rtsp(url)
            if not ok:
                return url, False, f"ONVIF found URI but stream failed: {msg}"
            return url, True, f"ONVIF OK — {msg}"

        url = build_rtsp_url(ip, int(port or 554), username or "", password or "", path or "")
        ok, msg = probe_rtsp(url)
        if not ok:
            return url, False, f"RTSP failed: {msg}"
        return url, True, f"RTSP OK — {msg}"

    def add_camera(
        self,
        name: str,
        ip: str,
        port: int,
        username: str,
        password: str,
        path: str,
        protocol: str = "rtsp",
        require_live: bool = True,
    ) -> Tuple[Optional[CameraConfig], bool, str]:
        """
        Add camera after resolving/probing.
        Returns (config|None, success, message).
        On probe failure nothing is saved.
        """
        with self._lock:
            if len(self.cameras) >= MAX_CAMERAS:
                return None, False, f"Maximum of {MAX_CAMERAS} cameras reached"

        protocol = (protocol or "rtsp").lower().strip()
        if protocol not in ("rtsp", "onvif"):
            return None, False, "Protocol must be rtsp or onvif"

        default_port = 80 if protocol == "onvif" else 554
        port = int(port) if port else default_port

        url, ok, message = self.resolve_and_probe(
            protocol=protocol,
            ip=ip,
            port=port,
            username=username,
            password=password,
            path=path,
        )

        if require_live and not ok:
            return None, False, message

        if not vault.unlocked:
            return None, False, "Unlock the dashboard vault before adding cameras"

        with self._lock:
            if len(self.cameras) >= MAX_CAMERAS:
                return None, False, f"Maximum of {MAX_CAMERAS} cameras reached"

            cid = uuid.uuid4().hex[:8]
            while cid in self.cameras:
                cid = uuid.uuid4().hex[:8]

            if not (name or "").strip():
                name = f"Camera {len(self.cameras) + 1}"

            cfg = CameraConfig(
                id=cid,
                name=name.strip(),
                ip=(ip or "").strip(),
                port=port,
                username=username or "",
                password=password or "",
                path=path or "",
                protocol=protocol,
                rtsp_url=strip_rtsp_auth(url or ""),
                enabled=True,
                last_status="ok" if ok else "error",
                last_message=message,
            )
            self._seal_camera_secret(cfg)
            self.cameras[cid] = cfg
            self._order.append(cid)
            self._save()

        if cfg.enabled:
            self._start_worker(cfg)

        return cfg, ok, message

    def remove_camera(self, camera_id: str) -> bool:
        with self._lock:
            if camera_id not in self.cameras:
                return False
            w = self.workers.pop(camera_id, None)
            del self.cameras[camera_id]
            self._order = [c for c in self._order if c != camera_id]
            self._save()
        if w:
            w.stop()
        return True

    def update_camera(self, camera_id: str, data: dict) -> Tuple[Optional[CameraConfig], Optional[str]]:
        with self._lock:
            cfg = self.cameras.get(camera_id)
            if not cfg:
                return None, "Camera not found"
            if "name" in data and data["name"]:
                cfg.name = str(data["name"]).strip()
            if "ip" in data and data["ip"]:
                cfg.ip = str(data["ip"]).strip()
            if "port" in data:
                cfg.port = int(data["port"])
            if "username" in data:
                cfg.username = str(data.get("username") or "")
            if "password" in data and data["password"] and data["password"] != "••••••••":
                cfg.password = str(data["password"])
            if "path" in data:
                cfg.path = str(data.get("path") or "")
            if "protocol" in data and data["protocol"] in ("rtsp", "onvif"):
                cfg.protocol = data["protocol"]
            if "enabled" in data:
                cfg.enabled = bool(data["enabled"])

        if not vault.unlocked:
            return None, "Vault is locked"

        url, ok, message = self.resolve_and_probe(
            protocol=cfg.protocol,
            ip=cfg.ip,
            port=cfg.port,
            username=cfg.username,
            password=cfg.password,
            path=cfg.path,
        )
        should_start = False
        stop_worker: Optional[CameraWorker] = None
        with self._lock:
            cfg.rtsp_url = strip_rtsp_auth(url or cfg.rtsp_url)
            cfg.last_status = "ok" if ok else "error"
            cfg.last_message = message
            self._seal_camera_secret(cfg)
            self._save()
            if cfg.enabled:
                should_start = True
            else:
                stop_worker = self.workers.pop(camera_id, None)
        if should_start:
            self._start_worker(cfg)
        elif stop_worker:
            stop_worker.stop()
        return cfg, None if ok else message

    def add_detection(self, event: DetectionEvent) -> None:
        self.detections.appendleft(event)
        socketio.emit("detection", asdict(event))
        print(f"[DETECTION] {event.timestamp} | {event.message}", flush=True)

    def recent_detections(self, limit: int = 100) -> List[dict]:
        return [asdict(e) for e in list(self.detections)[:limit]]


manager = CameraManager()


def _session_ok() -> bool:
    return bool(session.get("authenticated"))


def _auth_public_paths() -> bool:
    path = request.path or ""
    if path.startswith("/static/"):
        return True
    if path in ("/login", "/setup", "/api/auth/status", "/api/auth/setup", "/api/auth/login"):
        return True
    if path == "/api/health":
        return True
    return False


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not vault.is_setup:
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "setup_required"}), 401
            return redirect(url_for("setup_page"))
        if not _session_ok():
            if request.path.startswith("/api/") or request.path.startswith("/stream/"):
                return jsonify({"ok": False, "error": "auth_required"}), 401
            return redirect(url_for("login_page"))
        if not vault.unlocked and not manager.unlock_until_reboot:
            # Session without vault (should be rare)
            if request.path.startswith("/api/") or request.path.startswith("/stream/"):
                return jsonify({"ok": False, "error": "vault_locked"}), 401
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)

    return wrapper


@app.before_request
def _gate_requests():
    if _auth_public_paths():
        return None
    if request.method == "OPTIONS":
        return None
    if not vault.is_setup:
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "setup_required", "setup_required": True}), 401
        if request.endpoint not in ("setup_page", "static"):
            return redirect(url_for("setup_page"))
        return None
    if not _session_ok():
        if request.path.startswith("/api/") or request.path.startswith("/stream/") or request.path.startswith("/Data/"):
            return jsonify({"ok": False, "error": "auth_required"}), 401
        return redirect(url_for("login_page"))
    return None


def _establish_session() -> None:
    session.clear()
    session["authenticated"] = True
    session.permanent = True


@app.route("/setup", methods=["GET"])
def setup_page():
    if vault.is_setup:
        return redirect(url_for("login_page"))
    return render_template("login.html", mode="setup")


@app.route("/login", methods=["GET"])
def login_page():
    if not vault.is_setup:
        return redirect(url_for("setup_page"))
    if _session_ok() and vault.unlocked:
        return redirect(url_for("index"))
    if _session_ok() and manager.unlock_until_reboot and vault.unlocked:
        return redirect(url_for("index"))
    return render_template("login.html", mode="login")


@app.route("/api/auth/status")
def auth_status():
    return jsonify(
        {
            "ok": True,
            "setup": vault.is_setup,
            "authenticated": _session_ok(),
            "vault_unlocked": vault.unlocked,
            "unlock_until_reboot": manager.unlock_until_reboot,
        }
    )


@app.route("/api/auth/setup", methods=["POST"])
def auth_setup():
    if vault.is_setup:
        return jsonify({"ok": False, "error": "Already configured"}), 400
    data = request.get_json(force=True, silent=True) or {}
    password = str(data.get("password") or "")
    confirm = str(data.get("confirm") or "")
    if password != confirm:
        return jsonify({"ok": False, "error": "Passwords do not match"}), 400
    ok, message = vault.setup(password)
    if not ok:
        return jsonify({"ok": False, "error": message}), 400
    applied_ok, applied_msg = manager.apply_vault_secrets()
    if not applied_ok:
        # Setup still valid; cameras may be empty
        print(f"[AUTH] setup vault apply: {applied_msg}", flush=True)
    _establish_session()
    manager.start_enabled_workers()
    return jsonify({"ok": True, "message": message, "settings": manager.get_settings()})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    if not vault.is_setup:
        return jsonify({"ok": False, "error": "setup_required", "setup_required": True}), 400
    data = request.get_json(force=True, silent=True) or {}
    password = str(data.get("password") or "")
    if vault.unlocked and manager.unlock_until_reboot:
        # Still verify password for a new browser session
        ok, message = vault.unlock(password)
        if not ok:
            return jsonify({"ok": False, "error": message}), 401
    else:
        ok, message = vault.unlock(password)
        if not ok:
            return jsonify({"ok": False, "error": message}), 401
        applied_ok, applied_msg = manager.apply_vault_secrets()
        if not applied_ok:
            vault.lock()
            return jsonify({"ok": False, "error": applied_msg}), 500
        manager.start_enabled_workers()
    _establish_session()
    return jsonify({"ok": True, "message": message, "settings": manager.get_settings()})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    if not manager.unlock_until_reboot:
        manager.stop_all_workers()
        manager.clear_vault_secrets()
        vault.lock()
        print("[AUTH] Logged out — vault locked", flush=True)
    else:
        print("[AUTH] Logged out — vault stays unlocked until reboot", flush=True)
    return jsonify({"ok": True, "vault_unlocked": vault.unlocked})


@app.route("/api/auth/lock", methods=["POST"])
def auth_lock():
    """Force-lock vault (stops streams) even if unlock-until-reboot is on."""
    session.clear()
    # Stop workers before wiping secrets / locking the vault.
    manager.stop_all_workers()
    manager.clear_vault_secrets()
    vault.lock()
    print("[AUTH] Vault locked manually", flush=True)
    return jsonify({"ok": True, "vault_unlocked": False, "redirect": "/login"})


@app.route("/api/auth/change-password", methods=["POST"])
def auth_change_password():
    if not _session_ok():
        return jsonify({"ok": False, "error": "auth_required"}), 401
    data = request.get_json(force=True, silent=True) or {}
    current = str(data.get("current_password") or "")
    new = str(data.get("new_password") or "")
    confirm = str(data.get("confirm_password") or "")
    if new != confirm:
        return jsonify({"ok": False, "error": "New passwords do not match"}), 400
    # Ensure vault unlocked with current password first
    if not vault.unlocked:
        ok, msg = vault.unlock(current)
        if not ok:
            return jsonify({"ok": False, "error": msg}), 401
        manager.apply_vault_secrets()

    ok, message, old_fernet = vault.change_password(current, new)
    if not ok:
        return jsonify({"ok": False, "error": message}), 400

    # Re-encrypt all camera secrets with new key (vault already holds new fernet)
    with manager._lock:
        for cfg in manager.cameras.values():
            plain = cfg.password
            if not plain and cfg.password_enc and old_fernet is not None:
                try:
                    plain = old_fernet.decrypt(cfg.password_enc.encode("ascii")).decode("utf-8")
                except Exception:  # noqa: BLE001
                    plain = ""
            if plain:
                cfg.password = plain
                cfg.password_enc = vault.encrypt(plain)
        manager._save()
    return jsonify({"ok": True, "message": message})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/photos")
def photos_page():
    return render_template("photos.html")


@app.route("/Data/<path:filename>")
def serve_snapshot(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        return "Not found", 404
    return send_from_directory(SNAPSHOT_DIR, filename)


@app.route("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "detector_ready": manager.detector.ready,
            "detector_error": manager.detector.error,
            "camera_count": len(manager.cameras),
            "max_cameras": MAX_CAMERAS,
            "snapshot_delay_sec": manager.snapshot_delay_sec,
            "snapshot_enabled": manager.snapshot_enabled,
            "photo_count": manager.photo_count(),
            "auth_setup": vault.is_setup,
            "vault_unlocked": vault.unlocked,
            "authenticated": _session_ok(),
        }
    )


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(manager.get_settings())


@app.route("/api/settings", methods=["PUT", "POST"])
def put_settings():
    data = request.get_json(force=True, silent=True) or {}
    if (
        "snapshot_delay_sec" not in data
        and "snapshot_enabled" not in data
        and "unlock_until_reboot" not in data
    ):
        return jsonify(
            {"ok": False, "error": "snapshot_delay_sec, snapshot_enabled, or unlock_until_reboot required"}
        ), 400

    delay = data.get("snapshot_delay_sec", None)
    enabled = data.get("snapshot_enabled", None)
    unlock = data.get("unlock_until_reboot", None)
    if enabled is not None:
        enabled = bool(enabled)
    if unlock is not None:
        unlock = bool(unlock)

    ok, message, settings = manager.update_settings(
        snapshot_delay_sec=delay,
        snapshot_enabled=enabled,
        unlock_until_reboot=unlock,
    )
    if not ok:
        return jsonify({"ok": False, "success": False, "error": message, "message": message}), 400
    socketio.emit("settings", settings)
    return jsonify({"ok": True, "success": True, "message": message, "settings": settings})


@app.route("/api/photos", methods=["GET"])
def api_photos():
    return jsonify(manager.list_photos())


@app.route("/api/photos/<path:filename>", methods=["DELETE"])
def api_delete_photo(filename: str):
    if not manager.delete_photo(filename):
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "success": True})


@app.route("/api/cameras", methods=["GET"])
def get_cameras():
    return jsonify(manager.list_public())


@app.route("/api/cameras", methods=["POST"])
def post_camera():
    data = request.get_json(force=True, silent=True) or {}
    protocol = (data.get("protocol") or "rtsp").lower()
    try:
        port = int(data.get("port") or (80 if protocol == "onvif" else 554))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "success": False, "error": "Invalid port"}), 400

    cfg, ok, message = manager.add_camera(
        name=data.get("name", ""),
        ip=data.get("ip", ""),
        port=port,
        username=data.get("username", ""),
        password=data.get("password", ""),
        path=data.get("path", ""),
        protocol=protocol,
        require_live=True,
    )
    if not ok or cfg is None:
        print(f"[ADD FAIL] {protocol.upper()} {data.get('ip')}: {message}", flush=True)
        return jsonify(
            {
                "ok": False,
                "success": False,
                "protocol": protocol,
                "error": message,
                "message": message,
            }
        ), 400

    public = next((c for c in manager.list_public() if c["id"] == cfg.id), None)
    print(f"[ADD OK] {protocol.upper()} {cfg.name} ({cfg.ip}): {message}", flush=True)
    return jsonify(
        {
            "ok": True,
            "success": True,
            "protocol": protocol,
            "message": message,
            "camera": public,
        }
    )


@app.route("/api/cameras/test", methods=["POST"])
def test_camera():
    """Test RTSP/ONVIF without saving."""
    data = request.get_json(force=True, silent=True) or {}
    protocol = (data.get("protocol") or "rtsp").lower()
    try:
        port = int(data.get("port") or (80 if protocol == "onvif" else 554))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "success": False, "error": "Invalid port"}), 400

    url, ok, message = manager.resolve_and_probe(
        protocol=protocol,
        ip=data.get("ip", ""),
        port=port,
        username=data.get("username", ""),
        password=data.get("password", ""),
        path=data.get("path", ""),
    )
    return jsonify(
        {
            "ok": ok,
            "success": ok,
            "protocol": protocol,
            "message": message,
            "error": None if ok else message,
            "rtsp_url_preview": redact_rtsp_url(url or ""),
        }
    ), (200 if ok else 400)


@app.route("/api/cameras/<camera_id>", methods=["PUT"])
def put_camera(camera_id: str):
    data = request.get_json(force=True, silent=True) or {}
    cfg, err = manager.update_camera(camera_id, data)
    if cfg is None:
        return jsonify({"ok": False, "success": False, "error": err or "Not found"}), 404
    public = next((c for c in manager.list_public() if c["id"] == cfg.id), None)
    return jsonify(
        {
            "ok": err is None,
            "success": err is None,
            "message": err or "Updated",
            "error": err,
            "camera": public,
        }
    )


@app.route("/api/cameras/<camera_id>", methods=["DELETE"])
def delete_camera(camera_id: str):
    if not manager.remove_camera(camera_id):
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "success": True})


@app.route("/api/detections")
def get_detections():
    limit = request.args.get("limit", 100, type=int)
    return jsonify(manager.recent_detections(limit))


@app.route("/stream/<camera_id>")
def stream(camera_id: str):
    if camera_id not in manager.cameras and camera_id not in manager.workers:
        return "Camera not found", 404

    def generate():
        boundary = b"--frame"
        idle_rounds = 0
        while True:
            if camera_id not in manager.cameras and camera_id not in manager.workers:
                break
            w = manager.workers.get(camera_id)
            jpeg = w.get_jpeg() if w else None
            if not jpeg:
                jpeg = _black_jpeg()
                idle_rounds += 1
                if idle_rounds > 200:
                    break
            else:
                idle_rounds = 0
            yield (
                boundary
                + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode("ascii")
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
            time.sleep(0.04)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@socketio.on("connect")
def on_connect():
    if vault.is_setup and not _session_ok():
        disconnect()
        return False
    socketio.emit(
        "status",
        {
            "detector_ready": manager.detector.ready,
            "cameras": manager.list_public() if vault.unlocked else [],
            "settings": manager.get_settings(),
        },
    )


def main() -> None:
    manager.start_all()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Camera Dashboard → http://{host}:{port}", flush=True)
    if not vault.is_setup:
        print("[AUTH] First run — open /setup to create a dashboard password", flush=True)
    elif not vault.unlocked:
        print("[AUTH] Login required to unlock camera credentials", flush=True)
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True, use_reloader=False)


if __name__ == "__main__":
    main()
