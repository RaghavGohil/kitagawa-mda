"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
    MapContainer,
    TileLayer,
    ZoomControl,
    ScaleControl,
    useMap,
    useMapEvent,
    useMapEvents,
} from "react-leaflet";
import { Vessel, ZoneType } from "@/types";
import { VesselMarker } from "@/components/map/VesselMarker";
import { ZoneLayer } from "@/components/map/ZoneLayer";
import { AISTrackLayer } from "@/components/map/AISTrackLayer";
import "leaflet/dist/leaflet.css";

interface MapViewProps {
    vessels: Vessel[];
    selectedVessel: Vessel | null;
    onVesselSelect: (vessel: Vessel | null) => void;
    showTracks: boolean;
    visibleZoneTypes: Set<ZoneType>;
    playbackTime: Date;
    timeRangeMs?: number;
    onViewChange?: (bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }, zoom: number) => void;
}

// =============================================================================
// SUB-COMPONENTS
// =============================================================================

const MapClickHandler = ({ onClick }: { onClick: () => void }) => {
    useMapEvent("click", () => onClick());
    return null;
};

const MapViewListener = ({ onUpdate }: { onUpdate: (z: number, bounds: L.LatLngBounds) => void }) => {
    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

    useEffect(() => {
        return () => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
        };
    }, []);

    return null;
};

const MapViewFitBounds = () => {
    const map = useMap();
    const hasFitted = useRef(false);

    useEffect(() => {
        if (!hasFitted.current) {
            map.fitBounds([[-70, -180], [70, 180]], { animate: false });
            hasFitted.current = true;
        }
    }, [map]);

    return null;
};

const MapInitialCenter = ({ vessels, enabled }: { vessels: Vessel[]; enabled: boolean }) => {
    const map = useMap();
    const hasCentered = useRef(false);

    useEffect(() => {
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

const MapFocusVessel = ({ vessel }: { vessel: Vessel | null }) => {
    const map = useMap();
    const lastVesselId = useRef<string | null>(null);

    useEffect(() => {
        if (vessel?.position?.lat != null && vessel.position.lng != null) {
            if (vessel.id !== lastVesselId.current) {
                map.flyTo([vessel.position.lat, vessel.position.lng], 12, {
                    animate: true,
                    duration: 0.5,
                });
                lastVesselId.current = vessel.id;
            }
        } else {
            lastVesselId.current = null;
        }
    }, [vessel, map]);

    return null;
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export const MapView = ({
    vessels,
    selectedVessel,
    onVesselSelect,
    showTracks,
    visibleZoneTypes,
    playbackTime,
    timeRangeMs,
    onViewChange,
}: MapViewProps) => {
    const [zoom, setZoom] = useState(3);

    const handleUpdate = useCallback((z: number, bounds: L.LatLngBounds) => {
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
            style={{ background: "oklch(0.18 0.01 240)" }}
            center={[15, 0]}
            zoom={3}
            zoomControl={false}
            attributionControl
            minZoom={3}
            worldCopyJump={false}
            maxBounds={[[-85, -180], [85, 180]]}
            maxBoundsViscosity={1.0}
        >
            <MapViewFitBounds />
            <MapViewListener onUpdate={handleUpdate} />

            <TileLayer
                url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                maxZoom={19}
                noWrap={true}
                bounds={[[-85, -180], [85, 180]]}
            />

            <ZoomControl position="topright" />
            <ScaleControl position="bottomleft" imperial={false} />

            <ZoneLayer visibleZoneTypes={visibleZoneTypes} />

            <AISTrackLayer
                show={showTracks}
                playbackTime={playbackTime}
                correlatedVessels={vessels
                    .filter(v => parseInt(v.mmsi) > 0 && v.position?.lat != null && v.position?.lng != null)
                    .map(v => ({
                        mmsi: parseInt(v.mmsi),
                        lat: v.position.lat,
                        lon: v.position.lng,
                        detectionTime: v.position.timestamp.getTime(),
                    }))}
            />

            {vessels.map((vessel) => (
                <VesselMarker
                    key={vessel.id}
                    vessel={vessel}
                    isSelected={selectedVessel?.id === vessel.id}
                    showTrack={showTracks || selectedVessel?.id === vessel.id}
                    onClick={onVesselSelect}
                    zoom={zoom}
                    playbackTime={playbackTime}
                    timeRangeMs={timeRangeMs}
                />
            ))}

            <MapFocusVessel vessel={selectedVessel} />
            <MapInitialCenter vessels={vessels} enabled={!selectedVessel} />
            <MapClickHandler onClick={() => onVesselSelect(null)} />
        </MapContainer>
    );
};
