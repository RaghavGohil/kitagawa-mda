// ========================
// Kitagawa MDA Data
// ========================

// ===== Types =====
export type VesselType = "ship" | "unidentified";
export type AnomalyType = "none" | "anomaly"; // none = Unidentified None, anomaly = Unidentified Anomaly. "ship" type implies Identified.
export type ZoneType = "eez" | "restricted" | "port" | "shipping_lane";

export interface VesselPosition {
  lat: number;
  lng: number;
  timestamp: Date;
  speed: number; // knots
  heading: number; // degrees
  course: number; // degrees
}

export interface Vessel {
  id: string;
  mmsi: string;
  imo: string;
  name: string;
  callSign: string;
  flag: string;
  type: VesselType; // ALWAYS ship
  length: number;
  width: number;
  draught: number;
  destination: string;
  eta: Date | null;
  position: VesselPosition;
  track: VesselPosition[];
  anomaly: {
    type: AnomalyType;
    confidence: number;
    description: string;
  };
  behaviorProfile: {
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
  type: AnomalyType;
  timestamp: Date;
}

export interface Zone {
  id: string;
  name: string;
  type: "eez" | "restricted" | "port" | "shipping_lane";
  coordinates: [number, number][];
  description: string;
}

// ===== UI Metadata =====
// Combined metadata for the UI representation
export const vesselTypeData: Record<
  VesselType,
  { label: string; color: string }
> = {
  ship: { label: "Identified Vessel", color: "#3B82F6" },
  unidentified: { label: "Unidentified", color: "#94a3b8" },
};

export const anomalyTypeData: Record<
  AnomalyType,
  { label: string; color: string }
> = {
  none: { label: "None", color: "#94a3b8" },
  anomaly: { label: "Anomaly", color: "#FACC15" },
};

export const zoneTypeData: Record<ZoneType, { label: string; color: string }> =
{
  eez: { label: "EEZ Boundaries", color: "#3B82F6" },
  restricted: { label: "Restricted Zones", color: "#EF4444" },
  port: { label: "Port Zones", color: "#22C55E" },
  shipping_lane: { label: "Shipping Lanes", color: "#FB923C" },
};

// ===== Helpers =====
const generateCallSign = (): string => {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  return (
    letters[Math.floor(Math.random() * letters.length)] +
    letters[Math.floor(Math.random() * letters.length)] +
    Math.floor(Math.random() * 10000)
      .toString()
      .padStart(4, "0")
  );
};

const getAnomalyDescription = (type: AnomalyType): string =>
  type === "anomaly"
    ? "Detected anomalous behavior (speed, route, or AIS gap)"
    : "";

// ===== Track Generator =====
const generateTrack = (
  startLat: number,
  startLng: number,
  points: number,
  speedRange: [number, number],
  headingBase: number,
): VesselPosition[] => {
  const track: VesselPosition[] = [];
  let lat = startLat;
  let lng = startLng;
  const now = new Date();

  for (let i = points - 1; i >= 0; i--) {
    const speed =
      speedRange[0] + Math.random() * (speedRange[1] - speedRange[0]);
    const heading = headingBase + (Math.random() - 0.5) * 20;
    const course = heading + (Math.random() - 0.5) * 5;

    track.push({
      lat,
      lng,
      timestamp: new Date(now.getTime() - i * 15 * 60 * 1000),
      speed,
      heading,
      course,
    });

    const distance = (speed * 0.25) / 60;
    lat += (distance * Math.cos((heading * Math.PI) / 180)) / 60;
    lng +=
      (distance * Math.sin((heading * Math.PI) / 180)) /
      (60 * Math.cos((lat * Math.PI) / 180));
  }

  return track;
};

// ===== Zones =====
export const zones: Zone[] = [
  {
    id: "eez-us",
    name: "US East Coast EEZ",
    type: "eez",
    coordinates: [
      [35, -80],
      [35, -70],
      [42, -70],
      [42, -80],
      [35, -80],
    ],
    description: "Exclusive Economic Zone of the United States - East Coast",
  },
  {
    id: "restricted-1",
    name: "Naval Exercise Area",
    type: "restricted",
    coordinates: [
      [37, -75],
      [37, -73],
      [39, -73],
      [39, -75],
      [37, -75],
    ],
    description: "Temporary restricted zone for naval exercises",
  },
  {
    id: "port-norfolk",
    name: "Norfolk Port Zone",
    type: "port",
    coordinates: [
      [36.8, -76.5],
      [36.8, -76.0],
      [37.1, -76.0],
      [37.1, -76.5],
      [36.8, -76.5],
    ],
    description: "Port of Norfolk anchorage and approach",
  },
  {
    id: "shipping-lane-1",
    name: "Atlantic Shipping Lane",
    type: "shipping_lane",
    coordinates: [
      [36, -76],
      [36, -74],
      [40, -72],
      [40, -74],
      [36, -76],
    ],
    description: "Major Atlantic shipping lane",
  },
];

// ===== Vessel Generation =====
const flags = ["Panama", "Liberia", "Singapore", "Japan", "Norway", "USA"];
const destinations = [
  "Singapore",
  "Rotterdam",
  "Shanghai",
  "Los Angeles",
  "Tokyo",
];
const vesselNames = [
  "Ever Given",
  "MSC Oscar",
  "OOCL Hong Kong",
  "Madrid Maersk",
  "CMA CGM Antoine",
];

export const generateVessels = (count = 50): Vessel[] => {
  const vessels: Vessel[] = [];
  const centerLat = 15;
  const centerLng = 115;
  const spread = 20;

  for (let i = 0; i < count; i++) {
    const startLat = centerLat + (Math.random() - 0.5) * spread * 2;
    const startLng = centerLng + (Math.random() - 0.5) * spread * 2;
    const heading = Math.random() * 360;
    const track = generateTrack(startLat, startLng, 20, [5, 18], heading);
    const currentPos = track[track.length - 1];
    const hasAnomaly = Math.random() < 0.2;

    vessels.push({
      id: `vessel-${i}`,
      mmsi: `${200000000 + Math.floor(Math.random() * 600000000)}`,
      imo: `IMO${9000000 + Math.floor(Math.random() * 999999)}`,
      name: vesselNames[i % vesselNames.length],
      callSign: generateCallSign(),
      flag: flags[Math.floor(Math.random() * flags.length)],
      type: "ship",
      length: 50 + Math.random() * 250,
      width: 10 + Math.random() * 50,
      draught: 5 + Math.random() * 15,
      destination:
        destinations[Math.floor(Math.random() * destinations.length)],
      eta: new Date(Date.now() + Math.random() * 7 * 24 * 60 * 60 * 1000),
      position: currentPos,
      track,
      anomaly: {
        type: hasAnomaly ? "anomaly" : "none",
        confidence: hasAnomaly ? 0.6 + Math.random() * 0.35 : 0,
        description: getAnomalyDescription(hasAnomaly ? "anomaly" : "none"),
      },
      behaviorProfile: {
        typicalSpeed: { min: 5, max: 18, avg: 11.5 },
        typicalRoutes: [
          destinations[Math.floor(Math.random() * destinations.length)],
        ],
        deviationScore: hasAnomaly
          ? 0.4 + Math.random() * 0.5
          : Math.random() * 0.2,
      },
    });
  }

  return vessels;
};

export const vessels = generateVessels(50);

// ===== Alerts (GLOBAL) =====
export const alerts: Alert[] = vessels
  .filter((v) => v.anomaly.type === "anomaly")
  .map((v) => ({
    id: `alert-${v.id}`,
    vesselId: v.id,
    vesselName: v.name,
    type: "anomaly" as const,
    timestamp: v.position.timestamp,
  }))
  .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

// ===== Dashboard Stats =====
export interface DashboardStats {
  activeVessels: number;
  anomaliesDetected: number;
  highRiskZones: number;
  aisGaps: number;
  averageSpeed: number;
  vesselsByType: Record<VesselType, number>;
}

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
