FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/road-user-platform

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/

ENV PYTHONPATH=/opt/road-user-platform/src

EXPOSE 8000

CMD ["uvicorn", "src.backend_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
