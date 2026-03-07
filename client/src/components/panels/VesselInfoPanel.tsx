import {
  Ship,
  Compass,
  Gauge,
  MapPin,
  Clock,
  AlertTriangle,
  Route,
  Anchor,
  ArrowRight,
  Loader2,
} from 'lucide-react';
import { Vessel } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';
import { anomalyTypeData, vesselTypeData } from '@/data/data';

interface VesselInfoPanelProps {
  vessel: Vessel;
  isLoading?: boolean;
}

const vesselTypeLabels: Record<string, string> = {
  ship: 'Identified Vessel',
  unidentified: 'Unidentified Vessel',
};


export const VesselInfoPanel = ({ vessel, isLoading }: VesselInfoPanelProps) => {
  const hasAnomaly = vessel.anomaly.type === 'anomaly';
  const vesselColor = vessel.type === 'ship'
    ? (vessel.anomaly.type === 'anomaly' ? anomalyTypeData['anomaly'].color : vesselTypeData['ship'].color)
    : anomalyTypeData[vessel.anomaly.type].color;

  return (
    <div className="flex flex-col w-full pb-[10px]">
      {/* ===== HEADER ===== */}
      <div className="p-[10px] flex flex-col items-center gap-[10px] relative border-b border-border/40 bg-muted/5">
        <div
          className="p-[10px] rounded-lg border transition-none"
          style={{
            backgroundColor: `${vesselColor}10`,
            borderColor: `${vesselColor}25`,
            color: vesselColor
          }}
        >
          <Ship className="h-6 w-6" />
        </div>

        <div className="text-center space-y-[10px]">
          <h3 className="font-bold text-base text-foreground">{vessel.name}</h3>
          <div className="flex items-center justify-center gap-[10px]">
            <span
              className="text-xs font-bold"
              style={{ color: vesselColor }}
            >
              {vesselTypeLabels[vessel.type]}
            </span>
            <div className="h-1.5 w-1.5 rounded-lg bg-border/40" />
            <span className="text-xs text-muted-foreground font-mono">{vessel.id.substring(0, 8)}</span>
          </div>
        </div>

        {/* SHIP IMAGE */}
        <div className="w-full h-[150px] bg-muted/20 border border-border/60 rounded-xl overflow-hidden flex items-center justify-center text-xs text-muted-foreground group relative">
          {isLoading ? (
            <div className="flex flex-col items-center gap-[10px] animate-pulse-subtle">
              <Loader2 className="h-6 w-6 animate-spin" style={{ color: vesselColor }} />
              <span className="text-[10px] font-bold uppercase tracking-widest opacity-60">Acquiring Image...</span>
            </div>
          ) : vessel.chipUrl ? (
            <img
              src={vessel.chipUrl}
              alt={vessel.name}
              className="w-full h-full object-cover group-hover:scale-105"
            />
          ) : (
            <div className="flex flex-col items-center gap-[10px] opacity-30">
              <Anchor className="h-9 w-9" />
              <span>No image available</span>
            </div>
          )}
        </div>
      </div>

      {/* ===== ALERTS ===== */}
      {hasAnomaly && (
        <div className="mx-[10px] mt-[10px] p-[10px] rounded-lg border border-yellow-500/20 bg-yellow-500/5">
          <div className="flex items-start gap-[10px]">
            <div className="p-[10px] rounded-md bg-yellow-500/10">
              <AlertTriangle className="h-4 w-4 text-yellow-500" />
            </div>
            <div className="space-y-[10px]">
              <span className="text-sm font-semibold text-yellow-600 dark:text-yellow-400 block">Suspicious Activity</span>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {vessel.anomaly.description || 'This vessel is behaving unusually for its type.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ===== SHIP DETAILS ===== */}
      <div className="px-[10px] py-[10px] space-y-[10px]">

        {/* REGISTRY */}
        <div className="space-y-[10px]">
          <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Registration</h4>
          <div className="grid grid-cols-2 gap-[10px]">
            <InfoItem label="MMSI" value={vessel.mmsi} />
            <InfoItem label="IMO" value={vessel.imo} />
            <InfoItem label="Call Sign" value={vessel.callSign} />
            <InfoItem label="Flag" value={vessel.flag} />
          </div>
        </div>

        {/* POSITION */}
        <div className="space-y-[10px]">
          <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Navigation</h4>
          <div className="grid grid-cols-2 gap-[10px]">
            <InfoItem label="Position" value={`${vessel.position.lat?.toFixed(3)}, ${vessel.position.lng?.toFixed(3)}`} />
            <InfoItem label="Last Update" value={vessel.position.timestamp ? format(vessel.position.timestamp, 'HH:mm:ss') : 'N/A'} />
            <InfoItem label="Speed" value={vessel.position.speed != null ? vessel.position.speed.toFixed(1) + ' kn' : 'N/A'} />
            <InfoItem label="Heading" value={vessel.position.heading != null ? vessel.position.heading.toFixed(0) + '°' : 'N/A'} />
          </div>
        </div>

        {/* DIMENSIONS */}
        <div className="space-y-[10px]">
          <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Specifications</h4>
          <div className="grid grid-cols-2 gap-[10px]">
            <InfoItem label="Length" value={vessel.length ? vessel.length.toFixed(0) + 'm' : '—'} />
            <InfoItem label="Width" value={vessel.width ? vessel.width.toFixed(0) + 'm' : '—'} />
          </div>
        </div>

        {/* SOURCE */}
        {vessel.imageName && (
          <div className="pt-[10px] border-t border-border/40">
            <div className="bg-muted/10 p-[10px] rounded-md flex flex-col gap-[10px]">
              <span className="text-[10px] font-medium text-muted-foreground">Internal ID</span>
              <span className="text-xs font-mono break-all text-muted-foreground/80">{vessel.imageName}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

/* ===================== COMPONENTS ===================== */

const InfoItem = ({ label, value, mono }: { label: string; value: string | undefined | null; mono?: boolean }) => (
  <div className="flex flex-col gap-[10px]">
    <span className="text-[9px] uppercase font-bold text-muted-foreground/40 tracking-wider font-sans">{label}</span>
    <span className={cn(
      "text-[11px] font-bold leading-none text-foreground/90",
      mono && "font-mono tracking-tighter"
    )}>
      {value || '—'}
    </span>
  </div>
);
