"use client";

import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { Tooltip, Polyline, CircleMarker, Marker, useMap, useMapEvent } from "react-leaflet";
import L from "leaflet";
import { API_BASE_URL } from "@/lib/api";


interface AISTrack {
    mmsi: number;
    points: { lat: number; lon: number; timestamp: string }[];
    centerIdx?: number;
}

const getVesselIcon = (
    color: string,
    isSelected: boolean,
    rotation: number = 0,
    name: string = "",
    labelOpacity: number = 0,
    globalOpacity: number = 1
) => L.divIcon({
    className: "custom-vessel-icon",
    html: `
        <div style="position: relative; width: 30px; height: 30px; opacity: ${globalOpacity}; transition: opacity 0.3s ease;">
            <div style="width: 30px; height: 30px; transform: rotate(${rotation}deg);">
                <svg width="30" height="30" viewBox="-10 -10 120 120" style="cursor: pointer;">
                    <polygon points="50,5 92,95 50,75 8,95" fill="${color}" fill-opacity="${isSelected ? 0.95 : 0.8}" stroke="${color}" stroke-width="${isSelected ? 8 : 4}" />
                </svg>
            </div>
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
    const [zoom, setZoom] = useState(map.getZoom());
    const lastFetchParams = useRef<string>("");
    const abortControllerRef = useRef<AbortController | null>(null);

    // Track zoom level for label visibility
    useMapEvent("zoomend", () => {
        setZoom(map.getZoom());
    });

    const fetchTracks = useCallback(async () => {
        if (!show) {
            setTracks([]);
            return;
        }

        const bounds = map.getBounds();
        const currentZoom = map.getZoom();

        // Round time to 6h chunks to leverage caching while staying responsive
        const chunkMs = 6 * 60 * 60 * 1000;
        const roundedTimeMs = Math.round(playbackTime.getTime() / chunkMs) * chunkMs;

        // Expanded window: 72h back, 24h forward for rich historical context
        const time_start = new Date(roundedTimeMs - 72 * 60 * 60 * 1000).toISOString();
        const time_end = new Date(roundedTimeMs + 24 * 60 * 60 * 1000).toISOString();
        // Bucket center_time to 1h chunks to reduce DB connection churn during scrubbing
        const bucketMs = 1 * 60 * 60 * 1000;
        const bucketedTimeMs = Math.round(playbackTime.getTime() / bucketMs) * bucketMs;
        const focalCenterTime = new Date(bucketedTimeMs).toISOString();

        const mmsisStr = Array.from(new Set(
            (correlatedVessels || [])
                .filter(v => bounds.pad(0.5).contains([v.lat, v.lon]))
                .map(v => v.mmsi)
        )).join(",");

        const paramsStr = `${bounds.toBBoxString()}-${currentZoom}-${time_start}-${time_end}-${focalCenterTime}-${mmsisStr}`;
        if (paramsStr === lastFetchParams.current) return;
        lastFetchParams.current = paramsStr;

        // Discovery threshold: Only allow fetch without vessels if zoomed in past or at level 6
        // Adjusted per user feedback: "if zoom level is 6 show everything"
        if (mmsisStr.length === 0 && currentZoom < 6) {
            setTracks([]);
            return;
        }

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        try {
            const mmsisToFetch = mmsisStr.length > 0 ? mmsisStr : "DISCOVERY";
            console.log(`[AISTrackLayer] Fetching: zoom=${currentZoom}, mode=${mmsisToFetch}, center=${focalCenterTime}`);

            const params = new URLSearchParams({
                min_lon: bounds.getWest().toFixed(6),
                min_lat: bounds.getSouth().toFixed(6),
                max_lon: bounds.getEast().toFixed(6),
                max_lat: bounds.getNorth().toFixed(6),
                zoom: Math.round(currentZoom).toString(),
                limit: "1000",
                time_start,
                time_end,
                center_time: focalCenterTime,
                mmsis: mmsisStr,
            });

            const url = `${API_BASE_URL}/api/v1/ais/tracks?${params}`;
            const response = await fetch(url, { signal: abortControllerRef.current.signal });
            if (response.ok) {
                const data = await response.json();
                console.log(`[AISTrackLayer] Received: ${data.tracks?.length || 0} tracks`);
                const processedTracks = (data.tracks || []).map((t: any) => ({
                    ...t,
                    points: t.points.map((p: any) => ({
                        ...p,
                        time: new Date(p.timestamp).getTime()
                    }))
                }));
                setTracks(processedTracks);
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

    // Determine if we are in "Live" mode or "Historical Playback" mode
    const isLivePlayback = Math.abs(playbackTime.getTime() - Date.now()) < 5 * 60 * 1000;

    // Zoom opacity for labels (aligned with new Zoom 6 threshold)
    const labelOpacity = zoom <= 4 ? 0 : zoom === 5 ? 0.5 : 1;

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
            const t1 = (t.points[i] as any).time;
            const t2 = (t.points[i + 1] as any).time;

            if (refTime >= t1 && refTime <= t2) {
                const factor = (refTime - t1) / (t2 - t1);
                currentPos = {
                    lat: t.points[i].lat + (t.points[i + 1].lat - t.points[i].lat) * factor,
                    lon: t.points[i].lon + (t.points[i + 1].lon - t.points[i].lon) * factor,
                };
                closestIdx = i;
                break;
            }
        }

        // 2. If no perfect interval, find the absolute closest point
        if (!currentPos) {
            t.points.forEach((p: any, idx: number) => {
                const pTime = p.time;
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

        return {
            mmsi: t.mmsi,
            points: t.points, // Use the natural, full track points
            centerIdx: closestIdx,
            currentPos,
            cog,
            vessel: vessel?.vessel,
            name: vessel?.vessel?.name || (t.mmsi ? `${t.mmsi}` : "Dark Vessel")
        };
    }).filter(Boolean);

    return (
        <>
            {trackVisuals.map((track: any) => {
                const firstTime = new Date(track.points[0].timestamp).getTime();
                const lastTime = new Date(track.points[track.points.length - 1].timestamp).getTime();
                const nowTime = playbackTime.getTime();

                // Overall temporal fading (for the ship icon)
                const FADE_WINDOW_MS = 15 * 60 * 1000;
                const fadeIn = Math.min(1, Math.max(0, (nowTime - firstTime) / FADE_WINDOW_MS));
                const fadeOut = nowTime <= lastTime
                    ? 1
                    : Math.min(1, Math.max(0, (FADE_WINDOW_MS - (nowTime - lastTime)) / FADE_WINDOW_MS));
                const temporalOpacity = Math.min(fadeIn, fadeOut);
                const trailColor = "#10b981"; // Unified Emerald Green

                return (
                    <Fragment key={`track-group-${track.mmsi}`}>
                        {/* 
                            Trajectory Focal Points:
                            We only show the immediate 5 points ahead and behind the vessel.
                            This provides a clean, scientific trend without historical clutter.
                        */}
                        {track.points.map((p: any, idx: number) => {
                            const idxDiff = Math.abs(idx - track.centerIdx);
                            if (idxDiff > 5) return null;

                            // Scale opacity and radius by proximity to center
                            const pointOpacity = idxDiff === 0 ? 1.0 : (1 - (idxDiff / 6)) * 0.8;
                            const radius = idxDiff === 0 ? 2.2 : idxDiff <= 2 ? 1.6 : 1.0;

                            return (
                                <CircleMarker
                                    key={`ais-dot-${track.mmsi}-${idx}`}
                                    center={[p.lat, p.lon]}
                                    radius={radius}
                                    pathOptions={{
                                        color: trailColor,
                                        fillColor: trailColor,
                                        fillOpacity: pointOpacity * (isLivePlayback ? 1.0 : temporalOpacity),
                                        stroke: false,
                                        interactive: false,
                                    }}
                                />
                            );
                        })}

                        {/* Ship Icon (Triangle) with precise heading */}
                        {(!isLivePlayback || !track.vessel) && (
                            <Marker
                                position={[track.currentPos.lat, track.currentPos.lon]}
                                icon={getVesselIcon(
                                    trailColor,
                                    String(track.mmsi) === selectedMmsi,
                                    track.cog,
                                    track.name,
                                    labelOpacity,
                                    isLivePlayback ? 1.0 : temporalOpacity
                                )}
                                eventHandlers={{
                                    click: () => {
                                        if (onVesselSelect) {
                                            const syntheticFallback = {
                                                id: String(track.mmsi),
                                                mmsi: String(track.mmsi),
                                                type: track.type || "ship",
                                                name: track.name,
                                                position: {
                                                    lat: track.currentPos?.lat ?? track.points[0]?.lat ?? 0,
                                                    lng: track.currentPos?.lon ?? track.points[0]?.lon ?? 0,
                                                    heading: track.cog ?? 0,
                                                    speed: track.points[0]?.sog ?? 0,
                                                    timestamp: track.points[0]?.timestamp ? new Date(track.points[0].timestamp) : new Date(),
                                                },
                                                anomaly: {}
                                            };
                                            onVesselSelect(track.vessel || syntheticFallback);
                                        }
                                    }
                                }}
                            />
                        )}
                        {/* 
                            The 'Worm' Trajectory:
                            Draw a connecting line only for the immediate 5-point window.
                        */}
                        <Polyline
                            positions={track.points
                                .slice(Math.max(0, track.centerIdx - 5), Math.min(track.points.length, track.centerIdx + 6))
                                .map((p: any) => [p.lat, p.lon])
                            }
                            pathOptions={{
                                color: trailColor,
                                weight: 2.0,
                                opacity: 0.4 * (isLivePlayback ? 1.0 : temporalOpacity),
                                interactive: false,
                            }}
                        />
                    </Fragment>
                );
            })}
        </>
    );
};
