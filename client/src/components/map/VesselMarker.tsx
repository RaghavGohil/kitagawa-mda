"use client";

import { Marker, Polyline } from "react-leaflet";
import L from "leaflet";
import { Vessel } from "@/types";
import { anomalyTypeData, vesselTypeData } from "@/data/data";

interface VesselMarkerProps {
    vessel: Vessel;
    isSelected: boolean;
    showTrack: boolean;
    onClick: (vessel: Vessel | null) => void;
    zoom: number;
    playbackTime: Date;
    timeRangeMs?: number;
}

export const VesselMarker = ({
    vessel,
    isSelected,
    showTrack,
    onClick,
    zoom,
    playbackTime,
    timeRangeMs = 2 * 24 * 60 * 60 * 1000,
}: VesselMarkerProps) => {
    const size = 33;

    // Time-based opacity
    const ageMs = playbackTime.getTime() - vessel.position.timestamp.getTime();
    const normalizedAge = Math.max(0, Math.min(1, ageMs / timeRangeMs));
    const timeOpacity = Math.max(0.3, 1 - normalizedAge);

    if (ageMs < 0 || ageMs > timeRangeMs) return null;

    // Color
    const baseColor =
        vessel.type === "ship" ? vesselTypeData["ship"].color :
            vessel.anomaly.type === "anomaly" ? anomalyTypeData["anomaly"].color :
                anomalyTypeData["unidentified"].color;

    const ageHours = ageMs / (1000 * 60 * 60);
    const color = baseColor;
    const strokeColor = baseColor;
    const strokeWidth = isSelected ? 8 : (ageHours < 1 ? 6 : 4);

    // Zoom opacity for labels
    const labelOpacity = (zoom <= 8 ? 0 : zoom === 9 ? 0.4 : zoom === 10 ? 0.7 : 1) * timeOpacity;

    // SVG
    const hasHeading = vessel.position.heading !== 0 && vessel.position.heading != null;

    const svgContent = hasHeading
        ? `<svg width="${size}" height="${size}" viewBox="-10 -10 120 120" style="transform: rotate(${vessel.position.heading}deg); transition: transform 0.15s linear; cursor: pointer; pointer-events: none; position: absolute; top: 0; left: 0;">
        <polygon points="50,5 92,95 50,75 8,95" fill="${color}" fill-opacity="${(isSelected ? 0.95 : 0.8) * timeOpacity}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-opacity="${timeOpacity}" />
      </svg>`
        : `<svg width="${size}" height="${size}" viewBox="0 0 100 100" style="cursor: pointer; pointer-events: none; position: absolute; top: 0; left: 0;">
        <circle cx="50" cy="50" r="${isSelected ? 33 : 24}" fill="${color}" fill-opacity="${(isSelected ? 0.95 : 0.7) * timeOpacity}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-opacity="${timeOpacity}" />
      </svg>`;

    const icon = L.divIcon({
        className: "",
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        html: `
      <div style="position: relative; width: ${size}px; height: ${size}px;">
        ${svgContent}
        <div style="opacity: ${labelOpacity}; position: absolute; top: 100%; left: 50%; transform: translateX(-50%); font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.1em; text-shadow: 0 0 4px rgba(0,0,0,0.9), 0 0 2px rgba(0,0,0,1); pointer-events: none; white-space: nowrap; margin-top: 10px; transition: opacity 0.2s ease-in-out; color: ${color};">
          ${vessel.name}
        </div>
      </div>
    `,
    });

    // Track
    const isCorrelated = vessel.mmsi && vessel.mmsi.trim() !== "";
    const shouldShowTrack = isCorrelated && (showTrack || isSelected);
    const trackPositions: [number, number][] = vessel.track.map(p => [p.lat, p.lng]);

    // Jitter for overlapping markers
    const idNum = parseInt(vessel.id.split("-").pop() || "0", 16) || 0;
    const jitterLat = ((idNum % 7) - 3) * 0.00008;
    const jitterLng = (((idNum / 7) % 7) - 3) * 0.00008;

    const position: [number, number] = [
        vessel.position.lat + jitterLat,
        vessel.position.lng + jitterLng,
    ];

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

            <Marker
                position={position}
                icon={icon}
                eventHandlers={{
                    click: () => onClick(vessel),
                }}
            />
        </>
    );
};
