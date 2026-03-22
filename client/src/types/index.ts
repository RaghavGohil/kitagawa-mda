export type VesselType = "ship" | "unidentified";
export type AnomalyType = "identified" | "anomaly" | "out_of_coverage";

export type ZoneType = "eez" | "restricted" | "port" | "shipping_lane";

export interface VesselPosition {
    lat: number;
    lng: number;
    timestamp: Date;
    speed: number;
    heading: number;
    course: number;
}

export interface Vessel {
    id: string;
    mmsi: string;
    imo?: string;
    name: string;
    callSign?: string;
    flag?: string;
    type: VesselType;
    length?: number;
    width?: number;
    draught?: number;
    destination?: string;
    eta?: string | null;
    position: VesselPosition;
    track: VesselPosition[];
    anomaly: {
        type: AnomalyType;
        confidence: number;
        description: string;
    };
    color?: string;  // Backend-authoritative color from classification
    behaviorProfile?: {
        typicalSpeed: { min: number; max: number; avg: number };
        typicalRoutes: string[];
        deviationScore: number;
    };
    chipUrl?: string;
    imageName?: string;
}

export interface Alert {
    id: string;
    vesselId: string;
    vesselName: string;
    type: "anomaly" | "unidentified_in_coverage";
    timestamp: Date;
}

export interface Zone {
    id: string;
    name: string;
    type: ZoneType;
    coordinates: [number, number][];
    description: string;
}

export interface DashboardStats {
    activeVessels: number;
    anomaliesDetected: number;
    highRiskZones: number;
    aisGaps: number;
    averageSpeed: number;
    vesselsByType: Record<VesselType, number>;
}

export interface LiveVessel {
    mmsi: number;
    timestamp: string;
    sog: number;
    cog: number;
    lat: number;
    lon: number;
}
