"use client";

import { useEffect, useState, useCallback } from "react";
import { useMap, useMapEvent } from "react-leaflet";
import L from "leaflet";
import { API_BASE_URL } from "@/lib/api";

interface CoverageCell {
    type: "Feature";
    geometry: { type: "Polygon"; coordinates: number[][][] };
    properties: { vessel_count: number; intensity: number };
}

interface CoverageLayerProps {
    show: boolean;
    days?: number;
}

/**
 * CoverageLayer renders an AIS density-based synthetic coverage overlay.
 * Each grid cell is colored by the number of distinct vessels observed,
 * showing where AIS reception is known (blue = low density, cyan = high).
 * This is a proxy for satellite/terrestrial AIS base station coverage.
 */
export const CoverageLayer = ({ show, days = 30 }: CoverageLayerProps) => {
    const map = useMap();
    const [layerGroup] = useState(() => L.layerGroup());

    const fetchAndRender = useCallback(async () => {
        if (!show) {
            layerGroup.clearLayers();
            return;
        }

        const bounds = map.getBounds();
        const zoom = map.getZoom();

        // Only show grid at reasonable zoom levels
        const gridSize = zoom < 5 ? 2.0 : zoom < 8 ? 1.0 : 0.5;

        const params = new URLSearchParams({
            min_lon: bounds.getWest().toFixed(4),
            min_lat: bounds.getSouth().toFixed(4),
            max_lon: bounds.getEast().toFixed(4),
            max_lat: bounds.getNorth().toFixed(4),
            grid_size: gridSize.toString(),
            days: days.toString(),
        });

        try {
            const res = await fetch(`${API_BASE_URL}/api/v1/ais/coverage-grid?${params}`);
            if (!res.ok) return;

            const data: { features: CoverageCell[] } = await res.json();

            layerGroup.clearLayers();

            data.features.forEach((cell) => {
                const { intensity } = cell.properties;
                const coords = cell.geometry.coordinates[0];
                const latLngs: [number, number][] = coords.map(
                    ([lng, lat]) => [lat, lng] as [number, number]
                );

                const polygon = L.polygon(latLngs, {
                    color: "transparent",
                    fillColor: intensity > 0.7
                        ? "#22d3ee"    // Cyan — high density
                        : intensity > 0.3
                            ? "#38bdf8"   // Sky blue — medium
                            : "#2563eb",  // Dark blue — low density
                    fillOpacity: 0.15 + intensity * 0.25,
                    weight: 1,
                    interactive: true,
                });

                polygon.on("mouseover", (e) => {
                    const layer = e.target;
                    layer.setStyle({
                        fillOpacity: 0.6,
                        color: "#67e8f9",
                        weight: 1,
                    });
                });

                polygon.on("mouseout", (e) => {
                    const layer = e.target;
                    layer.setStyle({
                        fillOpacity: 0.15 + intensity * 0.25,
                        color: "transparent",
                        weight: 1,
                    });
                });

                polygon.on("click", (e) => {
                    map.fitBounds(e.target.getBounds(), { padding: [50, 50] });
                });

                polygon.bindTooltip(
                    `<strong>AIS Reception Density</strong><br/>` +
                    `Vessels seen: ${cell.properties.vessel_count}<br/>` +
                    `<span class="text-xs opacity-70">Click to zoom into this sector</span>`,
                    { sticky: true, className: "custom-tooltip", direction: "top" }
                );

                layerGroup.addLayer(polygon);
            });
        } catch (err) {
            console.error("[CoverageLayer] Failed to fetch:", err);
        }
    }, [map, show, days, layerGroup]);

    // Add/remove layer group from map
    useEffect(() => {
        if (show) {
            layerGroup.addTo(map);
            fetchAndRender();
        } else {
            layerGroup.clearLayers();
            layerGroup.remove();
        }

        return () => {
            layerGroup.clearLayers();
            layerGroup.remove();
        };
    }, [show, map, layerGroup, fetchAndRender]);

    useMapEvent("moveend", () => {
        if (show) fetchAndRender();
    });

    return null;
};
