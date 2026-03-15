"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { X, Loader2, Clock, AlertCircle, XCircle, Menu } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { usePipelineStatus } from "@/hooks/useVessels";
import { Progress } from "@/components/ui/progress";

const STAGE_LABELS: Record<string, string> = {
    "Data Ingestion": "Downloading",
    "Vessel Detection": "Analyzing",
    "Saving Detections": "Saving Results",
    "Landmask Initialization": "Preparing",
    "AIS Data Sync": "Syncing AIS",
    "AIS Correlation": "Correlating",
    "Generating Map Chips": "Thumbnails",
    "Thumbnail Generation": "Thumbnails",
    "Finished": "Complete",
};

interface HeaderProps {
    onMenuToggle?: () => void;
    isMobile?: boolean;
}

export const Header = ({ isMobile }: HeaderProps) => {
    const [isQueueOpen, setIsQueueOpen] = useState(false);
    const { data: status } = usePipelineStatus();

    const isRunning = status?.status === "running";
    const isFailed = status?.status === "failed";
    const pendingCount = (status?.queued_images?.length || 0) + (status?.current_image ? 1 : 0);

    const [displayProgress, setDisplayProgress] = useState(0);
    const lastImageRef = useRef<string | null>(null);

    const getStageProgress = useCallback((): number => {
        if (!status) return 0;
        const stage = status.current_stage;
        if (stage === "Data Ingestion") return status.download_progress || 0;
        if (stage === "Vessel Detection") return status.inference_progress || 0;
        if (stage === "AIS Correlation") return status.correlation_progress || 0;
        if (stage === "Generating Map Chips" || stage === "Thumbnail Generation") return status.chips_progress || 0;
        return 0;
    }, [status]);

    useEffect(() => {
        const raw = getStageProgress();
        if (status?.current_image !== lastImageRef.current) {
            setDisplayProgress(0);
            setTimeout(() => { lastImageRef.current = status?.current_image || null; }, 0);
        } else {
            setDisplayProgress(raw);
        }
    }, [status, getStageProgress]);

    useEffect(() => {
        if (isFailed) setIsQueueOpen(true);
    }, [isFailed]);

    return (
        <>
            <header className="h-14 border-b border-border bg-background flex items-center justify-between px-2 sm:px-4 shrink-0 z-50">
                {/* LEFT */}
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                    <Image src="/logo.svg" alt="Kitagawa" width={220} height={44} className="h-8 w-auto shrink-0" />
                </div>

                {/* RIGHT */}
                <div className="flex items-center gap-2 sm:gap-3">
                    <div className="flex items-center gap-1.5 text-sm shrink-0">
                        <div className={cn(
                            "w-2.5 h-2.5 rounded-full shrink-0",
                            isRunning ? "bg-green-500 animate-glow" : isFailed ? "bg-red-500" : "bg-muted-foreground/30",
                        )} />
                        <span className={cn(
                            "text-xs sm:text-sm hidden sm:inline-block",
                            isRunning ? "text-green-500" : isFailed ? "text-red-400" : "text-muted-foreground",
                        )}>
                            {isFailed ? "Failed" : isRunning ? "Processing" : "Idle"}
                        </span>
                    </div>
                    <Button
                        variant={isFailed ? "destructive" : "outline"}
                        size="sm"
                        className="h-9 gap-2"
                        onClick={() => setIsQueueOpen(true)}
                    >
                        {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : isFailed ? <XCircle className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                        <span className="hidden sm:inline">Queue</span> ({pendingCount})
                    </Button>
                </div>
            </header>

            {/* QUEUE MODAL */}
            {isQueueOpen && (
                <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="bg-background border border-border rounded-t-xl sm:rounded-xl shadow-2xl w-full sm:max-w-lg max-h-[80vh] overflow-hidden flex flex-col sm:mx-4">
                        {/* Modal header */}
                        <div className="flex justify-between items-center px-5 py-4 border-b border-border shrink-0">
                            <div>
                                <h3 className="text-base font-semibold">Image Queue</h3>
                                <p className="text-sm text-muted-foreground mt-0.5">Pipeline monitoring</p>
                            </div>
                            <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => setIsQueueOpen(false)}>
                                <X className="h-5 w-5" />
                            </Button>
                        </div>

                        {/* Modal body */}
                        <div className="p-5 space-y-4 overflow-y-auto flex-1">
                            {/* Error */}
                            {isFailed && (
                                <div className="space-y-2">
                                    <h4 className="text-sm font-medium text-destructive flex items-center gap-2">
                                        <AlertCircle className="w-4 h-4" /> Error
                                    </h4>
                                    <div className="bg-destructive/10 border border-destructive/20 p-4 rounded-lg">
                                        <p className="text-sm text-destructive">{status?.message || "Unknown error"}</p>
                                    </div>
                                </div>
                            )}

                            {/* Currently processing */}
                            {status?.current_image && isRunning && (
                                <div className="space-y-3">
                                    <h4 className="text-sm font-medium text-muted-foreground">Currently Processing</h4>
                                    <div className="bg-muted/50 border border-border p-4 rounded-lg space-y-3">
                                        <div className="flex justify-between items-start gap-3">
                                            <p className="text-sm font-mono break-all">{status.current_image}</p>
                                            <Badge variant="secondary" className="shrink-0">Active</Badge>
                                        </div>
                                        {status.current_stage && status.current_stage !== "Finished" && (
                                            <div className="space-y-2">
                                                <div className="flex justify-between text-sm">
                                                    <span className="text-muted-foreground">{STAGE_LABELS[status.current_stage] || status.current_stage}</span>
                                                    <span className="font-mono font-medium">{Math.round(displayProgress)}%</span>
                                                </div>
                                                <Progress value={displayProgress} className="h-2" />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Queued */}
                            {status?.queued_images && status.queued_images.length > 0 && (
                                <div className="space-y-3">
                                    <h4 className="text-sm font-medium text-muted-foreground">Queued ({status.queued_images.length})</h4>
                                    <div className="space-y-2">
                                        {status.queued_images.map((img) => (
                                            <div key={img} className="flex justify-between items-center p-3 rounded-lg border border-border">
                                                <p className="text-sm font-mono text-muted-foreground truncate mr-3">{img}</p>
                                                <Badge variant="outline" className="shrink-0">Pending</Badge>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Empty */}
                            {(!status || status.status === "idle") && pendingCount === 0 && (
                                <div className="py-12 flex flex-col items-center text-center">
                                    <Clock className="w-10 h-10 text-muted-foreground/20 mb-4" />
                                    <p className="text-base font-medium">No active tasks</p>
                                    <p className="text-sm text-muted-foreground mt-1">Pipeline is idle</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};
