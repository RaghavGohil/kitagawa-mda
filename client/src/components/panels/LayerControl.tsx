import { useState } from 'react';
import { Layers, TriangleAlert, MapPin, Route, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
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
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden shadow-md animate-in fade-in duration-300">
      {/* Main Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          "flex w-full items-center justify-between px-[10px] py-[10px] bg-muted/5 border-border hover:bg-muted/10 transition-none group",
          isExpanded ? "border-b" : "border-none"
        )}
      >
        <div className="flex items-center gap-[10px]">
          <Layers className="h-[21px] w-[21px] text-primary" />
          <span className="text-sm font-bold tracking-tight">Map Layers</span>
        </div>
        <div className="flex items-center">
          <ChevronRight className={cn("h-[15px] w-[15px] text-muted-foreground/50 transition-transform duration-200", isExpanded ? "rotate-90" : "rotate-0")} />
        </div>
      </button>

      {isExpanded && (
        <div className="divide-y divide-border">
          {/* ===== Vessel Types ===== */}
          <div className="p-[10px] space-y-[10px]">
            <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Vessel Types</h4>

            <div className="space-y-[10px]">
              {Object.entries(anomalyTypeData).map(([id, meta]) => (
                <label key={id} className="flex items-center justify-between group cursor-pointer">
                  <div className="flex items-center gap-[10px]">
                    <div
                      className="h-3 w-3 rounded-lg shrink-0"
                      style={{ backgroundColor: meta.color }}
                    />
                    <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-none">{meta.label}</span>
                  </div>
                  <Switch
                    checked={visibleAnomalyTypes.has(id as AnomalyType)}
                    onCheckedChange={() => onAnomalyTypesToggle(id as AnomalyType)}
                  />
                </label>
              ))}
            </div>
          </div>

          {/* ===== Geographic Context ===== */}
          <div className="p-[10px] space-y-[10px] bg-muted/5">
            <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Map Overlay</h4>

            <div className="space-y-[10px]">
              {Object.entries(zoneTypeData)
                .filter(([id]) => id === 'eez' || id === 'shipping_lane')
                .map(([id, meta]) => (
                  <label key={id} className="flex justify-between items-center group cursor-pointer">
                    <div className="flex items-center gap-[10px]">
                      <div
                        className="h-3 w-3 rounded-lg shrink-0 opacity-50"
                        style={{ backgroundColor: meta.color }}
                      />
                      <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-none">{meta.label}</span>
                    </div>
                    <Switch
                      checked={visibleZoneTypes.has(id as ZoneType)}
                      onCheckedChange={() => onZoneTypesToggle(id as ZoneType)}
                    />
                  </label>
                ))}

              {/* Tracks */}
              <div className="pt-[10px] border-t border-border">
                <label className="flex justify-between items-center group cursor-pointer">
                  <div className="flex items-center gap-[10px]">
                    <Route className="h-[15px] w-[15px] text-muted-foreground" />
                    <span className="text-sm font-bold text-muted-foreground group-hover:text-foreground transition-none">Vessel Tracks</span>
                  </div>
                  <Switch
                    checked={showTracks}
                    onCheckedChange={onShowTracksChange}
                  />
                </label>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
