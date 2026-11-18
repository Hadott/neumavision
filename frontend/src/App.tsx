import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Clock,
  Download,
  FileImage,
  FileText,
  Gauge,
  History,
  ImagePlus,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  MapPin,
  Mountain,
  Play,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Upload,
  UsersRound,
  Wrench,
  X,
  XCircle,
  Ruler
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { api, getSession, setSession, setUnauthorizedHandler } from "./api";
import AdminAccounts from "./AdminAccounts";
import logoIcon from "./assets/logo-icon-dark.png";
import DashboardStats from "./DashboardStats";
import DashboardMap, { criticalityColor, criticalityLabel, criticalityOf, type Criticality } from "./DashboardMap";
import Login from "./Login";
import MapPanel from "./MapPanel";
import type { Account, DashboardFinding, Detection, DetectionProgress, Health, InferenceHealth, ManualCriticality, Mission, MissionImage, MissionSummary, RepairStatus, Session } from "./types";
import { AnimatePresence, motion } from "framer-motion";
import { AnimatedNumber, SkeletonCards, SkeletonDashboard } from "./components/Animated";

type Screen = "history" | "workspace" | "dashboard" | "accounts";
type View = "upload" | "review" | "report";
type Busy = "upload" | "detect" | "report" | "open" | null;
type DashReview = "pending" | "confirmed";

const inferenceStatusLabel: Record<InferenceHealth["status"], string> = {
  up: "Encendida · Up",
  down: "Apagada · Down",
  starting: "Encendiendo",
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
  const [screen, setScreen] = useState<Screen>("history");
  const [view, setView] = useState<View>("upload");
  const [mission, setMission] = useState<Mission | null>(null);
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
  const [deletingId, setDeletingId] = useState("");
  const [criticalityBusyId, setCriticalityBusyId] = useState("");
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
  const [faenas, setFaenas] = useState<Account[]>([]);
  const [faenaFiltro, setFaenaFiltro] = useState("");
  const [missionFaena, setMissionFaena] = useState("");
  const isAdmin = session?.cuenta.rol === "admin";

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
    if (labels.length) setEnabledLabels((current) => current.length ? current.filter((label) => labels.includes(label)) : labels);
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
    setMissionsLoading(true);
    try {
      const list = await api.listMissions(isAdmin ? faenaFiltro || undefined : undefined);
      setMissions(list);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible cargar el historial de misiones.");
    } finally {
      setMissionsLoading(false);
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

  function goToHistory() {
    setScreen("history");
    setError("");
  }

  function handleLogin(next: Session) {
    setSession(next);
    setSessionState(next);
    setScreen("history");
    setError("");
  }

  function logout(message = "") {
    setSession(null);
    setSessionState(null);
    setFaenas([]);
    setFaenaFiltro("");
    setMissionFaena("");
    setMissions([]);
    setDashFindings([]);
    setMission(null);
    setScreen("history");
    setError(message);
  }

  function changeFaenaFiltro(value: string) {
    setFaenaFiltro(value);
    setMissionFaena(value);
  }

  function openDashboard() {
    setScreen("dashboard");
    setError("");
  }

  function viewAccountMissions(account: Account) {
    setFaenaFiltro(account.id);
    setScreen("history");
    setError("");
  }

  function startNewMission() {
    resetWorkspace();
    setScreen("workspace");
  }

  async function openMission(id: string) {
    setBusy("open");
    setError("");
    try {
      const loaded = await api.getMission(id);
      setMission(loaded);
      setSelectedImageId("");
      setEnabledLabels(Array.from(new Set(loaded.images.flatMap((image) => image.detections.map((item) => item.label)))));
      setView(loaded.status === "review" ? "review" : "upload");
      setScreen("workspace");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible abrir la misión.");
    } finally {
      setBusy(null);
    }
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
      setMission(created);
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
      setMission(processed);
      setEnabledLabels(Array.from(new Set(processed.images.flatMap((image) => image.detections.map((item) => item.label)))));
      setView("review");
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
    void openMission(finding.mission_id);
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
        // Reemplaza la imagen completa: el backend puede confirmar automáticamente sus
        // hallazgos pendientes al asignar una criticidad, y queremos reflejar eso también.
        images: current.images.map((item) => item.id === image.id ? updated : item)
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible guardar la criticidad de la imagen.");
    } finally {
      setCriticalityBusyId("");
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
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon"><img src={logoIcon} alt="NeumaDiesel" /></span>
          <span><strong>NEUMADIESEL</strong><small>Visión de caminos</small></span>
        </div>
        <div className="top-actions">
          {isAdmin && (
            <select className="faena-select" value={faenaFiltro} onChange={(event) => changeFaenaFiltro(event.target.value)} title="Faena visible">
              <option value="">Todas las faenas</option>
              {faenas.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}
            </select>
          )}
          {screen !== "history" && <button className="button ghost" onClick={goToHistory}><History size={15} /> Historial</button>}
          {screen !== "dashboard" && <button className="button ghost" onClick={openDashboard}><LayoutDashboard size={15} /> Dashboard</button>}
          {isAdmin && screen !== "accounts" && <button className="button ghost" onClick={() => setScreen("accounts")}><UsersRound size={15} /> Cuentas</button>}
          {screen !== "workspace" && <button className="button ghost" onClick={startNewMission}><RotateCcw size={15} /> Nueva misión</button>}
          {screen === "workspace" && mission && <button className="button ghost" onClick={startNewMission}><RotateCcw size={15} /> Nueva misión</button>}
          <span className="account-chip" title={session.cuenta.correo}>
            <i>{session.cuenta.nombre.split(/\s+/).map((word) => word[0]).join("").slice(0, 3).toUpperCase()}</i>
            <span><strong>{session.cuenta.nombre}</strong><small>{isAdmin ? "Administrador" : session.cuenta.correo}</small></span>
          </span>
          <button className="button ghost" onClick={() => logout()}><LogOut size={15} /> Cerrar sesión</button>
        </div>
      </header>

      <div className="inference-health" role="status">
        <strong><span className={`inference-indicator ${inferenceHealth?.status ?? "unknown"}`} aria-hidden="true" />
          Jade · {inferenceStatusLabel[inferenceHealth?.status ?? "unknown"]}
        </strong>
        {inferenceHealth?.idle_timeout_seconds != null && (
          <small>
            {inferenceHealth.status === "starting"
              ? "Jade está iniciando y cargando los modelos. Puede tardar unos minutos."
              : inferenceHealth.idle_timeout_seconds === 0
                ? "Apagado automático desactivado."
                : `El arranque puede tardar unos minutos. Se apaga tras ${inferenceHealth.idle_timeout_seconds / 60} min sin inferencias.`}
          </small>
        )}
      </div>

      <AnimatePresence mode="wait">
      {screen === "accounts" && isAdmin && (
        <motion.div key="accounts" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
              <span className="overline">Administración de plataforma</span>
              <h1>Usuarios y faenas</h1>
              <p>Administra los datos de acceso y revisa las misiones de cada cuenta.</p>
            </div>
            <div className="architecture"><span><ShieldCheck size={14} /> Solo administradores</span></div>
          </section>
          <AdminAccounts onViewMissions={viewAccountMissions} />
        </motion.div>
      )}
      {screen === "history" && (
        <motion.div key="history" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
              <span className="overline">Plataforma de inspección RGB</span>
              <h1>Historial de misiones</h1>
              <p>Revisa las misiones ya procesadas o inicia una nueva inspección del camino minero.</p>
            </div>
          </section>

          {error && <div className="error-banner"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError("")}><X size={15} /></button></div>}

          <section className="workspace history-layout">
            <div className="history-toolbar">
              <div><span className="overline">Misiones</span><h2>{missions.length} registradas</h2></div>
              <div className="history-toolbar-actions">
                <button className="button ghost" onClick={refreshMissions} disabled={missionsLoading}>
                  {missionsLoading ? <LoaderCircle className="spin" size={15} /> : <RotateCcw size={15} />} Actualizar
                </button>
                <button className="button primary" onClick={startNewMission}><Upload size={16} /> Nueva misión</button>
              </div>
            </div>

            {missionsLoading && !missions.length ? (
              <SkeletonCards count={6} />
            ) : missions.length ? (
              <div className="history-grid">
                {missions.map((item) => (
                  <div
                    key={item.id}
                    className="card history-card"
                    role="button"
                    tabIndex={0}
                    onClick={() => busy !== "open" && openMission(item.id)}
                    onKeyDown={(event) => {
                      if ((event.key === "Enter" || event.key === " ") && busy !== "open") openMission(item.id);
                    }}
                  >
                    <button
                      type="button"
                      className="history-delete"
                      title="Eliminar misión"
                      disabled={deletingId === item.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDeleteMission(item.id, item.name);
                      }}
                    >
                      {deletingId === item.id ? <LoaderCircle className="spin" size={14} /> : <Trash2 size={14} />}
                    </button>
                    <div className="history-card-top">
                      <span className={`status-badge ${item.status}`}>{statusLabel(item.status)}</span>
                      <span className="history-date"><Calendar size={12} /> {formatDate(item.created_at)}</span>
                    </div>
                    <h3>{item.name}</h3>
                    {isAdmin && item.faena_name && <span className="history-faena"><Mountain size={11} /> {item.faena_name}</span>}
                    <p>{item.segment}</p>
                    <div className="history-card-stats">
                      <span><FileImage size={13} /> {item.image_count} imágenes</span>
                      <span><ScanLine size={13} /> {item.detection_count} hallazgos</span>
                      <span><CheckCircle2 size={13} /> {item.confirmed_count} confirmados</span>
                    </div>
                    {(item.criticidad_critico_count + item.criticidad_moderado_count + item.criticidad_optimo_count) > 0 && (
                      <div className="history-card-semaphore">
                        {item.criticidad_critico_count > 0 && <span className="mini-crit-chip critico"><i />{item.criticidad_critico_count}</span>}
                        {item.criticidad_moderado_count > 0 && <span className="mini-crit-chip moderado"><i />{item.criticidad_moderado_count}</span>}
                        {item.criticidad_optimo_count > 0 && <span className="mini-crit-chip optimo"><i />{item.criticidad_optimo_count}</span>}
                      </div>
                    )}
                    <span className="history-open">Abrir misión <ArrowRight size={13} /></span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="card history-empty">
                <Mountain size={22} />
                <strong>Todavía no hay misiones</strong>
                <span>Crea una misión nueva cargando imágenes de inspección.</span>
                <button className="button primary" onClick={startNewMission}><Upload size={16} /> Nueva misión</button>
              </div>
            )}
          </section>
        </motion.div>
      )}

      {screen === "dashboard" && (
        <motion.div key="dashboard" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <section className="hero">
            <div>
              <span className="overline">Plataforma de inspección RGB</span>
              <h1>Dashboard operacional</h1>
              <p>Monitorea la criticidad de los hallazgos en los caminos mineros, revisa su ubicación en el mapa y compara su evolución entre inspecciones.</p>
            </div>
          </section>

          {error && <div className="error-banner"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError("")}><X size={15} /></button></div>}

          <nav className="steps">
            <button className={dashTab === "mapa" ? "active" : ""} onClick={() => setDashTab("mapa")}><MapPin size={14} /> Mapa</button>
            <button className={dashTab === "estadisticas" ? "active" : ""} onClick={() => setDashTab("estadisticas")}><Gauge size={14} /> Estadísticas</button>
          </nav>

          {dashLoading && !dashFindings.length ? (
            <section className="workspace dash-wide"><SkeletonDashboard /></section>
          ) : !dashFindings.length ? (
            <section className="workspace"><div className="card history-empty">
              <Mountain size={22} />
              <strong>Todavía no hay hallazgos</strong>
              <span>Procesa una misión para ver sus hallazgos en el dashboard operacional.</span>
              <button className="button primary" onClick={startNewMission}><Upload size={16} /> Nueva misión</button>
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
                    <span className="kpi-icon" style={{ background: "#edf0f1", color: "#4c5962" }}><Gauge size={19} /></span>
                    <span><strong><AnimatedNumber value={dashStats.total} /></strong><span>Hallazgos activos</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span className="kpi-icon" style={{ background: "#fff1ef", color: "#c0392b" }}><AlertTriangle size={19} /></span>
                    <span><strong style={{ color: "#c0392b" }}><AnimatedNumber value={dashStats.critico} /></strong><span>Críticos</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span className="kpi-icon" style={{ background: "#fef3c7", color: "#a16207" }}><Clock size={19} /></span>
                    <span><strong style={{ color: "#a16207" }}><AnimatedNumber value={dashStats.moderado} /></strong><span>Moderados</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span className="kpi-icon" style={{ background: "#e2f6f2", color: "#167d72" }}><CheckCircle2 size={19} /></span>
                    <span><strong style={{ color: "#167d72" }}><AnimatedNumber value={dashStats.optimo} /></strong><span>Óptimos / leves</span></span>
                  </div>
                </div>
                <div className="repair-progress">
                  <div className="repair-progress-head">
                    <span><Wrench size={13} /> Avance de reparación</span>
                    <strong><AnimatedNumber value={dashStats.repaired} /> de <AnimatedNumber value={dashStats.total} /> reparados · {dashStats.total ? Math.round((dashStats.repaired / dashStats.total) * 100) : 0}%</strong>
                  </div>
                  <div className="repair-bar"><span style={{ width: `${dashStats.total ? (dashStats.repaired / dashStats.total) * 100 : 0}%` }} /></div>
                </div>
              </div>

              <div className="dash-grid">
                <aside className="card filters-card">
                  <div className="card-title compact">
                    <div><span className="overline">Filtros</span><h2>Hallazgos</h2></div>
                    <SlidersHorizontal size={18} />
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
                    <div><ScanLine size={15} /><span>Visibles</span><strong><AnimatedNumber value={dashVisible.length} /></strong></div>
                    <div><Mountain size={15} /><span>Misiones</span><strong><AnimatedNumber value={dashMissionOptions.length} /></strong></div>
                  </div>
                </aside>

                <div className="card dash-map-card">
                  <div className="dash-map-heading">
                    <div>
                      <MapPin size={16} style={{ marginTop: 1 }} />
                      <span><strong>Mapa de hallazgos</strong><small>Sectores del camino con anomalías detectadas</small></span>
                    </div>
                    <span className="pill">{dashVisible.length} en vista</span>
                  </div>
                  <div className="legend-row">
                    <span className="legend-chip" style={{ background: "#fff1ef", color: "#8f3f31" }}><i style={{ background: "#c0392b" }} />Crítico · <AnimatedNumber value={dashVisibleCritico} /></span>
                    <span className="legend-chip" style={{ background: "#fef3c7", color: "#a16207" }}><i style={{ background: "#a16207" }} />Moderado · <AnimatedNumber value={dashVisibleModerado} /></span>
                    <span className="legend-chip" style={{ background: "#e2f6f2", color: "#167d72" }}><i style={{ background: "#167d72" }} />Óptimo · <AnimatedNumber value={dashVisibleOptimo} /></span>
                    <span className="legend-chip" style={{ background: "#eef2f3", color: "#4c5962" }}><Check size={9} />Reparado · <AnimatedNumber value={dashVisibleRepaired} /></span>
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
                            {selectedFinding.review_status === "confirmed" ? <Check size={9} /> : <CircleDot size={9} />}
                            {selectedFinding.review_status === "confirmed" ? "Confirmado" : "Pendiente de revisión"}
                          </span>
                          <span className="status-pill" style={{ background: selectedFinding.repair_status === "repaired" ? "#e2f6f2" : "#fef3c7", color: selectedFinding.repair_status === "repaired" ? "#167d72" : "#a16207" }}>
                            {selectedFinding.repair_status === "repaired" ? <Wrench size={9} /> : <Clock size={9} />}
                            {selectedFinding.repair_status === "repaired" ? "Reparado" : "Pendiente de reparación"}
                          </span>
                        </div>

                        <div className="detail-rows">
                          <div className="detail-row">
                            <MapPin size={14} />
                            <div><span className="field-label">Coordenadas</span><strong className="field-value">{selectedFinding.latitude !== null ? `${selectedFinding.latitude.toFixed(6)}, ${selectedFinding.longitude?.toFixed(6)}` : "Sin coordenadas EXIF"}</strong></div>
                          </div>
                          <div className="detail-row">
                            <Calendar size={14} />
                            <div><span className="field-label">Detectado</span><strong className="field-value">{formatDateTime(selectedFinding.created_at)}</strong></div>
                          </div>
                          <div className="detail-row">
                            <FileImage size={14} />
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
                          {repairBusyId === selectedFinding.id ? <LoaderCircle className="spin" size={14} /> : <Check size={14} />}
                          {selectedFinding.repair_status === "repaired" ? "Marcar como pendiente" : "Marcar como reparada"}
                        </button>
                        <button className="button secondary full" onClick={() => goToFindingMission(selectedFinding)} disabled={busy === "open"}>
                          Ver misión completa <ArrowRight size={14} />
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="detail-empty">
                      <MapPin size={22} />
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
              <span className="overline">Plataforma de inspección RGB</span>
              <h1>Inspección del camino</h1>
              <p>Detecta condiciones que pueden dañar los neumáticos de camiones CAEX y localiza los sectores que requieren mantenimiento.</p>
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
          {health?.detector === "mock" && view !== "upload" && <div className="error-banner"><AlertTriangle size={16} /><span>Análisis simulado: los resultados son ficticios y no corresponden a detecciones reales.</span></div>}

          {busy === "upload" && (
            <section className="task-progress" aria-label="Carga de fotos">
              <strong>{uploadProgress?.fraction === 1 ? "Guardando imágenes en Nina…" : "Subiendo imágenes a Nina…"}</strong>
              <ProgressBar label="Datos enviados a Nina" fraction={uploadProgress?.fraction ?? 0} />
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
                    {detectionProgress?.phase === "starting" ? "Esperando que Jade esté lista…"
                      : detectionProgress?.phase === "saving" ? "Guardando los resultados…"
                      : detectionProgress ? "Procesando imágenes…" : "Detección solicitada"}
                  </strong>
                  <ProgressBar label="Imágenes procesadas"
                    fraction={detectionProgress ? detectionProgress.completed / detectionProgress.total : undefined} />
                  <small>
                    Tiempo transcurrido · {formatDuration(elapsed)}
                    {detectionProgress && ` · ${detectionProgress.completed} de ${detectionProgress.total} imágenes procesadas`}
                    {detectionProgress?.estimated_remaining_seconds != null &&
                      ` · Quedan aprox. ${formatDuration(detectionProgress.estimated_remaining_seconds * 1000)} de análisis`}
                  </small>
                  {!detectionProgress && <small>Porcentaje pendiente de los datos de progreso de Nina.</small>}
                  {detectionProgress?.phase === "starting" && (
                    <small>Si Jade está apagada, encenderla y cargar los modelos puede tardar unos minutos.</small>
                  )}
                </section>
              ) : detectionSummary?.missionId === mission.id && (
                <p className="inference-duration">
                  <Clock size={15} />
                  <span>
                    {detectionSummary.imageCount} {detectionSummary.imageCount === 1 ? "imagen procesada" : "imágenes procesadas"}
                    {" en "}{formatDuration(detectionSummary.milliseconds)}
                  </span>
                </p>
              )}
            </div>
          )}

          {view === "upload" && (
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
                    <span className="upload-icon"><Upload size={25} /></span>
                    <strong>Arrastra las imágenes aquí</strong>
                    <small>JPG, PNG o WebP</small>
                    <span className="button secondary"><ImagePlus size={15} /> Seleccionar archivos</span>
                  </div>
                  {files.length > 0 && <div className="queued-files">
                    <div className="queue-head"><strong>{files.length} imágenes listas</strong><button type="button" onClick={() => setFiles([])}>Quitar todas</button></div>
                    {files.slice(0, 4).map((file, index) => <div className="queued-file" key={`${file.name}-${index}`}><FileImage size={16} /><span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small><button type="button" onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={14} /></button></div>)}
                    {files.length > 4 && <small className="more-files">+ {files.length - 4} archivos adicionales</small>}
                  </div>}
                  <div className="form-actions">
                    <button className="button primary" disabled={busy !== null}><Upload size={16} />{busy === "upload" ? "Subiendo…" : "Crear misión"}</button>
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
                  <div className={busy === "detect" ? "current" : mission?.status === "review" ? "complete" : ""}><span>{mission?.status === "review" ? <Check size={14} /> : "2"}</span><div><strong>{health?.detector !== "mock" ? "Ejecutar detector" : "Análisis simulado"}</strong><small>{health?.detector !== "mock" ? "Modelo de detección disponible" : "Resultados ficticios; no son detecciones reales"}</small></div></div>
                  <div className={mission?.status === "review" ? "complete" : ""}><span>{mission?.status === "review" ? <Check size={14} /> : "3"}</span><div><strong>Preparar revisión</strong><small>Resultados normalizados por imagen</small></div></div>
                </div>
                <div className="process-note"><ShieldCheck size={16} /><span>Las misiones quedan disponibles para revisión y seguimiento.</span></div>
                {health?.detector === "mock" && <div className="admin-account-message error"><AlertTriangle size={14} /> El análisis es ficticio: los resultados no corresponden a detecciones reales.</div>}
                <button className="button primary full large" onClick={runDetection} disabled={!mission || busy !== null}>{busy === "detect" ? <><LoaderCircle className="spin" size={17} /> Analizando imágenes…</> : <><Play fill="currentColor" size={16} /> {health?.detector !== "mock" ? "Ejecutar detección" : "Ejecutar análisis ficticio"}</>}</button>
              </aside>
            </section>
          )}

          {view === "review" && mission && selectedImage && (
            <section className="workspace review-layout fade-in-view">
              <aside className="card filters-card">
                <div className="card-title compact"><div><span className="overline">Filtros</span><h2>Hallazgos</h2></div><SlidersHorizontal size={18} /></div>
                <div className="filter-list">
                  {availableLabels.map((label) => <button key={label} className={enabledLabels.includes(label) ? "enabled" : ""} onClick={() => toggleLabel(label)}><i style={{ background: colorForLabel[label] ?? fallbackColor }} /><span>{label}</span><strong>{counts[label] ?? 0}</strong><em>{enabledLabels.includes(label) && <Check size={11} />}</em></button>)}
                </div>
                <div className="threshold">
                  <label><span>Confianza mínima</span><strong>{confidence(threshold)}</strong></label>
                  <input type="range" min="0.3" max="0.95" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
                  <small><span>30%</span><span>95%</span></small>
                </div>
                <div className="stats-mini">
                     <div><ScanLine size={15} /><span>Visibles</span><strong><AnimatedNumber value={filteredAll.length} /></strong></div>
                  <div><CircleDot size={15} /><span>Pendientes</span><strong><AnimatedNumber value={pending} /></strong></div>
                  <div><CheckCircle2 size={15} /><span>Confirmadas</span><strong><AnimatedNumber value={confirmed} /></strong></div>
                </div>
              </aside>

              <div className="viewer-column">
                <div className="card viewer-card">
                  <div className="image-meta"><div><FileImage size={17} /><span><strong>{selectedImage.filename}</strong><small>{selectedImage.latitude ? `${selectedImage.latitude.toFixed(5)}, ${selectedImage.longitude?.toFixed(5)}` : "Sin coordenadas EXIF"}</small></span></div><div className="image-meta-actions">{(selectedImage.road_width_url || selectedImage.analysis_url) && <div className="view-switch" role="group" aria-label="Vista de la imagen">{imageViewOptions.map((option) => <button key={option.value} type="button" className={imageView === option.value ? "active" : ""} onClick={() => setImageView(option.value)}>{option.label}</button>)}</div>}{selectedImage.road_width && <span className={`width-badge ${widthClass(selectedImage.road_width.estado)}`} title="Ancho de pista (percentil 10)"><Ruler size={13} />{selectedImage.road_width.confianza_pista != null ? `${selectedImage.road_width.clase_pista ?? "Pista"} ${confidence(selectedImage.road_width.confianza_pista)} · ` : ""}{selectedImage.road_width.ancho_min_m != null ? `${selectedImage.road_width.ancho_min_m.toFixed(1).replace(".", ",")} m` : "—"} · {selectedImage.road_width.estado}</span>}<span className="pill">{visibleDetections.length} hallazgos</span></div></div>
                  <div className="image-stage">
                    <img width={selectedImage.width} height={selectedImage.height} src={api.imageUrl(imageView !== "rocas" ? (selectedImage.road_width_url ?? selectedImage.analysis_url ?? selectedImage.image_url) : selectedImage.image_url)} alt="Camino minero bajo revisión" />
                    {imageView !== "segmentacion" && visibleDetections.map((item) => <div key={item.id} className={`box ${item.review_status}`} title={`${item.label} · ${confidence(item.confidence)}`} style={{ left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.width * 100}%`, height: `${item.height * 100}%`, borderColor: colorForLabel[item.label] ?? fallbackColor, ...(imageView === "ambas" ? originalPatch(item, selectedImage) : {}) }}><span className="box-conf">{confidence(item.confidence)}</span></div>)}
                    <span className="demo-watermark">{health?.detector === "mock" ? "SIMULACIÓN" : "INFERENCIA"}</span>
                  </div>
                  <div className="viewer-nav"><button onClick={() => selectRelative(-1)}><ArrowLeft size={15} /> Anterior</button><span>{orderedImages.findIndex((image) => image.id === selectedImage.id) + 1} / {orderedImages.length}</span><button onClick={() => selectRelative(1)}>Siguiente <ArrowRight size={15} /></button></div>
                </div>
                <section className="card mission-gallery" aria-labelledby="mission-gallery-title">
                  <div className="card-title compact">
                    <h2 id="mission-gallery-title">Imágenes de la misión</h2>
                    <span className="pill">{orderedImages.length}</span>
                  </div>
                  <div className="mission-gallery-grid">
                    {orderedImages.map((image, index) => (
                      <button key={image.id} type="button" aria-pressed={image.id === selectedImage.id}
                        onClick={() => setSelectedImageId(image.id)} title={image.filename}>
                        <img loading="lazy" src={api.imageUrl(image.analysis_url ?? image.road_width_url ?? image.image_url)} alt="" />
                        <strong>{index + 1}. {image.filename}</strong>
                        <small>{image.detections.length} {image.detections.length === 1 ? "hallazgo" : "hallazgos"}</small>
                      </button>
                    ))}
                  </div>
                </section>
              </div>

              <aside className="card review-card">
                <div className="card-title compact"><div><span className="overline">Imagen actual</span><h2>Revisión</h2></div><span className="pill">{selectedImage.detections.length}</span></div>
                <div className="detection-list">
                  {selectedImage.detections.map((item, index) => <div className={`detection-item ${item.review_status}`} key={item.id} style={{ ["--i" as string]: index } as any}>
                    <div><i style={{ background: colorForLabel[item.label] ?? fallbackColor }} /><strong>{item.label}</strong><span>{confidence(item.confidence)}</span></div>
                    <div className="confidence-line"><span style={{ width: confidence(item.confidence), background: colorForLabel[item.label] ?? fallbackColor }} /></div>
                    <span className="status-pill" style={{ marginTop: 2, background: item.review_status === "confirmed" ? "#e2f6f2" : item.review_status === "rejected" ? "#fdecea" : "#fef3c7", color: item.review_status === "confirmed" ? "#167d72" : item.review_status === "rejected" ? "#c0392b" : "#a16207" }}>
                      {item.review_status === "confirmed" ? <Check size={9} /> : item.review_status === "rejected" ? <XCircle size={9} /> : <CircleDot size={9} />}
                      {item.review_status === "confirmed" ? "Confirmado" : item.review_status === "rejected" ? "Descartado" : "Pendiente"}
                    </span>
                  </div>)}
                </div>
                <button className="button primary full" onClick={() => setView("report")}><FileText size={16} /> Preparar informe</button>

                <div className="review-criticality">
                  <div className="review-criticality-head">
                    <span><Gauge size={13} /> Criticidad de la imagen</span>
                    <span className={`review-status-pill ${selectedImage.criticidad_manual ? "done" : "pending"}`}>
                      {selectedImage.criticidad_manual ? <CheckCircle2 size={11} /> : <CircleDot size={11} />}
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
                    <div className="map-heading"><div><MapPin size={16} /><span><strong>Mapa de hallazgos</strong><small>Sectores del camino que requieren revisión o mantenimiento.</small></span></div><span className="pill">{mission.images.filter((image) => image.latitude !== null).length} ubicaciones</span></div>
                    <MapPanel mission={mission} selectedImageId={selectedImageId} onSelectImage={(image) => setSelectedImageId(image.id)} />
                  </div>
                  <div className="report-info"><MapPin size={17} /><span><strong>Ubicación aproximada por imagen</strong><small>Las coordenadas GPS se obtienen de los metadatos EXIF cuando están disponibles.</small></span></div>
                </div>
              </article>
              <aside className="card export-card">
                <span className="export-icon"><FileText size={27} /></span>
                <span className="overline">Exportación</span>
                <h2>Informe listo</h2>
                <p>El PDF se genera en FastAPI con los datos actuales de la misión y el estado de revisión.</p>
                <div className="export-list"><span><Check size={14} /> Resumen consolidado</span><span><Check size={14} /> Conteo por clase</span><span><Check size={14} /> Detalle por imagen</span><span><Check size={14} /> Estado de cada hallazgo</span><span><Check size={14} /> Imagen de las fichas: {imageViewOptions.find((option) => option.value === imageView)?.label}</span></div>
                <button className="button primary full large" onClick={downloadReport} disabled={busy !== null}>{busy === "report" ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />} Descargar PDF</button>
                <button className="button secondary full" onClick={() => setView("review")}><ArrowLeft size={15} /> Volver a revisión</button>
              </aside>
            </section>
          )}
        </motion.div>
      )}
      </AnimatePresence>

      <footer><span>NeumaDiesel</span></footer>
    </main>
  );
}
