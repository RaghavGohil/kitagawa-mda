import { useState } from 'react';
import { Layers, TriangleAlert, MapPin, Route, ChevronDown, ChevronUp } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { AnomalyType, ZoneType } from '@/types';
import {
  anomalyTypeData,
  zoneTypeData,
} from '@/data/data';

interface LayerControlProps {
  visibleAnomalyTypes: Set<AnomalyType>;
  visibleZoneTypes: Set<ZoneType>;
  showTracks: boolean;
  onAnomalyTypesToggle: (type: AnomalyType) => void;
  onZoneTypesToggle: (type: ZoneType) => void;
  onShowTracksChange: (show: boolean) => void;
}

export const LayerControl = ({
  visibleAnomalyTypes,
  visibleZoneTypes,
  showTracks,
  onAnomalyTypesToggle,
  onZoneTypesToggle,
  onShowTracksChange,
}: LayerControlProps) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [classificationExpanded, setClassificationExpanded] = useState(true);
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
          {/* ===== Vessel Classification (single consolidated section) ===== */}
          <div className="px-3 py-3 space-y-2">
            <button
              onClick={() => setClassificationExpanded(!classificationExpanded)}
              className="flex w-full justify-between text-xs uppercase text-muted-foreground"
            >
              <div className="flex items-center gap-2">
                <TriangleAlert className="h-3.5 w-3.5" />
                Vessel Classification
              </div>
              {classificationExpanded ? <ChevronUp /> : <ChevronDown />}
            </button>

            {classificationExpanded &&
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
                    onCheckedChange={() => onAnomalyTypesToggle(id as AnomalyType)}
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
              Object.entries(zoneTypeData)
                .filter(([id]) => id === 'eez' || id === 'shipping_lane')
                .map(([id, meta]) => (
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
