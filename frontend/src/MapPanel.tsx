import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

import type { Mission, MissionImage } from "./types";

type MapPanelProps = {
  mission: Mission;
  selectedImageId?: string;
  onSelectImage?: (image: MissionImage) => void;
};

export default function MapPanel({ mission, selectedImageId, onSelectImage }: MapPanelProps) {
  const locatedImages = mission.images.filter(
    (image) => image.latitude !== null && image.longitude !== null
  );
  if (!locatedImages.length) {
    return (
      <div className="map-empty">
        <strong>Sin coordenadas disponibles</strong>
        <span>Las imágenes con GPS en sus metadatos EXIF aparecerán automáticamente en este mapa.</span>
      </div>
    );
  }
  const center: [number, number] = [
    locatedImages.reduce((total, image) => total + Number(image.latitude), 0) / locatedImages.length,
    locatedImages.reduce((total, image) => total + Number(image.longitude), 0) / locatedImages.length
  ];

  return (
    <MapContainer center={center} zoom={16} scrollWheelZoom className="findings-map">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {locatedImages.map((image) => {
        const activeDetections = image.detections.filter((item) => item.review_status !== "rejected");
        return (
          <CircleMarker
            key={image.id}
            center={[Number(image.latitude), Number(image.longitude)]}
            radius={Math.min(15, 7 + activeDetections.length * 2)}
            pathOptions={{
              color: selectedImageId === image.id ? "#101820" : "#c95f17",
              fillColor: "#f28b32",
              fillOpacity: 0.88,
              weight: selectedImageId === image.id ? 3 : 2
            }}
            eventHandlers={{ click: () => onSelectImage?.(image) }}
          >
            <Popup>
              <strong>{image.filename}</strong><br />
              {activeDetections.length} hallazgos<br />
              {Number(image.latitude).toFixed(6)}, {Number(image.longitude).toFixed(6)}
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
