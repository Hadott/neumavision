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
# Create backend\.env locally and configure DATABASE_URL as described below.
uvicorn app.main:app --reload
```

Linux o macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
# Create backend/.env locally and configure DATABASE_URL as described below.
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

`npm run dev` también inicia el backend automáticamente (usa `backend/venv` o `backend/.venv`) si no está corriendo. Abre http://localhost:5173: el frontend llama a `/api/v1` y Vite lo redirige al backend, así que no hay que configurar otro puerto.

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

El endpoint `POST /api/v1/auth/login` inicia sesión. Las cuentas las aprovisiona
un administrador; no hay registro público ni recuperación por correo.

## Endpoints principales

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/api/v1/health` | Verifica API, detector y base de datos |
| `POST` | `/api/v1/auth/login` | Inicia sesión y entrega un token |
| `GET` | `/api/v1/auth/me` | Devuelve la cuenta autenticada |
| `GET` | `/api/v1/auth/faenas` | Lista faenas (solo administrador) |
| `GET` | `/api/v1/auth/admin/faenas` | Lista cuentas y cantidad de misiones (solo administrador) |
| `POST` | `/api/v1/auth/admin/faenas` | Crea una cuenta de faena (solo administrador) |
| `PATCH` | `/api/v1/auth/admin/faenas/{id}` | Actualiza nombre y correo (solo administrador) |
| `PUT` | `/api/v1/auth/faenas/{id}/password` | Restablece contraseña (solo administrador) |
| `POST` | `/api/v1/missions` | Crea una misión y sube imágenes |
| `POST` | `/api/v1/missions/demo` | Genera imágenes demo |
| `POST` | `/api/v1/missions/{id}/detect` | Ejecuta el detector configurado |
| `GET` | `/api/v1/missions/{id}` | Obtiene imágenes y hallazgos |
| `PATCH` | `/api/v1/missions/{id}/detections/{id}` | Confirma o descarta un hallazgo |
| `GET` | `/api/v1/missions/{id}/report` | Descarga el informe PDF |

El restablecimiento administrativo requiere un token Bearer de administrador y
una contraseña de al menos 8 caracteres. No existe un endpoint público de
restablecimiento; usa HTTPS fuera del entorno local. Envía
`PUT /api/v1/auth/faenas/{faena_id}/password` con el cuerpo
`{"contrasena":"nueva-clave"}`.

La creación de cuentas también requiere un token Bearer de administrador y
asigna siempre el rol `faena`; el cuerpo de
`POST /api/v1/auth/admin/faenas` es
`{"nombre":"Faena","correo":"contacto@empresa.cl","contrasena":"clave-inicial"}`.

## Pruebas

```bash
cd backend
pytest -q
```

# neumavision
