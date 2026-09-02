# Contexto del proyecto — Rock Detector / Inspección de Caminos Mineros

## 1. Descripción general

El proyecto consiste en desarrollar una plataforma web para inspección de caminos mineros mediante imágenes RGB capturadas por dron.

El objetivo principal es detectar anomalías u objetos que puedan dañar los neumáticos de camiones CAEX, principalmente:

- Rocas.
- Baches.
- Desprendimientos de roca.
- Otros objetos extraños que eventualmente se definan como clases del modelo.

La plataforma recibirá lotes de imágenes correspondientes a una misión de inspección, procesará las imágenes mediante un modelo YOLO y almacenará los resultados.

Posteriormente permitirá visualizar los hallazgos y generar un informe final descargable.

## 2. Alcance del MVP

El MVP debe permitir:

1. Inicio de sesión por faena.
2. Crear una misión de inspección.
3. Subir un lote de imágenes.
4. Guardar las imágenes en Amazon S3.
5. Procesar las imágenes con un modelo YOLO.
6. Registrar las detecciones en PostgreSQL.
7. Extraer geolocalización desde EXIF cuando esté disponible.
8. Mostrar las detecciones encontradas.
9. Mostrar los hallazgos en un mapa.
10. Generar un informe final de la misión.
11. Descargar el informe.
12. Consultar historial de misiones.

Fuera del MVP:

- Automatización del dron.
- Automatización del hangar.
- Fotogrametría.
- Nube de puntos.
- Reconstrucción 3D.
- RabbitMQ.
- Arquitecturas distribuidas complejas.
- Múltiples tipos de usuario.

## 3. Arquitectura general

```text
Frontend
   |
   v
Backend FastAPI
   |
   +-------------------+
   |                   |
   v                   v
Amazon RDS          Amazon S3
PostgreSQL          Imágenes / PDF
   |
   |
Backend
   |
   v
Servicio de inferencia YOLO
Docker en Amazon EC2
   |
   v
best.pt
```

### Frontend

Responsable de:

- Login.
- Visualización de misiones.
- Creación de misiones.
- Carga de imágenes.
- Visualización de resultados.
- Mapa.
- Descarga del informe.

El framework del frontend puede definirse posteriormente.

### Backend

Framework principal:

- Python.
- FastAPI.

Responsabilidades:

- Autenticación.
- Gestión de faenas.
- Gestión de misiones.
- Recepción de imágenes.
- Comunicación con S3.
- Comunicación con RDS PostgreSQL.
- Comunicación con el servicio de inferencia.
- Persistencia de detecciones.
- Generación de informes.
- Entrega de información al frontend.

### Servicio de inferencia

Se ejecutará en Amazon EC2 dentro de Docker.

Contendrá:

- Python.
- Runtime compatible con YOLO.
- Modelo entrenado `best.pt`.
- API de inferencia, probablemente FastAPI.

Su responsabilidad es únicamente realizar inferencia.

Ejemplo conceptual:

```text
POST /predict
```

Entrada:

```text
imagen
```

Salida conceptual:

```json
{
  "detections": [
    {
      "class": "roca",
      "confidence": 0.94,
      "bbox": [120, 80, 250, 210]
    }
  ]
}
```

Este servicio no entrena el modelo. Solo utiliza el modelo ya entrenado para hacer predicciones sobre imágenes nuevas.

## 4. Servicios AWS

### Amazon EC2

Ejecutará el servicio de inferencia YOLO dentro de Docker.

### Amazon S3

Almacenará:

- Imágenes originales.
- Archivos derivados si posteriormente se requieren.
- Informes PDF.

PostgreSQL no almacenará imágenes binarias. Solo almacenará referencias o claves de S3.

### Amazon RDS

Motor:

- PostgreSQL.

Será utilizado para almacenar los datos estructurados de la aplicación.

No se instalará PostgreSQL manualmente en EC2.

## 5. Modelo Entidad-Relación

Las entidades definitivas del MVP son:

- FAENA
- MISION
- IMAGEN
- DETECCION
- INFORME

### FAENA

La faena representa directamente la cuenta que inicia sesión.

No existe una entidad USUARIO independiente.

Campos:

- `id_faena` PK
- `nombre`
- `email`
- `password_hash`
- `fecha_creacion`

### MISION

Representa una inspección.

Campos:

- `id_mision` PK
- `id_faena` FK
- `nombre`
- `fecha`
- `descripcion`
- `estado`

Estados iniciales sugeridos:

- `pendiente`
- `procesando`
- `completada`
- `error`

Relación:

```text
FAENA 1:N MISION
```

### IMAGEN

Cada misión contiene múltiples imágenes.

Campos:

- `id_imagen` PK
- `id_mision` FK
- `nombre_archivo`
- `url_s3`
- `latitud`
- `longitud`
- `altitud`
- `fecha_captura`
- `estado_proceso`

La geolocalización inicialmente provendrá del EXIF de la fotografía.

Relación:

```text
MISION 1:N IMAGEN
```

### DETECCION

Una detección representa un objeto detectado por YOLO dentro de una imagen.

Ejemplos:

- roca
- bache
- desprendimiento

Una imagen puede producir cero o muchas detecciones.

Una misma roca física que aparezca en dos fotografías distintas se considerará inicialmente como dos detecciones diferentes.

Campos:

- `id_deteccion` PK
- `id_imagen` FK
- `clase`
- `confianza`
- `bbox_x`
- `bbox_y`
- `bbox_ancho`
- `bbox_alto`

Por ahora no almacenar:

- latitud
- longitud
- url_evidencia_s3

La ubicación se obtiene desde la IMAGEN asociada.

Relación:

```text
IMAGEN 1:0..N DETECCION
```

Cada DETECCION pertenece a una sola IMAGEN.

### INFORME

Cada misión tendrá como máximo un informe final.

Una misión puede todavía no tener informe mientras se encuentra pendiente o procesándose.

Campos:

- `id_informe` PK
- `id_mision` FK UNIQUE
- `fecha_generacion`
- `url_pdf_s3`
- `total_hallazgos`

Relación:

```text
MISION 1:0..1 INFORME
```

## 6. MER resumido

```text
FAENA
  |
  | 1:N
  v
MISION -------- 1:0..1 -------- INFORME
  |
  | 1:N
  v
IMAGEN
  |
  | 1:0..N
  v
DETECCION
```

## 7. Flujo principal de una misión

1. La faena inicia sesión.
2. La faena crea una misión.
3. Se carga un lote de imágenes.
4. El backend crea los registros de imágenes.
5. Las imágenes se almacenan en S3.
6. Se extraen metadatos EXIF.
7. El backend envía cada imagen al servicio de inferencia.
8. YOLO ejecuta `best.pt`.
9. El servicio devuelve detecciones.
10. El backend almacena las detecciones en PostgreSQL.
11. La misión pasa a estado completada.
12. Se genera un informe.
13. El PDF se almacena en S3.
14. Se registra el informe en PostgreSQL.
15. El frontend permite consultar resultados, mapa e informe.

## 8. Camino crítico de implementación

Primero implementar el flujo completo con una sola imagen:

```text
Crear misión
    |
    v
Subir imagen
    |
    v
Guardar imagen
    |
    v
Ejecutar YOLO
    |
    v
Guardar detecciones
    |
    v
Mostrar resultado
```

Una vez que funcione correctamente, implementar procesamiento por lotes.

## 9. API inicial sugerida

### Autenticación

```text
POST /auth/login
```

### Misiones

```text
POST /misiones
GET  /misiones
GET  /misiones/{id}
```

### Imágenes

```text
POST /misiones/{id}/imagenes
GET  /misiones/{id}/imagenes
GET  /imagenes/{id}
```

### Detecciones

```text
GET /imagenes/{id}/detecciones
```

### Informe

```text
GET  /misiones/{id}/informe
POST /misiones/{id}/informe
```

## 10. Seguridad y aislamiento de datos

La aplicación será multi-faena.

Cada faena solamente debe acceder a sus propios datos.

Después del login, el backend debe conocer `id_faena`.

Nunca confiar en un `id_faena` enviado por el frontend para autorizar acceso.

El backend debe obtener la faena autenticada desde la sesión o token.

Ejemplo:

```text
Faena autenticada:
id_faena = 3

Solo puede consultar:
MISION.id_faena = 3
```

Las imágenes, detecciones e informes se filtran por las relaciones con la misión.

## 11. Organización sugerida del repositorio

```text
rock_detector/
├── frontend/
├── backend/
├── inference/
├── docs/
├── docker-compose.yml
├── PROJECT_CONTEXT.md
├── AGENTS.md
└── README.md
```

Backend sugerido:

```text
backend/
└── app/
    ├── main.py
    ├── api/
    ├── models/
    ├── schemas/
    ├── services/
    ├── database/
    └── core/
```

## 12. Docker

Se planea dockerizar:

- Frontend.
- Backend.
- Servicio de inferencia.

No dockerizar en producción:

- PostgreSQL.

La base de datos estará en Amazon RDS.

## 13. Principios de desarrollo

Mantener el MVP simple.

Priorizar:

- código claro;
- componentes separados;
- responsabilidades bien definidas;
- seguridad entre faenas;
- trazabilidad de errores;
- diseño modular;
- facilidad de despliegue.

No introducir arquitectura distribuida compleja anticipadamente.

RabbitMQ, SQS u otras colas pueden evaluarse posteriormente si el volumen de imágenes lo requiere.

## 14. Orden recomendado de desarrollo

1. Requisitos funcionales.
2. Arquitectura.
3. MER.
4. Diseño de API.
5. Estructura de repositorio.
6. Base de datos PostgreSQL.
7. Backend mínimo.
8. Subida de imágenes.
9. Integración con S3.
10. Servicio de inferencia local.
11. Comunicación backend-inferencia.
12. Persistencia de detecciones.
13. Frontend.
14. Procesamiento por lote.
15. Mapa.
16. Informe PDF.
17. Autenticación y aislamiento por faena.
18. Pruebas.
19. Docker.
20. Despliegue en AWS.

## 15. Estado actual

Actualmente:

- El alcance general está definido.
- La arquitectura está definida a alto nivel.
- Se decidió utilizar AWS en lugar de Supabase.
- La base de datos será Amazon RDS PostgreSQL.
- Las imágenes estarán en Amazon S3.
- La inferencia YOLO se ejecutará en EC2 utilizando Docker.
- El MER básico está definido.
- Aún se debe terminar el diseño de requisitos funcionales y API antes de implementar todo el backend.
