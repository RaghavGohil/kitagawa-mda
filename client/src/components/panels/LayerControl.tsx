"use client";

import { useState } from "react";
import { Layers, Route, ChevronDown } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { AnomalyType, ZoneType } from "@/types";
import { anomalyTypeData, zoneTypeData } from "@/data/data";
import { Separator } from "@/components/ui/separator";

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
        <div className="rounded-lg border border-border">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex w-full items-center justify-between px-4 py-3 hover:bg-accent/50 transition-colors rounded-lg"
            >
                <div className="flex items-center gap-2.5">
                    <Layers className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Layers</span>
                </div>
                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
            </button>

            {isExpanded && (
                <div className="border-t border-border">
                    {/* Vessel Types */}
                    <div className="p-4 space-y-3">
                        <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Vessel Types</h4>
                        {Object.entries(anomalyTypeData).map(([id, meta]) => (
                            <label key={id} className="flex items-center justify-between cursor-pointer group py-0.5">
                                <div className="flex items-center gap-2.5">
                                    <div className="h-3 w-3 rounded-full" style={{ backgroundColor: meta.color }} />
                                    <span className="text-sm group-hover:text-foreground transition-colors">{meta.label}</span>
                                </div>
                                <Switch
                                    checked={visibleAnomalyTypes.has(id as AnomalyType)}
                                    onCheckedChange={() => onAnomalyTypesToggle(id as AnomalyType)}
                                />
                            </label>
                        ))}
                    </div>

                    <Separator />

                    {/* Map Overlays */}
                    <div className="p-4 space-y-3">
                        <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Overlays</h4>
                        {Object.entries(zoneTypeData)
                            .filter(([id]) => id === "eez" || id === "shipping_lane")
                            .map(([id, meta]) => (
                                <label key={id} className="flex items-center justify-between cursor-pointer group py-0.5">
                                    <div className="flex items-center gap-2.5">
                                        <div className="h-3 w-3 rounded-full opacity-60" style={{ backgroundColor: meta.color }} />
                                        <span className="text-sm group-hover:text-foreground transition-colors">{meta.label}</span>
                                    </div>
                                    <Switch
                                        checked={visibleZoneTypes.has(id as ZoneType)}
                                        onCheckedChange={() => onZoneTypesToggle(id as ZoneType)}
                                    />
                                </label>
                            ))}

                        <Separator />

                        <label className="flex items-center justify-between cursor-pointer group py-0.5">
                            <div className="flex items-center gap-2.5">
                                <Route className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm font-medium group-hover:text-foreground transition-colors">Vessel Tracks</span>
                            </div>
                            <Switch checked={showTracks} onCheckedChange={onShowTracksChange} />
                        </label>
                    </div>
                </div>
            )}
        </div>
    );
};
