import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock,
  CloudOff,
  Database,
  Download,
  FileImage,
  FileText,
  Gauge,
  History,
  ImagePlus,
  Layers3,
  LayoutDashboard,
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
  Trash2,
  Upload,
  Wrench,
  X,
  XCircle
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import logoIcon from "./assets/logo-icon-dark.png";
import DashboardMap, { criticalityColor, criticalityLabel, criticalityOf, type Criticality } from "./DashboardMap";
import MapPanel from "./MapPanel";
import type { DashboardFinding, Detection, Health, Mission, MissionImage, MissionSummary, RepairStatus } from "./types";

type Screen = "history" | "workspace" | "dashboard";
type View = "upload" | "review" | "report";
type Busy = "upload" | "demo" | "detect" | "report" | "open" | null;
type DashReview = "pending" | "confirmed";

const colorForLabel: Record<string, string> = {
  Bache: "#ff6847",
  Piedra: "#f2b23e",
  "Desprendimiento de roca": "#9e82ff"
};

const fallbackColor = "#4ca8ff";
const confidence = (value: number) => `${Math.round(value * 100)}%`;
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
  const [screen, setScreen] = useState<Screen>("history");
  const [view, setView] = useState<View>("upload");
  const [mission, setMission] = useState<Mission | null>(null);
  const [selectedImageId, setSelectedImageId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [missionName, setMissionName] = useState("Inspección camino de acceso");
  const [segment, setSegment] = useState("Tramo A");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState("");
  const [threshold, setThreshold] = useState(0.65);
  const [enabledLabels, setEnabledLabels] = useState<string[]>([]);
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const [missionsLoading, setMissionsLoading] = useState(false);
  const [deletingId, setDeletingId] = useState("");
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

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (screen === "history") {
      refreshMissions();
    } else if (screen === "dashboard") {
      refreshDashboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen]);

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
    const critico = dashFindings.filter((item) => criticalityOf(item.confidence) === "critico").length;
    const moderado = dashFindings.filter((item) => criticalityOf(item.confidence) === "moderado").length;
    const optimo = dashFindings.filter((item) => criticalityOf(item.confidence) === "optimo").length;
    const repaired = dashFindings.filter((item) => item.repair_status === "repaired").length;
    return { total: dashFindings.length, critico, moderado, optimo, repaired };
  }, [dashFindings]);
  const dashVisible = useMemo(() => dashFindings.filter((item) => {
    if (!dashCriticality.includes(criticalityOf(item.confidence))) return false;
    if (!dashLabels.includes(item.label)) return false;
    if (!dashReview.includes(item.review_status as DashReview)) return false;
    if (!dashRepair.includes(item.repair_status)) return false;
    if (dashMission && item.mission_id !== dashMission) return false;
    return true;
  }), [dashFindings, dashCriticality, dashLabels, dashReview, dashRepair, dashMission]);
  const dashVisibleCritico = dashVisible.filter((item) => criticalityOf(item.confidence) === "critico").length;
  const dashVisibleModerado = dashVisible.filter((item) => criticalityOf(item.confidence) === "moderado").length;
  const dashVisibleOptimo = dashVisible.filter((item) => criticalityOf(item.confidence) === "optimo").length;
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
  const selectedCriticality = selectedFinding ? criticalityOf(selectedFinding.confidence) : null;

  async function refreshMissions() {
    setMissionsLoading(true);
    try {
      const list = await api.listMissions();
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
      const list = await api.dashboardFindings();
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

  function openDashboard() {
    setScreen("dashboard");
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
      setSelectedImageId(loaded.images[0]?.id ?? "");
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
      void refreshMissions();
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
      void refreshMissions();
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
      void refreshMissions();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "La detección no pudo completarse.");
    } finally {
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
          <span className="brand-icon"><img src={logoIcon} alt="NeumaDiesel" /></span>
          <span><strong>NEUMADIESEL</strong><small>Visión de caminos</small></span>
        </div>
        <div className="top-actions">
          <span className={`connection ${health ? "online" : "offline"}`}>
            {health ? <Server size={14} /> : <CloudOff size={14} />}
            {health ? `API · ${health.detector}` : "API sin conexión"}
          </span>
          {screen !== "history" && <button className="button ghost" onClick={goToHistory}><History size={15} /> Historial</button>}
          {screen !== "dashboard" && <button className="button ghost" onClick={openDashboard}><LayoutDashboard size={15} /> Dashboard</button>}
          {screen !== "workspace" && <button className="button ghost" onClick={startNewMission}><RotateCcw size={15} /> Nueva misión</button>}
          {screen === "workspace" && mission && <button className="button ghost" onClick={startNewMission}><RotateCcw size={15} /> Nueva misión</button>}
        </div>
      </header>

      {screen === "history" && (
        <>
          <section className="hero">
            <div>
              <span className="overline">Plataforma de inspección RGB</span>
              <h1>Historial de misiones</h1>
              <p>Revisa las misiones ya procesadas o inicia una nueva inspección del camino minero.</p>
            </div>
            <div className="architecture">
              <span><Server size={14} /> FastAPI</span>
              <ChevronRight size={13} />
              <span><Layers3 size={14} /> React</span>
              <ChevronRight size={13} />
              <span><Database size={14} /> {health?.database ?? "PostgreSQL"}</span>
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
              <div className="card history-empty"><LoaderCircle className="spin" size={20} /><span>Cargando misiones…</span></div>
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
                    <p>{item.segment}</p>
                    <div className="history-card-stats">
                      <span><FileImage size={13} /> {item.image_count} imágenes</span>
                      <span><ScanLine size={13} /> {item.detection_count} hallazgos</span>
                      <span><CheckCircle2 size={13} /> {item.confirmed_count} confirmados</span>
                    </div>
                    <span className="history-open">Abrir misión <ArrowRight size={13} /></span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="card history-empty">
                <Mountain size={22} />
                <strong>Todavía no hay misiones</strong>
                <span>Crea una misión nueva o usa datos demo para ver la plataforma en acción.</span>
                <button className="button primary" onClick={startNewMission}><Upload size={16} /> Nueva misión</button>
              </div>
            )}
          </section>
        </>
      )}

      {screen === "dashboard" && (
        <>
          <section className="hero">
            <div>
              <span className="overline">Plataforma de inspección RGB</span>
              <h1>Dashboard operacional</h1>
              <p>Monitorea la criticidad de los hallazgos en los caminos mineros y revisa el detalle de cada uno sin salir del mapa.</p>
            </div>
            <div className="architecture">
              <span><Server size={14} /> FastAPI</span>
              <ChevronRight size={13} />
              <span><Layers3 size={14} /> React</span>
              <ChevronRight size={13} />
              <span><Database size={14} /> {health?.database ?? "SQLite"}</span>
            </div>
          </section>

          {error && <div className="error-banner"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError("")}><X size={15} /></button></div>}

          {dashLoading && !dashFindings.length ? (
            <section className="workspace"><div className="card history-empty"><LoaderCircle className="spin" size={20} /><span>Cargando dashboard…</span></div></section>
          ) : !dashFindings.length ? (
            <section className="workspace"><div className="card history-empty">
              <Mountain size={22} />
              <strong>Todavía no hay hallazgos</strong>
              <span>Procesa una misión para ver sus hallazgos en el dashboard operacional.</span>
              <button className="button primary" onClick={startNewMission}><Upload size={16} /> Nueva misión</button>
            </div></section>
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
                    <span><strong>{dashStats.total}</strong><span>Hallazgos activos</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span className="kpi-icon" style={{ background: "#fff1ef", color: "#c0392b" }}><AlertTriangle size={19} /></span>
                    <span><strong style={{ color: "#c0392b" }}>{dashStats.critico}</strong><span>Críticos</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span className="kpi-icon" style={{ background: "#fef3c7", color: "#a16207" }}><Clock size={19} /></span>
                    <span><strong style={{ color: "#a16207" }}>{dashStats.moderado}</strong><span>Moderados</span></span>
                  </div>
                  <div className="card kpi-card">
                    <span className="kpi-icon" style={{ background: "#e2f6f2", color: "#167d72" }}><CheckCircle2 size={19} /></span>
                    <span><strong style={{ color: "#167d72" }}>{dashStats.optimo}</strong><span>Óptimos / leves</span></span>
                  </div>
                </div>
                <div className="repair-progress">
                  <div className="repair-progress-head">
                    <span><Wrench size={13} /> Avance de reparación</span>
                    <strong>{dashStats.repaired} de {dashStats.total} reparados · {dashStats.total ? Math.round((dashStats.repaired / dashStats.total) * 100) : 0}%</strong>
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
                          <strong>{value === "critico" ? dashVisibleCritico : value === "moderado" ? dashVisibleModerado : dashVisibleOptimo}</strong>
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
                    <div><ScanLine size={15} /><span>Visibles</span><strong>{dashVisible.length}</strong></div>
                    <div><Mountain size={15} /><span>Misiones</span><strong>{dashMissionOptions.length}</strong></div>
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
                    <span className="legend-chip" style={{ background: "#fff1ef", color: "#8f3f31" }}><i style={{ background: "#c0392b" }} />Crítico · {dashVisibleCritico}</span>
                    <span className="legend-chip" style={{ background: "#fef3c7", color: "#a16207" }}><i style={{ background: "#a16207" }} />Moderado · {dashVisibleModerado}</span>
                    <span className="legend-chip" style={{ background: "#e2f6f2", color: "#167d72" }}><i style={{ background: "#167d72" }} />Óptimo · {dashVisibleOptimo}</span>
                    <span className="legend-chip" style={{ background: "#eef2f3", color: "#4c5962" }}><Check size={9} />Reparado · {dashVisibleRepaired}</span>
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
                          disabled={repairBusyId === selectedFinding.id || (selectedFinding.repair_status !== "repaired" && selectedFinding.review_status !== "confirmed")}
                          title={selectedFinding.repair_status !== "repaired" && selectedFinding.review_status !== "confirmed" ? "Solo se pueden marcar como reparados los hallazgos confirmados" : undefined}
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
        </>
      )}

      {screen === "workspace" && (
        <>
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
              <span><Database size={14} /> {health?.database ?? "PostgreSQL"}</span>
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
                    {visibleDetections.map((item) => <div key={item.id} className={`box ${item.review_status}`} style={{ left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.width * 100}%`, height: `${item.height * 100}%`, borderColor: colorForLabel[item.label] ?? fallbackColor }}><span style={{ background: colorForLabel[item.label] ?? fallbackColor }}>{item.label} · {confidence(item.confidence)}</span>{item.review_status === "confirmed" && <i style={{ background: colorForLabel[item.label] ?? fallbackColor }}><Check size={11} /></i>}</div>)}
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
                    <span className="status-pill" style={{ marginTop: 2, background: item.review_status === "confirmed" ? "#e2f6f2" : item.review_status === "rejected" ? "#fdecea" : "#fef3c7", color: item.review_status === "confirmed" ? "#167d72" : item.review_status === "rejected" ? "#c0392b" : "#a16207" }}>
                      {item.review_status === "confirmed" ? <Check size={9} /> : item.review_status === "rejected" ? <XCircle size={9} /> : <CircleDot size={9} />}
                      {item.review_status === "confirmed" ? "Confirmado" : item.review_status === "rejected" ? "Descartado" : "Pendiente"}
                    </span>
                  </div>)}
                </div>
                <button className="button primary full" onClick={() => setView("report")}><FileText size={16} /> Preparar informe</button>
              </aside>
            </section>
          )}

          {view === "report" && mission && (
            <section className="workspace report-layout">
              <article className="card report-preview">
                <div className="report-header"><img className="report-header-logo" src={logoIcon} alt="NeumaDiesel" /><span className="overline">Informe de inspección</span><h2>{mission.name}</h2><p>{mission.segment} · {new Date(mission.created_at).toLocaleDateString("es-CL")}</p>{health?.detector === "mock" && <span className="demo-label"><AlertTriangle size={13} /> Resultados simulados</span>}</div>
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
        </>
      )}

      <footer><span>NeumaDiesel · Proyecto Capstone UCN</span><span><ShieldCheck size={13} /> Frontend y backend desacoplados</span></footer>
    </main>
  );
}
