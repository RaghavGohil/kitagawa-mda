import { useState, useMemo, useCallback, useEffect } from "react";

import { Header } from "@/components/layout/Header";
import { Loader2 } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import { VesselInfoPanel } from "@/components/panels/VesselInfoPanel";
import { LayerControl } from "@/components/panels/LayerControl";
import { SearchFilterPanel } from "@/components/panels/SearchFilterPanel";
import { Playback } from "@/components/panels/Playback";
import { LeftDrawer } from "@/components/layout/LeftDrawer";
import { Alerts } from "@/components/panels/Alerts";

import {
  Vessel,
  AnomalyType,
  ZoneType,
} from "@/types";

import {
  anomalyTypeData,
  zoneTypeData,
} from "@/data/data";

import { useVessels, useVessel, useAlerts } from "@/hooks/useVessels";

const Index = () => {
  /* ================= API DATA ================= */

  const [mapBounds, setMapBounds] = useState<{ minLon: number; minLat: number; maxLon: number; maxLat: number } | undefined>();
  const [mapZoom, setMapZoom] = useState(10);

  const { data: vesselsData, isLoading: vesselsLoading, error } = useVessels({
    limit: 2000,
    bounds: mapBounds,
    zoom: mapZoom
  });
  const [alertLimit, setAlertLimit] = useState(20);
  const { data: alertsData, isLoading: alertsLoading } = useAlerts(alertLimit);

  const vessels = vesselsData?.vessels ?? [];
  const alerts = (alertsData ?? []);

  /* ================= VESSEL DETAIL (for sidebar) ================= */

  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);
  const { data: vesselDetail, isLoading: isDetailLoading } = useVessel(selectedVessel?.id);

  // Merge detail data into selected vessel when available
  const enrichedVessel = useMemo(() => {
    if (!selectedVessel) return null;
    if (!vesselDetail) return selectedVessel;
    return { ...selectedVessel, ...vesselDetail };
  }, [selectedVessel, vesselDetail]);

  /* ================= PLAYBACK TIME ================= */
  const [playbackTime, setPlaybackTime] = useState<Date>(() => new Date("2025-01-01T00:00:00Z")); // Default to Jan 2025
  const [jumpToTime, setJumpToTime] = useState<Date | null>(null);
  const [timeRangeMs, setTimeRangeMs] = useState<number>(2 * 24 * 60 * 60 * 1000); // Default 2 days

  const handleTimeRangeChange = useCallback((start: Date, end: Date) => {
    setTimeRangeMs(end.getTime() - start.getTime());
  }, []);

  /* ================= STATE ================= */

  const [filteredVessels, setFilteredVessels] = useState<Vessel[]>([]);


  useEffect(() => {
    if (vessels.length > 0) {
      setFilteredVessels(vessels);
    }
  }, [vessels]);

  const allAnomalyTypes = Object.keys(anomalyTypeData) as AnomalyType[];
  const allZoneTypes = Object.keys(zoneTypeData) as ZoneType[];

  const [visibleAnomalyTypes, setVisibleAnomalyTypes] = useState<Set<AnomalyType>>(
    () => new Set(allAnomalyTypes),
  );

  const [visibleZoneTypes, setVisibleZoneTypes] = useState<Set<ZoneType>>(
    () => new Set(['eez', 'shipping_lane'] as ZoneType[]), // Start with EEZ and Shipping Lanes visible
  );

  const [showTracks, setShowTracks] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(true);

  /* ================= HANDLERS ================= */

  const handleAnomalyTypesToggle = useCallback((type: AnomalyType) => {
    setVisibleAnomalyTypes((prev) => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }, []);

  const handleZoneTypesToggle = useCallback((type: ZoneType) => {
    setVisibleZoneTypes((prev) => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }, []);

  const handleVesselSelect = useCallback((vessel: Vessel | null) => {
    setSelectedVessel(vessel);
    setDrawerOpen(true);
    // Jump playback to vessel's detection time
    if (vessel?.position?.timestamp) {
      setJumpToTime(new Date(vessel.position.timestamp));
    }
  }, []);

  const handleAlertClick = useCallback((alertVesselId: string) => {
    // alertVesselId is like "unidentified-123" or "367692620" (MMSI)
    // Vessel list IDs are like "vessel--123" or "vessel-367692620"
    let targetId: string;
    if (alertVesselId.startsWith('unidentified-')) {
      const num = alertVesselId.replace('unidentified-', '');
      targetId = `vessel--${num}`;
    } else {
      targetId = `vessel-${alertVesselId}`;
    }

    // Try to find the vessel in the already-loaded list
    const found = vessels.find(v => v.id === targetId);
    if (found) {
      handleVesselSelect(found);
    } else {
      // Create a minimal stub so useVessel can fetch details
      handleVesselSelect({
        id: targetId,
        mmsi: '',
        name: alertVesselId,
        position: { lat: 0, lng: 0, timestamp: new Date(), speed: 0, heading: 0, course: 0 },
        track: [],
        anomaly: { type: 'anomaly', confidence: 0, description: '' },
      } as Vessel);
    }
  }, [vessels, handleVesselSelect]);

  useEffect(() => {
    if (!selectedVessel) setDrawerOpen(true);
  }, [selectedVessel]);

  /* ================= FILTERED VESSELS ================= */

  const visibleVessels = useMemo(() => {
    return filteredVessels.filter(
      (v) => visibleAnomalyTypes.has(v.anomaly.type),
    );
  }, [filteredVessels, visibleAnomalyTypes]);

  // Filter by playback time
  const timeFilteredVessels = useMemo(() => {
    return visibleVessels.filter(v =>
      v.position.timestamp.getTime() <= playbackTime.getTime()
    );
  }, [visibleVessels, playbackTime]);

  /* ================= LOADING STATE ================= */

  /* ================= LOADING STATE ================= */
  // if (isLoading) {
  //   return (
  //     <div className="h-screen w-screen flex items-center justify-center bg-background">
  //       <div className="text-center">
  //         <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
  //         <p className="text-muted-foreground">Loading vessel data...</p>
  //       </div>
  //     </div>
  //   );
  // }

  if (error) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <div className="text-center max-w-md p-6">
          <div className="text-destructive text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold mb-2">Connection Error</h2>
          <p className="text-muted-foreground mb-4">
            Unable to connect to the backend API. Please ensure the server is
            running on port 8000.
          </p>
          <code className="text-xs bg-muted p-2 rounded block">
            cd server && uvicorn main:app --reload --port 8000
          </code>
        </div>
      </div>
    );
  }

  /* ================= RENDER ================= */

  return (
    <div className="h-screen w-screen overflow-hidden bg-background flex flex-col font-sans">
      <Header />

      <main className="relative flex-1 w-full overflow-hidden">
        {/* ================= MAP ================= */}
        <div className="absolute inset-0 z-0">
          <MapView
            vessels={timeFilteredVessels}
            selectedVessel={enrichedVessel}
            onVesselSelect={handleVesselSelect}
            showTracks={showTracks}
            visibleZoneTypes={visibleZoneTypes}
            playbackTime={playbackTime}
            timeRangeMs={timeRangeMs}
            onViewChange={(bounds, zoom) => {
              setMapBounds(bounds);
              setMapZoom(zoom);
            }}
          />
          {vesselsLoading && (
            <div className="absolute top-[10px] left-1/2 -translate-x-1/2 z-[1000] bg-card/90 backdrop-blur-md px-[14px] py-[10px] rounded-xl border border-primary/30 flex items-center gap-[10px] shadow-2xl animate-in slide-in-from-top-2 duration-300">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              <span className="text-[10px] uppercase font-black tracking-[0.2em] text-primary animate-pulse-subtle">Updating</span>
            </div>
          )}
        </div>

        {/* ================= SEARCH HUB (FLOATING) ================= */}
        <div className="absolute top-[10px] right-[10px] z-20">
          <SearchFilterPanel
            vessels={vessels}
            onFilteredVessels={setFilteredVessels}
            onVesselSelect={handleVesselSelect}
            isDocked={false}
          />
        </div>

        {/* ================= COMMAND CENTER (LEFT DRAWER) ================= */}
        <LeftDrawer
          open={drawerOpen}
          width={typeof window !== 'undefined' && window.innerWidth < 768 ? '100%' : '380px'}
          collapsedWidth={0}
          onToggle={() => setDrawerOpen((o) => !o)}
        >
          <div className="flex flex-col h-full">
            {/* DYNAMIC CONTENT AREA */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {enrichedVessel ? (
                <VesselInfoPanel vessel={enrichedVessel} isLoading={isDetailLoading} />
              ) : (
                <div className="p-[10px] space-y-[10px]">
                  <Alerts
                    alerts={alerts}
                    isLoading={alertsLoading}
                    onAlertClick={handleAlertClick}
                    alertLimit={alertLimit}
                    onAlertLimitChange={setAlertLimit}
                  />
                  <LayerControl
                    visibleAnomalyTypes={visibleAnomalyTypes}
                    visibleZoneTypes={visibleZoneTypes}
                    showTracks={showTracks}
                    onAnomalyTypesToggle={handleAnomalyTypesToggle}
                    onZoneTypesToggle={handleZoneTypesToggle}
                    onShowTracksChange={setShowTracks}
                  />
                </div>
              )}
            </div>
          </div>
        </LeftDrawer>

        {/* ================= TIME CONTROLS ================= */}
        <div className="absolute bottom-[10px] left-1/2 -translate-x-1/2 z-20 w-full max-w-2xl px-[10px] pointer-events-auto">
          <Playback
            onTimeChange={setPlaybackTime}
            onTimeRangeChange={handleTimeRangeChange}
            jumpToTime={jumpToTime}
          />
        </div>

      </main>
    </div>
  );
};

export default Index;
