import type { SignalExplanation } from "../api/types";

const DEFAULT_THRESHOLD = 0.79;

const pctFormat = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function formatRelevance(value: number): string {
  return `${pctFormat.format(Math.floor(value * 1000) / 10)}%`;
}

export function relevanceThreshold(explanation: SignalExplanation): number {
  return explanation.relevance_threshold ?? DEFAULT_THRESHOLD;
}

export function formatThreshold(explanation: SignalExplanation): string {
  return `${Math.round(relevanceThreshold(explanation) * 100)}%`;
}

export function isBelowRelevance(explanation: SignalExplanation): boolean {
  return explanation.relevance !== undefined && explanation.relevance < relevanceThreshold(explanation);
}

/** Тег «Релевантность NN%» из модели — с одним знаком после запятой. */
export function displayTag(tag: string, explanation: SignalExplanation): string {
  if (tag.startsWith("Релевантность") && explanation.relevance !== undefined) {
    return `Релевантность ${formatRelevance(explanation.relevance)}`;
  }
  return tag;
}
