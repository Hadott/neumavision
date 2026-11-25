import {
  BarChart3,
  CircuitBoard,
  Cpu,
  ExternalLink,
  HardDrive,
  MapPin,
  MemoryStick,
  Network,
  Power,
  PowerOff,
  Server,
  Timer,
  Check,
  ChevronDown,
  ChevronsUpDown,
  LoaderCircle,
  LogOut,
  Mountain,
  Plus,
  Route,
  Trash2,
  Users,
  X,
  ZoomIn,
  ZoomOut
} from "lucide-react";
import { FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { api, getSession, setSession, setUnauthorizedHandler } from "./api";
import AdminAccounts from "./AdminAccounts";
import logoIcon from "./assets/logo-icon-dark.png";
import DashboardStats from "./DashboardStats";
import DashboardMap, { criticalityColor, criticalityLabel, criticalityOf, type Criticality } from "./DashboardMap";
import Login from "./Login";
import MapPanel from "./MapPanel";
import type { Faena, DashboardFinding, Detection, DetectionProgress, Health, InferenceHealth, InferenceInstance, ManualCriticality, Mission, MissionImage, MissionSummary, RepairStatus, ReviewStatus, RoadWidth, Session } from "./types";
import { AnimatePresence, motion } from "framer-motion";
import { AnimatedNumber, SkeletonCards, SkeletonDashboard } from "./components/Animated";

const HISTORY_PATH = "/historial";
const NEW_MISSION_PATH = "/misiones/nueva";

function currentLocation() {
  return window.location.pathname.replace(/\/+$/, "") + window.location.search || "/";
}

function navigate(path: string, replace = false) {
  if (currentLocation() === path) return;
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
type View = "upload" | "review" | "report";
type Busy = "upload" | "detect" | "report" | null;
type DashReview = "pending" | "confirmed";

const inferenceStatusLabel: Record<InferenceHealth["status"], string> = {
  up: "Servicio encendido",
  down: "Servicio apagado",
  starting: "Encendiendo",
  waiting_capacity: "Esperando capacidad de AWS",
  stopping: "Apagando",
  unavailable: "Servicio sin respuesta",
  unknown: "Estado no disponible",
  disabled: "Inferencia remota desactivada",
};

const colorForLabel: Record<string, string> = {
  Rocas: "#dc2626",
  "Rocas fuera de pista": "#38bdf8",
  "Carpeta Buen Estado": "#2bb8a8",
  "Material Pedregoso": "#9e82ff"
};

const fallbackColor = "#4ca8ff";
const jadeTone = (status?: InferenceHealth["status"]) =>
  status === "up" ? "on"
    : status === "starting" || status === "waiting_capacity" || status === "stopping" ? "busy"
    : status === "unavailable" ? "error" : "off";
// Las rocas fuera de la pista no van al informe: se ocultan por defecto y solo se muestran como referencia.
const OFF_ROAD_LABEL = "Rocas fuera de pista";
const withoutOffRoad = (labels: string[]) => labels.filter((label) => label !== OFF_ROAD_LABEL);
type ImageView = "ambas" | "segmentacion" | "rocas";
const imageViewOptions: { value: ImageView; label: string }[] = [
  { value: "ambas", label: "Pista + rocas" },
  { value: "segmentacion", label: "Pista y ancho" },
  { value: "rocas", label: "Solo rocas" },
];

// Dentro de cada caja se muestra la foto original (sin la mascara azul del ancho de pista):
// se usa la misma imagen como fondo, escalada y desplazada para que calce con la caja.
const originalPatch = (item: Detection, image: MissionImage) => {
  if (!image.road_width_url) return {};
  const w = Math.max(item.width, 1e-4);
  const h = Math.max(item.height, 1e-4);
  const posX = w < 1 ? (item.x / (1 - w)) * 100 : 0;
  const posY = h < 1 ? (item.y / (1 - h)) * 100 : 0;
  return {
    backgroundImage: `url("${api.imageUrl(image.image_url)}")`,
    backgroundSize: `${100 / w}% ${100 / h}%`,
    backgroundPosition: `${posX}% ${posY}%`,
    backgroundRepeat: "no-repeat",
  };
};

// Semaforo del ancho de pista calculado por el modelo de segmentacion
const widthClass = (estado: string) => {
  const value = estado.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  if (value.startsWith("optimo")) return "optimo";
  if (value.startsWith("moderado")) return "moderado";
  if (value.startsWith("critico")) return "critico";
  return "sin";
};
const confidence = (value: number) => `${Math.round(value * 100)}%`;

function RoadWidthCard({ width }: { width: RoadWidth }) {
  // Umbrales de la tarjeta original para un Komatsu 830E de 7,3 m.
  const critical = 3 * 7.3;
  const optimal = 3.5 * 7.3;
  const minimum = width.ancho_min_m;
  const format = (value: number, decimals = 1) => value.toFixed(decimals).replace(".", ",");
  const marker = minimum == null ? null
    : minimum < critical ? 40 * minimum / critical
    : minimum < optimal ? 40 + 25 * (minimum - critical) / (optimal - critical)
    : Math.min(65 + 35 * (minimum - optimal) / (optimal * 0.4), 100);

  return (
    <section className="road-width-summary" aria-labelledby="road-width-title">
      <div className="road-width-summary-heading">
        <h2 id="road-width-title">Ancho de pista</h2>
        <span className={`width-badge ${widthClass(width.estado)}`}>{width.estado}</span>
      </div>
      <div className="road-width-measurement">
        <strong>{minimum == null ? "—" : `${format(minimum)} m`}</strong>
        <span>ancho mínimo del tramo</span>
      </div>
      <div className="road-width-scale" aria-label={`Umbrales de ancho: ${format(critical)} y ${format(optimal)} metros`}>
        {marker != null && <i aria-hidden="true" style={{ left: `${marker}%` }} />}
        <span>{format(critical)}</span>
        <span>{format(optimal)}</span>
      </div>
      <div className="road-width-details">
        <p>Mediano: {width.ancho_mediano_m == null ? "—" : `${format(width.ancho_mediano_m)} m`} · Eje medido: {format(width.eje_medible_pct, 0)} %</p>
        <p>GSD: {width.gsd_cm_px == null ? "desconocido" : `${format(width.gsd_cm_px, 2)} cm/px (${width.fuente_gsd})`} · Komatsu 830E</p>
      </div>
    </section>
  );
}

function LegacyRoadWidthPatch({ image }: { image: MissionImage }) {
  // La tarjeta antigua se dibujaba en la esquina inferior izquierda a escala
  // 0,72 × ancho / 1536. Restauramos esa zona con los píxeles de la foto original.
  const scale = (image.width / 1536) * 0.72;
  const padding = 4;
  const left = Math.max(0, 24 * scale - padding);
  const right = Math.max(0, image.width - 388 * scale - padding);
  const top = Math.max(0, image.height - 238 * scale - padding);
  const bottom = Math.max(0, 18 * scale - padding);
  return (
    <img
      className="legacy-road-width-patch"
      src={api.imageUrl(image.image_url)}
      alt=""
      style={{ clipPath: `inset(${top / image.height * 100}% ${right / image.width * 100}% ${bottom / image.height * 100}% ${left / image.width * 100}%)` }}
    />
  );
}

function ReviewImageZoom({ image, children }: { image: MissionImage; children: ReactNode }) {
  const [zoom, setZoom] = useState(100);
  const viewport = useRef<HTMLDivElement>(null);

  function changeZoom(next: number) {
    const element = viewport.current;
    if (!element) return;
    const centerX = (element.scrollLeft + element.clientWidth / 2) / element.scrollWidth;
    const centerY = (element.scrollTop + element.clientHeight / 2) / element.scrollHeight;
    setZoom(next);
    requestAnimationFrame(() => {
      element.scrollTo(
        centerX * element.scrollWidth - element.clientWidth / 2,
        centerY * element.scrollHeight - element.clientHeight / 2,
      );
    });
  }

  return (
    <>
      <div className="image-zoom-controls" role="group" aria-label="Zoom de la imagen">
        <button type="button" className="button ghost" aria-label="Alejar imagen" disabled={zoom === 100} onClick={() => changeZoom(zoom - 25)}><ZoomOut size={16} /></button>
        <button type="button" className="button ghost" aria-label={`Restablecer zoom al 100% (actual: ${zoom}%)`} onClick={() => changeZoom(100)}>{zoom}%</button>
        <button type="button" className="button ghost" aria-label="Acercar imagen" disabled={zoom === 300} onClick={() => changeZoom(zoom + 25)}><ZoomIn size={16} /></button>
      </div>
      <div
        className="image-zoom-viewport"
        ref={viewport}
        style={{ aspectRatio: `${image.width} / ${image.height}` }}
        tabIndex={zoom > 100 ? 0 : undefined}
        role="region"
        aria-label="Imagen de hallazgos"
      >
        <div className="image-stage" style={{ width: `${zoom}%` }}>{children}</div>
      </div>
    </>
  );
}

const filenameOrder = new Intl.Collator("es-CL", { numeric: true });
const formatDuration = (milliseconds: number) => {
  const seconds = Math.round(milliseconds / 1000);
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
};

function ProgressBar({ label, fraction }: { label: string; fraction?: number }) {
  const percent = fraction == null ? undefined : Math.floor(fraction * 100);
  return (
    <div className="task-progress-bar">
      <div className="task-progress-track" role="progressbar" aria-label={label}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        {percent != null && <div className="task-progress-fill" style={{ width: `${percent}%` }} />}
      </div>
      <span aria-hidden="true">{percent == null ? "—" : `${percent}%`}</span>
    </div>
  );
}
const statusLabel = (status: string) => (status === "review" ? "En revisión" : "Cargada");
const formatDate = (value: string) =>
  new Date(value).toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
const formatDateTime = (value: string) =>
  new Date(value).toLocaleString("es-CL", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

const ALL_CRITICALITY: Criticality[] = ["critico", "moderado", "optimo"];
const ALL_DASH_REVIEW: DashReview[] = ["pending", "confirmed"];
const ALL_DASH_REPAIR: RepairStatus[] = ["pending", "repaired"];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [inferenceHealth, setInferenceHealth] = useState<InferenceHealth | null>(null);
  const [startingInference, setStartingInference] = useState(false);
  const [stoppingInference, setStoppingInference] = useState(false);
  const [inferenceStartError, setInferenceStartError] = useState("");
  const [savingAutoShutdown, setSavingAutoShutdown] = useState(false);
  const [autoShutdownError, setAutoShutdownError] = useState("");
  const [idleMinutes, setIdleMinutes] = useState("");
  const [inferenceInstance, setInferenceInstance] = useState<InferenceInstance | null>(null);
  const [instanceError, setInstanceError] = useState("");
  const idleTimeout = inferenceHealth?.idle_timeout_seconds;
  const [location, setLocation] = useState(currentLocation);
  const [path, query = ""] = location.split("?", 2);
  const missionPath = path === NEW_MISSION_PATH ? null : /^\/misiones\/([a-zA-Z0-9_-]+)$/.exec(path)?.[1];
  const routeQuery = new URLSearchParams(query);
  const evidenceImageId = routeQuery.get("imagen");
  const evidenceDetectionId = routeQuery.get("deteccion");
  const newMission = path === NEW_MISSION_PATH;
  const [view, setView] = useState<View>("upload");
  const [loadedMission, setMission] = useState<Mission | null>(null);
  const [selectedImageId, setSelectedImageId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [missionName, setMissionName] = useState("");
  const [segment, setSegment] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [detectionStart, setDetectionStart] = useState<{ missionId: string; timestamp: number } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [uploadProgress, setUploadProgress] = useState<{ fraction: number; remaining: number | null } | null>(null);
  const [detectionProgress, setDetectionProgress] = useState<DetectionProgress | null>(null);
  const [detectionSummary, setDetectionSummary] = useState<{
    missionId: string;
    milliseconds: number;
    imageCount: number;
  } | null>(null);
  const [error, setError] = useState("");
  const [threshold, setThreshold] = useState(0.3);
  // Vista de la imagen en Revision; la misma opcion define la imagen de cada ficha del informe.
  const [imageView, setImageView] = useState<ImageView>("ambas");
  const [enabledLabels, setEnabledLabels] = useState<string[]>([]);
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const [missionsLoading, setMissionsLoading] = useState(false);
  const missionListRequest = useRef(0);
  const [historyFrom, setHistoryFrom] = useState("");
  const [historyTo, setHistoryTo] = useState("");
  const [historySegment, setHistorySegment] = useState("");
  const [historyName, setHistoryName] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [criticalityBusyId, setCriticalityBusyId] = useState("");
  const [reviewBusyId, setReviewBusyId] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const [dashFindings, setDashFindings] = useState<DashboardFinding[]>([]);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashSelectedId, setDashSelectedId] = useState("");
  const [dashCriticality, setDashCriticality] = useState<Criticality[]>(ALL_CRITICALITY);
  const [dashLabels, setDashLabels] = useState<string[]>([]);
  const [dashReview, setDashReview] = useState<DashReview[]>(ALL_DASH_REVIEW);
  const [dashRepair, setDashRepair] = useState<RepairStatus[]>(ALL_DASH_REPAIR);
  const [dashMission, setDashMission] = useState("");
  const [repairBusyId, setRepairBusyId] = useState("");
  const [dashTab, setDashTab] = useState<"mapa" | "estadisticas">("mapa");
  const [session, setSessionState] = useState<Session | null>(getSession());
  const [faenas, setFaenas] = useState<Faena[]>([]);
  const [faenaFiltro, setFaenaFiltro] = useState("");
  const [missionFaena, setMissionFaena] = useState("");
  const isAdmin = session?.cuenta.rol === "admin";
  const screen = path === "/dashboard" ? "dashboard"
    : path === "/cuentas" && isAdmin ? "accounts"
    : newMission || missionPath ? "workspace" : "history";
  const mission = loadedMission?.id === missionPath ? loadedMission : null;
  const visibleMissions = useMemo(() => {
    const from = historyFrom ? new Date(`${historyFrom}T00:00:00`) : null;
    const until = historyTo ? new Date(`${historyTo}T00:00:00`) : null;
    if (until) until.setDate(until.getDate() + 1);
    const tramo = historySegment.trim().toLocaleLowerCase("es-CL");
    const name = historyName.trim().toLocaleLowerCase("es-CL");
    return missions.filter((item) => {
      const createdAt = new Date(item.created_at);
      return (!isAdmin || !faenaFiltro || item.faena_id === faenaFiltro)
        && (!from || createdAt >= from)
        && (!until || createdAt < until)
        && (!tramo || item.segment.toLocaleLowerCase("es-CL").includes(tramo))
        && (!name || item.name.toLocaleLowerCase("es-CL").includes(name));
    });
  }, [missions, isAdmin, faenaFiltro, historyFrom, historyTo, historySegment, historyName]);

  useEffect(() => {
    if (screen !== "accounts") return;
    let active = true;
    setInferenceInstance(null);
    setInstanceError("");
    api.inferenceInstance().then((instance) => {
      if (active) setInferenceInstance(instance);
    }).catch((requestError) => {
      if (active) setInstanceError(requestError instanceof Error ? requestError.message : "No se pudo consultar la instancia.");
    });
    return () => { active = false; };
  }, [screen, session?.token]);

  useEffect(() => {
    const updateLocation = () => {
      setLocation(currentLocation());
      setError("");
    };
    window.addEventListener("popstate", updateLocation);
    return () => window.removeEventListener("popstate", updateLocation);
  }, []);

  useEffect(() => {
    if (session && screen === "history" && path !== HISTORY_PATH) navigate(HISTORY_PATH, true);
  }, [session, screen, path]);

  useEffect(() => {
    if (newMission) resetWorkspace();
  }, [newMission]);

  useEffect(() => {
    if (!session || !missionPath || loadedMission?.id === missionPath) return;
    let active = true;
    api.getMission(missionPath).then((loaded) => {
      if (!active) return;
      setSelectedImageId("");
      setEnabledLabels(withoutOffRoad(Array.from(new Set(loaded.images.flatMap((image) => image.detections.map((item) => item.label))))));
      setView(loaded.status === "review" ? "review" : "upload");
      setMission(loaded);
    }).catch((requestError) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "No fue posible abrir la misión.");
    });
    return () => { active = false; };
  }, [session, missionPath, loadedMission?.id]);

  useEffect(() => {
    if (evidenceImageId && mission?.images.some((image) => image.id === evidenceImageId)) {
      setSelectedImageId(evidenceImageId);
      setView("review");
    }
  }, [mission, evidenceImageId]);


  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!session) return;
    let active = true;
    let timer: number;
    async function pollInferenceHealth() {
      const next = await api.inferenceHealth().catch(() => null);
      if (!active) return;
      setInferenceHealth(next);
      timer = window.setTimeout(pollInferenceHealth, 5000);
    }
    void pollInferenceHealth();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [session]);

  useEffect(() => {
    setUnauthorizedHandler(() => logout("Tu sesión venció. Inicia sesión nuevamente."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!session) return;
    // Confirma que la sesión guardada sigue vigente y, si es administrador, carga las faenas.
    api.me().catch(() => undefined);
    if (session.cuenta.rol === "admin") {
      api.faenas().then(setFaenas).catch(() => setFaenas([]));
    }
  }, [session?.token]);

  useEffect(() => {
    if (!session) return;
    if (screen === "history") {
      refreshMissions();
    } else if (screen === "dashboard") {
      refreshDashboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, session?.token, faenaFiltro]);

  const orderedImages = useMemo(() => [...(mission?.images ?? [])].sort(
    (left, right) => filenameOrder.compare(left.filename, right.filename) || left.id.localeCompare(right.id)
  ), [mission]);

  useEffect(() => {
    if (!mission?.images.length) return;
    if (!selectedImageId || !mission.images.some((image) => image.id === selectedImageId)) {
      setSelectedImageId(orderedImages[0].id);
    }
    const labels = Array.from(new Set(mission.images.flatMap((image) => image.detections.map((item) => item.label))));
    if (labels.length) setEnabledLabels((current) => current.length ? current.filter((label) => labels.includes(label)) : withoutOffRoad(labels));
  }, [mission, orderedImages, selectedImageId]);

  useEffect(() => {
    if (!detectionStart) return;
    const interval = window.setInterval(() => setElapsed(performance.now() - detectionStart.timestamp), 250);
    let active = true;
    let timer: number;
    const missionId = detectionStart.missionId;
    async function pollProgress() {
      try {
        const next = await api.detectionProgress(missionId);
        if (active && next) setDetectionProgress(next);
      } catch {
        // El POST de detección sigue siendo la fuente del resultado o del error.
      }
      if (active) timer = window.setTimeout(pollProgress, 1000);
    }
    void pollProgress();
    return () => {
      active = false;
      window.clearInterval(interval);
      window.clearTimeout(timer);
    };
  }, [detectionStart]);

  const allDetections = useMemo(
    () => mission?.images.flatMap((image) => image.detections) ?? [],
    [mission]
  );
  const availableLabels = useMemo(
    () => Array.from(new Set(allDetections.map((item) => item.label))),
    [allDetections]
  );
  const selectedImage = orderedImages.find((image) => image.id === selectedImageId) ?? orderedImages[0] ?? null;
  const imageDetections = selectedImage?.detections ?? [];
  const visibleDetections = imageView === "segmentacion" ? [] : imageDetections.filter(
    (item) => item.confidence >= threshold && enabledLabels.includes(item.label) && item.review_status !== "rejected"
  );
  const filteredAll = allDetections.filter(
    (item) => item.confidence >= threshold && enabledLabels.includes(item.label) && item.review_status !== "rejected"
  );
  const imagePending = imageDetections.filter((item) => item.review_status === "pending").length;
  const imageConfirmed = imageDetections.filter((item) => item.review_status === "confirmed").length;
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

  const availableDashLabels = useMemo(
    () => Array.from(new Set(dashFindings.map((item) => item.label))),
    [dashFindings]
  );
  const dashMissionOptions = useMemo(() => {
    const seen = new Map<string, { id: string; name: string; segment: string }>();
    dashFindings.forEach((item) => {
      if (!seen.has(item.mission_id)) {
        seen.set(item.mission_id, { id: item.mission_id, name: item.mission_name, segment: item.mission_segment });
      }
    });
    return Array.from(seen.values());
  }, [dashFindings]);
  const dashStats = useMemo(() => {
    const critico = dashFindings.filter((item) => criticalityOf(item.confidence, item.label) === "critico").length;
    const moderado = dashFindings.filter((item) => criticalityOf(item.confidence, item.label) === "moderado").length;
    const optimo = dashFindings.filter((item) => criticalityOf(item.confidence, item.label) === "optimo").length;
    const repaired = dashFindings.filter((item) => item.repair_status === "repaired").length;
    return { total: dashFindings.length, critico, moderado, optimo, repaired };
  }, [dashFindings]);
  const dashVisible = useMemo(() => dashFindings.filter((item) => {
    if (!dashCriticality.includes(criticalityOf(item.confidence, item.label))) return false;
    if (!dashLabels.includes(item.label)) return false;
    if (!dashReview.includes(item.review_status as DashReview)) return false;
    if (!dashRepair.includes(item.repair_status)) return false;
    if (dashMission && item.mission_id !== dashMission) return false;
    return true;
  }), [dashFindings, dashCriticality, dashLabels, dashReview, dashRepair, dashMission]);
  const dashVisibleCritico = dashVisible.filter((item) => criticalityOf(item.confidence, item.label) === "critico").length;
  const dashVisibleModerado = dashVisible.filter((item) => criticalityOf(item.confidence, item.label) === "moderado").length;
  const dashVisibleOptimo = dashVisible.filter((item) => criticalityOf(item.confidence, item.label) === "optimo").length;
  const dashVisibleRepaired = dashVisible.filter((item) => item.repair_status === "repaired").length;
  const dashLabelCounts = useMemo(() => availableDashLabels.reduce<Record<string, number>>((result, label) => {
    result[label] = dashVisible.filter((item) => item.label === label).length;
    return result;
  }, {}), [availableDashLabels, dashVisible]);
  const dashReviewCounts = {
    confirmed: dashVisible.filter((item) => item.review_status === "confirmed").length,
    pending: dashVisible.filter((item) => item.review_status === "pending").length
  };
  const dashRepairCounts = {
    pending: dashVisible.filter((item) => item.repair_status === "pending").length,
    repaired: dashVisibleRepaired
  };
  const selectedFinding = dashFindings.find((item) => item.id === dashSelectedId) ?? null;
  const selectedCriticality = selectedFinding ? criticalityOf(selectedFinding.confidence, selectedFinding.label) : null;

  async function refreshMissions() {
    const request = ++missionListRequest.current;
    setMissionsLoading(true);
    try {
      const list = await api.listMissions(isAdmin ? faenaFiltro || undefined : undefined);
      if (request === missionListRequest.current) setMissions(list);
    } catch (requestError) {
      if (request === missionListRequest.current) {
        setMissions([]);
        setError(requestError instanceof Error ? requestError.message : "No fue posible cargar el historial de misiones.");
      }
    } finally {
      if (request === missionListRequest.current) setMissionsLoading(false);
    }
  }

  async function refreshDashboard() {
    setDashLoading(true);
    try {
      const list = await api.dashboardFindings(isAdmin ? faenaFiltro || undefined : undefined);
      setDashFindings(list);
      const labels = Array.from(new Set(list.map((item) => item.label)));
      setDashLabels((current) => current.length ? current.filter((label) => labels.includes(label)) : labels);
      setDashSelectedId((current) => current && list.some((item) => item.id === current) ? current : (list[0]?.id ?? ""));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible cargar el dashboard.");
    } finally {
      setDashLoading(false);
    }
  }

  async function handleDeleteMission(missionId: string, missionName: string) {
    const confirmed = window.confirm(`¿Eliminar la misión "${missionName}"? Esta acción no se puede deshacer.`);
    if (!confirmed) return;
    setDeletingId(missionId);
    try {
      await api.deleteMission(missionId);
      setMissions((current) => current.filter((item) => item.id !== missionId));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible eliminar la misión.");
    } finally {
      setDeletingId("");
    }
  }

  async function startInference() {
    setStartingInference(true);
    setInferenceStartError("");
    try {
      await api.startInference();
      setInferenceHealth(await api.inferenceHealth());
    } catch (requestError) {
      setInferenceStartError(requestError instanceof Error ? requestError.message : "No se pudo solicitar el encendido.");
    } finally {
      setStartingInference(false);
    }
  }

  async function stopInference() {
    const confirmed = window.confirm("¿Apagar Jade ahora? Los análisis nuevos tendrán que volver a encenderlo, lo que tarda unos minutos.");
    if (!confirmed) return;
    setStoppingInference(true);
    setInferenceStartError("");
    try {
      await api.stopInference();
      setInferenceHealth(await api.inferenceHealth());
    } catch (requestError) {
      setInferenceStartError(requestError instanceof Error ? requestError.message : "No se pudo apagar Jade.");
    } finally {
      setStoppingInference(false);
    }
  }

  async function changeAutoShutdown(enabled: boolean, idleTimeoutSeconds?: number) {
    setSavingAutoShutdown(true);
    setAutoShutdownError("");
    try {
      const result = await api.setInferenceAutoShutdown(enabled, idleTimeoutSeconds);
      setInferenceHealth((current) => current && { ...current, ...result });
      if (enabled) setIdleMinutes("");
    } catch (requestError) {
      setAutoShutdownError(requestError instanceof Error ? requestError.message : "No se pudo cambiar el apagado automático.");
    } finally {
      setSavingAutoShutdown(false);
    }
  }

  function goToHistory() {
    navigate(HISTORY_PATH);
    setError("");
  }

  function handleLogin(next: Session) {
    setSession(next);
    setSessionState(next);
    setError("");
  }

  function logout(message = "") {
    missionListRequest.current += 1;
    setSession(null);
    setSessionState(null);
    setInferenceHealth(null);
    setInferenceStartError("");
    setIdleMinutes("");
    setAutoShutdownError("");
    clearHistoryFilters();
    setFaenas([]);
    setFaenaFiltro("");
    setMissionFaena("");
    setMissions([]);
    setDashFindings([]);
    setMission(null);
    if (!message) navigate(HISTORY_PATH, true);
    setError(message);
  }

  function changeFaenaFiltro(value: string) {
    setFaenaFiltro(value);
    setMissionFaena(value);
  }

  function openDashboard() {
    navigate("/dashboard");
    setError("");
  }

  function viewAccountMissions(account: Faena) {
    clearHistoryFilters();
    setFaenaFiltro(account.id);
    navigate(HISTORY_PATH);
    setError("");
  }

  function clearHistoryFilters() {
    setHistoryFrom("");
    setHistoryTo("");
    setHistorySegment("");
    setHistoryName("");
  }

  function startNewMission() {
    navigate(NEW_MISSION_PATH);
  }

  function openMission(id: string) {
    navigate(`/misiones/${encodeURIComponent(id)}`);
  }

  function acceptFiles(incoming: FileList | File[]) {
    const valid = Array.from(incoming).filter((file) => file.type.startsWith("image/"));
    setFiles((current) => [...current, ...valid]);
    setError("");
  }

  async function createMission(event: FormEvent) {
    event.preventDefault();
    if (!files.length) {
      setError("Selecciona al menos una imagen RGB.");
      return;
    }
    if (isAdmin && !missionFaena) {
      setError("Selecciona la faena a la que pertenece la misión.");
      return;
    }
    setBusy("upload");
    setError("");
    const startedAt = performance.now();
    setUploadProgress(null);
    try {
      const created = await api.createMission(missionName, segment, files, isAdmin ? missionFaena : undefined, (loaded, total) => {
        const fraction = loaded / total;
        const elapsedSeconds = (performance.now() - startedAt) / 1000;
        setUploadProgress({
          fraction,
          remaining: fraction > 0 && fraction < 1 ? elapsedSeconds / fraction * (1 - fraction) : null,
        });
      });
      if (window.location.pathname === NEW_MISSION_PATH) {
        setMission(created);
        navigate(`/misiones/${encodeURIComponent(created.id)}`, true);
      }
      setSelectedImageId("");
      setFiles([]);
      void refreshMissions();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible cargar la misión.");
    } finally {
      setUploadProgress(null);
      setBusy(null);
    }
  }

  async function runDetection() {
    if (!mission) return;
    const startedAt = performance.now();
    setBusy("detect");
    setError("");
    setElapsed(0);
    setDetectionSummary(null);
    setDetectionProgress(null);
    setDetectionStart({ missionId: mission.id, timestamp: startedAt });
    try {
      const processed = await api.detect(mission.id);
      setDetectionSummary({
        missionId: processed.id,
        milliseconds: performance.now() - startedAt,
        imageCount: processed.images.length,
      });
      setMission((current) => current?.id === processed.id ? processed : current);
      if (window.location.pathname === `/misiones/${encodeURIComponent(processed.id)}`) {
        setEnabledLabels(withoutOffRoad(Array.from(new Set(processed.images.flatMap((image) => image.detections.map((item) => item.label))))));
        setView("review");
      }
      void refreshMissions();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "La detección no pudo completarse.");
    } finally {
      setDetectionStart(null);
      setBusy(null);
    }
  }

  async function toggleRepairStatus(finding: DashboardFinding) {
    const next: RepairStatus = finding.repair_status === "repaired" ? "pending" : "repaired";
    setRepairBusyId(finding.id);
    try {
      const updated = await api.updateRepairStatus(finding.mission_id, finding.id, next);
      setDashFindings((current) => current.map((item) => item.id === finding.id ? { ...item, repair_status: updated.repair_status } : item));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible actualizar el estado de reparación.");
    } finally {
      setRepairBusyId("");
    }
  }

  function toggleDashCriticality(value: Criticality) {
    setDashCriticality((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  function toggleDashLabel(label: string) {
    setDashLabels((current) => current.includes(label) ? current.filter((item) => item !== label) : [...current, label]);
  }

  function toggleDashReview(value: DashReview) {
    setDashReview((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  function toggleDashRepair(value: RepairStatus) {
    setDashRepair((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  function goToFindingMission(finding: DashboardFinding) {
    const query = new URLSearchParams({ imagen: finding.image_id, deteccion: finding.id });
    navigate(`/misiones/${encodeURIComponent(finding.mission_id)}?${query}`);
  }

  async function downloadReport() {
    if (!mission) return;
    setBusy("report");
    setError("");
    try {
      await api.downloadReport(mission.id, imageView);
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
    if (!selectedImage) return;
    const currentIndex = orderedImages.findIndex((image) => image.id === selectedImage.id);
    const nextIndex = (currentIndex + direction + orderedImages.length) % orderedImages.length;
    setSelectedImageId(orderedImages[nextIndex].id);
  }

  async function setImageCriticality(image: MissionImage, level: ManualCriticality) {
    if (!mission) return;
    const next: ManualCriticality | null = image.criticidad_manual === level ? null : level;
    setCriticalityBusyId(image.id);
    try {
      const updated = await api.updateImageCriticality(mission.id, image.id, next);
      setMission((current) => current && ({
        ...current,
        // La criticidad también puede confirmar hallazgos pendientes.
        images: current.images.map((item) => item.id === image.id ? updated : item)
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible guardar la criticidad de la imagen.");
    } finally {
      setCriticalityBusyId("");
    }
  }

  async function reviewFinding(detection: Detection, status: ReviewStatus) {
    if (!mission) return;
    const next: ReviewStatus = detection.review_status === status ? "pending" : status;
    setReviewBusyId(detection.id);
    try {
      const updated = await api.reviewDetection(mission.id, detection.id, next);
      setMission((current) => current && ({
        ...current,
        images: current.images.map((image) => ({
          ...image,
          detections: image.detections.map((item) => item.id === detection.id ? { ...item, ...updated } : item)
        }))
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible guardar la revisión de la roca.");
    } finally {
      setReviewBusyId("");
    }
  }

  function resetWorkspace() {
    setMission(null);
    setSelectedImageId("");
    setEnabledLabels([]);
    setView("upload");
    setError("");
  }

  if (!session) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app-frame">
      <nav className="sidebar" aria-label="Principal">
        <button type="button" className="brand brand-button" onClick={goToHistory} aria-label="NeumaVision, ir a misiones">
          <span className="brand-icon"><img src={logoIcon} alt="" /></span>
          <span><strong>NeumaVision</strong><small>NeumaDiesel</small></span>
        </button>
        {isAdmin && (
          <label className="sidebar-field">
            <span>Faena</span>
            <span className={`faena-picker${faenaFiltro ? " selected" : ""}`}>
              <Mountain size={17} aria-hidden="true" />
              <select value={faenaFiltro} onChange={(event) => changeFaenaFiltro(event.target.value)}>
                <option value="">Todas las faenas</option>
                {faenas.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}
              </select>
              <ChevronsUpDown size={15} aria-hidden="true" />
            </span>
          </label>
        )}
        <div className="sidebar-links">
          <button type="button" className={screen === "history" || (screen === "workspace" && !newMission) ? "active" : ""}
            aria-current={screen === "history" ? "page" : undefined} onClick={goToHistory}><Route size={18} />Misiones</button>
          <button type="button" className={screen === "dashboard" ? "active" : ""}
            aria-current={screen === "dashboard" ? "page" : undefined} onClick={openDashboard}><BarChart3 size={18} />Dashboard</button>
          {isAdmin && <button type="button" className={screen === "accounts" ? "active" : ""}
            aria-current={screen === "accounts" ? "page" : undefined} onClick={() => navigate("/cuentas")}><Users size={18} />Administración</button>}
        </div>
        <button type="button" className={`button primary sidebar-new${newMission ? " current" : ""}`} onClick={startNewMission}><Plus size={16} />Nueva misión</button>

        <div className="sidebar-status" role="status">
          <strong><span className={`inference-indicator ${inferenceHealth?.status ?? "unknown"}`} aria-hidden="true" />
            {inferenceStatusLabel[inferenceHealth?.status ?? "unknown"]}
          </strong>
          {inferenceHealth?.idle_timeout_seconds != null && (
            <small>
              {inferenceHealth.status === "waiting_capacity"
                ? "AWS no tiene capacidad para Jade. Se reintenta cada 10 segundos."
                : inferenceHealth.status === "starting"
                ? "Cargando los modelos. Puede tardar unos minutos."
                : inferenceHealth.idle_timeout_seconds === 0
                  ? "Apagado automático desactivado."
                  : `Apagado automático tras ${inferenceHealth.idle_timeout_seconds / 60} min.`}
            </small>
          )}
          {isAdmin && screen !== "accounts" && inferenceHealth?.idle_timeout_seconds != null &&
            (inferenceHealth.status === "down" || inferenceHealth.status === "unavailable") && (
            <button type="button" className="button secondary" disabled={startingInference} onClick={startInference}>
              {startingInference ? "Solicitando encendido…" : "Encender Jade"}
            </button>
          )}
          {(inferenceStartError || inferenceHealth?.start_error) && (
            <small>{inferenceStartError || inferenceHealth?.start_error}</small>
          )}
        </div>

        <div className="sidebar-account" title={session.cuenta.correo}>
          <i>{session.cuenta.nombre.split(/\s+/).map((word) => word[0]).join("").slice(0, 2).toUpperCase()}</i>
          <span><strong>{session.cuenta.nombre}</strong><small>{isAdmin ? "Administrador" : session.cuenta.correo}</small></span>
          <button type="button" aria-label="Cerrar sesión" title="Cerrar sesión" onClick={() => logout()}><LogOut size={17} /></button>
        </div>
      </nav>

    <main className="shell">
      <AnimatePresence mode="wait">
      {screen === "accounts" && isAdmin && (
        <motion.div key="accounts" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
              <h1>Administración</h1>
            </div>
          </section>
          <section className="workspace" aria-labelledby="inference-settings-title">
            <div className="card jade-card">
              <header className="jade-header">
                <span className="jade-icon" aria-hidden="true"><Server size={22} /></span>
                <div>
                  <h2 id="inference-settings-title">Jade</h2>
                </div>
                <span className={`jade-status ${jadeTone(inferenceHealth?.status)}`} role="status">
                  <i aria-hidden="true" />{inferenceStatusLabel[inferenceHealth?.status ?? "unknown"]}
                </span>
                {idleTimeout != null && (inferenceHealth?.status === "down" || inferenceHealth?.status === "unavailable") && (
                  <button type="button" className="button primary" disabled={startingInference} onClick={startInference}>
                    {startingInference ? <LoaderCircle className="spin" size={16} /> : <Power size={16} />}
                    {startingInference ? "Solicitando encendido…" : "Encender Jade"}
                  </button>
                )}
                {idleTimeout != null && inferenceHealth?.status === "up" && (
                  <button type="button" className="button danger" disabled={stoppingInference} onClick={stopInference}>
                    {stoppingInference ? <LoaderCircle className="spin" size={16} /> : <PowerOff size={16} />}
                    {stoppingInference ? "Apagando…" : "Apagar Jade"}
                  </button>
                )}
              </header>
              {inferenceStartError && <p className="jade-message error" role="alert">{inferenceStartError}</p>}

              {instanceError ? <p className="jade-message" role="alert">{instanceError}</p> : inferenceInstance ? (
                <dl className="jade-specs">
                  <div><dt><Server size={15} aria-hidden="true" />Instancia</dt><dd>{inferenceInstance.instance_type}</dd></div>
                  {inferenceInstance.specifications_available && <>
                    <div className="jade-spec-gpu"><dt><CircuitBoard size={15} aria-hidden="true" />GPU</dt><dd>{inferenceInstance.gpus.map((gpu) => `${gpu.count > 1 ? `${gpu.count} × ` : ""}${gpu.name}`).join(", ") || "Sin GPU"}<small>{inferenceInstance.gpus.map((gpu) => `${gpu.memory_mib / 1024} GiB de memoria`).join(", ")}</small></dd></div>
                    <div><dt><Cpu size={15} aria-hidden="true" />vCPU</dt><dd>{inferenceInstance.vcpus ?? "—"}</dd></div>
                    <div><dt><MemoryStick size={15} aria-hidden="true" />RAM</dt><dd>{inferenceInstance.memory_mib == null ? "—" : `${inferenceInstance.memory_mib / 1024} GiB`}</dd></div>
                    {inferenceInstance.local_storage_gb != null && (
                      <div><dt><HardDrive size={15} aria-hidden="true" />Disco</dt><dd>{inferenceInstance.local_storage_gb} GB</dd></div>
                    )}
                    <div><dt><Network size={15} aria-hidden="true" />Red</dt><dd>{inferenceInstance.network_performance ?? "—"}</dd></div>
                  </>}
                  <div><dt><MapPin size={15} aria-hidden="true" />Región</dt><dd>{inferenceInstance.region}<small>Zona {inferenceInstance.availability_zone}</small></dd></div>
                </dl>
              ) : <p className="jade-message" role="status"><LoaderCircle className="spin" size={15} /> Consultando la instancia en AWS…</p>}
              {inferenceInstance?.specifications_available === false && <p className="jade-message" role="status">AWS no devolvió las especificaciones del tipo de instancia.</p>}
              {inferenceInstance?.specifications_url && (
                <a className="jade-link" href={inferenceInstance.specifications_url} target="_blank" rel="noreferrer">
                  Ficha técnica en AWS <ExternalLink size={14} aria-hidden="true" />
                </a>
              )}

              <form className="jade-shutdown" onSubmit={(event) => {
                event.preventDefault();
                void changeAutoShutdown(true, idleMinutes ? Number(idleMinutes) * 60 : undefined);
              }}>
                <span className="jade-shutdown-icon" aria-hidden="true"><Timer size={20} /></span>
                <div className="jade-shutdown-text">
                  <h3>
                    Apagado automático
                    {idleTimeout != null && <span className={`jade-pill ${idleTimeout > 0 ? "on" : "off"}`}>{idleTimeout > 0 ? "Activado" : "Desactivado"}</span>}
                  </h3>
                  {idleTimeout == null && <p role="status">Control no disponible.</p>}
                </div>
                {idleTimeout != null && (
                  <div className="jade-shutdown-controls">
                    <label className="jade-minutes">
                      <span className="sr-only">Minutos de inactividad</span>
                      <input type="number" min="1" max="1440" step="1" inputMode="numeric" value={idleMinutes}
                        placeholder={idleTimeout > 0 ? String(idleTimeout / 60) : "20"}
                        required={idleTimeout > 0} disabled={savingAutoShutdown}
                        onChange={(event) => setIdleMinutes(event.target.value)} />
                      <span aria-hidden="true">min</span>
                    </label>
                    <button type="submit" className="button primary" disabled={savingAutoShutdown}>
                      {savingAutoShutdown ? "Guardando…" : idleTimeout > 0 ? "Guardar" : "Activar"}
                    </button>
                    {idleTimeout > 0 && (
                      <button type="button" className="button secondary" disabled={savingAutoShutdown}
                        onClick={() => void changeAutoShutdown(false)}>Desactivar</button>
                    )}
                  </div>
                )}
              </form>
              {autoShutdownError && <p className="jade-message error" role="alert">{autoShutdownError}</p>}
            </div>
          </section>
          <AdminAccounts onViewMissions={viewAccountMissions} faenas={faenas} setFaenas={setFaenas} />
        </motion.div>
      )}
      {screen === "history" && (
        <motion.div key="history" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
              <h1>Misiones</h1>
            </div>
          </section>

          {error && <div className="error-banner"><span>{error}</span><button aria-label="Cerrar aviso" onClick={() => setError("")}><X size={15} /></button></div>}

          <section className="workspace history-layout">
            <div className="history-toolbar">
              <div><h2>{visibleMissions.length} {visibleMissions.length === 1 ? "misión" : "misiones"}</h2></div>
              <div className="history-toolbar-actions">
                <button className="button ghost" onClick={refreshMissions} disabled={missionsLoading}>
                  {missionsLoading ? <LoaderCircle className="spin" size={15} /> : null} Actualizar
                </button>
              </div>
            </div>
            <div className="filter-controls" role="group" aria-label="Filtros del historial de misiones">
              <label>Nombre de misión
                <input type="search" value={historyName} onChange={(event) => setHistoryName(event.target.value)} />
              </label>
              <label>Fecha de creación desde
                <input type="date" value={historyFrom} max={historyTo || undefined} onChange={(event) => setHistoryFrom(event.target.value)} />
              </label>
              <label>Hasta
                <input type="date" value={historyTo} min={historyFrom || undefined} onChange={(event) => setHistoryTo(event.target.value)} />
              </label>
              <label>Tramo
                <input type="search" value={historySegment} onChange={(event) => setHistorySegment(event.target.value)} />
              </label>
              <button type="button" className="button ghost" onClick={() => {
                clearHistoryFilters();
                if (isAdmin) changeFaenaFiltro("");
              }}>Limpiar filtros</button>
            </div>

            {missionsLoading && !visibleMissions.length ? (
              <SkeletonCards count={6} />
            ) : visibleMissions.length ? (
              <div className="card history-table-card">
                <table className="history-table">
                  <thead>
                    <tr>
                      <th scope="col">Misión</th>
                      {isAdmin && <th scope="col">Faena</th>}
                      <th scope="col">Fecha</th>
                      <th scope="col">Imágenes</th>
                      <th scope="col">Hallazgos</th>
                      <th scope="col">Confirmados</th>
                      <th scope="col">Criticidad</th>
                      <th scope="col">Estado</th>
                      <th scope="col"><span className="sr-only">Acciones</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleMissions.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <button type="button" className="history-name" onClick={() => openMission(item.id)}>{item.name}</button>
                          <small>{item.segment}</small>
                        </td>
                        {isAdmin && <td>{item.faena_name ?? "—"}</td>}
                        <td>{formatDate(item.created_at)}</td>
                        <td>{item.image_count}</td>
                        <td>{item.detection_count}</td>
                        <td>{item.confirmed_count}</td>
                        <td>
                          {(item.criticidad_critico_count + item.criticidad_moderado_count + item.criticidad_optimo_count) > 0 ? (
                            <div className="history-card-semaphore">
                              {item.criticidad_critico_count > 0 && <span className="mini-crit-chip critico" title="Imágenes críticas"><i />{item.criticidad_critico_count}</span>}
                              {item.criticidad_moderado_count > 0 && <span className="mini-crit-chip moderado" title="Imágenes moderadas"><i />{item.criticidad_moderado_count}</span>}
                              {item.criticidad_optimo_count > 0 && <span className="mini-crit-chip optimo" title="Imágenes óptimas"><i />{item.criticidad_optimo_count}</span>}
                            </div>
                          ) : <span className="muted">Sin clasificar</span>}
                        </td>
                        <td><span className={`status-badge ${item.status}`}>{statusLabel(item.status)}</span></td>
                        <td className="history-actions">
                          <button type="button" className="button secondary" onClick={() => openMission(item.id)}>Abrir</button>
                          <button
                            type="button"
                            className="history-delete"
                            aria-label={`Eliminar misión ${item.name}`}
                            title="Eliminar misión"
                            disabled={deletingId === item.id}
                            onClick={() => handleDeleteMission(item.id, item.name)}
                          >
                            {deletingId === item.id ? <LoaderCircle className="spin" size={14} /> : <Trash2 size={14} />}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (faenaFiltro || historyFrom || historyTo || historySegment.trim() || historyName.trim()) ? (
              <div className="card history-empty"><strong>No hay misiones que coincidan con los filtros.</strong></div>
            ) : (
              <div className="card history-empty">
                <strong>Todavía no hay misiones</strong>
                <span>Crea una misión nueva cargando imágenes de inspección.</span>
                <button className="button primary" onClick={startNewMission}>Nueva misión</button>
              </div>
            )}
          </section>
        </motion.div>
      )}

      {screen === "dashboard" && (
        <motion.div key="dashboard" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
              <h1>Dashboard</h1>
            </div>
          </section>

          {error && <div className="error-banner"><span>{error}</span><button aria-label="Cerrar aviso" onClick={() => setError("")}><X size={15} /></button></div>}

          <nav className="steps">
            <button className={dashTab === "mapa" ? "active" : ""} onClick={() => setDashTab("mapa")}> Mapa</button>
            <button className={dashTab === "estadisticas" ? "active" : ""} onClick={() => setDashTab("estadisticas")}> Estadísticas</button>
          </nav>

          {dashLoading && !dashFindings.length ? (
            <section className="workspace dash-wide"><SkeletonDashboard /></section>
          ) : !dashFindings.length ? (
            <section className="workspace"><div className="card history-empty">
              <strong>Todavía no hay hallazgos</strong>
              <span>Procesa una misión para ver sus hallazgos en el dashboard operacional.</span>
              <button className="button primary" onClick={startNewMission}>Nueva misión</button>
            </div></section>
          ) : dashTab === "estadisticas" ? (
            <section className="workspace dash-wide" style={{ paddingBottom: 24 }}>
              <DashboardStats findings={dashFindings} />
            </section>
          ) : (
            <section className="workspace dash-wide" style={{ paddingBottom: 24 }}>
              <div className="card" style={{ padding: "18px 19px 17px" }}>
                <div className="kpi-strip-head">
                  <h3>Resumen operacional</h3>
                  <small>Todas las misiones</small>
                </div>
                <div className="kpi-row">
                  <div className="card kpi-card">
                    <span><strong><AnimatedNumber value={dashStats.total} /></strong><span>Hallazgos activos</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span><strong style={{ color: "#c0392b" }}><AnimatedNumber value={dashStats.critico} /></strong><span>Críticos</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span><strong style={{ color: "#a16207" }}><AnimatedNumber value={dashStats.moderado} /></strong><span>Moderados</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span><strong style={{ color: "#167d72" }}><AnimatedNumber value={dashStats.optimo} /></strong><span>Óptimos / leves</span></span>
                  </div>
                </div>
                <div className="repair-progress">
                  <div className="repair-progress-head">
                    <span>Avance de reparación</span>
                    <strong><AnimatedNumber value={dashStats.repaired} /> de <AnimatedNumber value={dashStats.total} /> reparados · {dashStats.total ? Math.round((dashStats.repaired / dashStats.total) * 100) : 0}%</strong>
                  </div>
                  <div className="repair-bar"><span style={{ width: `${dashStats.total ? (dashStats.repaired / dashStats.total) * 100 : 0}%` }} /></div>
                </div>
              </div>

              <div className="dash-grid">
                <aside className="card filters-card">
                  <div className="card-title compact">
                    <div><span className="overline">Filtros</span><h2>Hallazgos</h2></div>
                  </div>

                  <div className="filter-group">
                    <span className="filter-group-label">Criticidad</span>
                    <div className="filter-list">
                      {ALL_CRITICALITY.map((value) => (
                        <button key={value} className={dashCriticality.includes(value) ? "enabled" : ""} onClick={() => toggleDashCriticality(value)}>
                          <i style={{ background: criticalityColor[value] }} />
                          <span>{criticalityLabel[value]}</span>
                          <strong><AnimatedNumber value={value === "critico" ? dashVisibleCritico : value === "moderado" ? dashVisibleModerado : dashVisibleOptimo} /></strong>
                          <em>{dashCriticality.includes(value) && <Check size={11} />}</em>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="filter-group">
                    <span className="filter-group-label">Tipo de hallazgo</span>
                    <div className="filter-list">
                      {availableDashLabels.map((label) => (
                        <button key={label} className={dashLabels.includes(label) ? "enabled" : ""} onClick={() => toggleDashLabel(label)}>
                          <i style={{ background: colorForLabel[label] ?? fallbackColor }} />
                          <span>{label}</span>
                          <strong>{dashLabelCounts[label] ?? 0}</strong>
                          <em>{dashLabels.includes(label) && <Check size={11} />}</em>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="filter-group">
                    <span className="filter-group-label">Estado</span>
                    <div className="filter-list">
                      <button className={dashReview.includes("confirmed") ? "enabled" : ""} onClick={() => toggleDashReview("confirmed")}>
                        <i style={{ background: "#c9d0d3" }} /><span>Confirmado</span><strong>{dashReviewCounts.confirmed}</strong>
                        <em>{dashReview.includes("confirmed") && <Check size={11} />}</em>
                      </button>
                      <button className={dashReview.includes("pending") ? "enabled" : ""} onClick={() => toggleDashReview("pending")}>
                        <i style={{ background: "#c9d0d3" }} /><span>Pendiente</span><strong>{dashReviewCounts.pending}</strong>
                        <em>{dashReview.includes("pending") && <Check size={11} />}</em>
                      </button>
                    </div>
                  </div>

                  <div className="filter-group">
                    <span className="filter-group-label">Reparación</span>
                    <div className="filter-list">
                      <button className={dashRepair.includes("pending") ? "enabled" : ""} onClick={() => toggleDashRepair("pending")}>
                        <i style={{ background: "#a16207" }} /><span>Pendiente de reparación</span><strong>{dashRepairCounts.pending}</strong>
                        <em>{dashRepair.includes("pending") && <Check size={11} />}</em>
                      </button>
                      <button className={dashRepair.includes("repaired") ? "enabled" : ""} onClick={() => toggleDashRepair("repaired")}>
                        <i style={{ background: "#167d72" }} /><span>Reparado</span><strong>{dashRepairCounts.repaired}</strong>
                        <em>{dashRepair.includes("repaired") && <Check size={11} />}</em>
                      </button>
                    </div>
                  </div>

                  <div className="field-mini">
                    <label>
                      <span>Misión / tramo</span>
                      <span className="select-wrap">
                        <select value={dashMission} onChange={(event) => setDashMission(event.target.value)}>
                          <option value="">Todas las misiones</option>
                          {dashMissionOptions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.segment}</option>)}
                        </select>
                        <ChevronDown size={12} />
                      </span>
                    </label>
                  </div>

                  <div className="stats-mini">
                    <div><span>Visibles</span><strong><AnimatedNumber value={dashVisible.length} /></strong></div>
                    <div><span>Misiones</span><strong><AnimatedNumber value={dashMissionOptions.length} /></strong></div>
                  </div>
                </aside>

                <div className="card dash-map-card">
                  <div className="dash-map-heading">
                    <div>
                      <span><strong>Mapa de hallazgos</strong></span>
                    </div>
                    <span className="pill">{dashVisible.length} en vista</span>
                  </div>
                  <div className="legend-row">
                    <span className="legend-chip" style={{ background: "#fff1ef", color: "#8f3f31" }}><i style={{ background: "#c0392b" }} />Crítico · <AnimatedNumber value={dashVisibleCritico} /></span>
                    <span className="legend-chip" style={{ background: "#fef3c7", color: "#a16207" }}><i style={{ background: "#a16207" }} />Moderado · <AnimatedNumber value={dashVisibleModerado} /></span>
                    <span className="legend-chip" style={{ background: "#e2f6f2", color: "#167d72" }}><i style={{ background: "#167d72" }} />Óptimo · <AnimatedNumber value={dashVisibleOptimo} /></span>
                    <span className="legend-chip" style={{ background: "#eef2f3", color: "#4c5962" }}>Reparado · <AnimatedNumber value={dashVisibleRepaired} /></span>
                  </div>
                  <DashboardMap findings={dashVisible} selectedId={dashSelectedId} onSelect={(finding) => setDashSelectedId(finding.id)} />
                </div>

                <aside className="card detail-card">
                  {selectedFinding && selectedCriticality ? (
                    <>
                      <div className="card-title compact">
                        <div><span className="overline">Punto seleccionado</span><h2>Detalle</h2></div>
                        <span className="crit-tag" style={{ background: `${criticalityColor[selectedCriticality]}1a`, color: criticalityColor[selectedCriticality] }}><i />{criticalityLabel[selectedCriticality]}</span>
                      </div>

                      <div className="detail-thumb">
                        <img src={api.imageUrl(selectedFinding.image_url)} alt={selectedFinding.label} />
                        <span className="label-tag">{selectedFinding.label} · {confidence(selectedFinding.confidence)}</span>
                      </div>

                      <div className="detail-body">
                        <h3>{selectedFinding.mission_name}</h3>
                        <p className="seg">{selectedFinding.mission_segment}</p>

                        <div className="status-pills">
                          <span className="status-pill" style={{ background: selectedFinding.review_status === "confirmed" ? "#e2f6f2" : "#fef3c7", color: selectedFinding.review_status === "confirmed" ? "#167d72" : "#a16207" }}>
                            {selectedFinding.review_status === "confirmed" ? "Confirmado" : "Pendiente de revisión"}
                          </span>
                          <span className="status-pill" style={{ background: selectedFinding.repair_status === "repaired" ? "#e2f6f2" : "#fef3c7", color: selectedFinding.repair_status === "repaired" ? "#167d72" : "#a16207" }}>
                            {selectedFinding.repair_status === "repaired" ? "Reparado" : "Pendiente de reparación"}
                          </span>
                        </div>

                        <div className="detail-rows">
                          <div className="detail-row">
                            <div><span className="field-label">Coordenadas</span><strong className="field-value">{selectedFinding.latitude !== null ? `${selectedFinding.latitude.toFixed(6)}, ${selectedFinding.longitude?.toFixed(6)}` : "Sin coordenadas EXIF"}</strong></div>
                          </div>
                          <div className="detail-row">
                            <div><span className="field-label">Detectado</span><strong className="field-value">{formatDateTime(selectedFinding.created_at)}</strong></div>
                          </div>
                          <div className="detail-row">
                            <div><span className="field-label">Imagen</span><strong className="field-value">{selectedFinding.image_filename}</strong></div>
                          </div>
                        </div>

                        <div className="detail-conf">
                          <div><span>Confianza del modelo</span><strong>{confidence(selectedFinding.confidence)}</strong></div>
                          <div className="confidence-line"><span style={{ width: confidence(selectedFinding.confidence), background: criticalityColor[selectedCriticality] }} /></div>
                        </div>
                      </div>

                      <div className="detail-actions">
                        <button
                          className={selectedFinding.repair_status === "repaired" ? "button secondary full" : "button positive full"}
                          disabled={repairBusyId === selectedFinding.id}
                          onClick={() => toggleRepairStatus(selectedFinding)}
                        >
                          {repairBusyId === selectedFinding.id ? <LoaderCircle className="spin" size={14} /> : null}
                          {selectedFinding.repair_status === "repaired" ? "Marcar como pendiente" : "Marcar como reparada"}
                        </button>
                        <button className="button secondary full" onClick={() => goToFindingMission(selectedFinding)}>
                          Ver imagen del hallazgo
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="detail-empty">
                      <strong>Selecciona un punto</strong>
                      <span>Haz clic en un marcador del mapa para ver el detalle del hallazgo.</span>
                    </div>
                  )}
                </aside>
              </div>
            </section>
          )}
        </motion.div>
      )}

      {screen === "workspace" && (
        <motion.div key="workspace" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
            
              {mission ? <>
                <button type="button" className="crumb" onClick={goToHistory}>Misiones /</button>
                <h1>{mission.name}</h1>
                <p>{mission.segment} · {formatDate(mission.created_at)} · {mission.images.length} {mission.images.length === 1 ? "imagen" : "imágenes"}</p>
              </> : <>
                <button type="button" className="crumb" onClick={goToHistory}>Misiones /</button>
                <h1>Nueva misión</h1>
                <p>Sube las fotos de un vuelo y analízalas para revisar las rocas en la pista y el ancho del camino.</p>
              </>}
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

          {error && <div className="error-banner"><span>{error}</span><button aria-label="Cerrar aviso" onClick={() => setError("")}><X size={15} /></button></div>}
          {health?.detector === "mock" && view !== "upload" && <div className="error-banner"><span>Análisis simulado: los resultados son ficticios y no corresponden a detecciones reales.</span></div>}

          {busy === "upload" && (
            <section className="task-progress" aria-label="Carga de fotos">
              <strong>{uploadProgress?.fraction === 1 ? "Guardando imágenes en la plataforma…" : "Subiendo imágenes a la plataforma…"}</strong>
              <ProgressBar label="Datos enviados a la plataforma" fraction={uploadProgress?.fraction ?? 0} />
              {uploadProgress?.remaining != null && (
                <small>Quedan aprox. {formatDuration(uploadProgress.remaining * 1000)}</small>
              )}
            </section>
          )}

          {mission && (
            <div role="status">
              {detectionStart?.missionId === mission.id ? (
                <section className="task-progress" aria-label="Progreso de inferencia">
                  <strong>
                    {detectionProgress?.phase === "starting" ? "Esperando que el servicio de inferencia esté listo…"
                      : detectionProgress?.phase === "saving" ? "Guardando los resultados…"
                      : detectionProgress ? "Procesando imágenes…" : "Detección solicitada"}
                  </strong>
                  <ProgressBar label="Imágenes procesadas"
                    fraction={detectionProgress ? detectionProgress.completed / detectionProgress.total : undefined} />
                  <small>
                    Tiempo transcurrido · {formatDuration(elapsed)}
                    {detectionProgress && ` · ${detectionProgress.completed} de ${detectionProgress.total} imágenes procesadas`}
                    {detectionProgress?.estimated_remaining_seconds != null && detectionProgress.completed >= 5 &&
                      ` · Quedan aprox. ${formatDuration(detectionProgress.estimated_remaining_seconds * 1000)} de análisis`}
                  </small>
                  {!detectionProgress && <small>Esperando que la plataforma informe el progreso.</small>}
                  {detectionProgress?.phase === "starting" && (
                    <small>Si el servicio de inferencia está apagado, iniciarlo y cargar los modelos puede tardar unos minutos.</small>
                  )}
                </section>
              ) : detectionSummary?.missionId === mission.id && (
                <p className="inference-duration">
                  <span>
                    {detectionSummary.imageCount} {detectionSummary.imageCount === 1 ? "imagen procesada" : "imágenes procesadas"}
                    {" en "}{formatDuration(detectionSummary.milliseconds)}
                  </span>
                </p>
              )}
            </div>
          )}

          {missionPath && !mission && !error && <p role="status">Cargando misión…</p>}

          {view === "upload" && (newMission || mission) && (
            <section className={`workspace upload-layout fade-in-view ${mission ? "has-mission" : ""}`}>
              <form className="card upload-card" onSubmit={createMission}>
                <div className="card-title">
                  <div><span className="overline">Entrada</span><h2>Imágenes de la misión</h2></div>
                  <span className="pill">RGB</span>
                </div>
                {!mission ? <>
                  <div className="field-grid">
                    <label><span>Nombre de misión</span><input required minLength={2} maxLength={120} placeholder="Ej.: Inspección camino de acceso" value={missionName} onChange={(event) => setMissionName(event.target.value)} /></label>
                    <label><span>Tramo</span><input required maxLength={120} placeholder="Ej.: Tramo A" value={segment} onChange={(event) => setSegment(event.target.value)} /></label>
                    {isAdmin && (
                      <label>
                        <span>Faena</span>
                        <select className="faena-select" value={missionFaena} onChange={(event) => setMissionFaena(event.target.value)}>
                          <option value="">Selecciona la faena…</option>
                          {faenas.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}
                        </select>
                      </label>
                    )}
                  </div>
                  <div
                    className={`dropzone ${dragging ? "dragging" : ""}`}
                    onClick={() => inputRef.current?.click()}
                    onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFiles(event.dataTransfer.files); }}
                  >
                    <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(event) => event.target.files && acceptFiles(event.target.files)} />
                    <strong>Arrastra las imágenes aquí</strong>
                    <small>JPG, PNG o WebP</small>
                    <span className="button secondary">Seleccionar archivos</span>
                  </div>
                  {files.length > 0 && <div className="queued-files">
                    <div className="queue-head"><strong>{files.length} imágenes listas</strong><button type="button" onClick={() => setFiles([])}>Quitar todas</button></div>
                    {files.slice(0, 4).map((file, index) => <div className="queued-file" key={`${file.name}-${index}`}><span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small><button type="button" aria-label={`Quitar ${file.name}`} onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={14} /></button></div>)}
                    {files.length > 4 && <small className="more-files">+ {files.length - 4} archivos adicionales</small>}
                  </div>}
                  <div className="form-actions">
                    <button className="button primary" disabled={busy !== null}>{busy === "upload" ? "Subiendo…" : "Crear misión"}</button>
                  </div>
                </> : <div className="uploaded-state">
                  <div><span className="overline">Carga completada</span><h3>{mission.name}</h3><p>{mission.segment} · {mission.images.length} imágenes</p></div>
                  <div className="mission-thumbs">{mission.images.slice(0, 5).map((image) => <img key={image.id} src={api.imageUrl(image.image_url)} alt="Camino cargado" />)}</div>
                </div>}
              </form>

              <aside className="card process-card">
                <div className="card-title"><div><span className="overline">Procesamiento</span><h2>Flujo de detección</h2></div></div>
                <div className="pipeline">
                  <div className={mission ? "complete" : "current"}><span>{mission ? <Check size={14} /> : "1"}</span><div><strong>Validar lote</strong><small>{mission ? `${mission.images.length} imágenes compatibles` : "Esperando imágenes"}</small></div></div>
                  <div className={busy === "detect" ? "current" : mission?.status === "review" ? "complete" : ""}><span>{mission?.status === "review" ? <Check size={14} /> : "2"}</span><div><strong>{health?.detector !== "mock" ? "Ejecutar detector" : "Análisis simulado"}</strong><small>{health?.detector !== "mock" ? "Modelo de detección disponible" : "Resultados ficticios; no son detecciones reales"}</small></div></div>
                  <div className={mission?.status === "review" ? "complete" : ""}><span>{mission?.status === "review" ? <Check size={14} /> : "3"}</span><div><strong>Preparar revisión</strong><small>Resultados normalizados por imagen</small></div></div>
                </div>
                <div className="process-note"><span>Las misiones quedan disponibles para revisión y seguimiento.</span></div>
                {health?.detector === "mock" && <div className="admin-account-message error">El análisis es ficticio: los resultados no corresponden a detecciones reales.</div>}
                <button className="button primary full large" onClick={runDetection} disabled={!mission || busy !== null}>{busy === "detect" ? <><LoaderCircle className="spin" size={17} /> Analizando imágenes…</> : <> {health?.detector !== "mock" ? "Ejecutar detección" : "Ejecutar análisis ficticio"}</>}</button>
              </aside>
            </section>
          )}

          {view === "review" && mission && selectedImage && (
            <section className="workspace tramo-strip" aria-labelledby="tramo-title">
              <div className="tramo-head">
                <h2 id="tramo-title">Recorrido del tramo</h2>
                <span>Imágenes en orden, coloreadas según el ancho medido</span>
              </div>
              <div className="tramo-list">
                {orderedImages.map((image, index) => {
                  const onRoad = image.detections.filter((item) => item.label !== OFF_ROAD_LABEL && item.review_status !== "rejected" && item.confidence >= threshold).length;
                  const width = image.road_width;
                  return (
                    <button key={image.id} type="button" aria-pressed={image.id === selectedImage.id}
                      className={`tramo-item ${width ? widthClass(width.estado) : "sin"}`}
                      onClick={() => setSelectedImageId(image.id)} title={image.filename}>
                      <img loading="lazy" src={api.imageUrl(image.image_url)} alt="" />
                      <span>
                        <strong>{index + 1} · {image.filename}</strong>
                        <small>
                          {width?.ancho_min_m != null ? `${width.ancho_min_m.toFixed(1).replace(".", ",")} m` : "Sin ancho"}
                          {" · "}{onRoad} {onRoad === 1 ? "roca" : "rocas"}
                        </small>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {view === "review" && mission && selectedImage && (
            <section className="workspace review-layout fade-in-view">
              <aside className="card filters-card">
                <div className="card-title compact"><div><h2>Mostrar</h2></div></div>
                <div className="filter-list">
                  {availableLabels.map((label) => <button key={label} className={enabledLabels.includes(label) ? "enabled" : ""} onClick={() => toggleLabel(label)}><i style={{ background: colorForLabel[label] ?? fallbackColor }} /><span>{label}</span><strong>{imageDetections.filter((item) => item.label === label).length}</strong><em>{enabledLabels.includes(label) && <Check size={11} />}</em></button>)}
                </div>
                <div className="threshold">
                  <label><span>Confianza mínima</span><strong>{confidence(threshold)}</strong></label>
                  <input type="range" min="0.3" max="0.95" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
                  <small><span>30%</span><span>95%</span></small>
                </div>
                <div className="stats-mini">
                  <div><span>Visibles</span><strong><AnimatedNumber value={visibleDetections.length} /></strong></div>
                  <div><span>Pendientes</span><strong><AnimatedNumber value={imagePending} /></strong></div>
                  <div><span>Confirmadas</span><strong><AnimatedNumber value={imageConfirmed} /></strong></div>
                </div>
              </aside>

              <div className="viewer-column">
                <div className="card viewer-card">
                  <div className="image-meta"><div><span><strong>{selectedImage.filename}</strong><small>{selectedImage.latitude ? `${selectedImage.latitude.toFixed(5)}, ${selectedImage.longitude?.toFixed(5)}` : "Sin coordenadas EXIF"}</small></span></div><div className="image-meta-actions">{(selectedImage.road_width_url || selectedImage.analysis_url) && <div className="view-switch" role="group" aria-label="Vista de la imagen">{imageViewOptions.map((option) => <button key={option.value} type="button" className={imageView === option.value ? "active" : ""} onClick={() => setImageView(option.value)}>{option.label}</button>)}</div>}<span className="pill">{visibleDetections.length} hallazgos</span></div></div>
                  <ReviewImageZoom key={selectedImage.id} image={selectedImage}>
                    <img width={selectedImage.width} height={selectedImage.height} src={api.imageUrl(imageView !== "rocas" ? (selectedImage.road_width_url ?? selectedImage.analysis_url ?? selectedImage.image_url) : selectedImage.image_url)} alt="Camino minero bajo revisión" />
                    {imageView !== "rocas" && selectedImage.road_width_url &&
                      selectedImage.road_width?.resumen_incrustado !== false && (
                        <LegacyRoadWidthPatch image={selectedImage} />
                      )}
                    {visibleDetections.map((item) => <div key={item.id} className={`box ${item.review_status}${item.id === evidenceDetectionId ? " linked-detection" : ""}`} title={`${item.label} · ${confidence(item.confidence)}`} style={{ left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.width * 100}%`, height: `${item.height * 100}%`, borderColor: colorForLabel[item.label] ?? fallbackColor, ...(imageView === "ambas" ? originalPatch(item, selectedImage) : {}) }}><span className="box-conf">{confidence(item.confidence)}</span></div>)}
                  </ReviewImageZoom>
                  <div className="viewer-nav"><button onClick={() => selectRelative(-1)}> Anterior</button><span>{orderedImages.findIndex((image) => image.id === selectedImage.id) + 1} / {orderedImages.length}</span><button onClick={() => selectRelative(1)}>Siguiente </button></div>
                </div>
              </div>

              <aside className="card review-card">
                {imageView !== "rocas" && selectedImage.road_width && (
                  <RoadWidthCard width={selectedImage.road_width} />
                )}
                <div className="card-title compact"><div><h2>Rocas en la pista</h2><small className="card-subtitle">Van al informe</small></div><span className="pill">{imageDetections.filter((item) => item.label !== OFF_ROAD_LABEL).length}</span></div>
                <div className="detection-list">
                  {imageDetections.filter((item) => item.label !== OFF_ROAD_LABEL).map((item, index) => (
                    <div className={`detection-item ${item.review_status}${item.id === evidenceDetectionId ? " linked-detection" : ""}`} key={item.id}>
                      <i style={{ background: colorForLabel[item.label] ?? fallbackColor }} />
                      <span className="detection-name">Roca {index + 1} <small>{confidence(item.confidence)}</small></span>
                      <button type="button" className={`review-toggle confirm${item.review_status === "confirmed" ? " on" : ""}`}
                        aria-pressed={item.review_status === "confirmed"} aria-label={`Confirmar roca ${index + 1}`} title="Confirmar"
                        disabled={reviewBusyId === item.id} onClick={() => reviewFinding(item, "confirmed")}><Check size={16} /></button>
                      <button type="button" className={`review-toggle reject${item.review_status === "rejected" ? " on" : ""}`}
                        aria-pressed={item.review_status === "rejected"} aria-label={`Descartar roca ${index + 1}`} title="Descartar"
                        disabled={reviewBusyId === item.id} onClick={() => reviewFinding(item, "rejected")}><X size={16} /></button>
                    </div>
                  ))}
                  {!imageDetections.some((item) => item.label !== OFF_ROAD_LABEL) && <p className="muted">Sin rocas en la pista en esta imagen.</p>}
                  {imageDetections.some((item) => item.label === OFF_ROAD_LABEL) && (
                    <p className="muted">{imageDetections.filter((item) => item.label === OFF_ROAD_LABEL).length} rocas fuera de la pista se muestran solo como referencia.</p>
                  )}
                </div>
                <button className="button primary full" onClick={() => setView("report")}>Generar informe</button>

                <div className="review-criticality">
                  <div className="review-criticality-head">
                    <span>Criticidad de la imagen</span>
                    <span className={`review-status-pill ${selectedImage.criticidad_manual ? "done" : "pending"}`}>
                      {selectedImage.criticidad_manual ? "Revisión realizada" : "Revisión pendiente"}
                    </span>
                  </div>
                  <div className="semaphore">
                    {(["critico", "moderado", "optimo"] as ManualCriticality[]).map((level) => (
                      <button
                        key={level}
                        type="button"
                        className={`semaphore-dot ${level} ${selectedImage.criticidad_manual === level ? "active" : ""}`}
                        title={criticalityLabel[level]}
                        disabled={criticalityBusyId === selectedImage.id}
                        onClick={() => setImageCriticality(selectedImage, level)}
                      >
                        {criticalityBusyId === selectedImage.id
                          ? <LoaderCircle className="spin" size={11} />
                          : selectedImage.criticidad_manual === level ? <Check size={12} /> : null}
                      </button>
                    ))}
                  </div>
                  <span className="review-criticality-current" style={{ color: selectedImage.criticidad_manual ? criticalityColor[selectedImage.criticidad_manual] : undefined }}>
                    {selectedImage.criticidad_manual ? criticalityLabel[selectedImage.criticidad_manual] : "Sin clasificar — elige un nivel"}
                  </span>
                </div>
              </aside>
            </section>
          )}

          {view === "report" && mission && (
            <section className="workspace report-layout fade-in-view">
              <article className="card report-preview">
                <div className="report-header"><img className="report-header-logo" src={logoIcon} alt="NeumaDiesel" /><span className="overline">Informe de inspección</span><h2>{mission.name}</h2><p>{mission.segment} · {new Date(mission.created_at).toLocaleDateString("es-CL")}</p></div>
                <div className="report-content">
                  <div className="metric-grid"><div><span>Imágenes</span><strong>{mission.images.length}</strong></div><div><span>Hallazgos</span><strong>{allDetections.length}</strong></div><div><span>Confirmados</span><strong>{confirmed}</strong></div><div><span>Confianza media</span><strong>{confidence(average)}</strong></div></div>
                  <h3>Distribución de anomalías</h3>
                  <div className="bar-list">{availableLabels.map((label) => <div key={label}><span>{label}</span><div><i style={{ width: `${allDetections.length ? ((counts[label] ?? 0) / Math.max(...Object.values(counts), 1)) * 100 : 0}%`, background: colorForLabel[label] ?? fallbackColor }} /></div><strong>{counts[label] ?? 0}</strong></div>)}</div>
                  <div className="map-section">
                    <div className="map-heading"><div><span><strong>Mapa de hallazgos</strong><small>Sectores del camino que requieren revisión o mantenimiento.</small></span></div><span className="pill">{mission.images.filter((image) => image.latitude !== null).length} ubicaciones</span></div>
                    <MapPanel mission={mission} selectedImageId={selectedImageId} onSelectImage={(image) => setSelectedImageId(image.id)} />
                  </div>
                  <div className="report-info"><span><strong>Ubicación aproximada por imagen</strong><small>Las coordenadas GPS se obtienen de los metadatos EXIF cuando están disponibles.</small></span></div>
                </div>
              </article>
              <aside className="card export-card">
                <span className="overline">Exportación</span>
                <h2>Informe listo</h2>
                <p>El PDF se genera en FastAPI con los datos actuales de la misión y el estado de revisión.</p>
                <div className="export-list"><span>Resumen consolidado</span><span>Conteo por clase</span><span>Detalle por imagen</span><span>Estado de cada hallazgo</span><span>Imagen de las fichas: {imageViewOptions.find((option) => option.value === imageView)?.label}</span></div>
                <button className="button primary full large" onClick={downloadReport} disabled={busy !== null}>{busy === "report" ? <LoaderCircle className="spin" size={17} /> : null} Descargar PDF</button>
                <button className="button secondary full" onClick={() => setView("review")}> Volver a revisión</button>
              </aside>
            </section>
          )}
        </motion.div>
      )}
      </AnimatePresence>

    </main>
    </div>
  );
}
