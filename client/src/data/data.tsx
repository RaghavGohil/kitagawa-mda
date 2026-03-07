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
  ship: { label: "Registry Matched", color: "#60a5fa" }, // Cyber Blue
  unidentified: { label: "No AIS Match", color: "#94a3b8" }, // Muted Slate
};

export const anomalyTypeData: Record<
  AnomalyType,
  { label: string; color: string }
> = {
  identified: { label: "Vessel Matched", color: "#60a5fa" }, // Cyber Blue
  no_anomaly: { label: "Status Normal", color: "#4ade80" }, // Mint Green (muted)
  anomaly: { label: "Target Anomaly", color: "#fb923c" }, // Tactical Orange/Amber
  unidentified: { label: "Unidentified", color: "#94a3b8" }, // Muted Slate
};

export const zoneTypeData: Record<ZoneType, { label: string; color: string }> =
{
  eez: { label: "EEZ Boundary", color: "#60a5fa" },
  restricted: { label: "Restricted Ops", color: "#f87171" }, // Tactical Red
  port: { label: "Port Zone", color: "#4ade80" },
  shipping_lane: { label: "Shipping Corridor", color: "#cbd5e1" }, // Steel/Light Slate
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
