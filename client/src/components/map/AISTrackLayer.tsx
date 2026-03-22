"use client";

import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { Polyline, CircleMarker, Marker, useMap, useMapEvent } from "react-leaflet";
import L from "leaflet";
import { API_BASE_URL } from "@/lib/api";


interface AISTrack {
    mmsi: number;
    points: { lat: number; lon: number; timestamp: string }[];
    centerIdx?: number;
}

const getVesselIcon = (color: string, isSelected: boolean, rotation: number = 0) => L.divIcon({
    className: "custom-vessel-icon",
    html: `
        <div style="position: relative; width: 30px; height: 30px; transform: rotate(${rotation}deg);">
            <svg width="30" height="30" viewBox="-10 -10 120 120" style="cursor: pointer;">
                <polygon points="50,5 92,95 50,75 8,95" fill="${color}" fill-opacity="${isSelected ? 0.95 : 0.8}" stroke="${color}" stroke-width="${isSelected ? 8 : 4}" />
            </svg>
        </div>
    `,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
});

/**
 * AISTrackLayer manages the fetching and rendering of AIS trajectories.
 * It provides a unified track visualization for both detected (correlated) 
 * vessels and standalone live ships using a single source of truth (DB).
 */
export const AISTrackLayer = ({
    show,
    playbackTime,
    correlatedVessels = [],
    onVesselSelect,
    selectedMmsi,
}: {
    show: boolean;
    playbackTime: Date;
    correlatedVessels?: { mmsi: number; lat: number; lon: number; detectionTime: number; vessel?: any }[];
    onVesselSelect?: (vessel: any) => void;
    selectedMmsi?: string | null;
}) => {
    const [tracks, setTracks] = useState<AISTrack[]>([]);
    const map = useMap();
    const lastFetchParams = useRef<string>("");
    const abortControllerRef = useRef<AbortController | null>(null);

    const fetchTracks = useCallback(async () => {
        // Only fetch if enabled and there are MMSIs to track
        if (!show || correlatedVessels.length === 0) {
            setTracks([]);
            return;
        }

        const bounds = map.getBounds();
        const zoom = map.getZoom();

        // Round time to 12h chunks to leverage caching and reduce API calls
        const chunkMs = 12 * 60 * 60 * 1000;
        const roundedTimeMs = Math.round(playbackTime.getTime() / chunkMs) * chunkMs;

        // Fetch wide window (24h) around playback time
        const time_start = new Date(roundedTimeMs - 24 * 60 * 60 * 1000).toISOString();
        const time_end = new Date(roundedTimeMs + 24 * 60 * 60 * 1000).toISOString();
        const mmsisStr = Array.from(new Set(correlatedVessels.map(v => v.mmsi))).join(",");

        const paramsStr = `${bounds.toBBoxString()}-${zoom}-${time_start}-${time_end}`;
        if (paramsStr === lastFetchParams.current) return;
        lastFetchParams.current = paramsStr;

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        try {
            const params = new URLSearchParams({
                min_lon: bounds.getWest().toFixed(6),
                min_lat: bounds.getSouth().toFixed(6),
                max_lon: bounds.getEast().toFixed(6),
                max_lat: bounds.getNorth().toFixed(6),
                zoom: zoom.toString(),
                limit: "1000", // Sufficient for local viewport
                time_start,
                time_end,
            });

            const url = `${API_BASE_URL}/api/v1/ais/tracks?${params}`;
            const response = await fetch(url, { signal: abortControllerRef.current.signal });
            if (response.ok) {
                const data = await response.json();
                setTracks(data.tracks || []);
            }
        } catch (err: unknown) {
            if (err instanceof Error && err.name === "AbortError") return;
            console.error("Failed to fetch AIS tracks:", err);
        }
    }, [map, show, playbackTime, correlatedVessels]);

    useMapEvent("moveend", fetchTracks);

    useEffect(() => {
        if (show) {
            fetchTracks();
        } else {
            setTracks([]);
            lastFetchParams.current = "";
        }
    }, [show, playbackTime, fetchTracks]);

    if (!show) return null;

    const vesselMap = new Map(correlatedVessels.map(v => [v.mmsi, v]));

    // Find interpolation between two points
    const interpolate = (p1: any, p2: any, time: number) => {
        const t1 = new Date(p1.timestamp).getTime();
        const t2 = new Date(p2.timestamp).getTime();
        const factor = (time - t1) / (t2 - t1);
        return {
            lat: p1.lat + (p2.lat - p1.lat) * factor,
            lon: p1.lon + (p2.lon - p1.lon) * factor,
        };
    };

    // Process tracks to find current vessel position + context points
    const trackVisuals = tracks.map(t => {
        const vessel = vesselMap.get(t.mmsi);
        const refTime = playbackTime.getTime();

        let currentPos: { lat: number, lon: number } | null = null;
        let closestIdx = -1;
        let minDiff = Infinity;

        // 1. Find the best interval for the reference time
        for (let i = 0; i < t.points.length - 1; i++) {
            const t1 = new Date(t.points[i].timestamp).getTime();
            const t2 = new Date(t.points[i + 1].timestamp).getTime();

            if (refTime >= t1 && refTime <= t2) {
                currentPos = interpolate(t.points[i], t.points[i + 1], refTime);
                closestIdx = i;
                break;
            }
        }

        // 2. If no perfect interval, find the absolute closest point
        if (!currentPos) {
            t.points.forEach((p, idx) => {
                const pTime = new Date(p.timestamp).getTime();
                const diff = Math.abs(pTime - refTime);
                if (diff < minDiff) {
                    minDiff = diff;
                    closestIdx = idx;
                }
            });
            if (closestIdx !== -1) {
                currentPos = { lat: t.points[closestIdx].lat, lon: t.points[closestIdx].lon };
            }
        }

        if (closestIdx === -1 || !currentPos) return null;

        const currentPoint = t.points[closestIdx] as any;
        const cog = currentPoint.cog || 0;

        // Windowing: 10 points before and 10 points after the reference time
        const startIdx = Math.max(0, closestIdx - 10);
        const endIdx = Math.min(t.points.length, closestIdx + 11);
        const slicedPoints = t.points.slice(startIdx, endIdx);
        const newCenterIdx = closestIdx - startIdx;

        return { mmsi: t.mmsi, points: slicedPoints, centerIdx: newCenterIdx, currentPos, cog, vessel: vessel?.vessel };
    }).filter(Boolean);

    return (
        <>
            {trackVisuals.map((track: any) => (
                <Fragment key={`track-group-${track.mmsi}`}>
                    <Polyline
                        positions={track.points.map((p: any) => [p.lat, p.lon])}
                        pathOptions={{
                            color: "#34d399",
                            weight: 1.5,
                            opacity: 0.4,
                            interactive: false,
                        }}
                    />

                    {/* Render sparse dots for texture - fewer points = better performance */}
                    {track.points.filter((_: any, i: number) => i % 4 === 0).map((p: any, idx: number) => (
                        <CircleMarker
                            key={`ais-dot-${track.mmsi}-${idx}`}
                            center={[p.lat, p.lon]}
                            radius={1.2}
                            pathOptions={{
                                color: "#34d399",
                                fillColor: "#34d399",
                                fillOpacity: 0.5,
                                stroke: false,
                                interactive: false,
                            }}
                        />
                    ))}

                    {/* Render the actual ship icon at its historical time-travel position */}
                    <Marker
                        position={[track.currentPos.lat, track.currentPos.lon]}
                        icon={getVesselIcon("#34d399", String(track.mmsi) === selectedMmsi, track.cog)}
                        eventHandlers={{
                            click: () => {
                                if (onVesselSelect) {
                                    onVesselSelect(track.vessel || { id: String(track.mmsi), mmsi: String(track.mmsi), type: 'ship' });
                                }
                            }
                        }}
                    />
                </Fragment>
            ))}
        </>
    );
};
