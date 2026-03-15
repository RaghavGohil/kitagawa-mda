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
                <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm">
                    {/* Backdrop Click-to-Close */}
                    <div className="absolute inset-0 z-0" onClick={() => setIsQueueOpen(false)} />

                    <div className="relative z-10 bg-background border border-border rounded-xl shadow-2xl w-full sm:max-w-lg max-h-[85dvh] flex flex-col overflow-hidden">
                        {/* Modal header */}
                        <div className="flex justify-between items-center px-5 py-4 border-b border-border shrink-0 bg-background/50 backdrop-blur-md">
                            <div>
                                <h3 className="text-lg font-bold tracking-tight">Image Queue</h3>
                            </div>
                            <Button variant="ghost" size="icon" className="h-9 w-9 hover:bg-muted" onClick={() => setIsQueueOpen(false)}>
                                <X className="h-5 w-5" />
                            </Button>
                        </div>

                        {/* Modal body */}
                        <div className="p-5 space-y-6 overflow-y-auto flex-1 custom-scrollbar">
                            {/* Error */}
                            {isFailed && (
                                <div className="space-y-2.5">
                                    <h4 className="text-xs font-bold uppercase tracking-wider text-destructive flex items-center gap-2">
                                        <AlertCircle className="w-3.5 h-3.5" /> Pipeline Error
                                    </h4>
                                    <div className="bg-destructive/10 border border-destructive/20 p-4 rounded-xl">
                                        <p className="text-sm leading-relaxed text-destructive/90">{status?.message || "Unknown error occurred during processing"}</p>
                                    </div>
                                </div>
                            )}

                            {/* Currently processing */}
                            {status?.current_image && isRunning && (
                                <div className="space-y-3.5">
                                    <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Active Task</h4>
                                    <div className="bg-muted/30 border border-border p-4 rounded-xl space-y-4">
                                        <div className="flex justify-between items-start gap-4">
                                            <p className="text-sm font-mono break-all leading-tight text-foreground/80">{status.current_image}</p>
                                            <Badge variant="secondary" className="shrink-0 bg-primary/10 text-primary border-primary/20 hover:bg-primary/20 transition-colors">PROCESSING</Badge>
                                        </div>
                                        {status.current_stage && status.current_stage !== "Finished" && (
                                            <div className="space-y-2.5">
                                                <div className="flex justify-between text-xs font-medium">
                                                    <span className="text-muted-foreground uppercase tracking-wide">{STAGE_LABELS[status.current_stage] || status.current_stage}</span>
                                                    <span className="font-mono text-primary">{Math.round(displayProgress)}%</span>
                                                </div>
                                                <Progress value={displayProgress} className="h-1.5 bg-muted/50" />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Queued */}
                            {status?.queued_images && status.queued_images.length > 0 && (
                                <div className="space-y-3.5">
                                    <div className="flex items-center justify-between">
                                        <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Waiting in Queue</h4>
                                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{status.queued_images.length}</span>
                                    </div>
                                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1 custom-scrollbar">
                                        {status.queued_images.map((img) => (
                                            <div key={img} className="flex justify-between items-center p-3 rounded-lg border border-border/50 bg-background/30 hover:bg-muted/20 transition-colors">
                                                <p className="text-xs font-mono text-muted-foreground truncate mr-4">{img}</p>
                                                <Badge variant="outline" className="shrink-0 text-[10px] font-bold tracking-tighter opacity-70">PENDING</Badge>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Empty */}
                            {(!status || status.status === "idle") && pendingCount === 0 && (
                                <div className="py-16 flex flex-col items-center text-center">
                                    <div className="w-12 h-12 rounded-2xl bg-muted/30 flex items-center justify-center mb-5">
                                        <Clock className="w-6 h-6 text-muted-foreground/40" />
                                    </div>
                                    <p className="text-base font-semibold text-foreground/90">No active tasks</p>
                                    <p className="text-sm text-muted-foreground mt-1.5 max-w-[200px]">The processing pipeline is currently idle and waiting for data.</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};
