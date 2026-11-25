# 3. Documentación del backend

El backend de NeumaDiesel Vision expone la API REST de inspección de caminos mineros. Autentica operadores y administradores, recibe misiones con fotografías, coordina la inferencia, registra resultados y entrega hallazgos e informes PDF. En modo remoto, el backend se ejecuta en Nina y envía las imágenes al servicio de inferencia de Jade.

## Aplicación FastAPI

FastAPI registra las rutas de autenticación, misiones y tablero bajo `/api/v1` de forma predeterminada. Pydantic define y valida los contratos HTTP. SQLModel y SQLAlchemy manejan las sesiones de PostgreSQL mediante psycopg. La documentación interactiva está en `/docs` y el esquema en `/openapi.json`.

El arranque crea el directorio de carga. Alembic inicializa y actualiza el esquema mediante `alembic upgrade head`. En una base nueva, crea el primer administrador con `python -m app.cuentas crear --nombre "Administrador" --correo admin@empresa.cl --admin`. Cuando Jade está configurada en modo remoto, FastAPI también inicia su monitor de inactividad. [Arranque de la aplicación](../backend/app/main.py) · [Acceso a datos](../backend/app/database.py) · [Administración de cuentas por consola](../backend/app/cuentas.py)

### Organización del código

| Módulo | Responsabilidad |
| --- | --- |
| [`main.py`](../backend/app/main.py) | Inicialización, CORS y rutas de salud y administración de Jade. |
| [`api/auth.py`](../backend/app/api/auth.py) | Inicio de sesión, datos de la cuenta y administración de faenas. |
| [`api/missions.py`](../backend/app/api/missions.py) | Carga, procesamiento, revisión, acceso a imágenes e informes de misión. |
| [`api/dashboard.py`](../backend/app/api/dashboard.py) | Consulta transversal de hallazgos dentro del alcance de la cuenta. |
| [`schemas.py`](../backend/app/schemas.py) y [`models.py`](../backend/app/models.py) | Contratos HTTP y modelos persistidos, respectivamente. |
| [`services/auth.py`](../backend/app/services/auth.py) y [`passwords.py`](../backend/app/services/passwords.py) | Firma y validación de tokens, resolución de la cuenta y hash de contraseñas. |
| [`detector.py`](../backend/app/services/detector.py) y [`jade.py`](../backend/app/services/jade.py) | Adaptadores de inferencia y coordinación del ciclo de vida de Jade. |
| [`storage.py`](../backend/app/services/storage.py) y [`metadata.py`](../backend/app/services/metadata.py) | Carga de archivos, lectura y escritura en S3, y extracción de coordenadas EXIF. |
| [`report.py`](../backend/app/services/report.py) y [`ancho_pista.py`](../backend/app/services/ancho_pista.py) | Generación del PDF y análisis local de ancho de pista. |

## Autenticación y permisos

Cada operador tiene una cuenta personal asignada a una faena. El login normaliza el correo y verifica la contraseña con Argon2 mediante pwdlib. La respuesta contiene `token` y `cuenta`, con `id`, `nombre`, `correo` y `rol`. El token usa una firma HMAC-SHA256 sobre una carga con el identificador y el vencimiento. La duración predeterminada es de 12 horas. El cliente usa `Authorization: Bearer <token>`; la dependencia de autenticación también admite `?token=` para solicitudes de imágenes iniciadas por el navegador.

El rol `operador` accede a las misiones y hallazgos de la faena asignada. El backend consulta esa asignación en la base de datos al validar el token. El rol `admin` puede acceder a las misiones de todas las faenas, filtrar por faena y asignar una faena existente al crear una misión. Las operaciones sobre imágenes y detecciones verifican además que el recurso pertenece a la misión solicitada. Una misión inaccesible para un operador devuelve `404`. [Autenticación](../backend/app/services/auth.py) · [Autorización de misiones](../backend/app/api/missions.py)

En **Administración → Cuentas y accesos**, el formulario **Crear faena** pide el nombre y **Crear usuario** pide el nombre, el correo, la contraseña inicial y el rol. Los operadores requieren una faena. Los administradores globales pueden acceder a todas. La revisión Alembic `20261125_0012` traslada los administradores y operadores a `usuario` conservando sus identificadores y hashes, y retira las credenciales de `faena`.

## Flujo de una misión

1. **Carga.** `POST /missions` crea la misión y registra las imágenes de un formulario multipart. Acepta JPEG, PNG y WebP. Pillow obtiene dimensiones y el backend extrae latitud y longitud cuando hay GPS en EXIF. La misión empieza en `uploaded` y las imágenes en `pending`. Si está configurado el bucket, los originales se almacenan en S3 y se eliminan las copias locales de la carga.
2. **Inferencia.** `POST /missions/{mission_id}/detect` procesa las imágenes una por una dentro de la solicitud HTTP. Con Jade administrada, el backend arranca la instancia si hace falta y espera a que el servicio esté listo. El cliente puede consultar el progreso en paralelo. Las fases son `starting`, `processing` y `saving`. El progreso se mantiene en memoria del proceso y la consulta devuelve `null` cuando no hay una ejecución activa.
3. **Persistencia.** Tras procesar todas las imágenes, el backend reemplaza las detecciones anteriores en una transacción, marca las imágenes como `completed` y pasa la misión a `review`. Reprocesar una misión reemplaza también las detecciones que ya tenían revisión o reparación registrada. Una respuesta válida sin detecciones puede completar el procesamiento.
4. **Revisión.** Cada detección admite `pending`, `confirmed` o `rejected`. La reparación es independiente y admite `pending` o `repaired`. Al pasar a `repaired`, se registra la fecha. Al volver a `pending`, se limpia. La criticidad manual de la imagen admite `critico`, `moderado`, `optimo` o `null`. Asignar un valor confirma las detecciones pendientes de esa imagen.
5. **Informe.** La descarga genera un PDF con las imágenes que contienen al menos un hallazgo de pista sin rechazo. Las detecciones fuera de pista pueden aparecer como contexto visual. Con S3 configurado, se reemplaza el PDF de la misión y se actualiza su registro en PostgreSQL. La respuesta es `application/pdf` con descarga adjunta. [Flujo de misiones](../backend/app/api/missions.py) · [Contratos de respuesta](../backend/app/schemas.py)

### Integración con el detector

`DETECTOR_MODE` selecciona `mock` para demostraciones, `yolo` para un modelo local, `neumavision` para el análisis local combinado o `remote` para Jade. En modo remoto, el backend llama a `POST /predict` de Jade mediante HTTP multipart, solicita el cálculo de ancho y adjunta un token de servicio si está configurado.

El adaptador valida dimensiones, límites de cajas, confianza y JPEG de análisis. Convierte cada caja en píxeles `[x1, y1, x2, y2]` a coordenadas normalizadas `x`, `y`, `width` y `height`, con origen en la esquina superior izquierda. Las rocas fuera de pista que devuelve Jade también se persisten como referencia en la revisión. El tablero y los conteos de hallazgos de las misiones las excluyen. Si falta un resultado de ancho utilizable, la imagen puede seguir disponible para revisar rocas. [Adaptadores de inferencia](../backend/app/services/detector.py)

### Archivos y coordinación de Jade

| Archivo | Comportamiento del backend |
| --- | --- |
| Original | Se guarda en el directorio de carga o en S3 bajo `originals/{mission_id}/`. Cuando el procesamiento o el informe necesita un original remoto, el backend lo recupera temporalmente. |
| JPEG de análisis | En modo remoto con S3, se publica bajo `analysis/{mission_id}/{image_id}/` y su clave se guarda en la imagen. En los modos que generan un JPEG local, se sirve desde el directorio de carga. |
| Ancho de pista | El resumen JSON y el JPEG anotado se guardan junto a la ruta local de la imagen. El detalle de misión incluye el resumen y la URL cuando están disponibles. |
| PDF | Si S3 está configurado, se guarda como `reports/{mission_id}/informe.pdf`. Cada misión tiene un registro de informe como máximo. |

PostgreSQL guarda metadatos y referencias. El backend sirve los archivos mediante rutas autenticadas. Borrar una misión elimina sus registros y su directorio local. Los objetos de S3 quedan en el bucket. [Almacenamiento](../backend/app/services/storage.py) · [Rutas de archivos](../backend/app/api/missions.py)

En modo remoto con `JADE_INSTANCE_ID`, Nina comprueba cada 15 segundos si Jade puede apagarse. El umbral inicial es de 1.200 segundos sin trabajos. El administrador puede modificarlo o desactivar el apagado durante la ejecución de Nina. Ese ajuste y el seguimiento de trabajos residen en memoria de un único proceso. El encendido manual devuelve `202` mientras Jade arranca en segundo plano. [Gestión de Jade](../backend/app/services/jade.py) · [Configuración](../backend/app/config.py)

## Endpoints

Las tablas muestran rutas relativas a `/api/v1`. `GET /health` y `POST /auth/login` son públicos. Las demás rutas requieren una cuenta autenticada. Las operaciones marcadas como **Admin** requieren ese rol.

### Cuentas

| Método y ruta | Entrada | Respuesta |
| --- | --- | --- |
| `POST /auth/login` | JSON con `correo` y `contrasena`. | `200` con token y cuenta. |
| `GET /auth/me` | — | `200` con la cuenta actual. |
| `GET /auth/faenas` | **Admin**. | `200` con la lista de faenas cliente. |
| `GET /auth/admin/faenas` | **Admin**. | `200` con las faenas y su cantidad de misiones. |
| `POST /auth/admin/faenas` | **Admin**. JSON con `nombre`. | `201` con la faena. |
| `PATCH /auth/admin/faenas/{faena_id}` | **Admin**. JSON con `nombre`. | `200` con la faena actualizada. |
| `DELETE /auth/admin/faenas/{faena_id}` | **Admin**. Faena sin usuarios ni misiones. | `204`. |
| `GET /auth/admin/usuarios` | **Admin**. | `200` con los usuarios. |
| `POST /auth/admin/usuarios` | **Admin**. JSON con `nombre`, `correo`, `contrasena`, `rol` e `id_faena` para operadores. | `201` con la cuenta. |
| `PUT /auth/admin/usuarios/{id}/password` | **Admin**. JSON con `contrasena` de 8 a 128 caracteres. | `204`. |

### Misiones y hallazgos

| Método y ruta | Entrada | Respuesta |
| --- | --- | --- |
| `POST /missions` | Multipart con `name`, uno o más campos `files`, `segment` opcional y `faena_id` obligatorio para admin. | `201` con la misión y sus imágenes. |
| `POST /missions/demo` | `faena_id` como parámetro de consulta para admin. | `201` con una misión de demostración. |
| `GET /missions` | `faena_id` opcional para admin. | `200` con resúmenes y conteos. |
| `GET /missions/{mission_id}` | — | `200` con la misión, sus imágenes y detecciones. |
| `DELETE /missions/{mission_id}` | — | `204`. |
| `POST /missions/{mission_id}/detect` | — | `200` con la misión procesada. |
| `GET /missions/{mission_id}/detect/progress` | — | `200` con el avance o `null`. |
| `PATCH /missions/{mission_id}/detections/{detection_id}` | JSON con `review_status`. | `200` con la detección actualizada. |
| `PATCH /missions/{mission_id}/detections/{detection_id}/repair` | JSON con `repair_status`. | `200` con la detección actualizada. |
| `PATCH /missions/{mission_id}/images/{image_id}/criticidad` | JSON con `criticidad_manual`. | `200` con la imagen actualizada. |
| `GET /missions/{mission_id}/images/{image_id}` | `analysis=true` para el JPEG de análisis. | `200` con la imagen original o procesada. |
| `GET /missions/{mission_id}/images/{image_id}/ancho` | — | `200` con el JPEG anotado de ancho de pista. |
| `GET /missions/{mission_id}/report` | `vista=ambas\|segmentacion\|rocas`. Por defecto, `ambas`. | `200` con el PDF generado. |
| `GET /dashboard/findings` | `faena_id` opcional para admin. | `200` con hallazgos de pista sin rechazo. |

### Sistema e inferencia

| Método y ruta | Entrada | Respuesta |
| --- | --- | --- |
| `GET /health` | — | `200` con el modo de detector y el motor de base de datos declarado. |
| `GET /inference/health` | — | `200` con estado de inferencia, umbral de apagado si aplica y error de arranque manual si existe. |
| `POST /inference/start` | **Admin**. | `202` con `{"status":"accepted"}`. |
| `PUT /inference/auto-shutdown` | **Admin**. JSON con `enabled` booleano e `idle_timeout_seconds` opcional entre 1 y 86.400. | `200` con el umbral efectivo en segundos. Cero representa desactivado. |
| `GET /inference/instance` | **Admin**. | `200` con tipo de instancia, región, zona y especificaciones disponibles. |

`GET /health` responde con datos de configuración sin consultar PostgreSQL, S3 o Jade. Para consultar la disponibilidad de inferencia se usa `GET /inference/health`. [Rutas de sistema](../backend/app/main.py)

### Errores habituales

| Código | Situación |
| --- | --- |
| `400` | Solicitud sin imágenes o administrador que intenta crear una misión sin indicar la faena. |
| `401` | Credenciales incorrectas o sesión inválida o vencida. |
| `403` | Operación reservada a un administrador. |
| `404` | Recurso inexistente o fuera del alcance de la cuenta. También aplica a archivos locales ausentes. |
| `409` | Misión ya en proceso, correo duplicado o administración de Jade sin configurar. |
| `415` | Tipo de contenido de imagen no admitido. |
| `422` | Datos inválidos, archivo que Pillow no puede abrir o solicitud de detección para una misión sin imágenes. |
| `502` | Error del detector durante el procesamiento o al consultar los datos de instancia de Jade. |
| `503` | Jade no disponible, fallo de almacenamiento o fallo de persistencia capturado por la operación. |

FastAPI devuelve los errores en el campo `detail`. Las validaciones automáticas pueden devolver una lista de errores en ese campo.

## Configuración del backend

La aplicación lee las variables de entorno y el archivo local ignorado `backend/.env` cuando se ejecuta desde `backend/`. [Definición de variables](../backend/app/config.py) · [Inicio local](../README.md#backend)

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | Conexión PostgreSQL de la aplicación. La base de desarrollo es `neumavisiondb`. |
| `SECRET_KEY`, `TOKEN_HOURS` | Clave de firma de al menos 32 caracteres y duración de la sesión. |
| `API_PREFIX`, `CORS_ORIGINS` | Prefijo de rutas y orígenes permitidos, separados por comas. Las URLs de imágenes emitidas por la API usan `/api/v1`. |
| `UPLOAD_DIR`, `ANALYSIS_S3_BUCKET` | Directorio local de trabajo y bucket privado para originales, JPEG de análisis remoto e informes. |
| `DETECTOR_MODE`, `YOLO_MODEL_PATH` | Selección de adaptador y ruta al modelo del modo `yolo`. |
| `INFERENCE_URL`, `INFERENCE_TOKEN`, `INFERENCE_TIMEOUT` | URL, token del servicio remoto y timeout HTTP de inferencia. El valor predeterminado del timeout es 300 segundos. |
| `JADE_INSTANCE_ID`, `JADE_REGION`, `JADE_START_TIMEOUT`, `JADE_IDLE_TIMEOUT_SECONDS` | Instancia, región, tiempo de espera de arranque y umbral de apagado. |
| `DEFAULT_GSD_CM_PX` | Escala en centímetros por píxel para el cálculo de ancho cuando se configura. |

Desde `backend/`, con el entorno de Python y la configuración local listos, el punto de entrada es `uvicorn app.main:app --reload`.
