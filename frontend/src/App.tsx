import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CloudOff,
  Database,
  Download,
  FileImage,
  FileText,
  Gauge,
  ImagePlus,
  Layers3,
  LoaderCircle,
  MapPin,
  Mountain,
  Play,
  RotateCcw,
  ScanLine,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Upload,
  X,
  XCircle
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import MapPanel from "./MapPanel";
import type { Detection, Health, Mission, MissionImage, ReviewStatus } from "./types";

type View = "upload" | "review" | "report";

const colorForLabel: Record<string, string> = {
  Bache: "#ff6847",
  Piedra: "#f2b23e",
  "Desprendimiento de roca": "#9e82ff"
};

const fallbackColor = "#4ca8ff";
const confidence = (value: number) => `${Math.round(value * 100)}%`;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [view, setView] = useState<View>("upload");
  const [mission, setMission] = useState<Mission | null>(null);
  const [selectedImageId, setSelectedImageId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [missionName, setMissionName] = useState("Inspección camino de acceso");
  const [segment, setSegment] = useState("Tramo A");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<"upload" | "demo" | "detect" | "report" | null>(null);
  const [error, setError] = useState("");
  const [threshold, setThreshold] = useState(0.65);
  const [enabledLabels, setEnabledLabels] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!mission?.images.length) return;
    if (!selectedImageId || !mission.images.some((image) => image.id === selectedImageId)) {
      setSelectedImageId(mission.images[0].id);
    }
    const labels = Array.from(new Set(mission.images.flatMap((image) => image.detections.map((item) => item.label))));
    if (labels.length) setEnabledLabels((current) => current.length ? current.filter((label) => labels.includes(label)) : labels);
  }, [mission, selectedImageId]);

  const allDetections = useMemo(
    () => mission?.images.flatMap((image) => image.detections) ?? [],
    [mission]
  );
  const availableLabels = useMemo(
    () => Array.from(new Set(allDetections.map((item) => item.label))),
    [allDetections]
  );
  const selectedImage = mission?.images.find((image) => image.id === selectedImageId) ?? mission?.images[0] ?? null;
  const visibleDetections = selectedImage?.detections.filter(
    (item) => item.confidence >= threshold && enabledLabels.includes(item.label) && item.review_status !== "rejected"
  ) ?? [];
  const filteredAll = allDetections.filter(
    (item) => item.confidence >= threshold && enabledLabels.includes(item.label) && item.review_status !== "rejected"
  );
  const pending = allDetections.filter((item) => item.review_status === "pending").length;
  const confirmed = allDetections.filter((item) => item.review_status === "confirmed").length;
  const average = allDetections.length
    ? allDetections.reduce((total, item) => total + item.confidence, 0) / allDetections.length
    : 0;
  const counts = useMemo(() => {
    return availableLabels.reduce<Record<string, number>>((result, label) => {
      result[label] = filteredAll.filter((item) => item.label === label).length;
      return result;
    }, {});
  }, [availableLabels, filteredAll]);

  function acceptFiles(incoming: FileList | File[]) {
    const valid = Array.from(incoming).filter((file) => file.type.startsWith("image/"));
    setFiles((current) => [...current, ...valid].slice(0, 100));
    setError("");
  }

  async function createMission(event: FormEvent) {
    event.preventDefault();
    if (!files.length) {
      setError("Selecciona al menos una imagen RGB.");
      return;
    }
    setBusy("upload");
    setError("");
    try {
      const created = await api.createMission(missionName, segment, files);
      setMission(created);
      setSelectedImageId(created.images[0]?.id ?? "");
      setFiles([]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible cargar la misión.");
    } finally {
      setBusy(null);
    }
  }

  async function createDemo() {
    setBusy("demo");
    setError("");
    try {
      const created = await api.createDemo();
      setMission(created);
      setSelectedImageId(created.images[0]?.id ?? "");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible crear la demostración.");
    } finally {
      setBusy(null);
    }
  }

  async function runDetection() {
    if (!mission) return;
    setBusy("detect");
    setError("");
    try {
      const processed = await api.detect(mission.id);
      setMission(processed);
      setEnabledLabels(Array.from(new Set(processed.images.flatMap((image) => image.detections.map((item) => item.label)))));
      setView("review");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "La detección no pudo completarse.");
    } finally {
      setBusy(null);
    }
  }

  async function updateReview(detection: Detection, reviewStatus: ReviewStatus) {
    if (!mission) return;
    try {
      const updated = await api.reviewDetection(mission.id, detection.id, reviewStatus);
      setMission((current) => current ? {
        ...current,
        images: current.images.map((image) => ({
          ...image,
          detections: image.detections.map((item) => item.id === updated.id ? updated : item)
        }))
      } : current);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible actualizar el hallazgo.");
    }
  }

  async function downloadReport() {
    if (!mission) return;
    setBusy("report");
    setError("");
    try {
      await api.downloadReport(mission.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible descargar el informe.");
    } finally {
      setBusy(null);
    }
  }

  function toggleLabel(label: string) {
    setEnabledLabels((current) => current.includes(label)
      ? current.filter((item) => item !== label)
      : [...current, label]);
  }

  function selectRelative(direction: -1 | 1) {
    if (!mission?.images.length || !selectedImage) return;
    const currentIndex = mission.images.findIndex((image) => image.id === selectedImage.id);
    const nextIndex = (currentIndex + direction + mission.images.length) % mission.images.length;
    setSelectedImageId(mission.images[nextIndex].id);
  }

  function resetWorkspace() {
    setMission(null);
    setSelectedImageId("");
    setEnabledLabels([]);
    setView("upload");
    setError("");
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon"><Mountain size={20} /></span>
          <span><strong>NEUMADIESEL</strong><small>Visión de caminos</small></span>
        </div>
        <div className="top-actions">
          <span className={`connection ${health ? "online" : "offline"}`}>
            {health ? <Server size={14} /> : <CloudOff size={14} />}
            {health ? `API · ${health.detector}` : "API sin conexión"}
          </span>
          {mission && <button className="button ghost" onClick={resetWorkspace}><RotateCcw size={15} /> Nueva misión</button>}
        </div>
      </header>

      <section className="hero">
        <div>
          <span className="overline">Plataforma de inspección RGB</span>
          <h1>Detecta. Revisa. Informa.</h1>
          <p>Detecta condiciones que pueden dañar los neumáticos de camiones CAEX y localiza los sectores que requieren mantenimiento.</p>
        </div>
        <div className="architecture">
          <span><Server size={14} /> FastAPI</span>
          <ChevronRight size={13} />
          <span><Layers3 size={14} /> React</span>
          <ChevronRight size={13} />
          <span><Database size={14} /> {health?.database ?? "SQLite"}</span>
        </div>
      </section>

      <nav className="steps">
        {([
          ["upload", "1", "Carga"],
          ["review", "2", "Revisión"],
          ["report", "3", "Informe"]
        ] as [View, string, string][]).map(([key, number, label]) => (
          <button key={key} className={view === key ? "active" : ""} onClick={() => mission && setView(key)} disabled={!mission && key !== "upload"}>
            <span>{number}</span>{label}
          </button>
        ))}
      </nav>

      {error && <div className="error-banner"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError("")}><X size={15} /></button></div>}

      {view === "upload" && (
        <section className={`workspace upload-layout ${mission ? "has-mission" : ""}`}>
          <form className="card upload-card" onSubmit={createMission}>
            <div className="card-title">
              <div><span className="overline">Entrada</span><h2>Imágenes de la misión</h2></div>
              <span className="pill">RGB</span>
            </div>
            {!mission ? <>
              <div className="field-grid">
                <label><span>Nombre de misión</span><input value={missionName} onChange={(event) => setMissionName(event.target.value)} /></label>
                <label><span>Tramo</span><input value={segment} onChange={(event) => setSegment(event.target.value)} /></label>
              </div>
              <div
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFiles(event.dataTransfer.files); }}
              >
                <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(event) => event.target.files && acceptFiles(event.target.files)} />
                <span className="upload-icon"><Upload size={25} /></span>
                <strong>Arrastra las imágenes aquí</strong>
                <small>JPG, PNG o WebP · hasta 100 archivos por lote</small>
                <span className="button secondary"><ImagePlus size={15} /> Seleccionar archivos</span>
              </div>
              {files.length > 0 && <div className="queued-files">
                <div className="queue-head"><strong>{files.length} imágenes listas</strong><button type="button" onClick={() => setFiles([])}>Quitar todas</button></div>
                {files.slice(0, 4).map((file, index) => <div className="queued-file" key={`${file.name}-${index}`}><FileImage size={16} /><span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small><button type="button" onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={14} /></button></div>)}
                {files.length > 4 && <small className="more-files">+ {files.length - 4} archivos adicionales</small>}
              </div>}
              <div className="form-actions">
                <button className="button primary" disabled={busy !== null}><Upload size={16} />{busy === "upload" ? "Subiendo…" : "Crear misión"}</button>
                <button className="button demo" type="button" onClick={createDemo} disabled={busy !== null}>{busy === "demo" ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />} Usar datos demo</button>
              </div>
            </> : <div className="uploaded-state">
              <span className="success-icon"><CheckCircle2 size={27} /></span>
              <div><span className="overline">Carga completada</span><h3>{mission.name}</h3><p>{mission.segment} · {mission.images.length} imágenes</p></div>
              <div className="mission-thumbs">{mission.images.slice(0, 5).map((image) => <img key={image.id} src={api.imageUrl(image.image_url)} alt="Camino cargado" />)}</div>
            </div>}
          </form>

          <aside className="card process-card">
            <div className="card-title"><div><span className="overline">Procesamiento</span><h2>Flujo de detección</h2></div><Gauge size={20} /></div>
            <div className="pipeline">
              <div className={mission ? "complete" : "current"}><span>{mission ? <Check size={14} /> : "1"}</span><div><strong>Validar lote</strong><small>{mission ? `${mission.images.length} imágenes compatibles` : "Esperando imágenes"}</small></div></div>
              <div className={busy === "detect" ? "current" : mission?.status === "review" ? "complete" : ""}><span>{mission?.status === "review" ? <Check size={14} /> : "2"}</span><div><strong>Ejecutar detector</strong><small>{health?.detector === "yolo" ? "Modelo YOLO conectado" : "Adaptador simulado"}</small></div></div>
              <div className={mission?.status === "review" ? "complete" : ""}><span>{mission?.status === "review" ? <Check size={14} /> : "3"}</span><div><strong>Preparar revisión</strong><small>Resultados normalizados por imagen</small></div></div>
            </div>
            <div className="process-note"><ShieldCheck size={16} /><span>El backend guarda cada misión y expone los resultados mediante una API documentada.</span></div>
            <button className="button primary full large" onClick={runDetection} disabled={!mission || busy !== null}>{busy === "detect" ? <><LoaderCircle className="spin" size={17} /> Analizando imágenes…</> : <><Play fill="currentColor" size={16} /> Ejecutar detección</>}</button>
          </aside>
        </section>
      )}

      {view === "review" && mission && selectedImage && (
        <section className="workspace review-layout">
          <aside className="card filters-card">
            <div className="card-title compact"><div><span className="overline">Filtros</span><h2>Hallazgos</h2></div><SlidersHorizontal size={18} /></div>
            <div className="filter-list">
              {availableLabels.map((label) => <button key={label} className={enabledLabels.includes(label) ? "enabled" : ""} onClick={() => toggleLabel(label)}><i style={{ background: colorForLabel[label] ?? fallbackColor }} /><span>{label}</span><strong>{counts[label] ?? 0}</strong><em>{enabledLabels.includes(label) && <Check size={11} />}</em></button>)}
            </div>
            <div className="threshold">
              <label><span>Confianza mínima</span><strong>{confidence(threshold)}</strong></label>
              <input type="range" min="0.5" max="0.95" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
              <small><span>50%</span><span>95%</span></small>
            </div>
            <div className="stats-mini">
              <div><ScanLine size={15} /><span>Visibles</span><strong>{filteredAll.length}</strong></div>
              <div><CircleDot size={15} /><span>Pendientes</span><strong>{pending}</strong></div>
              <div><CheckCircle2 size={15} /><span>Confirmadas</span><strong>{confirmed}</strong></div>
            </div>
          </aside>

          <div className="viewer-column">
            <div className="card viewer-card">
              <div className="image-meta"><div><FileImage size={17} /><span><strong>{selectedImage.filename}</strong><small>{selectedImage.latitude ? `${selectedImage.latitude.toFixed(5)}, ${selectedImage.longitude?.toFixed(5)}` : "Sin coordenadas EXIF"}</small></span></div><span className="pill">{visibleDetections.length} hallazgos</span></div>
              <div className="image-stage">
                <img src={api.imageUrl(selectedImage.image_url)} alt="Camino minero bajo revisión" />
                {visibleDetections.map((item) => <button key={item.id} className={`box ${item.review_status}`} style={{ left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.width * 100}%`, height: `${item.height * 100}%`, borderColor: colorForLabel[item.label] ?? fallbackColor }} onClick={() => updateReview(item, item.review_status === "confirmed" ? "pending" : "confirmed")}><span style={{ background: colorForLabel[item.label] ?? fallbackColor }}>{item.label} · {confidence(item.confidence)}</span>{item.review_status === "confirmed" && <i style={{ background: colorForLabel[item.label] ?? fallbackColor }}><Check size={11} /></i>}</button>)}
                <span className="demo-watermark">{health?.detector === "mock" ? "SIMULACIÓN" : "INFERENCIA"}</span>
              </div>
              <div className="viewer-nav"><button onClick={() => selectRelative(-1)}><ArrowLeft size={15} /> Anterior</button><span>{mission.images.findIndex((image) => image.id === selectedImage.id) + 1} / {mission.images.length}</span><button onClick={() => selectRelative(1)}>Siguiente <ArrowRight size={15} /></button></div>
            </div>
            <div className="thumbnail-row">{mission.images.map((image) => <button key={image.id} className={image.id === selectedImage.id ? "selected" : ""} onClick={() => setSelectedImageId(image.id)}><img src={api.imageUrl(image.image_url)} alt="Miniatura" /><span>{image.detections.length}</span></button>)}</div>
          </div>

          <aside className="card review-card">
            <div className="card-title compact"><div><span className="overline">Imagen actual</span><h2>Revisión</h2></div><span className="pill">{selectedImage.detections.length}</span></div>
            <div className="detection-list">
              {selectedImage.detections.map((item) => <div className={`detection-item ${item.review_status}`} key={item.id}>
                <div><i style={{ background: colorForLabel[item.label] ?? fallbackColor }} /><strong>{item.label}</strong><span>{confidence(item.confidence)}</span></div>
                <div className="confidence-line"><span style={{ width: confidence(item.confidence), background: colorForLabel[item.label] ?? fallbackColor }} /></div>
                <div className="review-actions">
                  <button className={item.review_status === "confirmed" ? "active confirm" : ""} onClick={() => updateReview(item, "confirmed")}><Check size={13} /> Confirmar</button>
                  <button className={item.review_status === "rejected" ? "active reject" : ""} onClick={() => updateReview(item, "rejected")}><XCircle size={13} /> Descartar</button>
                </div>
              </div>)}
            </div>
            <button className="button primary full" onClick={() => setView("report")}><FileText size={16} /> Preparar informe</button>
          </aside>
        </section>
      )}

      {view === "report" && mission && (
        <section className="workspace report-layout">
          <article className="card report-preview">
            <div className="report-header"><span className="overline">Informe de inspección</span><h2>{mission.name}</h2><p>{mission.segment} · {new Date(mission.created_at).toLocaleDateString("es-CL")}</p>{health?.detector === "mock" && <span className="demo-label"><AlertTriangle size={13} /> Resultados simulados</span>}</div>
            <div className="report-content">
              <div className="metric-grid"><div><span>Imágenes</span><strong>{mission.images.length}</strong></div><div><span>Hallazgos</span><strong>{allDetections.length}</strong></div><div><span>Confirmados</span><strong>{confirmed}</strong></div><div><span>Confianza media</span><strong>{confidence(average)}</strong></div></div>
              <h3>Distribución de anomalías</h3>
              <div className="bar-list">{availableLabels.map((label) => <div key={label}><span>{label}</span><div><i style={{ width: `${allDetections.length ? ((counts[label] ?? 0) / Math.max(...Object.values(counts), 1)) * 100 : 0}%`, background: colorForLabel[label] ?? fallbackColor }} /></div><strong>{counts[label] ?? 0}</strong></div>)}</div>
              <div className="map-section">
                <div className="map-heading"><div><MapPin size={16} /><span><strong>Mapa de hallazgos</strong><small>Sectores del camino que requieren revisión o mantenimiento.</small></span></div><span className="pill">{mission.images.filter((image) => image.latitude !== null).length} ubicaciones</span></div>
                <MapPanel mission={mission} selectedImageId={selectedImageId} onSelectImage={(image) => setSelectedImageId(image.id)} />
              </div>
              <div className="report-info"><MapPin size={17} /><span><strong>Ubicación aproximada por imagen</strong><small>FastAPI extrae automáticamente las coordenadas GPS de los metadatos EXIF cuando están disponibles.</small></span></div>
            </div>
          </article>
          <aside className="card export-card">
            <span className="export-icon"><FileText size={27} /></span>
            <span className="overline">Exportación</span>
            <h2>Informe listo</h2>
            <p>El PDF se genera en FastAPI con los datos actuales de la misión y el estado de revisión.</p>
            <div className="export-list"><span><Check size={14} /> Resumen consolidado</span><span><Check size={14} /> Conteo por clase</span><span><Check size={14} /> Detalle por imagen</span><span><Check size={14} /> Estado de cada hallazgo</span></div>
            <button className="button primary full large" onClick={downloadReport} disabled={busy !== null}>{busy === "report" ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />} Descargar PDF</button>
            <button className="button secondary full" onClick={() => setView("review")}><ArrowLeft size={15} /> Volver a revisión</button>
          </aside>
        </section>
      )}

      <footer><span>NeumaDiesel · Proyecto Capstone UCN</span><span><ShieldCheck size={13} /> Frontend y backend desacoplados</span></footer>
    </main>
  );
}
