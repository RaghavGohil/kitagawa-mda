import {
    VesselType,
    AnomalyType,
    ZoneType,
    Vessel,
    Zone,
    DashboardStats,
} from "@/types";

// ===== UI Metadata =====
export const vesselTypeData: Record<VesselType, { label: string; color: string }> = {
    ship: { label: "Registry Matched", color: "#60a5fa" },
    unidentified: { label: "No AIS Match", color: "#94a3b8" },
};

export const anomalyTypeData: Record<AnomalyType, { label: string; color: string }> = {
    identified: { label: "Identified", color: "#10b981" },
    anomaly: { label: "Dark Vessel", color: "#ef4444" },
    out_of_coverage: { label: "Out of Coverage", color: "#6b7280" },
};

export const zoneTypeData: Record<ZoneType, { label: string; color: string }> = {
    eez: { label: "EEZ Boundary", color: "#60a5fa" },
    restricted: { label: "Restricted Ops", color: "#f87171" },
    port: { label: "Port Zone", color: "#4ade80" },
    shipping_lane: { label: "Shipping Corridor", color: "#cbd5e1" },
};

// ===== Helpers =====
export const getAnomalyDescription = (type: AnomalyType): string => {
    switch (type) {
        case "identified": return "Matched to AIS vessel within tolerance";
        case "anomaly": return "Detected in coverage area — no AIS transmission (dark vessel)";
        case "out_of_coverage": return "Detected outside AIS coverage area — status unknown";
        default: return "";
    }
};

// ===== Zones =====
export const zones: Zone[] = [];

// ===== Dashboard Stats =====
export const getDashboardStats = (vessels: Vessel[]): DashboardStats => {
    let totalSpeed = 0;
    let anomaliesDetected = 0;
    let aisGaps = 0;

    vessels.forEach((v) => {
        totalSpeed += v.position.speed;
        if (v.anomaly.type === "anomaly") {
            anomaliesDetected++;
            aisGaps++;
        }
    });

    return {
        activeVessels: vessels.length,
        anomaliesDetected,
        highRiskZones: zones.filter((z) => z.type === "restricted").length,
        aisGaps,
        averageSpeed: Math.round((totalSpeed / vessels.length) * 10) / 10,
        vesselsByType: { ship: vessels.length, unidentified: 0 },
    };
};
