# Camera Dashboard — Docker image
# Published to: ghcr.io/commander-apemanx/camera-dashboard
# Local build: docker compose -f docker-compose.build.yml build

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=5000 \
    OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000|stimeout;5000000 \
    ULTRALYTICS_OFFLINE=0

# System libs for OpenCV / FFmpeg RTSP
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgl1 \
        libgomp1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer cache)
COPY requirements.txt .
RUN pip install --upgrade pip wheel setuptools \
    && pip install -r requirements.txt

# Application
COPY app.py .
COPY templates/ ./templates/
COPY static/ ./static/
COPY docker/entrypoint.sh /entrypoint.sh

# Optional pre-baked YOLO weights (speeds first start; downloaded at build if missing)
COPY yolov8n.pt* ./

RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/data /app/Data \
    && if [ ! -f /app/yolov8n.pt ]; then \
         python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"; \
       fi

# Persist config + detection photos outside the container
VOLUME ["/app/data", "/app/Data"]

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=8s --start-period=90s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
