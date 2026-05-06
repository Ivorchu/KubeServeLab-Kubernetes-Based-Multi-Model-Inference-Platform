FROM python:3.11-slim

WORKDIR /app

COPY services/scheduler/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/scheduler/ ./services/scheduler/

ENV PYTHONPATH=/app

CMD ["python", "-m", "services.scheduler.app.main"]
