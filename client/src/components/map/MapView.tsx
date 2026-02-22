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
import { useEffect, useRef, useState, useCallback } from "react";

interface MapViewProps {
  vessels: Vessel[];
  selectedVessel: Vessel | null;
  onVesselSelect: (vessel: Vessel | null) => void;
  showTracks: boolean;
  visibleZoneTypes: Set<ZoneType>;
  playbackTime: Date;
  onViewChange?: (bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }, zoom: number) => void;
}

// Component to deselect vessel on map click
const MapClickHandler = ({ onClick }: { onClick: () => void }) => {
  useMapEvent("click", () => {
    onClick();
  });
  return null;
};

// Component to track zoom and bounds
const MapViewListener = ({ onUpdate }: { onUpdate: (z: number, bounds: any) => void }) => {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const map = useMapEvents({
    zoomend: () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => onUpdate(map.getZoom(), map.getBounds()), 300);
    },
    moveend: () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => onUpdate(map.getZoom(), map.getBounds()), 300);
    },
  });

  // Cleanup
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return null;
};

// Component to center on first vessel once if no vessel is selected
const MapInitialCenter = ({ vessels, enabled }: { vessels: Vessel[]; enabled: boolean }) => {
  const map = useMap();
  const hasCentered = useRef(false);

  useEffect(() => {
    // Only center if we haven't already, we have vessels, AND it's enabled
    if (enabled && !hasCentered.current && vessels.length > 0) {
      const first = vessels[0];
      if (first.position?.lat != null && first.position.lng != null) {
        map.setView([first.position.lat, first.position.lng], 6);
        hasCentered.current = true;
      }
    }
  }, [vessels.length > 0, map, enabled]);

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
  onViewChange,
}: MapViewProps) => {
  const [zoom, setZoom] = useState(10);

  const handleUpdate = useCallback((z: number, bounds: any) => {
    setZoom(z);
    if (onViewChange) {
      onViewChange({
        minLon: bounds.getWest(),
        minLat: bounds.getSouth(),
        maxLon: bounds.getEast(),
        maxLat: bounds.getNorth(),
      }, z);
    }
  }, [onViewChange]);

  return (
    <MapContainer
      className="h-full w-full"
      center={[33.7, -118.2]} // Default to Long Beach/LA area
      zoom={10}
      zoomControl={false}
      attributionControl
    >
      <MapViewListener onUpdate={handleUpdate} />
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
      <AISTrackLayer
        show={showTracks}
        playbackTime={playbackTime}
        correlatedMmsis={vessels.map(v => parseInt(v.mmsi)).filter(m => m > 0)}
      />

      {/* Vessels */}
      {vessels.map((vessel) => (
        <VesselMarker
          key={vessel.id}
          vessel={vessel}
          isSelected={selectedVessel?.id === vessel.id}
          showTrack={showTracks || selectedVessel?.id === vessel.id}
          onClick={onVesselSelect}
          zoom={zoom}
          playbackTime={playbackTime}
        />
      ))}

      {/* Auto focus to selected vessel */}
      <MapFocusVessel vessel={selectedVessel} />

      {/* Initial center on load if no selection */}
      <MapInitialCenter vessels={vessels} enabled={!selectedVessel} />

      {/* Deselect handler */}
      <MapClickHandler onClick={() => onVesselSelect(null)} />
    </MapContainer>
  );
};
