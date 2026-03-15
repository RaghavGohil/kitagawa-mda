"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { Header } from "@/components/layout/Header";
import { Alerts } from "@/components/panels/Alerts";
import { LayerControl } from "@/components/panels/LayerControl";
import { SearchFilterPanel } from "@/components/panels/SearchFilterPanel";
import { VesselInfoPanel } from "@/components/panels/VesselInfoPanel";
import { Playback } from "@/components/panels/Playback";
import { useVessels, useVessel, useAlerts } from "@/hooks/useVessels";
import { Vessel, AnomalyType, ZoneType } from "@/types";
import { Loader2, X, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MapView = dynamic(
  () => import("@/components/map/MapView").then(mod => ({ default: mod.MapView })),
  { ssr: false, loading: () => <div className="h-full w-full bg-background" /> },
);

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 1024);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return isMobile;
}

export default function DashboardPage() {
  const isMobile = useIsMobile();

  const [selectedVesselId, setSelectedVesselId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showTracks, setShowTracks] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(new Date());
  const [jumpToTime, setJumpToTime] = useState<Date | null>(null);
  const [timeRangeMs, setTimeRangeMs] = useState<number>(31 * 24 * 60 * 60 * 1000);

  const [visibleAnomalyTypes, setVisibleAnomalyTypes] = useState<Set<AnomalyType>>(
    new Set(["identified", "no_anomaly", "anomaly", "unidentified"]),
  );
  const [visibleZoneTypes, setVisibleZoneTypes] = useState<Set<ZoneType>>(
    new Set(["eez", "shipping_lane"]),
  );

  const [mapBounds, setMapBounds] = useState<{ minLon: number; minLat: number; maxLon: number; maxLat: number } | undefined>();
  const [mapZoom, setMapZoom] = useState<number | undefined>();

  useEffect(() => {
    setSidebarOpen(!isMobile);
  }, [isMobile]);

  // ===================== DATA =====================
  const { data: vesselData, isLoading: isLoadingVessels } = useVessels({
    bounds: mapBounds,
    zoom: mapZoom,
    limit: 500,
  });
  const { data: selectedVesselDetail, isLoading: isLoadingDetail } = useVessel(selectedVesselId);
  const { data: alerts = [], isLoading: isLoadingAlerts } = useAlerts(50);

  const allVessels = vesselData?.vessels ?? [];

  // ===================== FILTERING =====================
  const [filteredVessels, setFilteredVessels] = useState<Vessel[] | null>(null);

  const visibleVessels = useMemo(() => {
    const base = filteredVessels || allVessels;
    return base.filter(v => visibleAnomalyTypes.has(v.anomaly.type));
  }, [allVessels, filteredVessels, visibleAnomalyTypes]);

  const timeFilteredVessels = useMemo(() => {
    return visibleVessels.filter(v => v.position.timestamp.getTime() <= playbackTime.getTime());
  }, [visibleVessels, playbackTime]);

  // ===================== HANDLERS =====================
  const handleVesselSelect = useCallback((vessel: Vessel | null) => {
    setSelectedVesselId(vessel?.id || null);
    if (vessel && isMobile) setSidebarOpen(false);
  }, [isMobile]);

  const handleAlertClick = useCallback((vesselId: string) => {
    const vessel = allVessels.find(v => v.id === `vessel-${vesselId}` || v.id === vesselId);
    if (vessel) {
      handleVesselSelect(vessel);
      setJumpToTime(vessel.position.timestamp);
    }
  }, [allVessels, handleVesselSelect]);

  const toggleAnomalyType = useCallback((type: AnomalyType) => {
    setVisibleAnomalyTypes(prev => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }, []);

  const toggleZoneType = useCallback((type: ZoneType) => {
    setVisibleZoneTypes(prev => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }, []);

  const handleViewChange = useCallback((bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }, zoom: number) => {
    setMapBounds(bounds);
    setMapZoom(zoom);
  }, []);

  const handleTimeChange = useCallback((time: Date) => setPlaybackTime(time), []);
  const handleTimeRangeChange = useCallback((start: Date, end: Date) => setTimeRangeMs(end.getTime() - start.getTime()), []);

  const selectedVessel = selectedVesselId
    ? selectedVesselDetail || allVessels.find(v => v.id === selectedVesselId) || null
    : null;

  return (
    <div className="h-screen w-full overflow-hidden bg-background flex flex-col">
      <Header />

      <main className="relative flex-1 w-full overflow-hidden flex flex-row">
        {/* =================== MAP AREA =================== */}
        <div className="relative flex-1 h-full min-w-0 overflow-hidden">
          {/* =================== MAP =================== */}
          <div className="absolute inset-0 z-0">
            <MapView
              vessels={timeFilteredVessels}
              selectedVessel={selectedVessel}
              onVesselSelect={handleVesselSelect}
              showTracks={showTracks}
              visibleZoneTypes={visibleZoneTypes}
              playbackTime={playbackTime}
              timeRangeMs={timeRangeMs}
              onViewChange={handleViewChange}
            />
            {isLoadingVessels && (
              <div className="absolute top-2 left-1/2 -translate-x-1/2 z-1000 bg-background/95 backdrop-blur-md border border-border rounded-lg px-6 py-2.5 flex items-center gap-3 shadow-2xl transition-all duration-300">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span className="text-sm font-medium tracking-tight text-foreground">Loading Vessels...</span>
              </div>
            )}
          </div>

          {/* SIDEBAR TAB TOGGLE (Visible only when sidebar is closed) */}
          {!sidebarOpen && (
            <div className="absolute top-0 left-0 z-50">
              <Button
                variant="outline"
                className="h-20 w-8 rounded-none rounded-br-md border-t-0 border-l-0 bg-background hover:bg-accent flex items-center justify-center transition-all duration-200 group"
                onClick={() => setSidebarOpen(true)}
              >
                <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:scale-110 transition-transform" />
              </Button>
            </div>
          )}

          {/* =================== SIDEBAR (OVERLAY) =================== */}
          {sidebarOpen && (
            <aside className={cn(
              "absolute top-0 left-0 z-50 h-full bg-background border-r border-border overflow-y-auto shadow-2xl transition-all duration-300",
              isMobile ? "w-full" : "w-[340px]",
            )}>
              <div className="flex flex-col h-full">
                {/* Sidebar header */}
                <div className="flex items-center justify-between px-5 h-20 border-b border-border shrink-0">
                  <div className="flex flex-col">
                    <h2 className="text-sm font-bold uppercase tracking-widest text-foreground">Explorer</h2>
                  </div>
                  <Button variant="ghost" size="icon" className="h-8 w-8 -mr-1" onClick={() => setSidebarOpen(false)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {/* Sidebar content */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                  <SearchFilterPanel
                    vessels={allVessels}
                    onFilteredVessels={setFilteredVessels}
                    onVesselSelect={handleVesselSelect}
                    isDocked
                  />
                  <Alerts alerts={alerts} isLoading={isLoadingAlerts} onAlertClick={handleAlertClick} />
                  <LayerControl
                    visibleAnomalyTypes={visibleAnomalyTypes}
                    visibleZoneTypes={visibleZoneTypes}
                    showTracks={showTracks}
                    onAnomalyTypesToggle={toggleAnomalyType}
                    onZoneTypesToggle={toggleZoneType}
                    onShowTracksChange={setShowTracks}
                  />
                </div>
              </div>
            </aside>
          )}

          {/* =================== VESSEL INFO =================== */}
          {selectedVessel && (
            <aside className={cn(
              "absolute top-0 right-0 h-full border-l border-border bg-background overflow-y-auto shadow-2xl transition-all",
              isMobile ? "z-50 w-full" : "z-20 w-[360px]",
            )}>
              <div className="sticky top-0 z-10 flex justify-between items-center px-5 py-4 bg-background border-b border-border">
                <span className="text-sm font-semibold truncate uppercase tracking-tight">{selectedVessel.name}</span>
                <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => setSelectedVesselId(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <VesselInfoPanel vessel={selectedVessel} isLoading={isLoadingDetail} />
            </aside>
          )}

          {/* =================== PLAYBACK =================== */}
          <div className="absolute bottom-6 left-0 right-0 z-10 px-4 flex justify-center pointer-events-none">
            <div className="w-full max-w-[600px] pointer-events-auto">
              <Playback
                onTimeChange={handleTimeChange}
                onTimeRangeChange={handleTimeRangeChange}
                jumpToTime={jumpToTime}
                compact={isMobile}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
