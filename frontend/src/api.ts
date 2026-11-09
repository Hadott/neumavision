import type { Account, DashboardFinding, Detection, Health, ManualCriticality, Mission, MissionImage, MissionSummary, RepairStatus, ReviewStatus, Session } from "./types";

// Por defecto la API se llama en la misma dirección del sitio; Vite la redirige al backend.
export const API_URL = import.meta.env.VITE_API_URL || "/api/v1";

// ---- Sesión ----
const SESSION_KEY = "neumavision.session";
let currentSession: Session | null = loadSession();
let onUnauthorized: (() => void) | null = null;

function loadSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function getSession(): Session | null {
  return currentSession;
}

export function setSession(session: Session | null) {
  currentSession = session;
  try {
    if (session) window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Si el navegador bloquea el almacenamiento, la sesión dura solo mientras la pestaña esté abierta.
  }
}

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

function authHeaders(): Record<string, string> {
  return currentSession ? { Authorization: `Bearer ${currentSession.token}` } : {};
}

function withFaena(path: string, faenaId?: string) {
  return faenaId ? `${path}?faena_id=${encodeURIComponent(faenaId)}` : path;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...(init?.headers ?? {}) }
    });
  } catch {
    throw new Error("No se pudo conectar con el servidor. Cierra y vuelve a ejecutar npm run dev.");
  }
  if (response.status === 404 && path.startsWith("/auth/")) {
    throw new Error("El servidor no tiene el inicio de sesión. Reinicia el backend para cargar los cambios.");
  }
  if (response.status === 401 && currentSession) {
    onUnauthorized?.();
  }
  if (!response.ok) {
    const fallback = response.status >= 500
      ? "No se pudo conectar con el servidor. Cierra y vuelve a ejecutar npm run dev."
      : "No fue posible completar la solicitud";
    const payload = await response.json().catch(() => ({ detail: fallback }));
    throw new Error(typeof payload.detail === "string" ? payload.detail : `Error ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),

  login: (correo: string, contrasena: string) =>
    request<Session>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ correo, contrasena })
    }),

  me: () => request<Account>("/auth/me"),

  faenas: () => request<Account[]>("/auth/faenas"),
  adminFaenas: () => request<Account[]>("/auth/admin/faenas"),
  createFaena: (nombre: string, correo: string, contrasena: string) =>
    request<Account>("/auth/admin/faenas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, correo, contrasena })
    }),
  updateFaena: (id: string, nombre: string, correo: string) =>
    request<Account>(`/auth/admin/faenas/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, correo })
    }),
  resetFaenaPassword: (id: string, contrasena: string) =>
    request<void>(`/auth/faenas/${id}/password`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contrasena })
    }),

  listMissions: (faenaId?: string) => request<MissionSummary[]>(withFaena("/missions", faenaId)),

  getMission: (id: string) => request<Mission>(`/missions/${id}`),

  createMission: (name: string, segment: string, files: File[], faenaId?: string) => {
    const body = new FormData();
    body.append("name", name);
    body.append("segment", segment);
    if (faenaId) body.append("faena_id", faenaId);
    files.forEach((file) => body.append("files", file));
    return request<Mission>("/missions", { method: "POST", body });
  },

  deleteMission: (missionId: string) =>
    fetch(`${API_URL}/missions/${missionId}`, { method: "DELETE", headers: authHeaders() }).then((response) => {
      if (response.status === 401) onUnauthorized?.();
      if (!response.ok && response.status !== 204) {
        throw new Error(`Error ${response.status}`);
      }
    }),

  detect: (missionId: string) => request<Mission>(`/missions/${missionId}/detect`, { method: "POST" }),
  editMission: (missionId: string, name: string, segment: string) =>
    request<Mission>(`/missions/${missionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, segment })
    }),
  reviewDetection: (missionId: string, detectionId: string, reviewStatus: ReviewStatus) =>
    request<Detection>(`/missions/${missionId}/detections/${detectionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_status: reviewStatus })
    }),

  updateRepairStatus: (missionId: string, detectionId: string, repairStatus: RepairStatus) =>
    request<Detection>(`/missions/${missionId}/detections/${detectionId}/repair`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repair_status: repairStatus })
    }),

  updateImageCriticality: (missionId: string, imageId: string, criticidad: ManualCriticality | null) =>
    request<MissionImage>(`/missions/${missionId}/images/${imageId}/criticidad`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ criticidad_manual: criticidad })
    }),

  dashboardFindings: (faenaId?: string) => request<DashboardFinding[]>(withFaena("/dashboard/findings", faenaId)),

  // Las imágenes se cargan con <img>, que no envía headers: el token va en la URL.
  imageUrl: (path: string) => {
    const url = `${API_URL.replace(/\/api\/v1$/, "")}${path}`;
    return currentSession ? `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(currentSession.token)}` : url;
  },

  downloadReport: async (missionId: string) => {
    const response = await fetch(`${API_URL}/missions/${missionId}/report`, { headers: authHeaders() });
    if (response.status === 401) onUnauthorized?.();
    if (!response.ok) throw new Error("No fue posible generar el informe");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `informe-${missionId.slice(0, 8)}.pdf`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
};
