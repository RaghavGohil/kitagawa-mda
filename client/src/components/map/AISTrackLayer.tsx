import { useEffect, useState, useCallback, useRef } from 'react';
import { Polyline, CircleMarker, useMap, useMapEvent } from 'react-leaflet';
import { API_BASE_URL } from '@/lib/api';

interface AISTrack {
    mmsi: number;
    points: { lat: number; lon: number }[];
}

export const AISTrackLayer = ({
    show,
    playbackTime,
    correlatedMmsis = []
}: {
    show: boolean;
    playbackTime: Date;
    correlatedMmsis?: number[];
}) => {
    const [tracks, setTracks] = useState<AISTrack[]>([]);
    const map = useMap();
    const lastFetchParams = useRef<string>("");
    const abortControllerRef = useRef<AbortController | null>(null);

    const fetchTracks = useCallback(async () => {
        if (!show || correlatedMmsis.length === 0) {
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
        const mmsisStr = correlatedMmsis.join(',');

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
    }, [map, show, playbackTime, correlatedMmsis.join(',')]);

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
    const filteredTracks = tracks.filter(t => correlatedMmsis.includes(t.mmsi));

    return (
        <>
            {filteredTracks.map((track) => (
                <div key={`track-group-${track.mmsi}`}>
                    <Polyline
                        positions={track.points.map(p => [p.lat, p.lon])}
                        pathOptions={{
                            color: '#10b981', // Dimmer Emerald
                            weight: 1.5,
                            opacity: 0.4,
                            interactive: false,
                        }}
                    />
                    {track.points.map((p, idx) => (
                        <CircleMarker
                            key={`ais-pt-${track.mmsi}-${idx}`}
                            center={[p.lat, p.lon]}
                            radius={2}
                            pathOptions={{
                                color: '#10b981',
                                fillColor: '#10b981',
                                fillOpacity: 0.6,
                                stroke: false,
                                interactive: false,
                            }}
                        />
                    ))}
                </div>
            ))}
        </>
    );
};
