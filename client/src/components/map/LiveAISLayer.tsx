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
    const reconnectCountRef = useRef(0);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        let isMounted = true;

        const connect = () => {
            if (!isMounted) return;

            const apiUrl = API_BASE_URL;
            // Convert http(s) to ws(s)
            const wsProtocol = apiUrl.startsWith("https") ? "wss:" : "ws:";
            const wsHost = apiUrl.replace(/^https?:\/\//, "");
            const wsUrl = `${wsProtocol}//${wsHost}/api/v1/ais/live/ws`;

            console.log(`[LiveAIS] Connecting to: ${wsUrl}`);
            const socket = new WebSocket(wsUrl);
            socketRef.current = socket;

            socket.onopen = () => {
                console.log("[LiveAIS] WebSocket Connected");
                reconnectCountRef.current = 0; // Reset on success
            };

            socket.onmessage = (event) => {
                try {
                    const data: LiveVessel = JSON.parse(event.data);
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
                console.log(`[LiveAIS] WebSocket Disconnected. Code: ${event.code}`);
                // Simple exponential backoff: 1s, 2s, 4s, up to 10s
                if (isMounted && reconnectCountRef.current < 10) {
                    const delay = Math.min(10000, Math.pow(2, reconnectCountRef.current) * 1000);
                    console.log(`[LiveAIS] Reconnecting in ${delay}ms... (attempt ${reconnectCountRef.current + 1})`);
                    reconnectTimeoutRef.current = setTimeout(() => {
                        reconnectCountRef.current++;
                        connect();
                    }, delay);
                }
            };

            socket.onerror = (err) => {
                console.error("[LiveAIS] WebSocket Error:", err);
            };
        };

        connect();

        // Sync buffer to parent every 1000ms
        const syncInterval = setInterval(() => {
            if (Object.keys(bufferRef.current).length > 0) {
                onUpdate({ ...bufferRef.current });
                bufferRef.current = {};
            }
        }, 1000);

        return () => {
            isMounted = false;
            clearInterval(syncInterval);
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
            if (socketRef.current) {
                socketRef.current.close();
                socketRef.current = null;
            }
        };
    }, [onUpdate, map]);

    return null;
};
