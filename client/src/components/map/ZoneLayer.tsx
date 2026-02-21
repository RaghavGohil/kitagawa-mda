import { Polygon, Tooltip } from 'react-leaflet';
import { zones, ZoneType, zoneTypeData } from '@/data/data';

interface ZoneLayerProps {
    visibleZoneTypes: Set<ZoneType>
}

/**
 * Derive Leaflet styles from zoneTypeData
 * (single source of truth)
 */
const getZoneStyle = (type: ZoneType) => {
  const baseColor = zoneTypeData[type].color;

  return {
    color: baseColor,
    fillColor: baseColor,
    fillOpacity:
      type === 'eez' ? 0.08 :
      type === 'shipping_lane' ? 0.06 :
      type === 'restricted' ? 0.18 :
      0.14,
    weight: 2,
    dashArray: type === 'eez' ? '8, 6' : undefined,
  };
};

export const ZoneLayer = ({
    visibleZoneTypes
}:ZoneLayerProps) => {
  return (
    <>
      {zones
        .filter(zone => visibleZoneTypes.has(zone.type))
        .map(zone => {
          const style = getZoneStyle(zone.type);

          return (
            <Polygon
              key={zone.id}
              positions={zone.coordinates}
              pathOptions={style}
            >
              <Tooltip sticky>
                <div className="font-sans text-sm">
                  <div className="font-semibold">
                    {zone.name}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {zone.description}
                  </div>
                </div>
              </Tooltip>
            </Polygon>
          );
        })}
    </>
  );
};

