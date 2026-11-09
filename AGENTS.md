# AGENTS.md

## Propósito

Este archivo define cómo debe trabajar Codex u otro agente de programación dentro de este repositorio.

Antes de realizar cambios importantes, leer también `PROJECT_CONTEXT.md`.

## Reglas generales

1. Mantener el MVP simple.
2. No introducir tecnologías, frameworks, servicios o dependencias nuevas sin una necesidad concreta.
3. Antes de cambiar una decisión arquitectónica existente, explicar brevemente el motivo.
4. Evitar sobreingeniería.
5. Priorizar código legible, modular y fácil de mantener.
6. No duplicar lógica innecesariamente.
7. No crear abstracciones prematuras.
8. Hacer cambios pequeños y verificables.
9. No modificar componentes no relacionados con la tarea actual salvo que sea necesario.
10. Si existe ambigüedad menor, escoger la opción más simple y consistente con `PROJECT_CONTEXT.md`.

## Stack acordado

### Backend

- Python.
- FastAPI.
- PostgreSQL.
- SQLAlchemy recomendado para acceso a datos.
- Alembic recomendado para migraciones cuando sea necesario.

### Infraestructura

- Amazon RDS PostgreSQL para base de datos.
- Amazon S3 para imágenes e informes.
- Amazon EC2 para el servicio de inferencia.

### IA

- Modelo YOLO ya entrenado.
- Pesos esperados en formato `best.pt`.
- El servicio de inferencia debe estar separado del backend principal.
- El servicio de inferencia no debe entrenar el modelo.
- Debe recibir imágenes y devolver detecciones estructuradas.

## Modelo de datos obligatorio para el MVP

No agregar nuevas entidades sin necesidad real.

Entidades actuales:

- FAENA
- MISION
- IMAGEN
- DETECCION
- INFORME

Cardinalidades:

```text
FAENA 1:N MISION
MISION 1:N IMAGEN
IMAGEN 1:0..N DETECCION
MISION 1:0..1 INFORME
```

### FAENA

La faena es la cuenta autenticada.

No crear una entidad `USUARIO` por ahora.

### MISION

Debe pertenecer a una FAENA.

Estados iniciales esperados:

- pendiente
- procesando
- completada
- error

### IMAGEN

Debe pertenecer a una MISION.

Puede contener información EXIF:

- latitud
- longitud
- altitud
- fecha_captura

### DETECCION

Debe pertenecer a una sola IMAGEN.

Una imagen puede tener cero o muchas detecciones.

Campos esperados:

- clase
- confianza
- bounding box

No agregar por ahora:

- latitud
- longitud
- url_evidencia_s3

### INFORME

Debe pertenecer a una MISION.

Una misión puede tener cero o un informe.

`id_mision` debe ser único en INFORME.

## Seguridad

La separación de datos entre faenas es obligatoria.

Nunca confiar en `id_faena` proporcionado por el frontend para autorizar operaciones.

La faena debe obtenerse desde el contexto autenticado.

Toda operación sobre:

- misiones;
- imágenes;
- detecciones;
- informes;

debe verificar directa o indirectamente que el recurso pertenece a la faena autenticada.

Una faena nunca debe poder consultar datos de otra.

## Archivos

No almacenar imágenes binarias dentro de PostgreSQL.

Usar S3 para:

- imágenes originales;
- informes PDF;
- otros archivos derivados cuando sean necesarios.

PostgreSQL debe guardar únicamente metadata y referencias de S3.

Preferir guardar claves de objeto S3 antes que URLs públicas permanentes cuando sea posible.

## Servicio de inferencia

Mantener el servicio de inferencia desacoplado del backend principal.

Responsabilidad:

```text
imagen -> YOLO -> detecciones
```

Debe devolver al menos:

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

No agregar entrenamiento, administración de datasets o lógica de negocio de la plataforma dentro del servicio de inferencia.

## Orden de implementación

Antes de implementar procesamiento masivo, completar primero el camino crítico para una sola imagen:

```text
crear misión
-> subir imagen
-> almacenar imagen
-> ejecutar inferencia
-> guardar detecciones
-> consultar resultado
```

Solo después agregar:

- lotes;
- mapa;
- informe PDF;
- mejoras de interfaz;
- optimizaciones.

## API

Mantener endpoints REST simples y coherentes.

Diseño inicial esperado:

```text
POST /auth/login

POST /misiones
GET  /misiones
GET  /misiones/{id}

POST /misiones/{id}/imagenes
GET  /misiones/{id}/imagenes
GET  /imagenes/{id}

GET  /imagenes/{id}/detecciones

GET  /misiones/{id}/informe
POST /misiones/{id}/informe
```

No tratar este listado como inmutable si durante la implementación se detecta una estructura mejor, pero cualquier cambio debe mantener simplicidad y coherencia.

## Base de datos

Usar claves primarias y foráneas explícitas.

Agregar índices donde exista una necesidad clara de consulta.

Mantener integridad referencial.

No duplicar datos que puedan obtenerse naturalmente por relaciones existentes.

Ejemplo:

No guardar `id_faena` en DETECCION si puede obtenerse mediante:

```text
DETECCION -> IMAGEN -> MISION -> FAENA
```

## Configuración

No guardar secretos en el repositorio.

Usar variables de entorno para:

- credenciales AWS;
- URL de PostgreSQL;
- secretos JWT;
- credenciales o claves externas;
- configuración del servicio de inferencia.

Usar únicamente el `.env` local ignorado por Git para configuración; no crear ni
mantener un `.env.example`. Nunca sobrescribir un `.env` existente ni añadir sus
credenciales a archivos versionados.

### RDS de desarrollo

La instancia RDS de desarrollo es `neumavisiondb`, en `us-east-2`, con endpoint
`neumavisiondb.c1ka8s46gz5i.us-east-2.rds.amazonaws.com`. La base de datos de la
aplicación dentro de esa instancia también se llama `neumavisiondb`; conectarse a
la instancia no selecciona automáticamente la base correcta.

- Base de datos de la aplicación: `neumavisiondb`.
- Usuario de conexión: `rock_admin`.
- Puerto: `5432`.
- URL local en `backend/.env`: `postgresql+psycopg://...@neumavisiondb.c1ka8s46gz5i.us-east-2.rds.amazonaws.com:5432/neumavisiondb`.
- La contraseña solo debe estar en el `.env` local ignorado por Git; nunca copiarla a este archivo, al chat o a logs.
- No confundir la base `neumavisiondb` con `rock_detector`, que existe en la instancia pero no es la base usada por la aplicación.
- Antes de migrar o inicializar, verificar la URL y `SELECT current_database()` para confirmar que el destino es `neumavisiondb`; no ejecutar operaciones de esquema sobre otra base por defecto.
- El acceso desde un PC requiere que RDS sea públicamente accesible y que el security group asociado permita entrada TCP `5432` desde la IP pública actual del PC como `/32`. No abrir el puerto a `0.0.0.0/0`.

En la última comprobación, `neumavisiondb` contenía las tablas `faena`, `mision`,
`imagen`, `deteccion`, `informe` y `alembic_version`. Si parecen faltar, primero
verificar base y esquema seleccionados en el cliente PostgreSQL; no asumir que
fueron borradas ni recrearlas antes de comprobar el destino.

## Calidad del código

Cuando se agregue funcionalidad:

1. Validar entradas.
2. Manejar errores previsibles.
3. Usar códigos HTTP correctos.
4. Evitar bloques `except` genéricos sin manejo.
5. Separar rutas, servicios, modelos y acceso a datos.
6. No poner toda la lógica en `main.py`.
7. Agregar tipos siempre que sea razonable.
8. Mantener nombres claros en español o inglés, pero ser consistente dentro del código.

## Pruebas

Antes de considerar una funcionalidad terminada, probar como mínimo:

- flujo exitoso;
- recurso inexistente;
- acceso de una faena a recursos de otra;
- imagen sin detecciones;
- imagen inválida;
- error del servicio de inferencia;
- error de S3;
- error de base de datos cuando corresponda.

No es necesario crear una suite enorme al comienzo. Priorizar pruebas del camino crítico.

## Dependencias

Antes de instalar una nueva dependencia:

1. Comprobar si Python/FastAPI/SQLAlchemy ya resuelven el problema.
2. Evitar librerías redundantes.
3. Justificar dependencias grandes.
4. Mantener archivos de dependencias actualizados.

## Documentación

Actualizar la documentación cuando cambie:

- arquitectura;
- esquema de base de datos;
- endpoints;
- variables de entorno;
- proceso de despliegue.

No dejar decisiones importantes únicamente implícitas en el código.

## Restricciones actuales

No implementar por ahora:

- RabbitMQ;
- Kafka;
- microservicios adicionales;
- Kubernetes;
- ECS;
- procesamiento distribuido complejo;
- tabla MODELO_IA;
- tabla USUARIO;
- fotogrametría;
- nube de puntos;
- reconstrucción 3D;
- automatización del dron;
- automatización del hangar.

Estas tecnologías o funciones solo deben incorporarse si los requisitos cambian de forma explícita.

## Comportamiento esperado de Codex

Cuando se solicite una tarea:

1. Leer el código relacionado antes de modificarlo.
2. Revisar `PROJECT_CONTEXT.md`.
3. Identificar el cambio mínimo necesario.
4. Implementarlo manteniendo la arquitectura existente.
5. Ejecutar o proponer las pruebas relevantes.
6. Resumir los archivos modificados.
7. Indicar cualquier supuesto importante.
8. No reescribir módulos completos sin necesidad.
