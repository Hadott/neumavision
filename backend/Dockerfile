
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Bibliotecas necesarias para procesamiento de imágenes
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Dependencias del backend
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# PyTorch y Ultralytics para inferencia con GPU
RUN pip install --no-cache-dir ultralytics

# Código del backend
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Recursos propios del backend
COPY assets ./assets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]

