import { Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Vessel } from '@/types';
import { anomalyTypeData, vesselTypeData } from '@/data/data';

interface VesselMarkerProps {
  vessel: Vessel;
  isSelected: boolean;
  showTrack: boolean;
  onClick: (vessel: Vessel | null) => void;
  zoom: number;
  playbackTime: Date;
  timeRangeMs?: number;
}

/* ===================== COMPONENT ===================== */

export const VesselMarker = ({
  vessel,
  isSelected,
  showTrack,
  onClick,
  zoom,
  playbackTime,
  timeRangeMs = 2 * 24 * 60 * 60 * 1000, // Default 2 days
}: VesselMarkerProps) => {
  // Fixed pixel size for marker
  const size = 32;

  /* ===================== TIME-BASED OPACITY ===================== */

  // Normalize age relative to the playback window
  const ageMs = playbackTime.getTime() - vessel.position.timestamp.getTime();

  // Linear fade from 1.0 at age 0 to 0.3 at the start of the window
  // Use a minimum of 0.3 opacity for anything in the window
  const normalizedAge = Math.max(0, Math.min(1, ageMs / timeRangeMs));
  const timeOpacity = Math.max(0.3, 1 - normalizedAge);

  // If ship is outside the window, don't show (sanity check, Index.tsx usually filters this)
  if (ageMs < 0 || ageMs > timeRangeMs) return null;

  /* ===================== COLOR (HEX) ===================== */

  const baseColor =
    vessel.type === 'ship' ? vesselTypeData['ship'].color :
      vessel.anomaly.type === 'anomaly' ? anomalyTypeData['anomaly'].color :
        anomalyTypeData['unidentified'].color;

  // Make fresh detections pop more
  const ageHours = ageMs / (1000 * 60 * 60);
  const color = baseColor;
  const strokeColor = baseColor;
  const strokeWidth = isSelected ? 8 : (ageHours < 1 ? 6 : 4);

  /* ===================== ZOOM OPACITY ===================== */

  // Labels fade away on zoom levels
  const labelOpacity = (zoom <= 8
    ? 0
    : zoom === 9
      ? 0.4
      : zoom === 10
        ? 0.7
        : 1) * timeOpacity;

  /* ===================== SVG ICON (arrow or dot) ===================== */

  const hasHeading = vessel.position.heading !== 0 && vessel.position.heading != null;

  const svgContent = hasHeading
    ? // Arrow polygon with heading rotation
    `<svg
          width="${size}"
          height="${size}"
          viewBox="-10 -10 120 120"
          style="
            transform: rotate(${vessel.position.heading}deg);
            transition: transform 0.15s linear;
            cursor: pointer;
            pointer-events: none;
            position: absolute;
            top: 0;
            left: 0;
          "
        >
          <polygon
            points="50,5 92,95 50,75 8,95"
            fill="${color}"
            fill-opacity="${(isSelected ? 0.95 : 0.8) * timeOpacity}"
            stroke="${strokeColor}"
            stroke-width="${strokeWidth}"
            stroke-opacity="${timeOpacity}"
          />
        </svg>`
    : // Circle dot for unknown heading
    `<svg
          width="${size}"
          height="${size}"
          viewBox="0 0 100 100"
          style="
            cursor: pointer;
            pointer-events: none;
            position: absolute;
            top: 0;
            left: 0;
          "
        >
          <circle
            cx="50" cy="50" r="${isSelected ? 32 : 24}"
            fill="${color}"
            fill-opacity="${(isSelected ? 0.95 : 0.7) * timeOpacity}"
            stroke="${strokeColor}"
            stroke-width="${strokeWidth}"
            stroke-opacity="${timeOpacity}"
          />
        </svg>`;

  const icon = L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `
      <div style="position: relative; width: ${size}px; height: ${size}px;">
        ${svgContent}
        <div style="
          opacity: ${labelOpacity};
          position: absolute;
          top: 100%;
          left: 50%;
          transform: translateX(-50%);
          font-size: 10px;
          font-weight: bold;
          color: white;
          text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
          pointer-events: none;
          white-space: nowrap;
          margin-top: 4px;
          transition: opacity 0.2s ease-in-out;
          color: ${color};
        ">
          ${vessel.name}
        </div>
      </div>
    `,
  });

  /* ===================== TRACK ===================== */

  // Only show tracks for correlated ships (those with an MMSI)
  const isCorrelated = vessel.mmsi && vessel.mmsi.trim() !== '';
  const shouldShowTrack = isCorrelated && (showTrack || isSelected);

  const trackPositions: [number, number][] = vessel.track.map(p => [
    p.lat,
    p.lng,
  ]);

  // Add very small jitter based on numerical part of ID to separate perfectly overlapping markers (e.g. from same sensor)
  const idNum = parseInt(vessel.id.split('-').pop() || '0', 16) || 0;
  const jitterLat = ((idNum % 7) - 3) * 0.00008;
  const jitterLng = (((idNum / 7) % 7) - 3) * 0.00008;

  const position: [number, number] = [
    vessel.position.lat + jitterLat,
    vessel.position.lng + jitterLng
  ];

  return (
    <>
      {shouldShowTrack && trackPositions.length > 1 && (
        <Polyline
          positions={trackPositions}
          pathOptions={{
            color,
            weight: isSelected ? 3 : 2,
            opacity: (isSelected ? 0.9 : 0.6) * timeOpacity,
            dashArray: isSelected ? undefined : '4,4',
          }}
        />
      )}

      <Marker
        position={position}
        icon={icon}
        eventHandlers={{
          click: () => onClick(vessel),
        }}
      />
    </>
  );
};

