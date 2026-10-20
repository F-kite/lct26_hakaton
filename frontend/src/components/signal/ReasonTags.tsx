import type { Signal } from "../../api/types";

export default function ReasonTags({ signal }: { signal: Signal }) {
  const tags = signal.explanation.key_predictors ?? [];
  const included = signal.status === "included";
  const heading = included ? "Почему это слабый сигнал:" : "Почему кандидат исключён:";
  const pct = Math.round(signal.score * 100);
  const predicted = signal.explanation.predicted_class;
  const isWeakSignalClass = predicted === "слабый сигнал";
  const reason = signal.explanation.reason; // модель v2 — конкретная причина решения
  const summary = !included && reason
    ? reason
    : included
    ? `Модель определила технологию как слабый сигнал с уверенностью ${pct}% — на основе ключевых упоминаний, которые присутствуют в источнике.`
    : isWeakSignalClass
      ? `Модель распознала признаки слабого сигнала, но с уверенностью всего ${pct}% — ниже порога, необходимого для попадания в выдачу.`
      : `Модель отнесла технологию к классу «${predicted ?? "зрелая технология"}», а не к слабым сигналам.`;

  return (
    <div className="rounded-xl p-5 glass-card glass-border-8">
      <h3 className="font-bold text-neutral-950  [-webkit-text-stroke:0.4px_currentColor]">{heading}</h3>
      <p className="mt-2 text-sm text-neutral-700">{summary}</p>
      {tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-md bg-neutral-50 px-2.5 py-1 text-sm text-neutral-600"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
      {/* {signal.explanation.rationale && (
        <p className="mt-4 border-t border-neutral-100 pt-3 font-mono text-xs text-neutral-400">
          {signal.explanation.rationale}
        </p>
      )} */}
    </div>
  );
}
