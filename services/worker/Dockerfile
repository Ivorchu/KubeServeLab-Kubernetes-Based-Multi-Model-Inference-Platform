FROM python:3.11-slim

WORKDIR /app

COPY services/worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/worker/ ./services/worker/

ENV PYTHONPATH=/app

CMD ["python", "-m", "services.worker.app.main"]
