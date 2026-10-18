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
}

export interface SignalExplanation {
  predicted_class: string | null;
  class_probabilities?: Record<string, number>;
  rationale?: string;
  key_predictors?: string[];
  enrichment_model?: string;
}

export type SignalStatus = "included" | "excluded";

export interface Signal {
  id: number;
  title: string;
  area: string | null;
  description: string | null;
  problem: string | null;
  potential_advantage: string | null;
  case_example: string | null;
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
