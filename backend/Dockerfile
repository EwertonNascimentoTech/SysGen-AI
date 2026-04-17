FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stitch_runner/package.json stitch_runner/package-lock.json stitch_runner/run.mjs stitch_runner/export_themes.mjs ./stitch_runner/
RUN cd stitch_runner && npm ci --omit=dev && rm -rf /root/.npm

COPY app ./app
COPY scripts ./scripts

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
