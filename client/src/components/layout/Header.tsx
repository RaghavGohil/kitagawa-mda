import { useState, useEffect, useRef, useCallback } from 'react';
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
      <header className="h-14 border-b border-border/60 bg-card/90 backdrop-blur-sm px-2 flex items-center justify-between relative z-10">
        <div className="flex items-center gap-2">
          <div>
            <h1 className="font-semibold text-lg tracking-tight">
              <img src={Logo} className="w-40" alt="Logo" />
            </h1>
            <p className="text-[10px] text-muted-foreground -mt-0.5">
              Maritime Domain Awareness System
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex flex-col items-end mr-2">
            <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest leading-none">Status</span>
            <span className={`text-xs font-semibold ${statusInfo.color}`}>
              {statusInfo.label}
            </span>
          </div>

          <Button
            className={`rounded-lg border bg-transparent hover:bg-muted text-white flex gap-2 h-9 ${isFailed ? 'border-red-500/50 animate-pulse' : ''}`}
            onClick={() => setIsQueueOpen(true)}
          >
            {isRunning && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {isFailed && <XCircle className="w-3.5 h-3.5 text-red-400" />}
            Image Queue ({pendingCount})
          </Button>
        </div>
      </header>

      {/* QUEUE MODAL */}
      {isQueueOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-xl max-h-[85vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex justify-between items-center p-4 border-b border-border shrink-0 bg-muted/20">
              <div>
                <h3 className="text-lg font-bold">Live Processing Queue</h3>
                <p className="text-xs text-muted-foreground">Real-time status of automatic satellite image analysis</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsQueueOpen(false)}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>

            {/* Queue List */}
            <div className="p-6 space-y-8 overflow-y-auto">

              {/* PIPELINE ERROR / FAILURE MESSAGE */}
              {isFailed && (
                <div className="space-y-3">
                  <h4 className="text-[10px] uppercase font-black tracking-widest text-red-400 flex items-center gap-2">
                    <XCircle className="w-3.5 h-3.5" /> Pipeline Error
                  </h4>
                  <div className="bg-red-500/10 border border-red-500/30 p-4 rounded-xl space-y-2">
                    <p className="text-sm text-red-300 font-medium">
                      {status?.message || 'An unknown error occurred during processing.'}
                    </p>
                    {status?.current_image && (
                      <p className="text-xs text-muted-foreground">
                        Failed while processing: <span className="font-mono font-bold text-red-400/80">{status.current_image}</span>
                      </p>
                    )}
                    {status?.started_at && status?.completed_at && (
                      <p className="text-[10px] text-muted-foreground/60">
                        Duration: {(() => {
                          const start = new Date(status.started_at).getTime();
                          const end = new Date(status.completed_at).getTime();
                          const secs = Math.round((end - start) / 1000);
                          return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
                        })()}
                      </p>
                    )}
                    {/* Failed images list */}
                    {status?.failed_images && status.failed_images.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-red-500/20">
                        <p className="text-[10px] uppercase font-bold text-red-400/70 mb-1">Failed Images</p>
                        {status.failed_images.map((img) => (
                          <p key={img} className="text-xs font-mono text-muted-foreground/70 break-all">{img}</p>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* CURRENTLY PROCESSING */}
              {status?.current_image && isRunning && (
                <div className="space-y-4">
                  <h4 className="text-[10px] uppercase font-black tracking-widest text-primary flex items-center gap-2">
                    <Loader2 className="w-3 h-3 animate-spin" /> Active Analysis
                  </h4>
                  <div className="bg-primary/5 border border-primary/20 p-4 rounded-xl flex flex-col gap-3">
                    <div className="flex justify-between items-start">
                      <span className="text-sm font-bold pr-4 break-all">{status.current_image}</span>
                      <Badge variant="outline" className="border-primary text-primary animate-pulse text-[10px] font-bold">Processing</Badge>
                    </div>
                    <div className="space-y-4">

                      {/* Single active stage progress bar */}
                      {status.current_stage && status.current_stage !== "Finished" && (
                        <div className="space-y-1.5">
                          <div className="flex justify-between text-[10px] uppercase tracking-wider font-extrabold text-muted-foreground/70">
                            <span>{STAGE_LABELS[status.current_stage] || status.current_stage}</span>
                            <span>{Math.round(displayProgress)}%</span>
                          </div>
                          <Progress value={displayProgress} className="h-1 bg-primary/10" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}


              {/* QUEUED IMAGES */}
              {status?.queued_images && status.queued_images.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-[10px] uppercase font-black tracking-widest text-muted-foreground flex items-center gap-2 px-1">
                    <Clock className="w-3 h-3" /> Scheduled in Queue
                  </h4>
                  <div className="space-y-2">
                    {status.queued_images.map((img) => (
                      <div key={img} className="bg-muted/30 border border-border/50 p-4 rounded-xl flex justify-between items-center group hover:bg-muted/50 transition-colors">
                        <span className="text-xs font-bold text-muted-foreground/80 pr-4 break-all">{img}</span>
                        <Badge variant="outline" className="text-[9px] bg-background font-bold tracking-tight shrink-0">Waiting</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(!status || status.status === 'idle') && pendingCount === 0 && (
                <div className="text-center py-16 space-y-4 rounded-2xl bg-muted/10 border border-dashed">
                  <div className="w-16 h-16 bg-muted/20 rounded-full flex items-center justify-center mx-auto ring-8 ring-muted/5">
                    <Clock className="w-8 h-8 text-muted-foreground/30" />
                  </div>
                  <div className="space-y-1 px-8">
                    <p className="text-sm font-bold text-muted-foreground">No active tasks</p>
                    <p className="text-xs text-muted-foreground/50 leading-relaxed">The system is polling Copernicus for new imagery automatically.</p>
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
