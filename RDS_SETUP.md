# 🗄️ Configurar AWS RDS PostgreSQL

Tu proyecto ha sido actualizado para usar **AWS RDS PostgreSQL** en lugar de SQLite.

## 📋 Paso 1: Crear RDS en AWS Console

1. Ve a [AWS RDS Console](https://console.aws.amazon.com/rds/)
2. Click en **Databases > Create database**
3. Selecciona:
   - **Engine type**: PostgreSQL
   - **Version**: 15 o 16
   - **Templates**: Free tier (gratis durante 12 meses)

4. **DB instance settings**:
   - DB instance identifier: `neumavision-db`
   - Master username: `postgres`
   - Master password: (guarda esto en lugar seguro)

5. **Connectivity**:
   - VPC: Default VPC
   - Public accessibility: **No** (desde producción EC2)
   - New security group: `neumavision-db-sg`

6. **Database options**:
   - Initial database name: `neumavision`
   - Backup retention: 7 days
   - Multi-AZ: No (para desarrollo)

7. Click en **Create database** y espera 5-10 minutos

---

## 🔌 Paso 2: Obtener Endpoint de RDS

Cuando el RDS esté listo (status: "Available"):

1. Ve a **Databases > neumavision-db**
2. Copia el **Endpoint**: 
   ```
   neumavision-db.XXXXXXXX.us-east-1.rds.amazonaws.com
   ```
3. El puerto es: `5432`

---

## 🔑 Paso 3: Actualizar `.env` Local

Abre o crea `backend/.env`:

```env
APP_NAME=NeumaDiesel Vision API
ENVIRONMENT=development
API_PREFIX=/api/v1
DATABASE_URL=postgresql+psycopg://postgres:PASSWORD@neumavision-db.XXXXXXXX.us-east-1.rds.amazonaws.com:5432/neumavision
UPLOAD_DIR=./data/uploads
DETECTOR_MODE=mock
YOLO_MODEL_PATH=./models/best.pt
CORS_ORIGINS=http://localhost:5173
```

**Reemplaza**:
- `PASSWORD` → la contraseña que configuraste
- `XXXXXXXX` → el ID de tu región (ej: c9akciq32vmf)

---

## ✅ Paso 4: Probar Conexión Local

```bash
cd backend

# Crear virtual env
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Probar conexión
python -c "from app.database import engine; print('✅ Conexión a RDS exitosa' if engine.connect() else '❌ Error')"
```

Si sale error, verifica:
- ❌ DATABASE_URL correcta
- ❌ Password correcta
- ❌ Endpoint correcto
- ❌ Tu IP en Security Group de RDS (si está en producción)

---

## 🚀 Paso 5: Ejecutar Backend Localmente

```bash
# Terminal 1: Backend
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

Abre:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000/docs

---

## 📊 Verificar que las Tablas se Crearon

Puedes conectarte a RDS desde tu máquina con pgAdmin o psql:

```bash
# Con psql
psql -h neumavision-db.XXXXXXXX.us-east-1.rds.amazonaws.com -U postgres -d neumavision

# O con DBeaver / pgAdmin (GUI)
```

---

## 🔒 Seguridad en Producción

Cuando despliegues a producción:

1. **Secrets Manager** (no hardcodear credenciales):
   ```bash
   aws secretsmanager create-secret \
     --name neumavision/db \
     --secret-string '{"username":"postgres","password":"...",...}'
   ```

2. **Security Group**: Solo permite acceso desde EC2 backends
   ```
   Inbound rule: PostgreSQL (5432) from Backend SG
   ```

3. **Multi-AZ**: Activa para alta disponibilidad
4. **Backups**: Automáticos cada día
5. **Encryption**: Habilita encriptación en reposo

---

## 📝 Cambios en el Proyecto

✅ **Actualizado**:
- `backend/.env.example` - DATABASE_URL apunta a RDS
- `backend/app/config.py` - Default es PostgreSQL

✅ **Sin cambios** (ya son compatibles):
- `backend/app/database.py` - Detecta PostgreSQL automáticamente
- `backend/app/models.py` - SQLModel funciona igual
- `backend/requirements.txt` - `psycopg[binary]` ya está incluido

---

## 🚨 Troubleshooting

### Error: "could not translate host name"
- Verifica que el endpoint es correcto
- Espera a que RDS esté completamente listo (5-10 min)

### Error: "password authentication failed"
- Verifica la contraseña exacta
- Caracteres especiales: usa comillas simples en bash

### Error: "connection refused"
- Si es local: instala PostgreSQL en tu PC
- Si es RDS: verifica Security Group permite tu IP

### Error: "database does not exist"
- Ejecuta `alembic upgrade head` desde `backend` para crear o actualizar las tablas
- Verifica que el nombre `neumavision` es correcto en RDS

---

## 📞 Soporte

Para más información:
- [AWS RDS PostgreSQL Docs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
- [SQLModel Docs](https://sqlmodel.tiangolo.com/)
- [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
