"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
    MapContainer,
    TileLayer,
    ZoomControl,
    ScaleControl,
    useMap,
    useMapEvent,
    useMapEvents,
} from "react-leaflet";
import { Vessel, ZoneType, LiveVessel, VesselPosition } from "@/types";
import { VesselMarker } from "@/components/map/VesselMarker";
import { ZoneLayer } from "@/components/map/ZoneLayer";
import { AISTrackLayer } from "@/components/map/AISTrackLayer";
import { LiveAISLayer } from "./LiveAISLayer";
import { CoverageLayer } from "./CoverageLayer";
import "leaflet/dist/leaflet.css";

interface MapViewProps {
    vessels: Vessel[];
    selectedVessel: Vessel | null;
    onVesselSelect: (vessel: Vessel | null) => void;
    showTracks: boolean;
    showLiveAIS: boolean;
    showCoverage?: boolean;
    visibleZoneTypes: Set<ZoneType>;
    playbackTime: Date;
    timeRangeMs?: number;
    onViewChange?: (bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }, zoom: number) => void;
}

// Helper to convert a LiveVessel (WebSocket) into a Vessel-like object for unified rendering
const mapLiveToVessel = (live: LiveVessel): Vessel => ({
    id: `live-${live.mmsi}`,
    mmsi: String(live.mmsi),
    name: live.name || `MMSI: ${live.mmsi}`,
    type: (live.type as any) || "ship",
    position: {
        lat: live.lat,
        lng: live.lon,
        timestamp: new Date(live.timestamp),
        speed: live.sog,
        heading: live.cog,
        course: live.cog,
    },
    track: [], // Will be handled by historical track layer
    anomaly: {
        type: "identified", // Live AIS is considered identified data
        confidence: 1.0,
        description: "Real-time AIS position report",
    },
});

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
    showLiveAIS,
    showCoverage = false,
    visibleZoneTypes,
    playbackTime,
    timeRangeMs,
    onViewChange,
}: MapViewProps) => {
    const [zoom, setZoom] = useState(3);
    const [liveVessels, setLiveVessels] = useState<Record<number, LiveVessel>>({});

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

    const handleLiveUpdate = useCallback((updates: Record<number, LiveVessel>) => {
        setLiveVessels(prev => ({ ...prev, ...updates }));
    }, []);

    // Clear live state when layer is toggled off
    useEffect(() => {
        if (!showLiveAIS) {
            setLiveVessels({});
        }
    }, [showLiveAIS]);

    const prevEntitiesRef = useRef<Map<string, Vessel>>(new Map());

    // Merge detected vessels with live AIS vessels
    const allEntities = useMemo(() => {
        const result: Vessel[] = [...vessels];
        const mmsiToVessel = new Map<string, Vessel>();

        // Index detections by MMSI
        vessels.forEach(v => {
            if (v.mmsi) mmsiToVessel.set(v.mmsi, v);
        });

        const isCurrentTime = Math.abs(playbackTime.getTime() - Date.now()) < 5 * 60 * 1000;
        const isLowZoom = zoom < 6;
        const gridSize = 180.0 / Math.pow(2, zoom);

        const liveRepresentatives: Record<string, LiveVessel> = {};

        Object.values(liveVessels).forEach(live => {
            const mmsiStr = String(live.mmsi);
            const existing = mmsiToVessel.get(mmsiStr);

            // Separate Layer Logic:
            // We no longer overwrite the detection's position with live AIS.
            // This allows the user to see the detection at the original 'inference' spot
            // while the live AIS shows where the boat is right now.
            if (showLiveAIS) {
                if (isLowZoom) {
                    const gridX = Math.floor(live.lon / gridSize);
                    const gridY = Math.floor(live.lat / gridSize);
                    const key = `${gridX},${gridY}`;
                    if (!liveRepresentatives[key] || live.mmsi < liveRepresentatives[key].mmsi) {
                        liveRepresentatives[key] = live;
                    }
                } else {
                    // Add as a separate marker even if we have a detection
                    // We give it a slightly different ID to avoid conflict
                    result.push(mapLiveToVessel(live));
                }
            }
        });

        if (isLowZoom && showLiveAIS) {
            Object.values(liveRepresentatives).forEach(live => {
                result.push(mapLiveToVessel(live));
            });
        }

        // --- STABLE IDENTITY PATCH ---
        const nextEntitiesMap = new Map<string, Vessel>();
        const finalResult = result.map(v => {
            const prev = prevEntitiesRef.current.get(v.id);
            // If it's effectively the same vessel at the same spot, reuse the old object reference
            if (prev &&
                prev.position.lat === v.position.lat &&
                prev.position.lng === v.position.lng &&
                prev.position.heading === v.position.heading &&
                prev.name === v.name
            ) {
                nextEntitiesMap.set(v.id, prev);
                return prev;
            }
            nextEntitiesMap.set(v.id, v);
            return v;
        });
        prevEntitiesRef.current = nextEntitiesMap;

        return finalResult;
    }, [vessels, liveVessels, showLiveAIS, playbackTime, zoom]);

    return (
        <MapContainer
            className="h-full w-full"
            style={{ background: "oklch(0.18 0.01 240)" }}
            preferCanvas={true}
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
                className="custom-map-tiles"
                url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                maxZoom={19}
                noWrap={true}
                bounds={[[-85, -180], [85, 180]]}
            />

            <ZoomControl position="topright" />
            <ScaleControl position="bottomleft" imperial={false} />

            <ZoneLayer visibleZoneTypes={visibleZoneTypes} />

            {/* Coverage density overlay — renders below vessel markers */}
            <CoverageLayer show={showCoverage} />

            <LiveAISLayer onUpdate={handleLiveUpdate} />

            <AISTrackLayer
                show={showTracks}
                playbackTime={playbackTime}
                onVesselSelect={onVesselSelect}
                selectedMmsi={selectedVessel?.mmsi}
                correlatedVessels={allEntities
                    .filter(v =>
                        parseInt(v.mmsi) > 0 &&
                        v.position?.lat != null &&
                        v.position?.lng != null
                    )
                    .map(v => ({
                        mmsi: parseInt(v.mmsi),
                        lat: v.position.lat,
                        lon: v.position.lng,
                        detectionTime: v.position.timestamp.getTime(),
                        vessel: v,
                    }))}
            />

            {allEntities.map((vessel) => (
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
