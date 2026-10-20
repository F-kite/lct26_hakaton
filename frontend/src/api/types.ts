// Зеркало backend/app/schemas.py

export interface SignalSource {
  feed_item_id: number;
  title: string;
  url: string;
  source_key: string;
  source_name: string;
  source_type: string;
  trust_level: "high" | "medium" | "low" | string;
  language: string;
  published_at: string | null;
  is_primary: boolean;
  relation?: string | null;
}

export interface SignalExplanation {
  predicted_class: string | null;
  class_probabilities?: Record<string, number>;
  rationale?: string;
  key_predictors?: string[];
  enrichment_model?: string;
  relevance?: number;
  reason?: string;
  passage_hint?: string;
}

export type SignalStatus = "included" | "excluded";

export interface WeakCriterion {
  criterion: string;
  fact: string;
}

export interface Signal {
  id: number;
  title: string;
  area: string | null;
  description: string | null;
  problem: string | null;
  potential_advantage: string | null;
  case_example: string | null;
  weak_criteria?: WeakCriterion[] | null;
  manifestations?: string[] | null;
  stage: string | null;
  mention_trend: string | null;
  score: number; // 0..1
  is_mainstream: boolean;
  status: SignalStatus;
  explanation: SignalExplanation;
  model_version: string;
  created_at: string;
  sources: SignalSource[];
}

export interface SearchCreatedResponse {
  query_id: number;
  status: string;
}

export type SearchPhase = "collecting" | "scoring" | "ranking" | "done" | null;

export interface SearchParams {
  query: string;
  date_from?: string | null; // YYYY-MM-DD, включительно
  date_to?: string | null;
}

export interface SearchStatusResponse {
  query_id: number;
  query_text: string;
  date_from?: string | null;
  date_to?: string | null;
  status: "pending" | "running" | "done" | "failed";
  phase: SearchPhase;
  sources_processed: number;
  candidates_found: number;
  signals_above_75: number;
  error: string | null;
  results: Signal[] | null;
  excluded: Signal[] | null;
}

export interface SummarySignal {
  signal_id: number;
  title: string;
  score: number;
  reason?: string | null;
}

export type SummaryStatus = "disabled" | "empty" | "pending" | "queued" | "running" | "done" | "failed";

export interface SearchSummaryResponse {
  status: SummaryStatus;
  queue_position?: number | null;
  overview?: string | null;
  key_signals: SummarySignal[];
  top_signals: SummarySignal[];
  model?: string | null;
  error?: string | null;
}

export type SourceSummaryStatus = "ready" | "pending" | "original" | "none";

export interface SignalSourceDetail extends SignalSource {
  summary: string | null;
  summary_model: string | null;
  summary_status: SourceSummaryStatus;
}

export interface SignalSourcesResponse {
  signal_id: number;
  title: string;
  sources: SignalSourceDetail[];
}
