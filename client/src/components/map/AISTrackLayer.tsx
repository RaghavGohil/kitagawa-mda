import { useEffect, useState, useCallback, useRef } from 'react';
import { Polyline, CircleMarker, useMap, useMapEvent } from 'react-leaflet';
import { API_BASE_URL } from '@/lib/api';

interface AISTrack {
    mmsi: number;
    points: { lat: number; lon: number, timestamp: string }[];
}

export const AISTrackLayer = ({
    show,
    playbackTime,
    correlatedVessels = []
}: {
    show: boolean;
    playbackTime: Date;
    correlatedVessels?: { mmsi: number, lat: number, lon: number, detectionTime: number }[];
}) => {
    const [tracks, setTracks] = useState<AISTrack[]>([]);
    const map = useMap();
    const lastFetchParams = useRef<string>("");
    const abortControllerRef = useRef<AbortController | null>(null);

    const fetchTracks = useCallback(async () => {
        if (!show || correlatedVessels.length === 0) {
            setTracks([]);
            return;
        }

        const bounds = map.getBounds();
        const zoom = map.getZoom();

        // Round playback time to the nearest 12 hours to prevent request spam during playback
        const chunkMs = 12 * 60 * 60 * 1000;
        const roundedTimeMs = Math.round(playbackTime.getTime() / chunkMs) * chunkMs;

        // Define a 48-hour window for better continuity
        const time_start = new Date(roundedTimeMs - 24 * 60 * 60 * 1000).toISOString();
        const time_end = new Date(roundedTimeMs + 24 * 60 * 60 * 1000).toISOString();
        const mmsisStr = correlatedVessels.map(v => v.mmsi).join(',');

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
                limit: '2000',
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
        } catch (err: any) {
            if (err.name === 'AbortError') return;
            console.error("Failed to fetch AIS tracks:", err);
        }
    }, [map, show, playbackTime, correlatedVessels.map(v => v.mmsi).join(',')]);

    useMapEvent('moveend', fetchTracks);

    useEffect(() => {
        if (show) {
            fetchTracks();
        } else {
            setTracks([]);
            lastFetchParams.current = "";
        }
    }, [show, playbackTime, fetchTracks]);

    if (!show) return null;

    // Filter tracks to only show those that belong to a currently visible identified vessel
    // and limit to recent ~15 points to avoid clutter, rendering as fading segments
    const vesselMap = new Map(correlatedVessels.map(v => [v.mmsi, v]));
    const filteredTracks = tracks
        .filter(t => vesselMap.has(t.mmsi))
        .map(t => {
            const vessel = vesselMap.get(t.mmsi)!;

            // Find closest point to detection time
            let closestIdx = -1;
            let minDiff = Infinity;

            t.points.forEach((p, idx) => {
                if (!p.timestamp) return;
                const pTime = new Date(p.timestamp).getTime();
                const diff = Math.abs(pTime - vessel.detectionTime);
                if (diff < minDiff) {
                    minDiff = diff;
                    closestIdx = idx;
                }
            });

            if (closestIdx === -1) {
                // Fallback to recent points if no timestamps match
                return { ...t, points: t.points.slice(-21), centerIdx: 10 };
            }

            // Take 10 points before, and 10 after
            const startIdx = Math.max(0, closestIdx - 10);
            const endIdx = Math.min(t.points.length, closestIdx + 11);

            const slicedPoints = t.points.slice(startIdx, endIdx);
            const newCenterIdx = closestIdx - startIdx;

            return { ...t, points: slicedPoints, centerIdx: newCenterIdx };
        });

    return (
        <>
            {filteredTracks.map((track) => (
                <div key={`track-group-${track.mmsi}`}>
                    {/* Render segments between points so they fade out from the center detection point */}
                    {track.points.map((p, idx) => {
                        const nextP = track.points[idx + 1];

                        // Calculate fade based on distance from the center detection point
                        // 0 at ends, 1 at center
                        const distFromCenter = Math.abs(idx - track.centerIdx);
                        const maxDist = 10;
                        const fadeFactor = Math.max(0, 1 - (distFromCenter / maxDist));

                        const fadeOpacity = 0.15 + fadeFactor * 0.75; // 0.15 to 0.90


                        return (
                            <div key={`ais-seg-${track.mmsi}-${idx}`}>
                                <CircleMarker
                                    center={[p.lat, p.lon]}
                                    radius={2}
                                    pathOptions={{
                                        color: '#34d399', // Emerald 400
                                        fillColor: '#34d399',
                                        fillOpacity: fadeOpacity,
                                        stroke: false,
                                        interactive: false,
                                    }}
                                />
                                {nextP && (
                                    <Polyline
                                        positions={[[p.lat, p.lon], [nextP.lat, nextP.lon]]}
                                        pathOptions={{
                                            color: '#34d399',
                                            weight: 2,
                                            opacity: fadeOpacity * 0.8, // Slightly more transparent than the circle
                                            interactive: false,
                                        }}
                                    />
                                )}
                            </div>
                        );
                    })}
                </div>
            ))}
        </>
    );
};
