# Prueba local del detector de rocas

Ejecutar desde la raíz del repositorio, con el entorno de inferencia existente:

```powershell
.\inference\.venv\Scripts\python.exe -m pip install -r inference/requirements.txt
.\inference\.venv\Scripts\python.exe inference/detection.py inference/test_images/prueba.jpg
.\inference\.venv\Scripts\python.exe inference/detection.py inference/test_images/prueba.jpg --conf 0.35 --device cpu
```

Usar el checkpoint YOLO26l de rocas en `inference/models/weights_det.pt`.
`weights_seg.pt` corresponde al segmentador de caminos YOLO26. El script
rechaza pesos idénticos al segmentador. Instala Ultralytics para cargar YOLO26:
https://docs.ultralytics.com/models/yolo26/

La confianza predeterminada es 0,30. Según la evaluación proporcionada por Peter,
0,35 y 0,40 aumentan precisión y reducen recall. El IoU 0,5 de esa evaluación es
el criterio de correspondencia con las etiquetas; no se usa como parámetro NMS.

La foto se divide en una grilla de 2 filas y 3 columnas sin solapamiento, sin
redimensionarla previamente. Para 3840×2160 cada tile mide 1280×1080. Otras
resoluciones generan un aviso y tiles proporcionales; no garantizan la misma
escala del entrenamiento. Se incluyen todos los píxeles, también en tamaños
impares. Cada tile pasa por letterbox cuadrado a `--imgsz 1280`, con
`--max-det 600` por tile, sin aumentaciones ni autocontraste. Para una imagen
que ya es un tile, usar `--rows 1 --columns 1`.

Las cajas se trasladan a coordenadas de la foto original. No hay solapamiento
ni fusión de objetos cortados por bordes de tiles. No se filtra con la máscara
del camino. El filtro de etiquetas menores de 24 px del entrenamiento no se
aplica a predicciones: falta definir si ese tamaño corresponde a ancho, alto
u otro criterio antes de usarlo como filtro de salida.

Salidas en `inference/outputs/`: `<nombre>_rocks.jpg` y `<nombre>_rocks.json`.
Las cajas JSON son `[x1, y1, x2, y2]` en píxeles de la imagen original y las clases
se leen del checkpoint. Una imagen sin rocas genera `detections: []`. Repetir una
prueba con el mismo nombre sobrescribe sus salidas; usar `--output` para comparar
umbrales. Pesos, imágenes y salidas están ignorados por Git.

Esta prueba es independiente del backend. `requirements.txt` agrega únicamente
Ultralytics para ejecutar ambos modelos YOLO26.

## Cruce con la máscara del camino

Con el entorno de inferencia que tiene Ultralytics:

```powershell
.\inference\.venv\Scripts\python.exe inference/pipeline.py inference/test_images/1.jpg
.\inference\.venv\Scripts\python.exe -m unittest discover -s inference -p "test_*.py"
```

El pipeline ejecuta ambos modelos sobre la misma imagen. Selecciona únicamente
la máscara de segmentación con mayor confianza, sin umbral mínimo, y conserva
todas las rocas devueltas por YOLO con confianza de 0,30 y grilla 2×3.
El detector de rocas entrega cajas, no máscaras de instancia: una alarma significa
que al menos un píxel de su caja intersecta la máscara del camino. Esto puede
incluir fondo dentro de la caja. Las cajas se recortan a la imagen para el cruce.

Salidas adicionales: `<nombre>_road_mask.png`, `<nombre>_alarms.jpg` y
`<nombre>_alarms.json`. El camino en buen estado se muestra verde y el camino con
material pedregoso naranja; las cajas con alarma rojas y
las demás amarillas. La imagen muestra sobre la máscara su clase, sin confianza:
`Camino en buen estado` (clase 1) o `Camino con material pedregoso`
(clase 2). JSON conserva todos los hallazgos, agrega `alarm` y
`road_overlap_pixels` por roca y una alarma global con el conteo. Si no hay
máscara, `cross_status` es `no_road_mask` y las alarmas son `null`: no se puede
determinar si las rocas están sobre el camino. Si hay máscara pero no rocas,
la alarma global es `false`. Las alarmas son locales (imagen, JSON y consola);
no envían notificaciones ni modifican el backend.

## Integración con la plataforma

Desde la raíz, iniciar el servicio en una terminal:

```powershell
.\inference\.venv\Scripts\python.exe -m pip install -r inference/requirements.txt
.\inference\.venv\Scripts\python.exe -m uvicorn api:app --app-dir inference --host 127.0.0.1 --port 8001
```

En otra terminal iniciar el backend con el adaptador remoto, conservando su `.env`:

```powershell
cd backend
$env:DETECTOR_MODE = "remote"
$env:INFERENCE_URL = "http://127.0.0.1:8001"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Iniciar el frontend como siempre (`npm.cmd run dev` desde `frontend/`). Subir una
misión y pulsar **Ejecutar detección**. Los modelos se cargan una vez por proceso;
las peticiones de inferencia se serializan con un lock para evitar ejecuciones
simultáneas sobre los modelos. Usar un solo worker de inferencia.

`POST /predict` recibe multipart `file`. Devuelve dimensiones, metadata de la
máscara seleccionada, únicamente las rocas que intersectan el camino y un JPEG
en base64 con la máscara y su etiqueta sin confianza. El backend guarda las
rocas como `DETECCION`, normaliza las cajas y sirve la imagen procesada mediante
`GET /api/v1/missions/{id}/images/{image_id}?analysis=true`, con el mismo control
de acceso por faena que el original. No se agregan tablas ni migraciones.

Sin máscara se devuelve 422 y el backend responde 502; nunca se transforma esa
situación en cero hallazgos. Un error al guardar resultados devuelve 503.
La sustitución de detecciones en una misión es transaccional: si falla una
imagen se conservan las detecciones anteriores. El JPEG derivado se guarda junto
al original como `<archivo>.vision.jpg`. Actualmente ambos siguen en almacenamiento
local del backend.

Configuración del backend: `DETECTOR_MODE=remote`, `INFERENCE_URL`,
`INFERENCE_TIMEOUT` (300 segundos por imagen) e `INFERENCE_TOKEN` opcional para
pruebas locales. Para comunicar dos EC2 usar la dirección privada del servicio,
restringir su puerto al backend y configurar el mismo `INFERENCE_TOKEN` secreto
en ambos procesos. El servicio lee ese valor del entorno; se puede cargar un
`.env` local con `uvicorn --env-file` sin versionarlo. No publicar el servicio de
inferencia directamente al navegador. No se modifican `.env` existentes.

## Despliegue en EC2 con Nina y Jade

Nina ejecuta el backend y Jade ejecuta este servicio. Si ambas instancias
comparten VPC, usar la IP privada de Jade y permitir entrada TCP 8001 en su
security group con la IP privada de Nina como origen (`/32`). Comprobar que
ninguna otra regla asociada a Jade expone ese puerto a Internet. Ver
[reglas de security groups de AWS](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html).

### Jade

Copiar el directorio `inference/` de la misma revisión que el backend desplegado
y colocar los checkpoints confiables en `inference/models/weights_seg.pt`
(YOLO26 de segmentación) y `inference/models/weights_det.pt` (YOLO26 de detección). Confirmar que son archivos
distintos con `sha256sum inference/models/weights_{seg,det}.pt`.

Desde el checkout, con Python y soporte para entornos virtuales instalados:

```bash
python3 -m venv inference/.venv
inference/.venv/bin/python -m pip install -r inference/requirements.txt
```

Configurar `INFERENCE_TOKEN` en el `.env` local ignorado por Git y restringir
su lectura al usuario del servicio. Usar una unidad systemd con un único worker.
Este ejemplo supone un checkout en `/home/ubuntu/neumavision` y el usuario
`ubuntu`. Ajustar ambas rutas y el usuario al host real.

```ini
[Unit]
Description=NeumaVision inference
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/neumavision/inference
EnvironmentFile=/home/ubuntu/neumavision/inference/.env
Environment=INFERENCE_PRELOAD=1
ExecStart=/home/ubuntu/neumavision/inference/.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8001 --workers 1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Guardar la unidad como `/etc/systemd/system/neumavision-inference.service`.
Ejecutar `sudo systemctl daemon-reload` y luego
`sudo systemctl enable --now neumavision-inference.service`.
Consultar el arranque con `sudo journalctl -u neumavision-inference -n 50`.

### Nina

Nina solicita a Jade la medición de ancho mediante `include_road_width=true`
en `POST /predict`. Jade devuelve el resumen y el JPEG anotado en
`road_width`. Si una versión anterior devuelve solo la máscara, Nina
calcula el ancho localmente. Si se configura `DEFAULT_GSD_CM_PX` en Nina,
se envía a Jade como escala de respaldo para fotos sin EXIF suficiente.

En Ubuntu, instalar `libgl1` para que OpenCV pueda calcular el ancho
del camino con la máscara que devuelve Jade.

```bash
sudo apt-get install --no-install-recommends libgl1
```

Desde Nina, comprobar primero que Jade responde:

```bash
curl -fsS --connect-timeout 5 http://IP_PRIVADA_JADE:8001/health
```

Validar también `POST /predict` con el token y una foto real de camino.
Con `INFERENCE_PRELOAD=1`, `/health` empieza a responder cuando se han
cargado ambos checkpoints. La predicción comprueba que el pipeline completo
funciona con el runtime de Jade.

En la configuración de arranque del backend de Nina, definir
`DETECTOR_MODE=remote`, `INFERENCE_URL=http://IP_PRIVADA_JADE:8001` y el mismo
`INFERENCE_TOKEN` de Jade. Conservar la configuración existente del backend y
reiniciar su servicio. Desde la plataforma, crear una misión de prueba con una
foto de camino y pulsar **Ejecutar detección**. Comprobar que se muestra la
imagen procesada y que se pueden consultar los hallazgos al recargar la misión.

### Encendido bajo demanda y resultados en S3

Usar una instancia Jade dedicada a la inferencia de Nina. El servicio de Jade
arranca automáticamente con el sistema operativo. Configurar en Nina:

| Variable | Valor |
| --- | --- |
| `DETECTOR_MODE` | `remote` |
| `INFERENCE_URL` | `http://IP_PRIVADA_JADE:8001` |
| `INFERENCE_TOKEN` | El mismo secreto de Jade |
| `JADE_INSTANCE_ID` | ID EC2 de Jade |
| `JADE_REGION` | Región de Jade (por defecto `us-east-2`) |
| `JADE_START_TIMEOUT` | Espera máxima del arranque y carga, en segundos (300 por defecto) |
| `JADE_IDLE_TIMEOUT_SECONDS` | Segundos de inactividad antes del apagado (1200 por defecto). Usar 0 para desactivar el apagado automático. |
| `INFERENCE_TIMEOUT` | Tiempo máximo por solicitud de imagen, en segundos (300 por defecto) |
| `ANALYSIS_S3_BUCKET` | Bucket privado para originales, JPEG procesados y PDF |

El rol de instancia de Nina requiere `ec2:DescribeInstances` sobre `*` y
`ec2:StartInstances` y `ec2:StopInstances` limitados al ARN de Jade. Para S3
requiere `s3:PutObject` y `s3:GetObject` en los prefijos `originals/*`,
`analysis/*` y `reports/*` del bucket. Ver [ejemplos de políticas de EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ExamplePolicies_EC2.html).

Instalar los requisitos del backend y aplicar la revisión Alembic
`20261118_0008` antes de actualizar el servicio. Verificar la URL y
`SELECT current_database()` antes de migrar RDS. Esta revisión agrega a
`imagen` la clave S3 opcional del JPEG procesado. Con el bucket configurado,
Nina guarda los originales en `originals/{id_mision}/{archivo}` y elimina
la copia local al finalizar la carga. Para procesar o generar informes,
recupera temporalmente el original desde S3 y lo borra al dejar de usarlo.
Al generar un informe, Nina guarda el PDF más reciente en
`reports/{id_mision}/informe.pdf` y su clave en `informe`. El visor comprueba
el acceso a la misión antes de entregar imágenes y PDF.

Con `JADE_INSTANCE_ID` configurado, ejecutar Nina con **un único proceso
y un único worker**. El endpoint de detección sigue siendo síncrono.
Ajustar el timeout del proxy para cubrir el arranque en frío y la inferencia
de todas las imágenes de una misión. Nina reintenta si AWS devuelve un error
de capacidad temporal de EC2. Cuando termina el último trabajo registrado,
Nina espera 20 minutos por defecto antes de solicitar el apagado. Una nueva misión
reinicia el plazo. Nina comprueba la inactividad cada 15 segundos mientras
el backend está en ejecución. Si se reinicia Nina, una instancia encendida
recibe un nuevo plazo de inactividad. Un error al detener Jade queda en el log.

`GET /api/v1/inference/health` requiere autenticación y combina el estado
de EC2 con la disponibilidad de `/health` de Jade. La plataforma actualiza
el indicador cada cinco segundos.

`GET /api/v1/missions/{id}/detect/progress` verifica el acceso a la misión y
devuelve la fase, las imágenes procesadas y una estimación del tiempo de
análisis restante tras completar la primera imagen. Devuelve `null` cuando
no hay una detección activa. El progreso se mantiene en el proceso de Nina
mientras se ejecuta la solicitud de detección.

Para validar en AWS, partir con Jade detenida y ejecutar la detección de una
misión pequeña. Verificar que Jade pasa a `running`, que el visor carga el JPEG
y las detecciones tras recargar la página, y que Jade pasa a `stopping` y luego
a `stopped` tras 20 minutos sin trabajos.
