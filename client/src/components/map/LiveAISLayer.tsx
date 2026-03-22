"use client";

import { useEffect, useRef } from "react";
import { LiveVessel } from "@/types";

interface LiveAISLayerProps {
    onUpdate: (vessels: Record<number, LiveVessel>) => void;
}

/**
 * LiveAISLayer acts as a background data provider for real-time AIS updates.
 * It manages the WebSocket connection and buffers incoming data,
 * providing batched updates to the parent component for unified rendering.
 * It does not render any UI elements itself.
 */
export const LiveAISLayer = ({ onUpdate }: LiveAISLayerProps) => {
    const socketRef = useRef<WebSocket | null>(null);
    const bufferRef = useRef<Record<number, LiveVessel>>({});

    useEffect(() => {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = window.location.host === "localhost" ? "localhost:8000" : window.location.host;
        const socket = new WebSocket(`${protocol}//${host}/api/v1/ais/live/ws`);
        socketRef.current = socket;

        socket.onopen = () => {
            console.log("[LiveAIS] WebSocket Connected (Global Mode)");
        };

        socket.onmessage = (event) => {
            try {
                const data: LiveVessel = JSON.parse(event.data);
                // Perform extreme buffering to maintain UI responsiveness
                bufferRef.current[data.mmsi] = data;
            } catch (error) {
                // Ignore parsing errors
            }
        };

        socket.onclose = () => {
            console.log("[LiveAIS] WebSocket Disconnected");
        };

        // Sync buffer to parent every 1000ms
        const syncInterval = setInterval(() => {
            if (Object.keys(bufferRef.current).length > 0) {
                onUpdate({ ...bufferRef.current });
                // Note: We don't clear the buffer entirely if we want to keep 
                // the "latest" state across syncs, but since the parent 
                // merges it, clearing is fine for bandwidth.
                bufferRef.current = {};
            }
        }, 1000);

        return () => {
            clearInterval(syncInterval);
            if (socket.readyState === WebSocket.OPEN) {
                socket.close();
            }
        };
    }, [onUpdate]);

    return null;
};
