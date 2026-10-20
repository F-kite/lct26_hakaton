FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/models/v2/download_encoder.py /tmp/download_encoder.py
RUN python /tmp/download_encoder.py /opt/e5-encoder
ENV E5_MODEL_DIR=/opt/e5-encoder

COPY app/ ./app/

CMD ["sh", "-c", "python -m app.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
