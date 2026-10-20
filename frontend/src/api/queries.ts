import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { addHistoryEntry, removeHistoryEntry } from "../lib/history";
import { api } from "./client";
import type { SearchCreatedResponse, SearchParams, SearchStatusResponse, Signal } from "./types";

const POLL_INTERVAL_MS = 3000;

export function useCreateSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: SearchParams) =>
      api.post<SearchCreatedResponse>("/search", {
        query: params.query,
        date_from: params.date_from || null,
        date_to: params.date_to || null,
      }),
    onSuccess: (data, params) => {
      addHistoryEntry(data.query_id, params.query);
      queryClient.invalidateQueries({ queryKey: ["searchStatus", data.query_id] });
    },
  });
}

export function useSearchStatus(queryId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["searchStatus", queryId],
    queryFn: () => api.get<SearchStatusResponse>(`/search/${queryId}/status`),
    enabled: enabled && queryId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "done" || status === "failed") return false;
      return POLL_INTERVAL_MS;
    },
  });
}

export function useCancelSearch() {
  return useMutation({
    mutationFn: (queryId: number) => api.post<void>(`/search/${queryId}/cancel`, {}),
    // у остановленного поиска нет результатов — в истории ему делать нечего
    onMutate: (queryId) => removeHistoryEntry(queryId),
  });
}

export function useSignalDetail(signalId: number | null) {
  return useQuery({
    queryKey: ["signal", signalId],
    queryFn: () => api.get<Signal>(`/insight/${signalId}`),
    enabled: signalId !== null,
  });
}
