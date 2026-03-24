import { Vessel, Alert, DashboardStats, AnomalyType } from "@/types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface VesselsResponse {
    vessels: ApiVesselSummary[];
    total: number;
}

interface AlertsResponse {
    alerts: ApiAlert[];
    total: number;
}

interface StatsResponse {
    active_vessels: number;
    anomalies_detected: number;
    sar_detections: number;
    eo_detections: number;
    average_speed: number;
    vessels_by_type: Record<string, number>;
}

interface ApiVesselSummary {
    mmsi: number;
    v_id: number;
    name: string;
    detection_count: number;
    avg_confidence: number;
    last_seen: string;
    lat: number;
    lon: number;
    sensor_types: string[];
    anomaly_type: AnomalyType;
    is_identified: boolean;
    color?: string;
    cog?: number | null;
    sog?: number | null;
}

interface ApiAlert {
    id: string;
    vessel_id: string;
    vessel_name: string;
    type: string;
    timestamp: string;
}

// Transform backend summary to frontend Vessel model
export function transformVesselSummary(api: ApiVesselSummary): Vessel {
    const mmsiVal = api.mmsi;
    const isIdentified = api.is_identified;

    return {
        id: isIdentified && mmsiVal > 0 ? `vessel-${mmsiVal}` : `unidentified-${api.v_id}`,
        mmsi: mmsiVal > 0 ? mmsiVal.toString() : "",
        name: api.name,
        type: isIdentified ? "ship" : "unidentified",
        color: api.color,  // Backend-authoritative color
        position: {
            lat: api.lat,
            lng: api.lon,
            timestamp: new Date(api.last_seen),
            speed: api.sog ?? 0,
            heading: api.cog ?? 0,
            course: api.cog ?? 0,
        },
        track: [],
        anomaly: {
            type: api.anomaly_type || "unidentified",
            confidence: api.avg_confidence,
            description: "",
        },
        imageName: api.sensor_types?.[0] || "Unknown",
    };
}

// API Functions
export async function fetchVessels(options?: {
    anomalyOnly?: boolean;
    satelliteType?: "SAR" | "EO";
    limit?: number;
    offset?: number;
    bounds?: { minLon: number; minLat: number; maxLon: number; maxLat: number };
    zoom?: number;
}): Promise<{ vessels: Vessel[]; total: number; anomalyCount: number }> {
    const params = new URLSearchParams();

    if (options?.anomalyOnly) params.set("anomaly_only", "true");
    if (options?.satelliteType) params.set("satellite_type", options.satelliteType);
    if (options?.limit) params.set("limit", options.limit.toString());
    if (options?.offset) params.set("offset", options.offset.toString());

    if (options?.bounds) {
        params.set("min_lon", options.bounds.minLon.toString());
        params.set("min_lat", options.bounds.minLat.toString());
        params.set("max_lon", options.bounds.maxLon.toString());
        params.set("max_lat", options.bounds.maxLat.toString());
    }
    if (options?.zoom) params.set("zoom", options.zoom.toString());
    const response = await fetch(`${API_BASE_URL}/api/v1/vessels?${params}`);

    if (!response.ok) {
        throw new Error(`Failed to fetch vessels: ${response.statusText}`);
    }

    const data: VesselsResponse = await response.json();

    return {
        vessels: data.vessels.map(transformVesselSummary),
        total: data.total,
        anomalyCount: 0,
    };
}

export async function fetchVessel(vesselId: string): Promise<Vessel> {
    let backendId: number;
    if (vesselId.startsWith("vessel-")) {
        backendId = parseInt(vesselId.replace("vessel-", ""), 10);
    } else if (vesselId.startsWith("unidentified-")) {
        backendId = -parseInt(vesselId.replace("unidentified-", ""), 10);
    } else {
        backendId = parseInt(vesselId, 10);
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/vessels/${backendId}`);

    if (!response.ok) {
        throw new Error(`Failed to fetch vessel: ${response.statusText}`);
    }

    const data = await response.json();
    const isUnidentified = data.mmsi === 0;
    const mmsiStr = isUnidentified ? "" : data.mmsi.toString();
    const vId = `vessel-${data.v_id}`;
    const latestDetection = data.detections[0] || {};
    const latestTrack = data.recent_track[0] || {};
    const chipUrl = latestDetection.chip_url ? `${API_BASE_URL}${latestDetection.chip_url}` : "";

    return {
        id: vId,
        mmsi: mmsiStr,
        name: data.name,
        type: isUnidentified ? "unidentified" : "ship",
        position: {
            lat: latestDetection.lat || latestTrack.lat || 0,
            lng: latestDetection.lon || latestTrack.lon || 0,
            timestamp: new Date(latestDetection.detection_datetime || latestTrack.timestamp || Date.now()),
            speed: latestTrack.sog ?? 0,
            heading: latestTrack.cog ?? 0,
            course: latestTrack.cog ?? 0,
        },
        track: data.recent_track.map((t: { lat: number; lon: number; timestamp: string; sog: number; cog: number }) => ({
            lat: t.lat,
            lng: t.lon,
            timestamp: new Date(t.timestamp),
            speed: t.sog,
            heading: t.cog,
            course: t.cog,
        })),
        anomaly: {
            type: data.anomaly_type || "unidentified",
            confidence: latestDetection.confidence || 0,
            description: "",
        },
        chipUrl,
        imageName: latestDetection.image_name,
    };
}

export async function fetchAlerts(limit?: number): Promise<Alert[]> {
    const params = limit ? `?limit=${limit}` : "";
    const response = await fetch(`${API_BASE_URL}/api/v1/alerts${params}`);

    if (!response.ok) {
        throw new Error(`Failed to fetch alerts: ${response.statusText}`);
    }

    const data: AlertsResponse = await response.json();

    return data.alerts.map(
        (alert): Alert => ({
            id: alert.id,
            vesselId: alert.vessel_id,
            vesselName: alert.vessel_name,
            type: alert.type as any,
            timestamp: new Date(alert.timestamp),
        }),
    );
}

export async function fetchStats(): Promise<DashboardStats> {
    const response = await fetch(`${API_BASE_URL}/api/v1/stats`);

    if (!response.ok) {
        throw new Error(`Failed to fetch stats: ${response.statusText}`);
    }

    const data: StatsResponse = await response.json();

    return {
        activeVessels: data.active_vessels,
        anomaliesDetected: data.anomalies_detected,
        highRiskZones: 1,
        aisGaps: data.anomalies_detected,
        averageSpeed: data.average_speed,
        vesselsByType: { ship: data.vessels_by_type.ship || 0, unidentified: data.vessels_by_type.unidentified || 0 },
    };
}

export interface PipelineStatus {
    status: "idle" | "running" | "completed" | "failed";
    progress: number;
    download_progress: number;
    inference_progress: number;
    correlation_progress: number;
    chips_progress: number;
    message: string;
    current_stage: string;
    started_at: string | null;
    completed_at: string | null;
    current_image: string | null;
    total_images: number;
    processed_images: string[];
    failed_images: string[];
    queued_images: string[];
}

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
    const response = await fetch(`${API_BASE_URL}/api/v1/pipeline/status`);
    if (!response.ok) {
        throw new Error(`Failed to fetch pipeline status: ${response.statusText}`);
    }
    return response.json();
}

export async function runPipeline(imageNames: string[]): Promise<{ status: string; images: string[] }> {
    const response = await fetch(`${API_BASE_URL}/api/v1/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(imageNames),
    });
    if (!response.ok) {
        throw new Error(`Failed to trigger pipeline: ${response.statusText}`);
    }
    return response.json();
}

export async function fetchCopernicusProducts(instrument: string = "SAR"): Promise<{ results: unknown[] }> {
    const response = await fetch(`${API_BASE_URL}/api/v1/pipeline/search?instrument=${instrument}`);
    if (!response.ok) {
        throw new Error(`Failed to search Copernicus: ${response.statusText}`);
    }
    return response.json();
}

export async function checkApiHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        return response.ok;
    } catch {
        return false;
    }
}

export async function fetchBoundaries(): Promise<{ type: string; features: unknown[] }> {
    const response = await fetch(`${API_BASE_URL}/api/v1/boundaries?cb=${Date.now()}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch boundaries: ${response.statusText}`);
    }
    return response.json();
}

import { LiveVessel } from "@/types";

export async function fetchLivePositions(bounds?: {
    minLon: number;
    minLat: number;
    maxLon: number;
    maxLat: number;
}): Promise<LiveVessel[]> {
    const params = new URLSearchParams();
    if (bounds) {
        params.set("min_lon", bounds.minLon.toString());
        params.set("min_lat", bounds.minLat.toString());
        params.set("max_lon", bounds.maxLon.toString());
        params.set("max_lat", bounds.maxLat.toString());
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/ais/live/positions?${params}`);
    if (!response.ok) {
        return [];
    }
    return response.json();
}
