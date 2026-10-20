import type { SignalSource, SignalSourceDetail } from "../../api/types";
import { isAssessment, relationLabel, sourceTypeLabel } from "../../lib/sourceLabels";

export function trustLabel(trustLevel: string): string {
  return trustLevel === "high" ? "Доверенный" : "Пониженная доверенность";
}

function dateParts(iso: string | null): { day: string; month: string; year: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  const monthGenitive = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" })
    .format(d)
    .replace(/^\d+\s*/, "");
  return { day: String(d.getDate()), month: monthGenitive, year: `${d.getFullYear()}` };
}

interface Props {
  source: SignalSource | SignalSourceDetail;
}

export default function SourceCard({ source }: Props) {
  const date = dateParts(source.published_at);
  const relation = relationLabel(source.relation, source.is_primary);
  const detail = "summary_status" in source ? source : null;
  const aiSummary = detail?.summary_status === "ready";

  return (
    <div className="glass-card glass-border-8 rounded-2xl p-5">
      <div className="flex flex-col gap-5 sm:flex-row sm:gap-0">
        <div className="shrink-0 sm:w-21 sm:pr-6">
          {date ? (
            <>
              <div className="font-display text-2xl text-neutral-950 [-webkit-text-stroke:1px_currentColor]">{date.day}</div>
              <div className="mt-1 text-sm text-neutral-600">{date.month}</div>
              <div className="mt-1 text-sm text-neutral-600">{date.year}</div>
            </>
          ) : (
            <div className="text-sm text-neutral-600">—</div>
          )}
        </div>

        <div className="flex-1 sm:border-l sm:border-neutral-300 sm:px-6">
          <h4 className="text-lg font-medium text-neutral-950 [-webkit-text-stroke:0.5px_currentColor]">{source.title}</h4>

          {detail?.summary && (
            <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-neutral-600">{detail.summary}</p>
          )}
          {detail?.summary_status === "pending" && (
            <div className="mt-3 space-y-2" aria-label="Готовим резюме">
              <div className="h-3 w-full animate-pulse rounded bg-neutral-200" />
              <div className="h-3 w-4/5 animate-pulse rounded bg-neutral-200" />
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-md bg-neutral-50 px-2.5 py-1 text-sm text-neutral-600">
              {source.source_name}
            </span>
            <span className="rounded-md bg-neutral-50 px-2.5 py-1 text-sm text-neutral-600">
              {sourceTypeLabel(source.source_type)}
            </span>
            {relation && (
              <span
                className={`rounded-md px-2.5 py-1 text-sm ${
                  source.is_primary ? "bg-primary-50 text-primary" : "bg-neutral-50 text-neutral-600"
                }`}
              >
                {relation}
              </span>
            )}
          </div>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="mt-4 inline-flex items-center gap-2 text-sm text-link hover:text-link-hover"
          >
            Открыть источник <span aria-hidden>→</span>
          </a>
        </div>

        <div className="shrink-0 divide-y divide-neutral-300 sm:w-56 sm:border-l sm:border-neutral-300 sm:pl-6 [&>div]:py-4 [&>div:first-child]:pt-0 [&>div:last-child]:pb-0">
          <div>
            <div className="text-sm text-neutral-500">Язык</div>
            <div className="mt-1 text-sm text-neutral-950">{source.language}</div>
          </div>
          <div>
            <div className="text-sm text-neutral-500">Статус источника</div>
            <div className="mt-1 text-sm text-neutral-950">{trustLabel(source.trust_level)}</div>
          </div>
          {aiSummary && (
            <div>
              <div className="text-sm text-neutral-500">
                {isAssessment(source.relation) ? "Оценка сгенерирована ИИ" : "Резюме сгенерировано ИИ"}
              </div>
              <div className="mt-1 text-sm text-neutral-950">{detail?.summary_model}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
