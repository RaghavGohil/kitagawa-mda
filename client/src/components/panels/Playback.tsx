import { useState, useEffect, useMemo } from 'react';
import { Play, Pause, SkipBack, SkipForward, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { format, subHours, addMinutes } from 'date-fns';

interface PlaybackProps {
  onTimeChange?: (time: Date) => void;
}

export const Playback = ({ onTimeChange }: PlaybackProps) => {
  const [isPlaying, setIsPlaying] = useState(false);

  /* ===================== TIME RANGE ===================== */
  // Data for Jan 2nd only exists from 00:00 to 06:00 UTC
  const startTime = useMemo(() => new Date("2025-01-02T00:00:00Z"), []);
  const now = useMemo(() => new Date("2025-01-02T06:00:00Z"), []);

  const [currentTime, setCurrentTime] = useState(50); // Start at 03:00 UTC (middle of data)
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  const getTimeFromValue = (value: number): Date => {
    const totalMinutes = 6 * 60; // 6 hour window where data exists
    const minutes = (value / 100) * totalMinutes;
    return addMinutes(startTime, minutes);
  };

  const displayTime = useMemo(
    () => getTimeFromValue(currentTime),
    [currentTime]
  );

  useEffect(() => {
    onTimeChange?.(displayTime);
  }, [displayTime, onTimeChange]);

  /* ===================== PLAYBACK LOOP ===================== */

  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      setCurrentTime(prev => {
        const next = prev + 0.1 * playbackSpeed;
        if (next >= 100) {
          setIsPlaying(false);
          return 100;
        }
        return next;
      });
    }, 100);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed]);

  /* ===================== SLIDER ===================== */

  const handleSliderChange = (value: number[]) => {
    setCurrentTime(value[0]);
    setIsPlaying(false);
  };

  /* ===================== UI ===================== */

  return (
    <div
      className="rounded-lg bg-card/95 border border-border/60 backdrop-blur"
    >
      <div className="p-2">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-primary" />
            <span className="text-xs text-muted-foreground">Playback</span>
          </div>
          <div className="font-mono text-sm">
            {format(displayTime, 'MMM dd, HH:mm')}
          </div>
        </div>

        {/* Slider */}
        <Slider
          value={[currentTime]}
          onValueChange={handleSliderChange}
          min={0}
          max={100}
          step={0.1}
          className="py-2"
        />

        {/* Time markers */}
        <div className="flex justify-between text-[10px] text-muted-foreground mt-2">
          <span>00:00</span>
          <span>01:30</span>
          <span>03:00</span>
          <span>04:30</span>
          <span>06:00</span>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-center gap-2 mt-3">
          <Button
            size="icon"
            className="h-8 w-8 bg-transparent hover:bg-muted text-white"
            onClick={() => setCurrentTime(0)}
          >
            <SkipBack className="h-4 w-4" />
          </Button>

          <Button
            size="icon"
            className="h-10 w-10 border bg-transparent hover:bg-muted text-white"
            onClick={() => setIsPlaying(p => !p)}
          >
            {isPlaying ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4 ml-0.5" />
            )}
          </Button>

          <Button
            size="icon"
            className="h-8 w-8 bg-transparent hover:bg-muted text-white"
            onClick={() => setCurrentTime(100)}
          >
            <SkipForward className="h-4 w-4" />
          </Button>

          {/* Speed */}
          <div className="ml-2 flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Speed:</span>
            {[1, 2, 4].map(speed => (
              <Button
                key={speed}
                className={`h-6 w-8 text-xs border border-border/60 text-white ${speed === playbackSpeed
                  ? 'bg-muted font-semibold'
                  : 'bg-transparent hover:bg-muted'
                  }`}
                onClick={() => setPlaybackSpeed(speed)}
              >
                {speed}x
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

