FROM python:3.10-slim

WORKDIR /app

# "medium" gives better Arabic/English accuracy than "small" on oral answers.
ENV WHISPER_MODEL=medium
ENV ACCESS_TOKEN_EXPIRE_MINUTES=10080
ENV GOOGLE_CLIENT_ID=576823116130-im8185suok743g2vttudc37f7qdt6lep.apps.googleusercontent.com

# Model caches live under /models, which is meant to be a mounted volume. Pointed at /tmp they
# were lost on every restart, and the container then spent the first few minutes of its life
# re-downloading about 1.3GB of weights while the first students waited.
ENV HF_HOME=/models/huggingface
ENV TRANSFORMERS_CACHE=/models/huggingface/transformers
ENV INSIGHTFACE_HOME=/models/insightface
ENV INSIGHTFACE_MODEL=buffalo_sc
ENV GAZE_MODEL_DIR=/models/gaze
ENV TORCH_HOME=/models/torch

# Install system dependencies (ffmpeg is needed by faster-whisper to decode audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgomp1 \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# torch from the default index pulls the CUDA build: about 2.5GB of GPU libraries that never run,
# since every model here is configured for the CPU. The CPU wheel index keeps the image small
# enough to pull and rebuild on a modest VPS.
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

COPY . .

RUN mkdir -p /models /data

# Hugging Face Spaces routes traffic to 7860 (no app_port in README). On a VPS, set PORT=8000.
ENV PORT=7860
EXPOSE 7860

# One worker on purpose. Answers are graded in a thread pool whose size MAX_CONCURRENT_GRADING
# caps, and that cap — like the rate limiter — counts per process, so several workers would each
# run their own full set of grading jobs and their own copy of every model. Raise
# MAX_CONCURRENT_GRADING to use more cores, not the worker count.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 75"]
