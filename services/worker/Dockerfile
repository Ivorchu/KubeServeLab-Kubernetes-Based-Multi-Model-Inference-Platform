FROM python:3.11-slim

WORKDIR /app

# Install CPU-only PyTorch first to avoid pulling the ~800 MB CUDA build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY services/worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/worker/ ./services/worker/

ENV PYTHONPATH=/app

CMD ["python", "-m", "services.worker.app.main"]
