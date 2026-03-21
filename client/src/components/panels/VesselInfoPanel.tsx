"use client";

import { Ship, Anchor, AlertTriangle, Loader2 } from "lucide-react";
import { Vessel } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { anomalyTypeData, vesselTypeData } from "@/data/data";

interface VesselInfoPanelProps {
    vessel: Vessel;
    isLoading?: boolean;
}

const InfoRow = ({ label, value, mono }: { label: string; value: string | undefined | null; mono?: boolean }) => (
    <div className="flex justify-between items-center py-1.5">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={cn("text-sm", mono && "font-mono")}>{value || "—"}</span>
    </div>
);

export const VesselInfoPanel = ({ vessel, isLoading }: VesselInfoPanelProps) => {
    const hasAnomaly = vessel.anomaly.type === "anomaly";
    const typeColor = vessel.type === "ship"
        ? (hasAnomaly ? anomalyTypeData["anomaly"].color : vesselTypeData["ship"].color)
        : anomalyTypeData[vessel.anomaly.type]?.color || "#94a3b8";

    return (
        <div className="flex flex-col w-full">
            {/* Vessel identity */}
            <div className="p-5 flex items-center gap-4">
                <div className="h-12 w-12 rounded-lg border border-border flex items-center justify-center shrink-0" style={{ color: typeColor }}>
                    <Ship className="h-6 w-6" />
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="text-base font-semibold truncate">{vessel.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs" style={{ borderColor: typeColor, color: typeColor }}>
                            {vessel.type === "ship" ? "Identified" : "Unidentified"}
                        </Badge>
                        <span className="text-xs text-muted-foreground font-mono">{vessel.id.substring(0, 8)}</span>
                    </div>
                </div>
            </div>

            {/* Ship chip image */}
            <div className="mx-5 h-40 bg-secondary rounded-lg overflow-hidden flex items-center justify-center border border-border">
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

            {/* Anomaly warning */}
            {hasAnomaly && (
                <div className="mx-5 mt-4 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                    <div className="flex gap-3">
                        <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-yellow-500">Suspicious Activity</p>
                            <p className="text-sm text-muted-foreground mt-1">{vessel.anomaly.description || "Unusual behavior detected for this vessel."}</p>
                        </div>
                    </div>
                </div>
            )}

            <Separator className="my-4" />

            {/* Registration */}
            <div className="px-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-3">Registration</h4>
                <InfoRow label="MMSI" value={vessel.mmsi} mono />
                <InfoRow label="IMO" value={vessel.imo} mono />
                <InfoRow label="Call Sign" value={vessel.callSign} />
                <InfoRow label="Flag" value={vessel.flag} />
            </div>

            <Separator className="my-4" />

            {/* Navigation */}
            <div className="px-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-3">Navigation</h4>
                <InfoRow
                    label="Position"
                    value={vessel.position.lat != null ? `${vessel.position.lat.toFixed(4)}, ${vessel.position.lng.toFixed(4)}` : undefined}
                    mono
                />
                <InfoRow label="Speed" value={vessel.position.speed != null ? `${vessel.position.speed.toFixed(1)} kn` : undefined} />
                <InfoRow label="Heading" value={vessel.position.heading != null ? `${vessel.position.heading.toFixed(0)}°` : undefined} />
                <InfoRow label="Last Seen" value={vessel.position.timestamp ? format(vessel.position.timestamp, "MMM dd, HH:mm") : undefined} />
            </div>

            <Separator className="my-4" />

            {/* Specifications */}
            <div className="px-5 pb-5 space-y-1">
                <h4 className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-3">Specifications</h4>
                <InfoRow label="Length" value={vessel.length ? `${vessel.length.toFixed(0)} m` : undefined} />
                <InfoRow label="Width" value={vessel.width ? `${vessel.width.toFixed(0)} m` : undefined} />
            </div>

            {vessel.imageName && (
                <>
                    <Separator />
                    <div className="p-5">
                        <p className="text-xs text-muted-foreground break-all">Source: <span className="font-mono">{vessel.imageName}</span></p>
                    </div>
                </>
            )}
        </div>
    );
};
