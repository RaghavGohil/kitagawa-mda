import { useState } from 'react';
import { Bell, Clock, ChevronRight, Loader2 } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { Alert } from '@/types';
import { Badge } from '@/components/ui/badge';

interface RecentAlertsProps {
  alerts: Alert[];
  isLoading?: boolean;
  onAlertClick?: (vesselId: string) => void;
  alertLimit?: number;
  onAlertLimitChange?: (limit: number) => void;
}

export const Alerts = ({
  alerts,
  isLoading = false,
  onAlertClick,
  alertLimit = 20,
  onAlertLimitChange,
}: RecentAlertsProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const formatTime = (ts: Date | string) => {
    const date = typeof ts === 'string' ? new Date(ts) : ts;
    return format(date, 'HH:mm');
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden shadow-lg transition-all animate-in fade-in duration-300">
      {/* Main Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          "flex w-full items-center justify-between px-[10px] py-[10px] bg-muted/5 border-border hover:bg-muted/10 transition-none group",
          isExpanded ? "border-b" : "border-none"
        )}
      >
        <div className="flex items-center gap-[10px]">
          <Bell className="h-[21px] w-[21px] text-primary" />
          <span className="text-sm font-bold tracking-tight">System Alerts</span>
          {alerts.length > 0 && !isExpanded && (
            <Badge variant="destructive" className="ml-1 h-[18px] min-w-[18px] flex items-center justify-center rounded-md bg-red-500 text-white text-[9px] p-0 font-black border-none shadow-[0_0_10px_rgba(239,68,68,0.4)]">
              {alerts.length}
            </Badge>
          )}
        </div>
        <div className="flex items-center">
          <ChevronRight className={cn("h-[15px] w-[15px] text-muted-foreground/50 transition-transform duration-200", isExpanded ? "rotate-90" : "rotate-0")} />
        </div>
      </button>

      {/* Main List */}
      {isExpanded && (
        <div className="flex flex-col h-[400px]">
          <div className="flex-1 overflow-y-auto p-[10px] space-y-[10px] custom-scrollbar">
            {isLoading ? (
              <div className="h-full flex flex-col items-center justify-center gap-4 opacity-40">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="text-sm font-medium animate-pulse-subtle">Scanning AIS feeds...</span>
              </div>
            ) : alerts.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-[10px] space-y-[10px] opacity-30">
                <Bell className="h-10 w-10" />
                <div className="space-y-[10px]">
                  <p className="text-sm font-bold">No High Priority Alerts</p>
                  <p className="text-xs font-medium leading-relaxed max-w-[210px]">System is currently monitoring all sectors with no detection triggers.</p>
                </div>
              </div>
            ) : (
              alerts.map((alert) => {
                const isUnidentified = alert.vesselId.startsWith('unidentified-');
                const idLabel = isUnidentified ? 'Unidentified Vessel' : `MMSI ${alert.vesselId.substring(0, 9)}`;

                return (
                  <button
                    key={alert.id}
                    onClick={() => onAlertClick?.(alert.vesselId)}
                    className="w-full text-left bg-muted/5 border border-border p-[10px] rounded-xl group hover:bg-muted/10 hover:border-primary/30 transition-all flex flex-col gap-[10px] relative overflow-hidden"
                  >
                    <div className={cn(
                      "absolute left-0 top-0 bottom-0 w-1.5 transition-all",
                      alert.type === 'anomaly' ? "bg-yellow-500" : "bg-red-500"
                    )} />

                    <div className="flex justify-between items-start w-full pl-2">
                      <div className="space-y-1">
                        <span className="text-sm font-bold leading-none block group-hover:text-primary transition-colors">
                          {alert.vesselName || 'Detection Event'}
                        </span>
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                          {idLabel}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-muted-foreground/60 text-[11px] font-bold">
                        <Clock className="w-3.5 h-3.5" />
                        {formatTime(alert.timestamp)}
                      </div>
                    </div>

                    <div className="flex items-center justify-end w-full pl-2">
                      <div className="flex items-center gap-1.5 text-primary text-[10px] font-bold uppercase opacity-0 group-hover:opacity-100 transition-opacity">
                        <span>Investigate</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
