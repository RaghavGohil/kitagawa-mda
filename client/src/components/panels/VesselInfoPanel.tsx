"use client";

import { Ship, Anchor, AlertTriangle, Loader2, Navigation, Clock, MapPin, Radar } from "lucide-react";
import { Vessel } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { anomalyTypeData, getAnomalyDescription } from "@/data/data";

interface VesselInfoPanelProps {
    vessel: Vessel;
    isLoading?: boolean;
    onIdentify?: (vesselId: string) => Promise<void>;
}

const InfoRow = ({ label, value, mono }: { label: string; value: string | undefined | null; mono?: boolean }) => (
    <div className="flex justify-between items-center py-1.5">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={cn("text-sm text-right", mono && "font-mono")}>{value || "—"}</span>
    </div>
);

export const VesselInfoPanel = ({ vessel, isLoading, onIdentify }: VesselInfoPanelProps) => {
    const isAnomaly = vessel.anomaly.type === "anomaly";
    const isOutOfCoverage = vessel.anomaly.type === "out_of_coverage";
    const isLive = vessel.id.startsWith("live-");

    // Use backend-authoritative color, fallback to anomaly type data
    const statusColor = vessel.color
        ?? anomalyTypeData[vessel.anomaly.type]?.color
        ?? "#6b7280";

    const statusLabel = anomalyTypeData[vessel.anomaly.type]?.label ?? "Unknown";
    const statusDescription = getAnomalyDescription(vessel.anomaly.type);

    return (
        <div className="flex flex-col w-full">
            {/* Vessel identity header */}
            <div className="p-5 flex items-center gap-4">
                <div
                    className="h-12 w-12 rounded-lg border flex items-center justify-center shrink-0"
                    style={{ borderColor: statusColor, color: statusColor, backgroundColor: `${statusColor}10` }}
                >
                    <Ship className="h-6 w-6" />
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="text-base font-semibold truncate">{vessel.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                        <Badge
                            variant="outline"
                            className="text-xs"
                            style={{ borderColor: statusColor, color: statusColor }}
                        >
                            {statusLabel}
                        </Badge>
                        {isLive && (
                            <Badge variant="outline" className="text-xs border-emerald-500 text-emerald-500">
                                <span className="relative flex h-1.5 w-1.5 mr-1">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                                </span>
                                LIVE
                            </Badge>
                        )}
                        {vessel.mmsi && (
                            <span className="text-xs text-muted-foreground font-mono">MMSI {vessel.mmsi}</span>
                        )}
                    </div>
                </div>
            </div>

            {/* Classification status banner */}
            <div
                className="mx-5 p-3 rounded-lg border flex items-center gap-3"
                style={{
                    borderColor: `${statusColor}30`,
                    backgroundColor: `${statusColor}08`,
                }}
            >
                <Radar className="h-4 w-4 shrink-0" style={{ color: statusColor }} />
                <div>
                    <p className="text-xs font-semibold" style={{ color: statusColor }}>{statusLabel}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{statusDescription}</p>
                </div>
            </div>

            {/* Ship chip image */}
            <div className="mx-5 mt-4 h-40 bg-secondary rounded-lg overflow-hidden flex items-center justify-center border border-border">
                {isLoading ? (
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                ) : vessel.chipUrl ? (
                    <img src={vessel.chipUrl} alt={vessel.name} className="w-full h-full object-cover" />
                ) : (
                    <div className="flex flex-col items-center gap-2 text-muted-foreground/30">
                        <Anchor className="h-10 w-10" />
                        <span className="text-sm">No image available</span>
                    </div>
                )}
            </div>

            {/* Dark vessel warning or Identify status */}
            {isAnomaly ? (
                <div className="mx-5 mt-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20">
                    <div className="flex gap-3">
                        <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-red-500">Dark Vessel Alert</p>
                            <p className="text-sm text-muted-foreground mt-1">
                                This vessel was detected in an area with AIS coverage but is not transmitting an AIS signal.
                            </p>
                        </div>
                    </div>
                </div>
            ) : isOutOfCoverage ? (
                <div className="mx-5 mt-4 p-4 rounded-lg bg-blue-500/10 border border-blue-500/20">
                    <div className="flex gap-3 items-center">
                        <Radar className="h-5 w-5 text-blue-500 shrink-0" />
                        <div className="flex-1">
                            <p className="text-sm font-semibold text-blue-500">Unidentified Vessel</p>
                            <p className="text-xs text-muted-foreground mt-0.5">No matching AIS data found in this area/time.</p>
                        </div>
                    </div>
                </div>
            ) : null}

            <Separator className="my-4" />

            {/* Registration */}
            <div className="px-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2">Registration</h4>
                <InfoRow label="MMSI" value={vessel.mmsi} mono />
                <InfoRow label="IMO" value={vessel.imo} mono />
                <InfoRow label="Call Sign" value={vessel.callSign} mono />
                <InfoRow label="Flag" value={vessel.flag} />
            </div>

            <Separator className="my-4" />

            {/* Navigation & Voyage */}
            <div className="px-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Navigation className="h-3.5 w-3.5" />
                    Voyage Info
                </h4>
                <InfoRow label="Destination" value={vessel.destination} />
                <InfoRow label="ETA" value={vessel.eta} />
                <InfoRow label="Position" value={vessel.position.lat != null ? `${vessel.position.lat.toFixed(4)}, ${vessel.position.lng.toFixed(4)}` : undefined} mono />
                <InfoRow label="Speed" value={vessel.position.speed != null ? `${vessel.position.speed.toFixed(1)} kn` : undefined} />
                <InfoRow label="Heading" value={vessel.position.heading != null ? `${vessel.position.heading.toFixed(0)}°` : undefined} />
                <InfoRow label="Course" value={vessel.position.course != null ? `${vessel.position.course.toFixed(0)}°` : undefined} />
            </div>

            <Separator className="my-4" />

            {/* Specifications */}
            <div className="px-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2">Specifications</h4>
                <InfoRow label="Length" value={vessel.length ? `${vessel.length.toFixed(0)} m` : undefined} />
                <InfoRow label="Width" value={vessel.width ? `${vessel.width.toFixed(0)} m` : undefined} />
                <InfoRow label="Draught" value={vessel.draught ? `${vessel.draught.toFixed(1)} m` : undefined} />
            </div>

            <Separator className="my-4" />

            {/* Detection Info */}
            <div className="px-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Clock className="h-3.5 w-3.5" />
                    Detection
                </h4>
                <InfoRow label="Last Seen" value={vessel.position.timestamp ? format(vessel.position.timestamp, "MMM dd, yyyy HH:mm") : undefined} />
                <InfoRow label="Confidence" value={vessel.anomaly.confidence != null ? `${(vessel.anomaly.confidence * 100).toFixed(1)}%` : undefined} />
                <InfoRow label="Classification" value={statusLabel} />
            </div>

            {vessel.imageName && (
                <>
                    <Separator className="my-4" />
                    <div className="px-5 pb-5">
                        <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2 flex items-center gap-2">
                            <MapPin className="h-3.5 w-3.5" />
                            Source
                        </h4>
                        <p className="text-xs text-muted-foreground break-all font-mono bg-secondary px-3 py-2 rounded">{vessel.imageName}</p>
                    </div>
                </>
            )}
        </div>
    );
};
