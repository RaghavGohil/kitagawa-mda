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
  Alert,
  vesselTypeData,
  anomalyTypeData,
  VesselType,
  AnomalyType,
  ZoneType,
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
  const { data: alertsData, isLoading: alertsLoading } = useAlerts(50);

  const vessels = vesselsData?.vessels ?? [];
  const alerts = (alertsData ?? []) as Alert[];

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
  const [playbackTime, setPlaybackTime] = useState<Date>(new Date("2025-01-02T03:00:00Z"));

  /* ================= STATE ================= */

  const [filteredVessels, setFilteredVessels] = useState<Vessel[]>([]);


  useEffect(() => {
    if (vessels.length > 0) {
      setFilteredVessels(vessels);
    }
  }, [vessels]);

  const allVesselTypes = Object.keys(vesselTypeData) as VesselType[];
  const allAnomalyTypes = Object.keys(anomalyTypeData) as AnomalyType[];
  const allZoneTypes = Object.keys(zoneTypeData) as ZoneType[];

  const [visibleVesselTypes, setVisibleVesselTypes] = useState<Set<VesselType>>(
    () => new Set(allVesselTypes),
  );

  const [visibleAnomalyTypes, setVisibleAnomalyTypes] = useState<Set<AnomalyType>>(
    () => new Set(allAnomalyTypes),
  );

  const [visibleZoneTypes, setVisibleZoneTypes] = useState<Set<ZoneType>>(
    () => new Set(), // Start with all zones hidden
  );

  const [showTracks, setShowTracks] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(true);

  /* ================= HANDLERS ================= */

  const handleVesselTypesToggle = useCallback((type: VesselType) => {
    setVisibleVesselTypes((prev) => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }, []);

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
      (v) =>
        visibleVesselTypes.has(v.type) &&
        visibleAnomalyTypes.has(v.anomaly.type),
    );
  }, [filteredVessels, visibleVesselTypes, visibleAnomalyTypes]);

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
    <div className="h-screen w-screen overflow-hidden bg-background">
      <Header />

      <div className="relative h-[calc(100vh-56px)] w-full">
        {/* ================= MAP ================= */}
        <div className="absolute inset-0 z-0">
          <MapView
            vessels={timeFilteredVessels}
            selectedVessel={enrichedVessel}
            onVesselSelect={handleVesselSelect}
            showTracks={showTracks}
            visibleZoneTypes={visibleZoneTypes}
            playbackTime={playbackTime}
            onViewChange={(bounds, zoom) => {
              setMapBounds(bounds);
              setMapZoom(zoom);
            }}
          />
          {vesselsLoading && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-background/80 backdrop-blur-sm px-3 py-1.5 rounded-full border shadow-lg flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              <span className="text-xs font-medium">Updating map data...</span>
            </div>
          )}
        </div>

        {/* ================= LEFT DRAWER ================= */}
        <LeftDrawer
          open={drawerOpen}
          width="25%"
          collapsedWidth={0}
          onToggle={() => setDrawerOpen((o) => !o)}
        >
          {enrichedVessel ? (
            <VesselInfoPanel vessel={enrichedVessel} isLoading={isDetailLoading} />
          ) : (
            <div className="flex flex-col space-y-2">
              <Alerts alerts={alerts} isLoading={alertsLoading} onAlertClick={handleAlertClick} />
              <LayerControl
                visibleVesselTypes={visibleVesselTypes}
                visibleAnomalyTypes={visibleAnomalyTypes}
                visibleZoneTypes={visibleZoneTypes}
                showTracks={showTracks}
                onVesselTypesToggle={handleVesselTypesToggle}
                onAnomalyTypesToggle={handleAnomalyTypesToggle}
                onZoneTypesToggle={handleZoneTypesToggle}
                onShowTracksChange={setShowTracks}
              />
            </div>
          )}
        </LeftDrawer>

        {/* ================= SEARCH ================= */}
        <div className="absolute top-2 right-2 z-20 pointer-events-auto">
          <SearchFilterPanel
            vessels={vessels}
            onFilteredVessels={setFilteredVessels}
            onVesselSelect={handleVesselSelect}
          />
        </div>

        {/* ================= TIME ================= */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-20 w-full max-w-xl px-4 pointer-events-auto">
          <Playback onTimeChange={setPlaybackTime} />
        </div>

      </div>
    </div>
  );
};

export default Index;
