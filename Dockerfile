FROM python:3.12-slim
# Build online once, then docker save/load. Processing never installs or downloads anything.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 reader
COPY models /app/models
ENV IVDAI_MODEL_DIR=/app/models OPENBLAS_NUM_THREADS=1 OMP_THREAD_LIMIT=1 PYTHONDONTWRITEBYTECODE=1
USER reader
EXPOSE 8000
CMD ["vehicle-document-ai", "serve", "--host", "0.0.0.0"]
