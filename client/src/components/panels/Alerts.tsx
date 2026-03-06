import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface Alert {
  id: string;
  vesselId: string;
  vesselName: string;
  type: 'anomaly' | 'unidentified_in_coverage';
  timestamp: Date;
}

interface RecentAlertsProps {
  alerts: Alert[];
  maxItems?: number;
  isLoading?: boolean;
  onAlertClick?: (vesselId: string) => void;
  alertLimit?: number;
  onAlertLimitChange?: (limit: number) => void;
}

/* ===================== LABELS ===================== */

const alertLabels: Record<string, { label: string; color: string }> = {
  anomaly: { label: 'AIS Position Mismatch', color: '#EF4444' },
  unidentified_in_coverage: { label: 'Dark Vessel', color: '#F59E0B' },
};

/* ===================== COMPONENT ===================== */

export const Alerts = ({
  alerts,
  maxItems = 50,
  isLoading = false,
  onAlertClick,
  alertLimit = 20,
  onAlertLimitChange,
}: RecentAlertsProps) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!alerts.length && !isLoading) return null;

  return (
    <div className="rounded-lg">
      {/* ===== Header ===== */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="
          flex w-full items-center justify-between
          px-3 py-2
          text-sm font-medium
          border-b
          hover:text-primary transition-colors
        "
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          <span>Alerts</span>
          <span className="text-[13px] text-muted-foreground">
            ({alerts.length})
          </span>
        </div>

        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {/* Alert limit selector */}
      {isExpanded && onAlertLimitChange && (
        <div className="px-3 py-1.5 flex items-center justify-between border-b text-[10px] text-muted-foreground">
          <span>Show:</span>
          <div className="flex gap-1">
            {[10, 20, 50, 100].map(n => (
              <button
                key={n}
                className={`px-1.5 py-0.5 rounded text-[10px] transition-colors
                  ${alertLimit === n ? 'bg-primary/20 text-primary font-semibold' : 'hover:bg-muted'}`}
                onClick={() => onAlertLimitChange(n)}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      )}

      {isExpanded && (
        <div className="divide-y divide-border max-h-64 overflow-y-auto">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-8 gap-2">
              <Loader2 className="h-5 w-5 animate-spin text-primary/40" />
              <span className="text-[10px] text-muted-foreground/50">Loading alerts...</span>
            </div>
          ) : (
            alerts.slice(0, maxItems).map((alert, index) => {
              const meta = alertLabels[alert.type] || { label: alert.type, color: '#94a3b8' };
              return (
                <div
                  key={`${alert.id}-${index}`}
                  className="
                  px-3 py-2
                  flex items-center justify-between gap-2
                  text-xs
                  hover:bg-accent/40 cursor-pointer transition-colors
                "
                  onClick={() => onAlertClick?.(alert.vesselId)}
                >
                  {/* ===== Left ===== */}
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="h-2 w-2 rounded-full shrink-0"
                      style={{ backgroundColor: meta.color }}
                    />
                    <span className="truncate text-muted-foreground">
                      {alert.vesselName}
                    </span>
                  </div>

                  {/* ===== Right ===== */}
                  <div className="flex flex-col items-end text-[10px] text-muted-foreground leading-tight flex-shrink-0">
                    <span className="font-semibold" style={{ color: meta.color }}>{meta.label}</span>
                    <span>
                      {formatDistanceToNow(alert.timestamp, {
                        addSuffix: true,
                      })}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
