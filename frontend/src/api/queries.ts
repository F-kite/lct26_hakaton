import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { addHistoryEntry, removeHistoryEntry } from "../lib/history";
import { api } from "./client";
import type {
  SearchCreatedResponse,
  SearchParams,
  SearchStatusResponse,
  SearchSummaryResponse,
  Signal,
} from "./types";

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

const SUMMARY_POLL_INTERVAL_MS = 2000;

export function useSearchSummary(queryId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["searchSummary", queryId],
    queryFn: () => api.get<SearchSummaryResponse>(`/search/${queryId}/summary`),
    enabled: enabled && queryId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" || status === "pending"
        ? SUMMARY_POLL_INTERVAL_MS
        : false;
    },
  });
}

export function useRetrySummary(queryId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SearchSummaryResponse>(`/search/${queryId}/summary/retry`, {}),
    onSuccess: (data) => queryClient.setQueryData(["searchSummary", queryId], data),
  });
}
