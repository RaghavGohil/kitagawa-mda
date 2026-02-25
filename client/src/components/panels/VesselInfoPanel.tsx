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
import { Vessel } from '@/data/data';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';

interface VesselInfoPanelProps {
  vessel: Vessel;
  isLoading?: boolean;
}

const vesselTypeLabels: Record<string, string> = {
  ship: 'Identified Vessel',
  unidentified: 'Unidentified Vessel',
};


export const VesselInfoPanel = ({ vessel, isLoading }: VesselInfoPanelProps) => {
  const hasAnomaly = vessel.anomaly.type !== 'none';

  return (
    <div className="flex flex-col w-full pb-8">
      {/* ===== Header ===== */}
      <div
        className={cn(
          'p-2 flex flex-col items-center gap-2',
          hasAnomaly && 'bg-gradient-to-b from-red-500/5 to-transparent'
        )}
      >
        <Ship className="h-6 w-6 text-primary" />
        <h3 className="font-semibold truncate text-center">{vessel.name}</h3>
        <p className="text-sm text-muted-foreground">
          {vesselTypeLabels[vessel.type]}
        </p>
        <div className="w-full bg-muted/20 rounded-md overflow-hidden flex items-center justify-center text-xs text-muted-foreground border border-border/50">
          {isLoading ? (
            <div className="w-full h-48 bg-muted/30 flex flex-col items-center justify-center gap-2">
              <Loader2 className="h-6 w-6 animate-spin text-primary/50" />
              <span className="text-[10px] text-muted-foreground/50">Loading vessel data...</span>
            </div>
          ) : vessel.chipUrl ? (
            <img
              src={vessel.chipUrl}
              alt={`Chip for ${vessel.name}`}
              className="w-full h-auto object-contain"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
                (e.target as HTMLImageElement).parentElement!.innerHTML = 'Image Load Error';
              }}
            />
          ) : (
            <div className="py-8">No Image Chip</div>
          )}
        </div>
      </div>

      {/* ===== Anomaly Alert ===== */}
      {hasAnomaly && (
        <div
          className="
            p-2 rounded-md border
            flex items-start gap-2
            border-yellow-400/40
            bg-yellow-400/5
          "
        >
          <AlertTriangle
            className="h-4 w-4 flex-shrink-0 text-yellow-400"
          />

          <div className="flex-1 min-w-0 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-yellow-300">
                Anomaly
              </span>

              <Badge
                variant="outline"
                className="
                  text-[10px] px-1.5 py-0
                  border-yellow-400/50
                  text-yellow-300
                "
              >
                {Math.round(vessel.anomaly.confidence * 100)}% confidence
              </Badge>
            </div>

            <p className="text-xs text-muted-foreground">
              {vessel.anomaly.description}
            </p>
          </div>
        </div>
      )}


      <Separator className="my-2" />

      {/* ===== Identification ===== */}
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground font-semibold">Identification</p>

        <InfoRow icon={MapPin} label={`MMSI: ${vessel.mmsi || '-'}`} />
        <InfoRow icon={Compass} label={`IMO: ${vessel.imo || '-'}`} />
        <InfoRow icon={Ship} label={`Call Sign: ${vessel.callSign || '-'}`} />
        <InfoRow icon={Anchor} label={`Flag: ${vessel.flag || '-'}`} />

        {vessel.imageName && (
          <div className="flex flex-col gap-1 mt-1">
            <p className="text-[10px] text-muted-foreground uppercase font-bold">Source Image</p>
            <p className="text-[11px] font-mono break-all bg-muted/30 p-1 rounded font-bold">{vessel.imageName}</p>
          </div>
        )}
      </div>

      <Separator className="my-2" />

      {/* ===== Detection Info ===== */}
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground font-semibold">Detection Info</p>

        <InfoRow
          icon={Gauge}
          label={`Confidence: ${vessel.anomaly.confidence ? (vessel.anomaly.confidence * 100).toFixed(1) + '%' : '-'}`}
        />
        <InfoRow
          icon={Clock}
          label={`Detected: ${vessel.position.timestamp ? format(vessel.position.timestamp, 'dd MMM yyyy HH:mm:ss') : '-'}`}
        />
        {vessel.track.length > 0 && (
          <InfoRow
            icon={Route}
            label={`Track Points: ${vessel.track.length}`}
          />
        )}
      </div>

      <Separator className="my-2" />

      {/* ===== Position & Voyage ===== */}
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground font-semibold">Position & Voyage</p>

        <InfoRow
          icon={MapPin}
          label={`Lat: ${vessel.position.lat?.toFixed(4) || '-'}, Lng: ${vessel.position.lng?.toFixed(4) || '-'}`}
        />
        <InfoRow
          icon={Gauge}
          label={`Speed: ${vessel.position.speed != null ? vessel.position.speed.toFixed(1) + ' kn' : '-'}, Heading: ${vessel.position.heading != null ? vessel.position.heading.toFixed(1) + '°' : '-'}`}
        />
        <InfoRow icon={ArrowRight} label={`Destination: ${vessel.destination || '-'}`} />
        <InfoRow
          icon={Clock}
          label={`ETA: ${vessel.eta ? format(vessel.eta, 'dd MMM yyyy HH:mm') : '-'}`}
        />
      </div>

      <Separator className="my-2" />

      {/* ===== Dimensions ===== */}
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground font-semibold">Dimensions</p>

        <InfoRow icon={Anchor} label={`Length: ${vessel.length ? vessel.length.toFixed(1) + ' m' : '-'}`} />
        <InfoRow icon={Anchor} label={`Width: ${vessel.width ? vessel.width.toFixed(1) + ' m' : '-'}`} />
        <InfoRow icon={Anchor} label={`Draught: ${vessel.draught ? vessel.draught.toFixed(1) + ' m' : '-'}`} />
      </div>

      <Separator className="my-2" />

      {/* ===== Behavior Profile ===== */}
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground font-semibold">Behavior Profile</p>

        <InfoRow
          icon={Gauge}
          label={`Speed: ${vessel.behaviorProfile.typicalSpeed.min}-${vessel.behaviorProfile.typicalSpeed.max} kn (avg ${vessel.behaviorProfile.typicalSpeed.avg.toFixed(1)} kn)`}
        />
        <InfoRow
          icon={Route}
          label={`Typical Routes: ${vessel.behaviorProfile.typicalRoutes.join(', ')}`}
        />
        <InfoRow
          icon={Compass}
          label={`Deviation Score: ${(vessel.behaviorProfile.deviationScore * 100).toFixed(1)}%`}
        />
      </div>
    </div>
  );
};

/* ===================== SMALL HELPER ===================== */

const InfoRow = ({
  icon: Icon,
  label,
}: {
  icon: any;
  label: string;
}) => (
  <div className="flex items-center gap-2 text-[13px]">
    <Icon className="w-3 h-3 text-muted-foreground" />
    {label}
  </div>
);

