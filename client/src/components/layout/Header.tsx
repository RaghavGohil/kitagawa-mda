import { useState, useEffect, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';
import Logo from '/logo.svg';
import { Button } from '@/components/ui/button';
import { X, Loader2, Clock, AlertCircle, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { usePipelineStatus } from '@/hooks/useVessels';
import { Progress } from "@/components/ui/progress";

// Map backend stage names to user-friendly labels
const STAGE_LABELS: Record<string, string> = {
  "Data Ingestion": "Downloading",
  "Vessel Detection": "Analyzing",
  "Saving Detections": "Saving Results",
  "Landmask Initialization": "Preparing",
  "AIS Data Sync": "Syncing AIS Data",
  "AIS Correlation": "Correlating Tracks",
  "Generating Map Chips": "Generating Thumbnails",
  "Thumbnail Generation": "Generating Thumbnails",
  "Finished": "Complete",
};

export const Header = () => {
  const [isQueueOpen, setIsQueueOpen] = useState(false);
  const { data: status } = usePipelineStatus();


  const isRunning = status?.status === 'running';
  const isFailed = status?.status === 'failed';
  const pendingCount = (status?.queued_images?.length || 0) + (status?.current_image ? 1 : 0);

  // Get current stage progress value
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
      // We don't update lastImageRef yet to ensure one render with 0
      setTimeout(() => {
        lastImageRef.current = status?.current_image || null;
      }, 0);
    } else {
      setDisplayProgress(raw);
    }
  }, [status, getStageProgress]);

  // Auto-open queue modal when pipeline fails
  useEffect(() => {
    if (isFailed) {
      setIsQueueOpen(true);
    }
  }, [isFailed]);

  // Get status label and color
  const getStatusInfo = () => {
    if (isFailed) return { label: 'Pipeline Failed', color: 'text-red-400' };
    if (isRunning) return { label: 'Processing Active', color: 'text-primary' };
    return { label: 'System Idle', color: 'text-muted-foreground text-opacity-40' };
  };

  const statusInfo = getStatusInfo();

  return (
    <>
      {/* Navbar */}
      <header className="h-[66px] border-b border-border bg-card/95 backdrop-blur-md flex items-center justify-between relative z-10 shadow-sm">
        {/* LEFT: LOGO & BRANDING */}
        <div className="flex items-center gap-[10px] min-w-[300px]">
          <div className="flex items-center active:opacity-80 transition-opacity cursor-pointer shrink-0">
            <img src={Logo} className="h-7 w-auto" alt="Logo" />
          </div>
          <div className="h-6 w-px bg-border" />
          <div className="flex flex-col justify-center">
            <span className="text-sm font-bold text-muted-foreground opacity-40">Maritime Domain Awareness</span>
          </div>
        </div>

        {/* RIGHT: STATUS & QUEUE */}
        <div className="flex items-center justify-end gap-[10px]">

          <div className="hidden md:flex flex-col items-end leading-tight gap-y-[2px]">

            <span className="text-[11px] uppercase font-bold text-muted-foreground/40 tracking-wider">
              System Status
            </span>

            <div className="flex items-center gap-[10px]">
              <div
                className={cn(
                  "w-2.5 h-2.5 rounded-full",
                  isRunning
                    ? "bg-green-500 animate-glow"
                    : isFailed
                      ? "bg-red-500"
                      : "bg-muted-foreground/20"
                )}
              />

              <span
                className={cn(
                  "text-[11px] font-bold uppercase tracking-wider",
                  isRunning
                    ? "text-green-500"
                    : isFailed
                      ? "text-red-500"
                      : "text-muted-foreground/40"
                )}
              >
                {statusInfo.label}
              </span>
            </div>

          </div>

          <Button
            variant={isFailed ? "destructive" : "outline"}
            size="sm"
            className={cn(
              "mr-[10px] rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-sm active:scale-95 border border-border",
              isRunning && "border-primary/40 bg-primary/5 text-primary hover:bg-primary/10"
            )}
            onClick={() => setIsQueueOpen(true)}
          >
            {isRunning ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : isFailed ? (
              <XCircle className="w-3.5 h-3.5" />
            ) : (
              <Clock className="w-3.5 h-3.5" />
            )}
            Image Queue ({pendingCount})
          </Button>
        </div>
      </header>

      {/* QUEUE MODAL */}
      {isQueueOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-[10px] animate-in fade-in duration-300">
          <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex justify-between items-center px-[10px] py-[10px] border-b border-border bg-muted/5 shrink-0">
              <div className="space-y-[10px]">
                <h3 className="text-lg font-bold">Image Queue</h3>
                <p className="text-[11px] text-muted-foreground font-medium">Monitoring satellite pipeline and AIS correlation</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-xl hover:bg-muted border border-transparent hover:border-border"
                onClick={() => setIsQueueOpen(false)}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>

            {/* Queue List */}
            <div className="p-[10px] space-y-[10px] overflow-y-auto custom-scrollbar">

              {/* ERROR MESSAGE */}
              {isFailed && (
                <div className="space-y-3 animate-in fade-in slide-in-from-top-2 duration-300">
                  <h4 className="text-[11px] font-bold text-red-500 uppercase tracking-widest flex items-center gap-[9px]">
                    <AlertCircle className="w-4 h-4" /> System Fault Detected
                  </h4>
                  <div className="bg-red-500/5 border border-red-500/20 p-6 rounded-xl">
                    <p className="text-xs text-red-600 dark:text-red-400 font-bold leading-relaxed">
                      {status?.message || 'An unknown error occurred during processing.'}
                    </p>
                  </div>
                </div>
              )}

              {/* CURRENTLY PROCESSING */}
              {status?.current_image && isRunning && (
                <div className="space-y-6 animate-in fade-in duration-300">
                  <h4 className="text-[11px] font-bold text-primary uppercase tracking-widest flex items-center gap-[9px]">
                    <Clock className="w-4 h-4" /> Active Process
                  </h4>
                  <div className="bg-muted/10 border border-border p-6 rounded-2xl space-y-6 shadow-inner">
                    <div className="flex justify-between items-start gap-4">
                      <div className="min-w-0 flex-1">
                        <span className="text-[10px] font-bold text-muted-foreground uppercase opacity-50 tracking-wider">Image Name</span>
                        <p className="text-xs font-mono text-foreground mt-[6px] break-all font-bold">{status.current_image}</p>
                      </div>
                      <Badge className="bg-transparent border border-primary/40 text-primary shrink-0 rounded-lg px-3 py-1 text-[10px] font-bold uppercase tracking-widest h-[24px]">
                        Processing
                      </Badge>
                    </div>

                    {status.current_stage && status.current_stage !== "Finished" && (
                      <div className="space-y-3 pt-2">
                        <div className="flex justify-between items-end">
                          <span className="text-sm font-bold text-foreground">{STAGE_LABELS[status.current_stage] || status.current_stage}</span>
                          <span className="text-lg font-black text-primary font-mono">{Math.round(displayProgress)}%</span>
                        </div>
                        <Progress value={displayProgress} className="h-3 rounded-lg bg-primary/10" />
                      </div>
                    )}
                  </div>
                </div>
              )}


              {/* QUEUED IMAGES */}
              {status?.queued_images && status.queued_images.length > 0 && (
                <div className="space-y-4">
                  <h4 className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                    <Clock className="w-4 h-4" /> Pipeline Backlog ({status.queued_images.length})
                  </h4>
                  <div className="space-y-3">
                    {status.queued_images.map((img) => (
                      <div key={img} className="bg-muted/5 border border-border p-4 rounded-xl flex justify-between items-center group hover:bg-muted/10 hover:border-primary/20 transition-all cursor-default overflow-hidden">
                        <div className="min-w-0 pr-4">
                          <p className="text-xs font-mono text-muted-foreground mt-1.5 truncate font-bold">{img}</p>
                        </div>
                        <Badge variant="outline" className="text-[9px] text-muted-foreground font-bold uppercase tracking-widest opacity-40 shrink-0 border-border rounded-lg">
                          Pending
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(!status || status.status === 'idle') && pendingCount === 0 && (
                <div className="py-[10px] flex flex-col items-center justify-center text-center space-y-[10px] bg-muted/5 border border-dashed border-border rounded-2xl">
                  <div className="h-16 w-16 rounded-full bg-muted/10 flex items-center justify-center">
                    <Clock className="w-8 h-8 text-muted-foreground/20" />
                  </div>
                  <div className="space-y-[10px] px-[10px]">
                    <p className="text-sm font-bold text-foreground">Operational Efficiency Nominal</p>
                    <p className="text-xs text-muted-foreground/60 leading-relaxed font-medium">Monitoring data streams. No active acquisition tasks are currently queued for processing.</p>
                  </div>
                </div>
              )}

            </div>
          </div>
        </div>
      )}
    </>
  );
};
