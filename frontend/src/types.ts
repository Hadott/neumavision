export type ReviewStatus = "pending" | "confirmed" | "rejected";

export type Detection = {
  id: string;
  label: string;
  confidence: number;
  x: number;
  y: number;
  width: number;
  height: number;
  review_status: ReviewStatus;
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

export type Health = {
  status: string;
  detector: string;
  database: string;
};
