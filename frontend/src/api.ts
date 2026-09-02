import type { DashboardFinding, Detection, Health, Mission, MissionSummary, RepairStatus, ReviewStatus } from "./types";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "No fue posible completar la solicitud" }));
    throw new Error(payload.detail || `Error ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),

  listMissions: () => request<MissionSummary[]>("/missions"),

  getMission: (id: string) => request<Mission>(`/missions/${id}`),

  createMission: (name: string, segment: string, files: File[]) => {
    const body = new FormData();
    body.append("name", name);
    body.append("segment", segment);
    files.forEach((file) => body.append("files", file));
    return request<Mission>("/missions", { method: "POST", body });
  },

  createDemo: () => request<Mission>("/missions/demo", { method: "POST" }),

  deleteMission: (missionId: string) =>
    fetch(`${API_URL}/missions/${missionId}`, { method: "DELETE" }).then((response) => {
      if (!response.ok && response.status !== 204) {
        throw new Error(`Error ${response.status}`);
      }
    }),

  detect: (missionId: string) => request<Mission>(`/missions/${missionId}/detect`, { method: "POST" }),

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

  dashboardFindings: () => request<DashboardFinding[]>("/dashboard/findings"),

  imageUrl: (path: string) => `${API_URL.replace(/\/api\/v1$/, "")}${path}`,

  downloadReport: async (missionId: string) => {
    const response = await fetch(`${API_URL}/missions/${missionId}/report`);
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
