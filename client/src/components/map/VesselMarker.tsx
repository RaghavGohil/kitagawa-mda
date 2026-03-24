"use client";

import { memo } from "react";
import { Marker, Polyline } from "react-leaflet";
import L from "leaflet";
import { Vessel, VesselType } from "@/types";

interface VesselMarkerProps {
    vessel: Vessel;
    isSelected: boolean;
    showTrack: boolean;
    onClick: (vessel: Vessel | null) => void;
    zoom: number;
    playbackTime: Date;
    timeRangeMs?: number;
}

const VesselMarkerComponent = ({
    vessel,
    isSelected,
    showTrack,
    onClick,
    zoom,
    playbackTime,
    timeRangeMs = 2 * 24 * 60 * 60 * 1000,
}: VesselMarkerProps) => {
    const isLive = vessel.id.startsWith("live-");
    const size = isLive ? 28 : 33;

    // Time-based opacity
    const ageMs = playbackTime.getTime() - vessel.position.timestamp.getTime();
    const normalizedAge = Math.max(0, Math.min(1, ageMs / timeRangeMs));
    const timeOpacity = isLive ? 1.0 : Math.max(0.3, 1 - normalizedAge);

    if (ageMs < -5 * 60 * 1000 || ageMs > timeRangeMs) return null;

    let color: string;
    if (isLive) {
        color = "#10b981"; // Emerald Green for Live AIS
    } else {
        color = vessel.color ?? (
            vessel.anomaly.type === "identified" ? "#3b82f6" : "#ef4444"
        );
    }

    const strokeColor = color;
    const strokeWidth = isSelected ? 8 : (ageMs / (1000 * 60 * 60) < 1 ? 6 : 4);

    const hasHeading = vessel.position.heading !== 0 && vessel.position.heading != null;
    const svgContent = hasHeading
        ? `<svg width="${size}" height="${size}" viewBox="-10 -10 120 120" style="transform: rotate(${vessel.position.heading}deg); transition: transform 0.8s linear;">
        <polygon points="50,5 92,95 50,75 8,95" fill="${color}" fill-opacity="${(isSelected ? 0.95 : 0.8) * timeOpacity}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-opacity="${timeOpacity}" />
      </svg>`
        : `<svg width="${size}" height="${size}" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="${isSelected ? 24 : 12}" fill="${color}" fill-opacity="${(isSelected ? 0.95 : 0.5) * timeOpacity}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-opacity="${timeOpacity}" />
      </svg>`;

    const icon = L.divIcon({
        className: "unified-vessel-icon",
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        html: `
      <div style="position: relative; width: ${size}px; height: ${size}px;">
        ${svgContent}
      </div>
    `,
    });

    const trackPositions: [number, number][] = vessel.track?.map(p => [p.lat, p.lng]) || [];
    let jitterLat = 0;
    let jitterLng = 0;
    if (!isLive) {
        const idNum = parseInt(vessel.id.split("-").pop() || "0", 16) || 0;
        jitterLat = ((idNum % 7) - 3) * 0.00008;
        jitterLng = (((idNum / 7) % 7) - 3) * 0.00008;
    }

    const position: [number, number] = [
        vessel.position.lat + jitterLat,
        vessel.position.lng + jitterLng,
    ];

    const isCorrelated = vessel.mmsi && String(vessel.mmsi).trim() !== "";
    const shouldShowTrack = isCorrelated && (showTrack || isSelected);

    return (
        <>
            {shouldShowTrack && trackPositions.length > 1 && (
                <Polyline
                    positions={trackPositions}
                    pathOptions={{
                        color,
                        weight: isSelected ? 3 : 2,
                        opacity: (isSelected ? 0.9 : 0.6) * timeOpacity,
                        dashArray: isSelected ? undefined : "4,4",
                    }}
                />
            )}
            <Marker position={position} icon={icon} eventHandlers={{ click: () => onClick(vessel) }} />
        </>
    );
};

export const VesselMarker = memo(VesselMarkerComponent, (prev, next) => {
    return (
        prev.vessel.id === next.vessel.id &&
        prev.vessel.position.lat === next.vessel.position.lat &&
        prev.vessel.position.lng === next.vessel.position.lng &&
        prev.vessel.position.heading === next.vessel.position.heading &&
        prev.isSelected === next.isSelected &&
        prev.showTrack === next.showTrack &&
        prev.zoom === next.zoom &&
        prev.playbackTime.getTime() === next.playbackTime.getTime()
    );
});
