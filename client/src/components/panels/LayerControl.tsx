import { useState } from 'react';
import { Layers, Ship, TriangleAlert, MapPin, Route, ChevronDown, ChevronUp } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import {
  anomalyTypeData,
  AnomalyType,
  zoneTypeData,
  VesselType,
  ZoneType,
  vesselTypeData,
} from '@/data/data';

interface LayerControlProps {
  visibleVesselTypes: Set<VesselType>;
  visibleAnomalyTypes: Set<AnomalyType>;
  visibleZoneTypes: Set<ZoneType>;
  showTracks: boolean;
  onVesselTypesToggle: (type: VesselType) => void;
  onAnomalyTypesToggle: (type: AnomalyType) => void;
  onZoneTypesToggle: (type: string) => void;
  onShowTracksChange: (show: boolean) => void;
}

export const LayerControl = ({
  visibleVesselTypes,
  visibleAnomalyTypes,
  visibleZoneTypes,
  showTracks,
  onVesselTypesToggle,
  onAnomalyTypesToggle,
  onZoneTypesToggle,
  onShowTracksChange,
}: LayerControlProps) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [vesselTypesExpanded, setVesselTypesExpanded] = useState(true);
  const [anomalyTypesExpanded, setAnomalyTypesExpanded] = useState(true);
  const [zonesExpanded, setZonesExpanded] = useState(true);

  return (
    <div className="rounded-lg">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium border-b hover:text-primary"
      >
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4" />
          Layers
        </div>
        {isExpanded ? <ChevronUp /> : <ChevronDown />}
      </button>

      {isExpanded && (
        <div className="divide-y">
          {/* ===== Vessel Types ===== */}
          <div className="px-3 py-3 space-y-2">
            <button
              onClick={() => setVesselTypesExpanded(!vesselTypesExpanded)}
              className="flex w-full justify-between text-xs uppercase text-muted-foreground"
            >
              <div className="flex items-center gap-2">
                <TriangleAlert className="h-3.5 w-3.5" />
                Vessel Types
              </div>
              {vesselTypesExpanded? <ChevronUp /> : <ChevronDown />}
            </button>

            {vesselTypesExpanded&&
              Object.entries(vesselTypeData).map(([id, meta]) => (
                <label
                  key={id}
                  className="flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: meta.color }}
                    />
                    {meta.label}
                  </div>
                  <Switch
                    checked={visibleVesselTypes.has(id as VesselType)}
                    onCheckedChange={() =>
                      onVesselTypesToggle(id as VesselType)
                    }
                    className="scale-75"
                  />
                </label>
              ))}
          </div>
          
          {/* ===== Anomaly Types ===== */}
          <div className="px-3 py-3 space-y-2">
            <button
              onClick={() => setAnomalyTypesExpanded(!anomalyTypesExpanded)}
              className="flex w-full justify-between text-xs uppercase text-muted-foreground"
            >
              <div className="flex items-center gap-2">
                <TriangleAlert className="h-3.5 w-3.5" />
                Anomaly Types
              </div>
              {anomalyTypesExpanded? <ChevronUp /> : <ChevronDown />}
            </button>

            {anomalyTypesExpanded&&
              Object.entries(anomalyTypeData).map(([id, meta]) => (
                <label
                  key={id}
                  className="flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: meta.color }}
                    />
                    {meta.label}
                  </div>
                  <Switch
                    checked={visibleAnomalyTypes.has(id as AnomalyType)}
                    onCheckedChange={() =>
                      onAnomalyTypesToggle(id as AnomalyType)
                    }
                    className="scale-75"
                  />
                </label>
              ))}
          </div>

          {/* ===== Zones ===== */}
          <div className="px-3 py-3 space-y-2">
            <button
              onClick={() => setZonesExpanded(!zonesExpanded)}
              className="flex w-full justify-between text-xs uppercase text-muted-foreground"
            >
              <div className="flex items-center gap-2">
                <MapPin className="h-3.5 w-3.5" />
                Zones
              </div>
              {zonesExpanded ? <ChevronUp /> : <ChevronDown />}
            </button>

            {zonesExpanded &&
              Object.entries(zoneTypeData).map(([id, meta]) => (
                <label key={id} className="flex justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: meta.color }}
                    />
                    {meta.label}
                  </div>
                  <Switch
                    checked={visibleZoneTypes.has(id as ZoneType)}
                    onCheckedChange={() => onZoneTypesToggle(id as ZoneType)}
                    className="scale-75"
                  />
                </label>
              ))}
          </div>

          {/* ===== Tracks ===== */}
          <div className="px-3 py-3">
            <label className="flex justify-between text-xs">
              <div className="flex items-center gap-2">
                <Route className="h-3.5 w-3.5" />
                Show Tracks
              </div>
              <Switch
                checked={showTracks}
                onCheckedChange={onShowTracksChange}
                className="scale-75"
              />
            </label>
          </div>
        </div>
      )}
    </div>
  );
};

