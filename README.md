# NeumaDiesel Vision Platform

Plataforma desacoplada para inspeccionar caminos mineros mediante imágenes RGB capturadas con dron. Detecta baches, piedras y desprendimientos de roca que pueden dañar los neumáticos de camiones CAEX, registra evidencias, extrae su ubicación aproximada y genera informes PDF.

## Arquitectura

- `backend/`: FastAPI + SQLModel en Python.
- `frontend/`: React + TypeScript + Vite.
- Base de datos: PostgreSQL en Amazon RDS mediante `DATABASE_URL`.
- Detector inicial: adaptador simulado. La clase `YoloDetector` queda preparada para integrar un modelo de Ultralytics.
- Informes: PDF generado en el backend con ReportLab.
- Geolocalización: lectura automática de coordenadas GPS desde EXIF.
- Mapa: visualización interactiva de hallazgos con React Leaflet y OpenStreetMap.

## Inicio manual

### Backend

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Linux o macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

### Frontend

En otra terminal:

```bash
cd frontend
npm install
npm run dev
```

## Conectar YOLO

1. Instala Ultralytics en el backend:

```bash
pip install ultralytics
```

2. Copia el modelo a `backend/models/best.pt`.
3. Configura el archivo `backend/.env`:

```env
DETECTOR_MODE=yolo
YOLO_MODEL_PATH=./models/best.pt
```

La API y el frontend no necesitan cambios porque el detector se reemplaza mediante el adaptador ubicado en `backend/app/services/detector.py`.

## Conectar PostgreSQL

Configura `DATABASE_URL` en `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://usuario:clave@host:5432/postgres
```

El esquema se controla con Alembic. Antes de iniciar el backend manualmente, aplica las migraciones:

```bash
cd backend
alembic upgrade head
```

Hasta que se implemente `POST /auth/login`, las misiones se asocian a una faena de desarrollo definida mediante
`DEVELOPMENT_FAENA_ID`. Este valor es una compatibilidad temporal y no reemplaza la autenticación.

## Endpoints principales

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/api/v1/health` | Verifica API, detector y base de datos |
| `POST` | `/api/v1/missions` | Crea una misión y sube imágenes |
| `POST` | `/api/v1/missions/demo` | Genera imágenes demo |
| `POST` | `/api/v1/missions/{id}/detect` | Ejecuta el detector configurado |
| `GET` | `/api/v1/missions/{id}` | Obtiene imágenes y hallazgos |
| `PATCH` | `/api/v1/missions/{id}/detections/{id}` | Confirma o descarta un hallazgo |
| `GET` | `/api/v1/missions/{id}/report` | Descarga el informe PDF |

## Pruebas

```bash
cd backend
pytest -q
```

# neumavision
