import type { Signal } from "../../api/types";
import { displayTag, formatRelevance, formatThreshold, isBelowRelevance } from "../../lib/relevance";

const CLASSES = ["слабый сигнал", "зрелая технология", "шум"];

export default function ReasonTags({ signal }: { signal: Signal }) {
  const { explanation } = signal;
  const tags = explanation.key_predictors ?? [];
  const criteria = signal.weak_criteria ?? [];
  const included = signal.status === "included";
  const heading = included ? "Почему это слабый сигнал:" : "Почему кандидат исключён:";
  const pct = Math.round(signal.score * 100);
  const predicted = explanation.predicted_class;
  const isWeakSignalClass = predicted === "слабый сигнал";
  const reason = explanation.reason;
  const isV2 = explanation.relevance !== undefined;

  const summary = isV2 && reason
    ? reason
    : included
    ? `Модель определила технологию как слабый сигнал с уверенностью ${pct}% — на основе ключевых упоминаний, которые присутствуют в источнике.`
    : isWeakSignalClass
      ? `Модель распознала признаки слабого сигнала, но с уверенностью всего ${pct}% — ниже порога, необходимого для попадания в выдачу.`
      : `Модель отнесла технологию к классу «${predicted ?? "зрелая технология"}», а не к слабым сигналам.`;

  const probabilities = explanation.class_probabilities ?? {};
  const relevanceText = explanation.relevance !== undefined ? formatRelevance(explanation.relevance) : null;

  return (
    <div className="rounded-xl p-5 glass-card glass-border-8">
      <h3 className="font-bold text-neutral-950  [-webkit-text-stroke:0.4px_currentColor]">{heading}</h3>
      <p className="mt-2 text-sm text-neutral-700">{summary}</p>

      {criteria.length > 0 && (
        <ul className="mt-4 space-y-2.5">
          {criteria.map((c) => (
            <li key={c.criterion} className="flex gap-3 text-sm">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-success" aria-hidden />
              <span>
                <span className="font-medium text-neutral-950">{c.criterion}.</span>{" "}
                <span className="text-neutral-700">{c.fact}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      {tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-md bg-neutral-50 px-2.5 py-1 text-sm text-neutral-600"
            >
              {displayTag(tag, explanation)}
            </span>
          ))}
        </div>
      )}

      {isV2 && (
        <div className="mt-5 grid gap-5 border-t border-neutral-200 pt-4 sm:grid-cols-2">
          <div>
            <div className="text-sm text-neutral-500">Стадия технологии по оценке модели</div>
            <ul className="mt-2 space-y-1.5">
              {CLASSES.filter((c) => probabilities[c] !== undefined).map((c) => {
                const value = Math.round(probabilities[c] * 100);
                return (
                  <li key={c} className="flex items-center gap-3 text-sm">
                    <span className={`w-36 shrink-0 ${c === predicted ? "font-medium text-neutral-950" : "text-neutral-600"}`}>
                      {c}
                    </span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-200">
                      <span
                        className={`block h-full ${c === "слабый сигнал" ? "bg-success" : "bg-neutral-400"}`}
                        style={{ width: `${value}%` }}
                      />
                    </span>
                    <span className="w-10 text-right tabular-nums text-neutral-700">{value}%</span>
                  </li>
                );
              })}
            </ul>
          </div>
          {relevanceText !== null && (
            <div>
              <div className="text-sm text-neutral-500">Соответствие запросу</div>
              <div
                className={`mt-2 font-display text-2xl font-bold ${
                  isBelowRelevance(explanation) ? "text-error" : "text-neutral-950"
                }`}
              >
                {relevanceText}
              </div>
              <p className="mt-1 text-xs text-neutral-500">
                Смысловая близость запроса и текста публикации. Порог попадания в выдачу —{" "}
                {formatThreshold(explanation)}.
              </p>
            </div>
          )}
        </div>
      )}

      {explanation.passage_hint && (
        <figure className="mt-5 border-l-2 border-primary pl-4">
          <figcaption className="text-sm text-neutral-500">Фрагмент источника, ближайший к запросу</figcaption>
          <blockquote className="mt-1 text-sm italic text-neutral-800" lang="en">
            «{explanation.passage_hint}»
          </blockquote>
        </figure>
      )}
    </div>
  );
}
