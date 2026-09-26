import type { Signal } from "../../api/types";

export default function ReasonTags({ signal }: { signal: Signal }) {
  const tags = signal.explanation.key_predictors ?? [];
  const heading = signal.status === "included" ? "Почему это слабый сигнал" : "Почему кандидат исключён";

  return (
    <div className="rounded-2xl bg-neutral-0 p-6 shadow-sm">
      <h3 className="font-bold text-neutral-950">{heading}</h3>
      {signal.explanation.rationale && (
        <p className="mt-2 text-sm text-neutral-600">{signal.explanation.rationale}</p>
      )}
      {tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-neutral-100 px-3 py-1.5 text-sm text-neutral-700"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
