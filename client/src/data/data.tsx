import {
  VesselType,
  AnomalyType,
  ZoneType,
  VesselPosition,
  Vessel,
  Alert,
  Zone,
  DashboardStats,
} from "../types";

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
  identified: { label: "Identified", color: "#3B82F6" },
  no_anomaly: { label: "No Anomaly", color: "#22C55E" },
  anomaly: { label: "Anomaly", color: "#EF4444" },
  unidentified: { label: "Unidentified", color: "#94a3b8" },
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

const getAnomalyDescription = (type: AnomalyType): string => {
  switch (type) {
    case "anomaly": return "Detected vessel not transmitting AIS in covered area";
    case "unidentified": return "Detected outside AIS coverage area — status unknown";
    case "identified": return "Matched to AIS vessel";
    case "no_anomaly": return "Matched to AIS, position verified";
    default: return "";
  }
};

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
