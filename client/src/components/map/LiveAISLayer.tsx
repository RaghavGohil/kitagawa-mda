"use client";

import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { LiveVessel } from "@/types";
import { API_BASE_URL } from "@/lib/api";

interface LiveAISLayerProps {
    onUpdate: (vessels: Record<number, LiveVessel>) => void;
}

/**
 * LiveAISLayer acts as a background data provider for real-time AIS updates.
 * It manages the WebSocket connection and buffers incoming data,
 * providing batched updates to the parent component for unified rendering.
 * 
 * Performance:
 * - Geographically filters incoming messages to the current map view.
 * - Buffers updates to 1s intervals to prevent React render-storms.
 */
export const LiveAISLayer = ({ onUpdate }: LiveAISLayerProps) => {
    const map = useMap();
    const socketRef = useRef<WebSocket | null>(null);
    const bufferRef = useRef<Record<number, LiveVessel>>({});

    useEffect(() => {
        const apiUrl = API_BASE_URL;
        // Convert http(s) to ws(s)
        const wsProtocol = apiUrl.startsWith("https") ? "wss:" : "ws:";
        const wsHost = apiUrl.replace(/^https?:\/\//, "");

        const socket = new WebSocket(`${wsProtocol}//${wsHost}/api/v1/ais/live/ws`);
        socketRef.current = socket;

        console.log(`[LiveAIS] Attempting connection to: ${wsProtocol}//${wsHost}/api/v1/ais/live/ws`);

        socket.onopen = () => {
            console.log("[LiveAIS] WebSocket Connected");
        };

        socket.onmessage = (event) => {
            try {
                const data: LiveVessel = JSON.parse(event.data);

                // Throttled log for debugging
                if (Math.random() < 0.05) {
                    console.log(`[LiveAIS] Received update for MMSI ${data.mmsi}`);
                }

                // Geographic Pre-filtering: Only buffer if within current view
                const bounds = map.getBounds();
                if (bounds.contains([data.lat, data.lon])) {
                    bufferRef.current[data.mmsi] = data;
                }
            } catch (error) {
                console.error("[LiveAIS] Error parsing message:", error);
            }
        };

        socket.onclose = (event) => {
            console.log(`[LiveAIS] WebSocket Disconnected. Code: ${event.code}, Reason: ${event.reason}`);
        };

        // Sync buffer to parent every 1000ms
        const syncInterval = setInterval(() => {
            if (Object.keys(bufferRef.current).length > 0) {
                onUpdate({ ...bufferRef.current });
                // We clear the buffer to ensure we only push NEW updates
                bufferRef.current = {};
            }
        }, 1000);

        return () => {
            clearInterval(syncInterval);
            if (socket.readyState === WebSocket.OPEN) {
                socket.close();
            }
        };
    }, [onUpdate, map]);

    return null;
};
