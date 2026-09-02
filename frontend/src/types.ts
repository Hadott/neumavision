export type ReviewStatus = "pending" | "confirmed" | "rejected";
export type RepairStatus = "pending" | "repaired";

export type Detection = {
  id: string;
  label: string;
  confidence: number;
  x: number;
  y: number;
  width: number;
  height: number;
  review_status: ReviewStatus;
  repair_status: RepairStatus;
  created_at: string;
};

export type MissionImage = {
  id: string;
  filename: string;
  width: number;
  height: number;
  latitude: number | null;
  longitude: number | null;
  image_url: string;
  detections: Detection[];
};

export type Mission = {
  id: string;
  name: string;
  segment: string;
  status: string;
  created_at: string;
  images: MissionImage[];
};

export type MissionSummary = {
  id: string;
  name: string;
  segment: string;
  status: string;
  created_at: string;
  image_count: number;
  detection_count: number;
  pending_count: number;
  confirmed_count: number;
};

export type DashboardFinding = {
  id: string;
  label: string;
  confidence: number;
  review_status: ReviewStatus;
  repair_status: RepairStatus;
  created_at: string;
  x: number;
  y: number;
  width: number;
  height: number;
  image_id: string;
  image_filename: string;
  image_url: string;
  latitude: number | null;
  longitude: number | null;
  mission_id: string;
  mission_name: string;
  mission_segment: string;
};

export type Health = {
  status: string;
  detector: string;
  database: string;
};
