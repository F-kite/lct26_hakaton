import { useState } from "react";

import type { Signal } from "../../api/types";
import { formatRelevance, formatThreshold, isBelowRelevance } from "../../lib/relevance";
import ConfidenceModal from "./ConfidenceModal";

export default function ConfidencePanel({ signal }: { signal: Signal }) {
  const [showModal, setShowModal] = useState(false);
  const { explanation } = signal;
  const pct = Math.round(signal.score * 100);
  const predicted = explanation.predicted_class;
  const isWeakSignalClass = predicted === "слабый сигнал";
  const excluded = signal.status === "excluded";
  const byRelevance = excluded && isBelowRelevance(explanation);

  const reason = explanation.reason;
  const description = excluded
    ? reason
      ? reason
      : isWeakSignalClass
      ? `Модель распознала признаки слабого сигнала, но с уверенностью всего ${pct}% — ниже порога, необходимого для попадания в выдачу.`
      : `Модель отнесла технологию к классу «${predicted ?? "не слабым сигналом"}» и не считает её слабым сигналом.`
    : pct >= 80
      ? "Высокая уверенность в классификации как слабого сигнала."
      : "Умеренная уверенность в классификации как слабого сигнала.";

  const relevance = explanation.relevance ?? 0;
  const label = byRelevance ? "Соответствие запросу" : "Уверенность модели";
  const value = byRelevance ? formatRelevance(relevance) : `${pct}%`;
  const barWidth = byRelevance ? relevance * 100 : pct;

  return (
    <div className="rounded-xl p-5 glass-card glass-border-8 [--glass-fill:var(--color-primary-50)]">
      <div className="text-sm text-neutral-700">{label}</div>
      <div className="mt-4 font-display text-4xl font-bold text-neutral-950">{value}</div>
      {byRelevance && (
        <div className="mt-1 text-sm text-error">ниже порога {formatThreshold(explanation)}</div>
      )}
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-neutral-0">
        <div
          className={`h-full ${excluded ? "bg-error" : "bg-success"}`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      {byRelevance && (
        <div className="mt-3 text-sm text-neutral-700">
          Ранняя стадия: <span className="font-medium text-neutral-950">{pct}%</span>
        </div>
      )}
      <p className="mt-3 text-sm text-neutral-950">{description}</p>
      <button
        type="button"
        onClick={() => setShowModal(true)}
        className="mt-4 text-sm font-medium text-link hover:text-link-hover hover:cursor-pointer"
      >
        Как определяется оценка?
      </button>
      {showModal && <ConfidenceModal signal={signal} onClose={() => setShowModal(false)} />}
    </div>
  );
}
