import { useMemo, useState } from "react";

import type { SignalSource } from "../../api/types";
import { relationLabel, sourceTypeLabel } from "../../lib/sourceLabels";

const PREVIEW_COUNT = 3;

function trustLabel(trustLevel: string): string {
  return trustLevel === "high" ? "Доверенный" : "Пониженная доверенность";
}

type LangFilter = "all" | "RU" | "EN";
type TrustFilter = "all" | "high" | "low";

function dateParts(iso: string | null): { day: string; month: string; year: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  const monthGenitive = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" })
    .format(d)
    .replace(/^\d+\s*/, "");
  return { day: String(d.getDate()), month: `${monthGenitive}`, year: `${d.getFullYear()}` };
}

function SourceCard({ source }: { source: SignalSource }) {
  const date = dateParts(source.published_at);
  const relation = relationLabel(source.relation, source.is_primary);
  return (
    <div className="glass-card glass-border-8 rounded-2xl p-5">
      <div className="flex flex-col gap-5 sm:flex-row sm:gap-0">
        {/* дата */}
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

        {/* основной блок */}
        <div className="flex-1 sm:border-l sm:border-neutral-300 sm:px-6">
          <h4 className="text-lg font-medium text-neutral-950 [-webkit-text-stroke:0.5px_currentColor]">{source.title}</h4>
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

        {/* мета: язык / статус / ИИ */}
        <div className="shrink-0 divide-y divide-neutral-300 sm:w-56 sm:border-l sm:border-neutral-300 sm:pl-6 [&>div]:py-4 [&>div:first-child]:pt-0 [&>div:last-child]:pb-0">
          <div>
            <div className="text-sm text-neutral-500">Язык</div>
            <div className="mt-1 text-sm text-neutral-950">{source.language}</div>
          </div>
          <div>
            <div className="text-sm text-neutral-500">Статус источника</div>
            <div className="mt-1 text-sm text-neutral-950">{trustLabel(source.trust_level)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface SourcesListProps {
  sources: SignalSource[];
}

export default function SourcesList({ sources }: SourcesListProps) {
  const [expanded, setExpanded] = useState(false);
  const [langFilter, setLangFilter] = useState<LangFilter>("all");
  const [trustFilter, setTrustFilter] = useState<TrustFilter>("all");

  const sorted = useMemo(
    () =>
      [...sources].sort(
        (a, b) =>
          Number(b.is_primary) - Number(a.is_primary) ||
          new Date(b.published_at ?? 0).getTime() - new Date(a.published_at ?? 0).getTime(),
      ),
    [sources],
  );

  const counts = useMemo(() => {
    const ru = sorted.filter((s) => s.language === "RU").length;
    const en = sorted.filter((s) => s.language === "EN").length;
    const high = sorted.filter((s) => s.trust_level === "high").length;
    const low = sorted.length - high;
    return { ru, en, high, low };
  }, [sorted]);

  const filtered = sorted.filter((s) => {
    if (langFilter !== "all" && s.language !== langFilter) return false;
    if (trustFilter === "high" && s.trust_level !== "high") return false;
    if (trustFilter === "low" && s.trust_level === "high") return false;
    return true;
  });

  const visible = expanded ? filtered : sorted.slice(0, PREVIEW_COUNT);

  return (
    <div className="">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-neutral-950 text-2xl [-webkit-text-stroke:0.4px_currentColor]">
          Источники и подтверждения <span className="text-primary text-base">{sorted.length}</span>
        </h3>
        {!expanded && sorted.length > PREVIEW_COUNT && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="text-base font-medium text-black-alpha hover:text-link-hover hover:cursor-pointer"
          >
            Смотреть все
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-col gap-6 sm:flex-row">
        <div className="flex-1 space-y-5">
          {visible.map((source) => (
            <SourceCard key={source.feed_item_id} source={source} />
          ))}
        </div>

        {expanded && (
          <div className="sticky top-6 h-fit w-full shrink-0 rounded-2xl bg-neutral-50 p-4 sm:w-56">
            <div className="flex items-center justify-between text-sm font-medium text-neutral-900">
              Фильтры
              <button
                type="button"
                onClick={() => {
                  setLangFilter("all");
                  setTrustFilter("all");
                }}
                className="text-xs font-normal text-neutral-500 hover:text-link"
              >
                Сбросить
              </button>
            </div>
            <div className="mt-3 text-xs text-neutral-500">Язык</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(
                [
                  ["all", `Все ${sorted.length}`],
                  ["RU", `RU ${counts.ru}`],
                  ["EN", `EN ${counts.en}`],
                ] as [LangFilter, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setLangFilter(value)}
                  className={`rounded-full px-2.5 py-1 text-xs ${langFilter === value ? "bg-primary text-white" : "bg-neutral-0 text-neutral-600"
                    }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mt-3 text-xs text-neutral-500">Статус</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(
                [
                  ["all", `Все ${sorted.length}`],
                  ["high", `Высокая ${counts.high}`],
                  ["low", `Пониженная ${counts.low}`],
                ] as [TrustFilter, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setTrustFilter(value)}
                  className={`rounded-full px-2.5 py-1 text-xs ${trustFilter === value ? "bg-primary text-white" : "bg-neutral-0 text-neutral-600"
                    }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
