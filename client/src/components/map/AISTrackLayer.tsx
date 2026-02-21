import { useEffect, useState } from 'react';
import { Polyline, useMap, useMapEvent } from 'react-leaflet';
import { API_BASE_URL } from '@/lib/api';

interface AISTrack {
    mmsi: number;
    points: { lat: number; lon: number }[];
}

export const AISTrackLayer = ({ show, playbackTime }: { show: boolean; playbackTime: Date }) => {
    const [tracks, setTracks] = useState<AISTrack[]>([]);
    const map = useMap();

    useMapEvent('moveend', () => {
        if (show) fetchTracks();
    });

    const fetchTracks = async () => {
        const bounds = map.getBounds();
        const zoom = map.getZoom();

        if (zoom < 8) {
            setTracks([]);
            return;
        }

        try {
            // Define a 24-hour window around playbackTime for historical AIS context
            const time_start = new Date(playbackTime.getTime() - 12 * 60 * 60 * 1000).toISOString();
            const time_end = new Date(playbackTime.getTime() + 12 * 60 * 60 * 1000).toISOString();

            const params = new URLSearchParams({
                min_lon: bounds.getWest().toFixed(6),
                min_lat: bounds.getSouth().toFixed(6),
                max_lon: bounds.getEast().toFixed(6),
                max_lat: bounds.getNorth().toFixed(6),
                zoom: zoom.toString(),
                limit: '100',
                time_start,
                time_end,
            });

            const url = `${API_BASE_URL}/api/v1/ais/tracks?${params}`;
            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                setTracks(data.tracks || []);
            }
        } catch (err) {
            console.error("Failed to fetch AIS tracks:", err);
        }
    };

    useEffect(() => {
        if (show) {
            fetchTracks();
        } else {
            setTracks([]);
        }
    }, [show, playbackTime]);

    if (!show) return null;

    return (
        <>
            {tracks.map((track) => (
                <Polyline
                    key={`ais-track-${track.mmsi}`}
                    positions={track.points.map(p => [p.lat, p.lon])}
                    pathOptions={{
                        color: '#34d399', // Emerald/Cyan for better contrast on dark map
                        weight: 2,
                        opacity: 0.6,
                        dashArray: '5, 10',
                        interactive: false,
                    }}
                />
            ))}
        </>
    );
};
