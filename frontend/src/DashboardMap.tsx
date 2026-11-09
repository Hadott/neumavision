import { CircleMarker, LayersControl, MapContainer, Popup, TileLayer } from "react-leaflet";

import type { DashboardFinding } from "./types";

export type Criticality = "critico" | "moderado" | "optimo";

export const criticalityColor: Record<Criticality, string> = {
  critico: "#c0392b",
  moderado: "#a16207",
  optimo: "#167d72"
};

export const criticalityLabel: Record<Criticality, string> = {
  critico: "Crítico",
  moderado: "Moderado",
  optimo: "Óptimo"
};

// Las detecciones de "Carpeta Buen Estado" no son una anomalía: siempre se clasifican como "óptimo",
// sin importar la confianza del modelo.
export const GOOD_CONDITION_LABEL = "Carpeta Buen Estado";

export function criticalityOf(confidence: number, label?: string): Criticality {
  if (label === GOOD_CONDITION_LABEL) return "optimo";
  if (confidence >= 0.8) return "critico";
  if (confidence >= 0.6) return "moderado";
  return "optimo";
}

type DashboardMapProps = {
  findings: DashboardFinding[];
  selectedId?: string;
  onSelect?: (finding: DashboardFinding) => void;
};

export default function DashboardMap({ findings, selectedId, onSelect }: DashboardMapProps) {
  const located = findings.filter((item) => item.latitude !== null && item.longitude !== null);
  if (!located.length) {
    return (
      <div className="map-empty dashboard-map">
        <strong>Sin coordenadas disponibles</strong>
        <span>Los hallazgos con GPS en sus metadatos EXIF aparecerán automáticamente en este mapa.</span>
      </div>
    );
  }
  const center: [number, number] = [
    located.reduce((total, item) => total + Number(item.latitude), 0) / located.length,
    located.reduce((total, item) => total + Number(item.longitude), 0) / located.length
  ];

  return (
    <MapContainer center={center} zoom={16} scrollWheelZoom className="dashboard-map">
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Calles">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satélite">
          <TileLayer
            attribution='Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            maxNativeZoom={19}
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      {located.map((item) => {
        const criticality = criticalityOf(item.confidence, item.label);
        const color = criticalityColor[criticality];
        const isSelected = selectedId === item.id;
        const isRepaired = item.repair_status === "repaired";
        return (
          <CircleMarker
            key={item.id}
            center={[Number(item.latitude), Number(item.longitude)]}
            radius={isSelected ? 12 : 8}
            pathOptions={{
              color: isSelected ? "#0b0c0e" : "white",
              weight: isSelected ? 3 : 2,
              fillColor: isRepaired ? "white" : color,
              fillOpacity: isRepaired ? 1 : 0.9
            }}
            eventHandlers={{ click: () => onSelect?.(item) }}
          >
            <Popup>
              <strong>{item.label}</strong> · {criticalityLabel[criticality]}<br />
              {item.mission_name} · {item.mission_segment}<br />
              {isRepaired ? "Reparado" : "Pendiente de reparación"}<br />
              {Number(item.latitude).toFixed(6)}, {Number(item.longitude).toFixed(6)}
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
