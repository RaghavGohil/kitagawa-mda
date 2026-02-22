import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchVessels,
  fetchVessel,
  fetchAlerts,
  fetchStats,
  checkApiHealth,
  fetchPipelineStatus,
} from "@/lib/api";

export function useVessels(options?: {
  anomalyOnly?: boolean;
  satelliteType?: "SAR" | "EO";
  limit?: number;
  offset?: number;
  bounds?: { minLon: number; minLat: number; maxLon: number; maxLat: number };
  zoom?: number;
}) {
  return useQuery({
    queryKey: ["vessels", options],
    queryFn: () => fetchVessels(options),
    placeholderData: (previousData) => previousData,
    staleTime: 10 * 1000, // 10 seconds
    refetchInterval: 20 * 1000, // 20 seconds
  });
}

export function useVessel(vesselId: string | null | undefined) {
  return useQuery({
    queryKey: ["vessel", vesselId],
    queryFn: () => fetchVessel(vesselId!),
    enabled: !!vesselId,
    staleTime: 60 * 1000,
  });
}

export function useAlerts(limit?: number) {
  return useQuery({
    queryKey: ["alerts", limit],
    queryFn: () => fetchAlerts(limit),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useApiHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: checkApiHealth,
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
    retry: 1,
  });
}

export function usePipelineStatus() {
  const queryClient = useQueryClient();

  useEffect(() => {
    // Construct WS URL from API URL base
    const apiUrl = (import.meta as any).env.VITE_API_URL || "http://localhost:8000";
    // If it's localhost:8000, use it. In prod, it might be the same domain.
    const wsBase = apiUrl.replace(/^http/, "ws");
    const wsUrl = `${wsBase}/api/v1/pipeline/ws`;

    let socket: WebSocket | null = null;
    let reconnectTimeout: any = null;

    const connect = () => {
      try {
        socket = new WebSocket(wsUrl);

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            const prev = queryClient.getQueryData(["pipeline-status"]) as any;
            queryClient.setQueryData(["pipeline-status"], data);

            // If we moved to a new image or finished a stage, refetch vessels
            if (data.current_image !== prev?.current_image ||
              data.current_stage !== prev?.current_stage ||
              (data.status === 'idle' && prev?.status === 'running')) {
              queryClient.invalidateQueries({ queryKey: ["vessels"] });
            }
          } catch (err) {
            console.error("[WS] Data parse error", err);
          }
        };

        socket.onclose = () => {
          reconnectTimeout = setTimeout(connect, 5000);
        };

        socket.onerror = () => {
          socket?.close();
        };
      } catch (err) {
        console.error("[WS] Connection error", err);
        reconnectTimeout = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (socket) socket.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [queryClient]);

  return useQuery({
    queryKey: ["pipeline-status"],
    queryFn: fetchPipelineStatus,
    staleTime: 1000,
    refetchInterval: (query) => {
      const data = query.state.data;
      // Much slower polling since we have WS as primary
      return data?.status === "running" ? 10000 : 30000;
    },
  });
}
