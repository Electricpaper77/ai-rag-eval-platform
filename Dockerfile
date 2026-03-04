FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT=8080
CMD exec gunicorn backend.app.main:app \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --timeout 120 \
    --worker-class uvicorn.workers.UvicornWorker
