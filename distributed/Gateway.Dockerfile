FROM python:3.11-slim
WORKDIR /app
COPY distributed/gateway_requirements.txt .
RUN pip install --no-cache-dir -r gateway_requirements.txt
COPY distributed/gateway.py .
CMD ["uvicorn","gateway:app","--host","0.0.0.0","--port","8080"]
