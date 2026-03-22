"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { Header } from "@/components/layout/Header";
import { Explorer } from "@/components/layout/Explorer";
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
  const [showTracks, setShowTracks] = useState(true);
  const [showLiveAIS, setShowLiveAIS] = useState(true);
  const [showCoverage, setShowCoverage] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(new Date());
  const [jumpToTime, setJumpToTime] = useState<Date | null>(null);
  const [timeRangeMs, setTimeRangeMs] = useState<number>(24 * 60 * 60 * 1000);

  const [visibleAnomalyTypes, setVisibleAnomalyTypes] = useState<Set<AnomalyType>>(
    new Set(["identified", "anomaly", "out_of_coverage"]),
  );
  const [visibleZoneTypes, setVisibleZoneTypes] = useState<Set<ZoneType>>(
    new Set(["eez", "shipping_lane"]),
  );

  const [mapBounds, setMapBounds] = useState<{ minLon: number; minLat: number; maxLon: number; maxLat: number } | undefined>();
  const [mapZoom, setMapZoom] = useState<number | undefined>();

  useEffect(() => {
    setSidebarOpen(!isMobile);
  }, [isMobile]);

  const handleViewChange = useCallback((bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number }, zoom: number) => {
    // Implement Overscan: fetch 25% more than the viewport to make panning smoother
    const lonPadding = (bounds.maxLon - bounds.minLon) * 0.25;
    const latPadding = (bounds.maxLat - bounds.minLat) * 0.25;

    setMapBounds({
      minLon: bounds.minLon - lonPadding,
      minLat: bounds.minLat - latPadding,
      maxLon: bounds.maxLon + lonPadding,
      maxLat: bounds.maxLat + latPadding,
    });
    setMapZoom(zoom);
  }, []);

  // ===================== DATA =====================
  // More aggressive dynamic vessel limit: ensure global and local completeness
  const vesselLimit = useMemo(() => {
    if (!mapZoom) return 1000;
    if (mapZoom >= 15) return 20000;
    if (mapZoom >= 12) return 10000;
    if (mapZoom >= 8) return 5000;
    if (mapZoom >= 5) return 2000;
    return 1000;
  }, [mapZoom]);

  const { data: vesselData, isLoading: isLoadingVessels } = useVessels({
    bounds: mapBounds,
    zoom: mapZoom,
    limit: vesselLimit,
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


  const handleTimeChange = useCallback((time: Date) => setPlaybackTime(time), []);
  const handleTimeRangeChange = useCallback((start: Date, end: Date) => setTimeRangeMs(end.getTime() - start.getTime()), []);

  const selectedVessel = selectedVesselId
    ? selectedVesselDetail || allVessels.find(v => v.id === selectedVesselId) || null
    : null;

  return (
    <div className="h-[100dvh] w-full overflow-hidden bg-background flex flex-col" data-vessel-panel-open={!!selectedVesselId}>
      <Header />

      <main className="relative flex-1 w-full overflow-hidden flex flex-row">
        {/* =================== MAP AREA =================== */}
        <div className="relative flex-1 h-full min-w-0 overflow-hidden">
          {/* =================== MAP =================== */}
          <div className="absolute inset-0 z-0 text-leaflet-nudge">
            <MapView
              vessels={timeFilteredVessels}
              selectedVessel={selectedVessel}
              onVesselSelect={handleVesselSelect}
              showTracks={showTracks}
              showLiveAIS={showLiveAIS}
              showCoverage={showCoverage}
              visibleZoneTypes={visibleZoneTypes}
              playbackTime={playbackTime}
              timeRangeMs={timeRangeMs}
              onViewChange={handleViewChange}
            />
            {isLoadingVessels && (
              <div className="absolute top-4 left-1/2 -translate-x-1/2 z-1000 bg-background/95 backdrop-blur-md border border-border rounded-lg px-6 py-2.5 flex items-center gap-3 shadow-2xl transition-all duration-300">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span className="text-sm font-medium tracking-tight text-foreground">Loading Vessels...</span>
              </div>
            )}
          </div>

          {/* =================== SIDEBAR (EXPLORER) =================== */}
          <Explorer
            open={sidebarOpen}
            onToggle={() => setSidebarOpen(prev => !prev)}
            width={isMobile ? "100%" : "340px"}
          >
            <div className="flex flex-col h-full bg-background border-r border-border shadow-2xl overflow-hidden">
              {/* Sidebar header */}
              <div className="flex items-center justify-between px-5 h-20 border-b border-border shrink-0">
                <div className="flex flex-col">
                  <h2 className="text-lg font-bold text-foreground">Explorer</h2>
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
                  showLiveAIS={showLiveAIS}
                  showCoverage={showCoverage}
                  onAnomalyTypesToggle={toggleAnomalyType}
                  onZoneTypesToggle={toggleZoneType}
                  onShowTracksChange={setShowTracks}
                  onShowLiveAISChange={setShowLiveAIS}
                  onShowCoverageChange={setShowCoverage}
                />
              </div>
            </div>
          </Explorer>

          {/* =================== VESSEL INFO =================== */}
          {selectedVessel && (
            <aside className={cn(
              "absolute top-0 right-0 h-full border-l border-border bg-background overflow-y-auto shadow-2xl",
              isMobile ? "z-[120] w-full" : "z-20 w-[360px]",
            )}>
              <div className="sticky top-0 z-10 flex justify-between items-center px-5 py-4 bg-background border-b border-border">
                <span className="text-sm font-semibold truncate uppercase tracking-tight">Vessel Info</span>
                <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => setSelectedVesselId(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <VesselInfoPanel vessel={selectedVessel} isLoading={isLoadingDetail} />
            </aside>
          )}

          {/* =================== PLAYBACK =================== */}
          <div className="absolute bottom-4 left-0 right-0 z-10 px-4 flex justify-center pointer-events-none">
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
