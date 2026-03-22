"use client";

import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { Polyline, CircleMarker, useMap, useMapEvent } from "react-leaflet";
import { API_BASE_URL } from "@/lib/api";

interface AISTrack {
    mmsi: number;
    points: { lat: number; lon: number; timestamp: string }[];
    centerIdx?: number;
}

/**
 * AISTrackLayer manages the fetching and rendering of AIS trajectories.
 * It provides a unified track visualization for both detected (correlated) 
 * vessels and standalone live ships using a single source of truth (DB).
 */
export const AISTrackLayer = ({
    show,
    playbackTime,
    correlatedVessels = [],
}: {
    show: boolean;
    playbackTime: Date;
    correlatedVessels?: { mmsi: number; lat: number; lon: number; detectionTime: number }[];
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

        const paramsStr = `${bounds.toBBoxString()}-${zoom}-${time_start}-${time_end}-${mmsisStr}`;
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
                limit: "3000",
                time_start,
                time_end,
                mmsis: mmsisStr,
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

    // Filter and slice tracks to be temporally relevant to the playback window
    const filteredTracks = tracks.map(t => {
        const vessel = vesselMap.get(t.mmsi);
        const refTime = vessel ? vessel.detectionTime : playbackTime.getTime();

        let closestIdx = -1;
        let minDiff = Infinity;

        t.points.forEach((p, idx) => {
            if (!p.timestamp) return;
            const pTime = new Date(p.timestamp).getTime();
            const diff = Math.abs(pTime - refTime);
            if (diff < minDiff) {
                minDiff = diff;
                closestIdx = idx;
            }
        });

        if (closestIdx === -1) {
            return { ...t, points: t.points.slice(-15), centerIdx: 7 };
        }

        // Windowing: 10 points before and 10 points after the reference time
        const startIdx = Math.max(0, closestIdx - 10);
        const endIdx = Math.min(t.points.length, closestIdx + 11);
        const slicedPoints = t.points.slice(startIdx, endIdx);
        const newCenterIdx = closestIdx - startIdx;

        return { ...t, points: slicedPoints, centerIdx: newCenterIdx };
    });

    return (
        <>
            {filteredTracks.map((track) => (
                <Fragment key={`track-group-${track.mmsi}`}>
                    {track.points.map((p, idx) => {
                        const nextP = track.points[idx + 1];
                        const distFromCenter = Math.abs(idx - (track.centerIdx ?? 10));
                        const maxDist = 10;
                        const fadeFactor = Math.max(0, 1 - (distFromCenter / maxDist));
                        const fadeOpacity = 0.2 + fadeFactor * 0.7; // Fading relative to playback focus

                        return (
                            <Fragment key={`ais-seg-${track.mmsi}-${idx}`}>
                                <CircleMarker
                                    center={[p.lat, p.lon]}
                                    radius={1.5}
                                    pathOptions={{
                                        color: "#34d399",
                                        fillColor: "#34d399",
                                        fillOpacity: fadeOpacity,
                                        stroke: false,
                                        interactive: false,
                                    }}
                                />
                                {nextP && (
                                    <Polyline
                                        positions={[[p.lat, p.lon], [nextP.lat, nextP.lon]]}
                                        pathOptions={{
                                            color: "#34d399",
                                            weight: 1.5,
                                            opacity: fadeOpacity * 0.7,
                                            interactive: false,
                                        }}
                                    />
                                )}
                            </Fragment>
                        );
                    })}
                </Fragment>
            ))}
        </>
    );
};
