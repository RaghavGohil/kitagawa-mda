import { useState, useEffect, useMemo, useCallback } from 'react';
import { Play, Pause, Clock, Settings2, Radio, Calendar, SkipBack, SkipForward, Timer } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface PlaybackProps {
  onTimeChange?: (time: Date) => void;
  onTimeRangeChange?: (start: Date, end: Date) => void;
  jumpToTime?: Date | null;
}

export const Playback = ({ onTimeChange, onTimeRangeChange, jumpToTime }: PlaybackProps) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [startTime, setStartTime] = useState(() => new Date("2025-01-01T00:00:00Z"));
  const [endTime, setEndTime] = useState(() => new Date("2025-02-01T00:00:00Z"));
  const [currentTime, setCurrentTime] = useState(100);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

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

  useEffect(() => {
    onTimeRangeChange?.(startTime, endTime);
  }, [startTime, endTime, onTimeRangeChange]);

  useEffect(() => {
    if (!isLive) return;
    const interval = setInterval(() => {
      // Don't auto-advance end time in 2025 mode unless explicitly wanted
      // setEndTime(new Date());
      // setCurrentTime(100);
    }, 5000);
    return () => clearInterval(interval);
  }, [isLive]);

  useEffect(() => {
    if (!jumpToTime) return;
    const totalMs = endTime.getTime() - startTime.getTime();
    if (totalMs <= 0) return;
    const targetMs = jumpToTime.getTime() - startTime.getTime();
    const pct = Math.max(0, Math.min(100, (targetMs / totalMs) * 100));
    setCurrentTime(pct);
    setIsPlaying(false);
  }, [jumpToTime, startTime, endTime]);

  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setCurrentTime(prev => {
        const totalMs = endTime.getTime() - startTime.getTime();
        const stepMs = 1000 * 60 * 10 * playbackSpeed;
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

  return (
    <div className="rounded-xl bg-card border border-border p-[10px] w-full shadow-2xl animate-in fade-in duration-300">
      <div className="flex flex-col gap-[10px]">

        {/* 0. HEADER */}
        <div className="flex items-center gap-[10px] px-[10px] py-[5px] border-b border-border/40 mb-[5px]">
          <Timer className="h-4 w-4 text-primary" />
          <span className="text-sm font-black uppercase tracking-widest text-foreground/80">Playback</span>
        </div>

        {/* 1. TIMELINE - VIDEO PLAYER STYLE */}
        <div className="space-y-[10px]">
          <div className="relative h-[9px] bg-muted/20 border border-border/40 rounded-lg cursor-pointer group/slider">
            <div
              className="absolute left-0 top-0 h-full bg-primary rounded-l-lg transition-none"
              style={{ width: `${currentTime}%` }}
            />
            {/* Slider Handle */}
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-[15px] w-[15px] bg-white rounded-full shadow-lg border-2 border-primary z-10 pointer-events-none transition-none"
              style={{ left: `${currentTime}%` }}
            />
            <input
              type="range"
              min={0}
              max={100}
              step={0.01}
              value={currentTime}
              onChange={(e) => {
                setCurrentTime(parseFloat(e.target.value));
                setIsPlaying(false);
              }}
              className="absolute left-0 top-0 w-full h-full opacity-0 cursor-pointer pointer-events-auto z-20"
            />
          </div>

          <div className="flex justify-between items-center text-[10px] font-bold text-muted-foreground uppercase tracking-widest px-[10px]">
            <div className="flex items-center gap-[10px]">
              <span className="text-foreground/60">{format(startTime, "MMM dd, HH:mm")}</span>
              <div className="h-3 w-px bg-border" />
              <div className={cn(
                "font-mono text-xs tracking-normal normal-case",
                isLive ? "text-red-500" : "text-primary"
              )}>
                {format(displayTime, "HH:mm:ss")}
              </div>
            </div>
            <div className="flex items-center gap-[10px]">
              <span className="text-foreground/40">{isLive ? 'Present (Live)' : format(endTime, "MMM dd, HH:mm")}</span>
            </div>
          </div>
        </div>

        {/* 2. CONTROLS ROW - YOUTUBE STYLE */}
        <div className="flex flex-col gap-[10px] pt-[10px] border-t border-border">

          <div className="flex items-center justify-between">
            {/* LEFT: MAIN ACTIONS */}
            <div className="flex items-center gap-[10px]">
              <Button
                variant="outline"
                size="icon"
                className="h-[42px] w-[42px] btn-standard border-border/60"
                onClick={() => {
                  setCurrentTime(0);
                  setIsPlaying(false);
                }}
                title="Jump to Start"
              >
                <SkipBack className="h-5 w-5 fill-muted-foreground/20" />
              </Button>

              <Button
                onClick={() => setIsPlaying(!isPlaying)}
                variant="outline"
                size="icon"
                className="h-[42px] w-[42px] btn-standard border-primary/20 bg-primary/5 hover:bg-primary/10"
              >
                {isPlaying ? <Pause className="h-5 w-5 text-primary fill-primary" /> : <Play className="h-5 w-5 text-primary fill-primary" />}
              </Button>

              <Button
                variant="outline"
                size="icon"
                className="h-[42px] w-[42px] btn-standard border-border/60"
                onClick={() => {
                  setCurrentTime(100);
                  setIsPlaying(false);
                }}
                title="Jump to End"
              >
                <SkipForward className="h-5 w-5 fill-muted-foreground/20" />
              </Button>

              <div className="h-6 w-px bg-border mx-[10px]" />

              <Button
                variant="outline"
                size="icon"
                className={cn(
                  "h-[42px] w-[42px] btn-standard",
                  isLive ? "border-red-500/50 text-red-500 bg-red-500/5" : "text-muted-foreground border-border/60"
                )}
                onClick={() => {
                  if (!isLive) {
                    setCurrentTime(100);
                    setIsPlaying(false);
                  }
                }}
                title="Go Live"
              >
                <Radio className={cn("h-5 w-5", isLive && "animate-pulse")} />
              </Button>
            </div>

            {/* CENTER: SPEED DROPDOWN */}
            <div className="flex items-center">
              <Select value={playbackSpeed.toString()} onValueChange={(v) => setPlaybackSpeed(parseFloat(v))}>
                <SelectTrigger className="w-[100px] h-[42px] bg-muted/5 border-border rounded-xl font-bold text-xs ring-0 focus:ring-0">
                  <SelectValue placeholder="Speed" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border rounded-xl shadow-2xl">
                  {[0.5, 1, 5, 20, 100].map((s) => (
                    <SelectItem key={s} value={s.toString()} className="text-xs font-bold py-[10px] rounded-lg focus:bg-primary/10 focus:text-primary">
                      {s === 1 ? 'Normal' : `${s}x`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* RIGHT: SETTINGS */}
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className="h-[42px] w-[42px] btn-standard border-border/60">
                  <Settings2 className="h-5 w-5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[300px] p-[10px] bg-card border-border rounded-xl shadow-2xl" align="end">
                <div className="space-y-[10px]">
                  <div className="flex flex-col gap-[10px]">
                    <div className="flex items-center gap-[10px]">
                      <Calendar className="h-[15px] w-[15px] text-foreground" />
                      <h4 className="font-bold text-base text-foreground">Playback Settings</h4>
                    </div>
                    <p className="text-xs text-muted-foreground">Define your operational timeframe (UTC)</p>
                  </div>

                  <div className="space-y-[10px] pt-[10px] border-t border-border">
                    <div className="space-y-[10px]">
                      <label className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60">Search Start</label>
                      <input
                        type="datetime-local"
                        className="w-full bg-muted/20 border border-border px-[10px] py-[10px] text-sm rounded-lg focus:outline-none"
                        value={format(startTime, "yyyy-MM-dd'T'HH:mm")}
                        onChange={(e) => {
                          const d = new Date(e.target.value);
                          if (!isNaN(d.getTime())) setStartTime(d);
                        }}
                      />
                    </div>
                    <div className="space-y-[10px]">
                      <label className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60">Search End</label>
                      <input
                        type="datetime-local"
                        className="w-full bg-muted/20 border border-border px-[10px] py-[10px] text-sm rounded-lg focus:outline-none"
                        value={format(endTime, "yyyy-MM-dd'T'HH:mm")}
                        onChange={(e) => {
                          const d = new Date(e.target.value);
                          if (!isNaN(d.getTime())) setEndTime(d);
                        }}
                      />
                    </div>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>

      </div>
    </div>
  );
};
