import { Vessel, Alert, DashboardStats, AnomalyType } from "@/data/data";

export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface VesselsResponse {
  vessels: any[]; // Use any to handle backend's summary format
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

// Minimal ApiVessel for the summary list
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
  anomaly_type: "none" | "anomaly";
  is_identified: boolean;
  cog?: number | null;
  sog?: number | null;
}

interface ApiAlert {
  id: string;
  vessel_id: string;
  vessel_name: string;
  type: "anomaly";
  timestamp: string;
}

// Transform backend summary to frontend Vessel model
function transformVesselSummary(api: ApiVesselSummary): Vessel {
  const mmsiVal = api.mmsi;
  const isIdentified = api.is_identified;

  return {
    id: `vessel-${api.v_id}`,
    mmsi: mmsiVal > 0 ? mmsiVal.toString() : "",
    imo: isIdentified ? "9000000" : "",
    name: api.name,
    callSign: isIdentified ? generateCallSign() : "",
    flag: isIdentified ? "International" : "Unknown",
    type: isIdentified ? "ship" : "unidentified",
    length: 150,
    width: 25,
    draught: 10,
    destination: "Open Sea",
    eta: null,
    position: {
      lat: api.lat,
      lng: api.lon,
      timestamp: new Date(api.last_seen),
      speed: api.sog ?? 12.5, // Use actual SOG if available, otherwise placeholder
      heading: api.cog ?? Math.abs((api.v_id * 137 + 42) % 360), // Use actual COG if available
      course: api.cog ?? 0,
    },
    track: [],
    anomaly: {
      type: api.anomaly_type || "none",
      confidence: api.avg_confidence,
      description: "",
    },
    behaviorProfile: {
      typicalSpeed: { min: 5, max: 18, avg: 11.5 },
      typicalRoutes: [],
      deviationScore: 0.1,
    },
    imageName: api.sensor_types?.[0] || "Unknown",
  };
}

function generateCallSign(): string {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  return (
    letters[Math.floor(Math.random() * letters.length)] +
    letters[Math.floor(Math.random() * letters.length)] +
    Math.floor(Math.random() * 10000)
      .toString()
      .padStart(4, "0")
  );
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
  if (options?.satelliteType)
    params.set("satellite_type", options.satelliteType);
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
    anomalyCount: 0, // Backend doesn't return count of anomalies separately in this endpoint yet
  };
}

export async function fetchVessel(vesselId: string): Promise<Vessel> {
  // vesselId is like "vessel-367692620" (identified) or "vessel--470" (unidentified, v_id is negative)
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
    imo: isUnidentified ? "" : `IMO${Math.floor(9000000 + (data.mmsi % 1000000))}`,
    name: data.name,
    callSign: isUnidentified ? "" : generateCallSign(),
    flag: isUnidentified ? "Unknown" : "International",
    type: isUnidentified ? "unidentified" : "ship",
    length: 150,
    width: 25,
    draught: 10,
    destination: "Open Sea",
    eta: null,
    position: {
      lat: latestDetection.lat || latestTrack.lat || 0,
      lng: latestDetection.lon || latestTrack.lon || 0,
      timestamp: new Date(latestDetection.detection_datetime || latestTrack.timestamp || Date.now()),
      speed: latestTrack.sog || 12.5,
      heading: latestTrack.cog || Math.abs((data.v_id * 137 + 42) % 360),
      course: latestTrack.cog || 0,
    },
    track: data.recent_track.map((t: any) => ({
      lat: t.lat,
      lng: t.lon,
      timestamp: new Date(t.timestamp),
      speed: t.sog,
      heading: t.cog,
      course: t.cog,
    })),
    anomaly: {
      type: data.anomaly_type || "none",
      confidence: latestDetection.confidence || 0,
      description: "",
    },
    behaviorProfile: {
      typicalSpeed: { min: 5, max: 18, avg: 11.5 },
      typicalRoutes: [],
      deviationScore: 0.1,
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
      type: "anomaly" as AnomalyType,
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
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(imageNames),
  });
  if (!response.ok) {
    throw new Error(`Failed to trigger pipeline: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchCopernicusProducts(instrument: string = "SAR"): Promise<{ results: any[] }> {
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

export { transformVesselSummary, generateCallSign };
