import {
  MapContainer,
  TileLayer,
  ZoomControl,
  ScaleControl,
  useMap,
  useMapEvent,
  useMapEvents,
} from "react-leaflet";
import { Vessel, Zone, ZoneType } from "@/data/data";
import { VesselMarker } from "./VesselMarker";
import { ZoneLayer } from "./ZoneLayer";
import { AISTrackLayer } from "./AISTrackLayer";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";

interface MapViewProps {
  vessels: Vessel[];
  selectedVessel: Vessel | null;
  onVesselSelect: (vessel: Vessel | null) => void;
  showTracks: boolean;
  visibleZoneTypes: Set<ZoneType>;
  playbackTime: Date;
}

// Component to deselect vessel on map click
const MapClickHandler = ({ onClick }: { onClick: () => void }) => {
  useMapEvent("click", () => {
    onClick();
  });
  return null;
};

// Component to track zoom level
const MapZoomListener = ({ onZoom }: { onZoom: (z: number) => void }) => {
  useMapEvents({
    zoomend: (e) => {
      onZoom(e.target.getZoom());
    },
  });
  return null;
};

// Component to center on first vessel once if no vessel is selected
const MapInitialCenter = ({ vessels }: { vessels: Vessel[] }) => {
  const map = useMap();
  const hasCentered = useRef(false);

  useEffect(() => {
    if (!hasCentered.current && vessels.length > 0) {
      const first = vessels[0];
      if (first.position?.lat != null && first.position.lng != null) {
        map.setView([first.position.lat, first.position.lng], 6);
        hasCentered.current = true;
      }
    }
  }, [vessels, map]);

  return null;
};

// Component to auto-zoom to selected vessel
const MapFocusVessel = ({ vessel }: { vessel: Vessel | null }) => {
  const map = useMap();
  const lastVesselId = useRef<string | null>(null);

  useEffect(() => {
    if (vessel?.position?.lat != null && vessel.position.lng != null) {
      if (vessel.id !== lastVesselId.current) {
        // Force zoom 12 for a clear focus using flyTo for robustness
        map.flyTo([vessel.position.lat, vessel.position.lng], 12, {
          animate: true,
          duration: 0.5
        });
        lastVesselId.current = vessel.id;
      }
    } else {
      lastVesselId.current = null;
    }
  }, [vessel, map]);

  return null;
};

export const MapView = ({
  vessels,
  selectedVessel,
  onVesselSelect,
  showTracks,
  visibleZoneTypes,
  playbackTime,
}: MapViewProps) => {
  const [zoom, setZoom] = useState(6);

  return (
    <MapContainer
      className="h-full w-full"
      center={[33.7, -118.2]} // Default to Long Beach/LA area
      zoom={10}
      zoomControl={false}
      attributionControl
    >
      <MapZoomListener onZoom={setZoom} />
      {/* Base Tiles */}
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        attribution="&copy; ESRI"
        maxZoom={15}
      />

      {/* Controls */}
      <ZoomControl position="bottomright" />
      <ScaleControl position="bottomleft" imperial={false} />

      {/* Zones */}
      <ZoneLayer visibleZoneTypes={visibleZoneTypes} />

      {/* Background AIS Tracks */}
      <AISTrackLayer show={showTracks} playbackTime={playbackTime} />

      {/* Vessels */}
      {vessels.map((vessel) => (
        <VesselMarker
          key={vessel.id}
          vessel={vessel}
          isSelected={selectedVessel?.id === vessel.id}
          showTrack={showTracks || selectedVessel?.id === vessel.id}
          onClick={onVesselSelect}
          zoom={zoom}
        />
      ))}

      {/* Auto focus to selected vessel */}
      <MapFocusVessel vessel={selectedVessel} />

      {/* Initial center on load if no selection */}
      {!selectedVessel && <MapInitialCenter vessels={vessels} />}

      {/* Deselect handler */}
      <MapClickHandler onClick={() => onVesselSelect(null)} />
    </MapContainer>
  );
};
