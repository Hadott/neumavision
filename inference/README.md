# Prueba local del detector de rocas

Ejecutar desde la raíz del repositorio, con el entorno de inferencia existente:

```powershell
.\inference\.venv\Scripts\python.exe -m pip install -r inference/requirements.txt
.\inference\.venv\Scripts\python.exe inference/detection.py inference/test_images/prueba.jpg
.\inference\.venv\Scripts\python.exe inference/detection.py inference/test_images/prueba.jpg --conf 0.35 --device cpu
```

Usar el checkpoint YOLO26l de rocas en `inference/models/weights_det.pt`.
`weights_seg.pt` corresponde a RF-DETR y se conserva sin cambios. El script
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
el runtime de detección al entorno existente; no instala el segmentador RF-DETR.

## Cruce con la máscara del camino

Con el entorno existente que ya tiene RF-DETR y Ultralytics:

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
local del backend; la conexión con S3 y el despliegue AWS siguen pendientes.

Configuración del backend: `DETECTOR_MODE=remote`, `INFERENCE_URL`,
`INFERENCE_TIMEOUT` (300 segundos por imagen) e `INFERENCE_TOKEN` opcional para
pruebas locales. Para comunicar dos EC2 usar la dirección privada del servicio,
restringir su puerto al backend y configurar el mismo `INFERENCE_TOKEN` secreto
en ambos procesos. El servicio lee ese valor del entorno; se puede cargar un
`.env` local con `uvicorn --env-file` sin versionarlo. No publicar el servicio de
inferencia directamente al navegador. No se modifican `.env` existentes.
