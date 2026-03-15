"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { Play, Pause, Radio, Calendar, SkipBack, SkipForward, Settings2, Timer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

interface PlaybackProps {
    onTimeChange?: (time: Date) => void;
    onTimeRangeChange?: (start: Date, end: Date) => void;
    jumpToTime?: Date | null;
    compact?: boolean;
}

export const Playback = ({ onTimeChange, onTimeRangeChange, jumpToTime, compact }: PlaybackProps) => {
    const [isPlaying, setIsPlaying] = useState(false);
    const [startTime, setStartTime] = useState(() => new Date("2025-01-01T00:00:00Z"));
    const [endTime, setEndTime] = useState(() => new Date("2025-02-01T00:00:00Z"));
    const [currentTime, setCurrentTime] = useState(100);
    const [playbackSpeed, setPlaybackSpeed] = useState(1);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    const isLive = currentTime >= 99.5;

    const getTimeFromValue = useCallback((value: number): Date => {
        const totalMs = endTime.getTime() - startTime.getTime();
        return new Date(startTime.getTime() + (value / 100) * totalMs);
    }, [startTime, endTime]);

    const displayTime = useMemo(
        () => isLive ? new Date() : getTimeFromValue(currentTime),
        [currentTime, getTimeFromValue, isLive],
    );

    useEffect(() => { onTimeChange?.(displayTime); }, [displayTime, onTimeChange]);
    useEffect(() => { onTimeRangeChange?.(startTime, endTime); }, [startTime, endTime, onTimeRangeChange]);

    useEffect(() => {
        if (!jumpToTime) return;
        const totalMs = endTime.getTime() - startTime.getTime();
        if (totalMs <= 0) return;
        const pct = Math.max(0, Math.min(100, ((jumpToTime.getTime() - startTime.getTime()) / totalMs) * 100));
        setCurrentTime(pct);
        setIsPlaying(false);
    }, [jumpToTime, startTime, endTime]);

    useEffect(() => {
        if (!isPlaying) return;
        const interval = setInterval(() => {
            setCurrentTime(prev => {
                const totalMs = endTime.getTime() - startTime.getTime();
                const stepPercent = ((1000 * 60 * 10 * playbackSpeed) / totalMs) * 100;
                const next = prev + stepPercent;
                if (next >= 100) { setIsPlaying(false); return 100; }
                return next;
            });
        }, 100);
        return () => clearInterval(interval);
    }, [isPlaying, playbackSpeed, startTime, endTime]);

    return (
        <div className="rounded-lg bg-background border border-border p-4 shadow-lg w-full">
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Timer className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-semibold">Playback</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className={cn(
                        "text-sm font-mono tabular-nums",
                        isLive ? "text-red-500" : "text-foreground",
                    )}>
                        {mounted ? format(displayTime, compact ? "HH:mm:ss" : "MMM dd, yyyy HH:mm:ss") : "\u00A0"}
                    </span>
                    {isLive && (
                        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-red-500/10 hover:bg-red-500/20 transition-colors cursor-default group/live">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                            </span>
                            <span className="text-[10px] font-bold tracking-wider text-red-500 uppercase">LIVE</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Timeline slider */}
            <div className="relative h-2 bg-secondary rounded-full mb-4 cursor-pointer group">
                <div
                    className="absolute left-0 top-0 h-full bg-foreground/60 rounded-full transition-[width] duration-100"
                    style={{ width: `${currentTime}%` }}
                />
                <div
                    className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-4 w-4 bg-foreground rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ left: `${currentTime}%` }}
                />
                <input
                    type="range"
                    min={0} max={100} step={0.01}
                    value={currentTime}
                    onChange={(e) => { setCurrentTime(parseFloat(e.target.value)); setIsPlaying(false); }}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                />
            </div>

            {/* Time labels - Always visible, refined for mobile */}
            <div className="flex justify-between text-[10px] sm:text-xs text-muted-foreground mb-3">
                <span>{format(startTime, "MMM dd, yyyy")}</span>
                <span>{format(endTime, "MMM dd, yyyy")}</span>
            </div>

            <Separator className="mb-3" />

            {/* Controls */}
            {/* Controls */}
            <div className="flex items-center justify-between gap-3">
                {/* Transport */}
                <div className="flex items-center gap-1 shrink-0">
                    <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => { setCurrentTime(0); setIsPlaying(false); }}>
                        <SkipBack className="h-4 w-4" />
                    </Button>
                    <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => setIsPlaying(!isPlaying)}>
                        {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    </Button>
                    <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => { setCurrentTime(100); setIsPlaying(false); }}>
                        <SkipForward className="h-4 w-4" />
                    </Button>
                </div>

                {/* Speed + Settings */}
                <div className="flex items-center gap-2">
                    <Select value={playbackSpeed.toString()} onValueChange={(v) => { if (v) setPlaybackSpeed(parseFloat(v)); }}>
                        <SelectTrigger className={cn("h-9 text-sm w-fit min-w-[64px]")}>
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {[0.5, 1, 5, 20, 100].map((s) => (
                                <SelectItem key={s} value={s.toString()}>
                                    {s === 1 ? "1×" : `${s}×`}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    <Popover>
                        <PopoverTrigger className="inline-flex items-center justify-center h-9 w-9 rounded-md border border-input bg-background hover:bg-muted hover:text-foreground transition-all duration-200 active:translate-y-px">
                            <Settings2 className="h-4 w-4 text-foreground" />
                        </PopoverTrigger>
                        <PopoverContent className="w-72 p-4" align="end" side="top">
                            <div className="space-y-4">
                                <div>
                                    <h4 className="text-sm font-semibold">Time Range</h4>
                                    <p className="text-sm text-muted-foreground mt-0.5">Set playback bounds (UTC)</p>
                                </div>
                                <Separator />
                                <div className="space-y-3">
                                    <div className="space-y-1.5">
                                        <label className="text-sm text-muted-foreground">Start</label>
                                        <input
                                            type="datetime-local"
                                            className="w-full bg-secondary border border-border px-3 py-2 text-sm rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
                                            value={format(startTime, "yyyy-MM-dd'T'HH:mm")}
                                            onChange={(e) => { const d = new Date(e.target.value); if (!isNaN(d.getTime())) setStartTime(d); }}
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <label className="text-sm text-muted-foreground">End</label>
                                        <input
                                            type="datetime-local"
                                            className="w-full bg-secondary border border-border px-3 py-2 text-sm rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
                                            value={format(endTime, "yyyy-MM-dd'T'HH:mm")}
                                            onChange={(e) => { const d = new Date(e.target.value); if (!isNaN(d.getTime())) setEndTime(d); }}
                                        />
                                    </div>
                                </div>
                            </div>
                        </PopoverContent>
                    </Popover>
                </div>
            </div>
        </div>
    );
};
