"use client";

import { GeoJSON } from "react-leaflet";
import { ZoneType } from "@/types";
import { zoneTypeData } from "@/data/data";
import { useQuery } from "@tanstack/react-query";
import { fetchBoundaries } from "@/lib/api";
import { useMemo } from "react";

interface ZoneLayerProps {
    visibleZoneTypes: Set<ZoneType>;
}

const getZoneStyle = (type: ZoneType) => {
    const meta = zoneTypeData[type] || { color: "#94a3b8" };
    const baseColor = meta.color;

    if (type === "eez") {
        return { color: baseColor, fillColor: baseColor, fillOpacity: 0.03, weight: 0.8, dashArray: "4, 4", opacity: 0.3 };
    }
    if (type === "shipping_lane") {
        return { color: baseColor, fillColor: baseColor, fillOpacity: 0, weight: 0.8, dashArray: "4, 4", opacity: 0.2 };
    }
    if (type === "restricted") {
        return { color: "#f87171", fillColor: "#f87171", fillOpacity: 0.08, weight: 1.5, dashArray: "3, 3", opacity: 0.5 };
    }
    return { color: baseColor, fillColor: baseColor, fillOpacity: 0.06, weight: 1, opacity: 0.4 };
};

export const ZoneLayer = ({ visibleZoneTypes }: ZoneLayerProps) => {
    const { data: boundaries } = useQuery({
        queryKey: ["boundaries", "v2"],
        queryFn: fetchBoundaries,
        staleTime: 0,
        retry: true,
    });

    const filteredData = useMemo(() => {
        if (!boundaries?.features) return null;

        const filtered = (boundaries.features as Array<{ properties?: { type?: string; name?: string } }>).filter(
            (f) => {
                const type = f.properties?.type;
                const name = f.properties?.name || "";
                return (
                    visibleZoneTypes.has(type as ZoneType) ||
                    (visibleZoneTypes.has("shipping_lane") && name.toLowerCase().includes("shipping lane"))
                );
            },
        );

        if (filtered.length === 0) return null;

        return {
            type: "FeatureCollection" as const,
            features: filtered,
        };
    }, [boundaries, visibleZoneTypes]);

    if (!filteredData) return null;

    return (
        <GeoJSON
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            data={filteredData as any}
            interactive={false}
            style={(feature) => {
                const type = feature?.properties?.type as ZoneType;
                return getZoneStyle(type);
            }}
            key={JSON.stringify([...visibleZoneTypes])}
        />
    );
};
