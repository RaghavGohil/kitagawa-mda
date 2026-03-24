"use client";

import { useState } from "react";
import { Bell, Clock, ChevronDown, Loader2 } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Alert } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface RecentAlertsProps {
    alerts: Alert[];
    isLoading?: boolean;
    onAlertClick?: (vesselId: string) => void;
}

export const Alerts = ({ alerts, isLoading = false, onAlertClick }: RecentAlertsProps) => {
    const [isExpanded, setIsExpanded] = useState(false);

    return (
        <div className="rounded-lg border border-border">
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex w-full items-center justify-between px-4 py-3 hover:bg-accent/50 transition-colors rounded-lg"
            >
                <div className="flex items-center gap-2.5">
                    <Bell className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Alerts</span>
                    {alerts.length > 0 && (
                        <Badge variant="destructive" className="h-5 min-w-5 px-1.5 text-[10px]">
                            {alerts.length}
                        </Badge>
                    )}
                </div>
                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
            </button>

            {isExpanded && (
                <div className="border-t border-border max-h-[400px] overflow-y-auto">
                    {isLoading ? (
                        <div className="p-8 flex flex-col items-center gap-3">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">Loading alerts…</span>
                        </div>
                    ) : alerts.length === 0 ? (
                        <div className="p-8 text-center">
                            <Bell className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
                            <p className="text-sm font-medium">No alerts</p>
                            <p className="text-sm text-muted-foreground mt-1">All systems nominal</p>
                        </div>
                    ) : (
                        <div className="p-2 space-y-1">
                            {alerts.map((alert) => (
                                <Button
                                    key={alert.id}
                                    variant="ghost"
                                    className="w-full h-auto py-3 px-3 justify-start text-left"
                                    onClick={() => onAlertClick?.(alert.vesselId)}
                                >
                                    <div className="flex items-start gap-3 w-full">
                                        <div className={cn(
                                            "w-2 h-2 rounded-full mt-1.5 shrink-0",
                                            alert.type === "identified" ? "bg-blue-500" : "bg-red-500",
                                        )} />
                                        <div className="min-w-0 flex-1">
                                            <div className="flex justify-between items-start gap-2">
                                                <span className="text-sm font-medium truncate">{alert.vesselName || "Detection"}</span>
                                                <span className="text-xs text-muted-foreground flex items-center gap-1 shrink-0">
                                                    <Clock className="w-3 h-3" />
                                                    {format(typeof alert.timestamp === "string" ? new Date(alert.timestamp) : alert.timestamp, "HH:mm")}
                                                </span>
                                            </div>
                                            <span className="text-xs text-muted-foreground mt-0.5 block">
                                                {alert.vesselId.startsWith("unidentified-") ? "Unidentified" : `MMSI ${alert.vesselId.substring(0, 9)}`}
                                            </span>
                                        </div>
                                    </div>
                                </Button>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
