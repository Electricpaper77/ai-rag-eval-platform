FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT=8080
CMD exec gunicorn backend.app.main:app -k uvicorn.workers.UvicornWorker --bind :$PORT --workers 1 --timeout 120
