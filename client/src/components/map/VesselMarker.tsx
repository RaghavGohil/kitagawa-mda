import { Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import { anomalyTypeData, Vessel, vesselTypeData } from '@/data/data';

interface VesselMarkerProps {
  vessel: Vessel;
  isSelected: boolean;
  showTrack: boolean;
  onClick: (vessel: Vessel) => void;
  zoom: number;
}

/* ===================== COMPONENT ===================== */

export const VesselMarker = ({
  vessel,
  isSelected,
  showTrack,
  onClick,
  zoom,
}: VesselMarkerProps) => {
  // Fixed pixel size for marker
  const size = 32;

  /* ===================== COLOR (HEX) ===================== */

  const color =
    vessel.mmsi === ''
      ? '#94a3b8' // Gray for unidentified
      : vessel.anomaly.type !== 'none'
        ? anomalyTypeData[vessel.anomaly.type].color
        : vesselTypeData.ship.color;

  /* ===================== ZOOM OPACITY ===================== */

  const labelOpacity = zoom <= 8
    ? 0
    : zoom === 9
      ? 0.4
      : zoom === 10
        ? 0.7
        : 1;

  /* ===================== SVG ARROW ICON ===================== */

  const icon = L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `
      <div style="position: relative; width: ${size}px; height: ${size}px;">
        <svg
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
            fill-opacity="${isSelected ? 0.9 : 0.65}"
            stroke="${color}"
            stroke-width="${isSelected ? 6 : 4}"
          />
        </svg>
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

  const trackPositions: [number, number][] = vessel.track.map(p => [
    p.lat,
    p.lng,
  ]);

  return (
    <>
      {trackPositions.length > 1 && (
        <Polyline
          positions={trackPositions}
          pathOptions={{
            color,
            weight: isSelected ? 3 : showTrack ? 2 : 1.5,
            opacity: isSelected ? 0.9 : showTrack ? 0.6 : 0.35,
            dashArray: isSelected ? undefined : '4,4',
          }}
        />
      )}

      <Marker
        position={[vessel.position.lat, vessel.position.lng]}
        icon={icon}
        eventHandlers={{
          click: () => onClick(vessel),
        }}
      />
    </>
  );
};

