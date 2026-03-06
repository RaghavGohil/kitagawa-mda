import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Play, Pause, SkipBack, SkipForward, Clock, Settings2, Radio } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { format } from 'date-fns';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface PlaybackProps {
  onTimeChange?: (time: Date) => void;
  onTimeRangeChange?: (start: Date, end: Date) => void;
  jumpToTime?: Date | null;
}

export const Playback = ({ onTimeChange, onTimeRangeChange, jumpToTime }: PlaybackProps) => {
  const [isPlaying, setIsPlaying] = useState(false);

  // Range covers 2 days before now to now
  const [startTime, setStartTime] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 2);
    return d;
  });
  const [endTime, setEndTime] = useState(() => new Date()); // Current time

  const [currentTime, setCurrentTime] = useState(100); // Start at 100% = now, so all data is visible
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  // Live mode: auto-update when slider is at the end
  const isLive = currentTime >= 99.5;

  const getTimeFromValue = useCallback((value: number): Date => {
    const totalMs = endTime.getTime() - startTime.getTime();
    const msSinceStart = (value / 100) * totalMs;
    return new Date(startTime.getTime() + msSinceStart);
  }, [startTime, endTime]);

  const displayTime = useMemo(
    () => isLive ? new Date() : getTimeFromValue(currentTime),
    [currentTime, getTimeFromValue, isLive]
  );

  useEffect(() => {
    onTimeChange?.(displayTime);
  }, [displayTime, onTimeChange]);

  // Broadcast the time range whenever it changes
  useEffect(() => {
    onTimeRangeChange?.(startTime, endTime);
  }, [startTime, endTime, onTimeRangeChange]);

  // Live mode: tick endTime forward every 5 seconds
  useEffect(() => {
    if (!isLive) return;

    const interval = setInterval(() => {
      setEndTime(new Date());
      setCurrentTime(100);
    }, 5000);

    return () => clearInterval(interval);
  }, [isLive]);

  // External jump: when a vessel/alert is clicked, jump to its time
  useEffect(() => {
    if (!jumpToTime) return;
    const totalMs = endTime.getTime() - startTime.getTime();
    if (totalMs <= 0) return;
    const targetMs = jumpToTime.getTime() - startTime.getTime();
    const pct = Math.max(0, Math.min(100, (targetMs / totalMs) * 100));
    setCurrentTime(pct);
    setIsPlaying(false);
  }, [jumpToTime]);

  /* ===================== PLAYBACK LOOP ===================== */

  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      setCurrentTime(prev => {
        // Speed scaling for longer windows (step size in percent)
        const totalMs = endTime.getTime() - startTime.getTime();
        const stepMs = 1000 * 60 * 10 * playbackSpeed; // 10 minutes per tick at 1x
        const stepPercent = (stepMs / totalMs) * 100;

        const next = prev + stepPercent;
        if (next >= 100) {
          setIsPlaying(false);
          return 100;
        }
        return next;
      });
    }, 100);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, startTime, endTime]);

  /* ===================== SLIDER ===================== */

  const handleSliderChange = (value: number[]) => {
    setCurrentTime(value[0]);
    setIsPlaying(false);
  };

  /* ===================== UI ===================== */

  return (
    <div className="rounded-xl bg-background/60 backdrop-blur-xl border border-border/40 shadow-2xl p-4 transition-all duration-300 hover:bg-background/80">
      <div className="flex flex-col gap-5">

        {/* Header & Main Readout */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-primary/10 text-primary">
              <Clock className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight">Timeline</span>
            {isLive && (
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/15 border border-red-500/30">
                <Radio className="h-3 w-3 text-red-400 animate-pulse" />
                <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider">Live</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className={`border px-4 py-1.5 rounded-lg font-mono text-sm font-bold shadow-inner ${isLive ? 'bg-red-500/10 border-red-500/20 text-red-400' : 'bg-primary/10 border-primary/20 text-primary'}`}>
              {format(displayTime, "yyyy-MM-dd HH:mm")}
            </div>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full hover:bg-muted/50">
                  <Settings2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-64 p-3 bg-background/95 backdrop-blur-xl border-border/40" align="end">
                <div className="space-y-3">
                  <h4 className="font-medium text-xs text-muted-foreground uppercase tracking-wider">Date Constraints</h4>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] text-muted-foreground uppercase font-semibold">Start Date (UTC)</label>
                    <input
                      type="datetime-local"
                      className="bg-background border border-border/40 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-2 focus:ring-primary shadow-sm"
                      value={format(startTime, "yyyy-MM-dd'T'HH:mm")}
                      onChange={(e) => {
                        const date = new Date(e.target.value + 'Z');
                        if (!isNaN(date.getTime())) setStartTime(date);
                      }}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] text-muted-foreground uppercase font-semibold">End Date (UTC)</label>
                    <input
                      type="datetime-local"
                      className="bg-background border border-border/40 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-2 focus:ring-primary shadow-sm"
                      value={format(endTime, "yyyy-MM-dd'T'HH:mm")}
                      onChange={(e) => {
                        const date = new Date(e.target.value + 'Z');
                        if (!isNaN(date.getTime())) setEndTime(date);
                      }}
                    />
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>

        {/* Timeline Slider & Markers */}
        <div className="px-1 group">
          <Slider
            value={[currentTime]}
            onValueChange={handleSliderChange}
            min={0}
            max={100}
            step={0.01}
            className="cursor-grab active:cursor-grabbing"
          />
          <div className="flex justify-between text-[10px] text-muted-foreground mt-3 font-mono tracking-wider opacity-60 group-hover:opacity-100 transition-opacity">
            <span>{format(startTime, "dd MMM HH:mm")}</span>
            <span>{isLive ? 'NOW' : format(endTime, "dd MMM HH:mm")}</span>
          </div>
        </div>

        {/* Playback Controls & Speed */}
        <div className="flex items-center justify-between pt-1">
          <div className="w-20" /> {/* Spacer for centered layout */}

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 rounded-full border-border/40 bg-background/50 hover:bg-muted"
              onClick={() => setCurrentTime(0)}
            >
              <SkipBack className="h-3.5 w-3.5" />
            </Button>

            <Button
              size="icon"
              className={`h-12 w-12 rounded-full shadow-lg transition-transform ${isPlaying ? 'bg-primary/90 scale-95' : 'bg-primary hover:scale-105'}`}
              onClick={() => setIsPlaying(p => !p)}
            >
              {isPlaying ? (
                <Pause className="h-5 w-5 text-primary-foreground" />
              ) : (
                <Play className="h-5 w-5 text-primary-foreground ml-1" />
              )}
            </Button>

            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 rounded-full border-border/40 bg-background/50 hover:bg-muted"
              onClick={() => setCurrentTime(100)}
              title="Jump to live"
            >
              <SkipForward className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Speed Selection */}
          <div className="flex items-center gap-1 bg-muted/30 p-1 rounded-full border border-border/30 w-28 justify-center">
            {[1, 2, 4].map(speed => (
              <button
                key={speed}
                className={`h-6 w-8 text-[11px] rounded-full transition-all flex items-center justify-center font-medium
                  ${speed === playbackSpeed
                    ? 'bg-background shadow-sm text-foreground font-semibold'
                    : 'text-muted-foreground hover:text-foreground'
                  }`}
                onClick={() => setPlaybackSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>

        </div>
      </div>
    </div>
  );
};
