FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install -r backend/requirements.txt

COPY backend backend

ARG HF_TOKEN=""
ENV HF_TOKEN=${HF_TOKEN}
ENV HF_DOWNLOAD_BACKEND=transfer \
    HF_DOWNLOAD_WORKERS=6 \
    HF_DOWNLOAD_SAFETENSOR_WORKERS=1 \
    HF_DOWNLOAD_MAX_ATTEMPTS=8 \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    HF_HUB_DISABLE_XET=1

# Preload model artifacts in the image so runtime startup does not require a long download.
RUN python backend/scripts/download_translategemma.py

# Avoid retaining token in runtime container environment.
ENV HF_TOKEN=""

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]