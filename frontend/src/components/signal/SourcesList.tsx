import { useMemo, useState } from "react";

import type { SignalSource } from "../../api/types";

const PREVIEW_COUNT = 3;

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
}

function trustLabel(trustLevel: string): string {
  return trustLevel === "high" ? "Доверенный" : "Пониженная доверенность";
}

type LangFilter = "all" | "RU" | "EN";
type TrustFilter = "all" | "high" | "low";

function SourceCard({ source, showAiDisclosure }: { source: SignalSource; showAiDisclosure: boolean }) {
  return (
    <div className="rounded-2xl bg-neutral-0 p-5 shadow-sm">
      <div className="flex gap-4">
        <div className="w-20 shrink-0 text-sm text-neutral-600">{formatDate(source.published_at)}</div>
        <div className="flex-1">
          <div className="text-xs text-neutral-500">{source.source_name}</div>
          <h4 className="font-medium text-neutral-900">{source.title}</h4>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs text-neutral-600">
              {source.source_type}
            </span>
            {showAiDisclosure && (
              <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs text-neutral-500">
                Резюме сгенерировано ИИ
              </span>
            )}
          </div>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-block text-sm font-medium text-link hover:text-link-hover"
          >
            Подробнее →
          </a>
        </div>
        <div className="w-36 shrink-0 text-xs text-neutral-500">
          <div>Язык</div>
          <div className="text-neutral-900">{source.language}</div>
          <div className="mt-2">Статус источника</div>
          <div className="text-neutral-900">{trustLabel(source.trust_level)}</div>
        </div>
      </div>
    </div>
  );
}

interface SourcesListProps {
  sources: SignalSource[];
  // Показывать бейдж "Резюме сгенерировано ИИ" у зарубежных (не RU) источников.
  enriched: boolean;
}

export default function SourcesList({ sources, enriched }: SourcesListProps) {
  const [expanded, setExpanded] = useState(false);
  const [langFilter, setLangFilter] = useState<LangFilter>("all");
  const [trustFilter, setTrustFilter] = useState<TrustFilter>("all");

  const sorted = useMemo(
    () =>
      [...sources].sort(
        (a, b) => new Date(b.published_at ?? 0).getTime() - new Date(a.published_at ?? 0).getTime(),
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
    <div className="rounded-2xl bg-neutral-0 p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-neutral-950  [-webkit-text-stroke:0.4px_currentColor]">
          Источники и подтверждения <span className="text-primary">{sorted.length}</span>
        </h3>
        {!expanded && sorted.length > PREVIEW_COUNT && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="text-sm font-medium text-link hover:text-link-hover"
          >
            Смотреть все
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-col gap-6 sm:flex-row">
        <div className="flex-1 space-y-3">
          {visible.map((source) => (
            <SourceCard
              key={source.feed_item_id}
              source={source}
              showAiDisclosure={enriched && source.language !== "RU"}
            />
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
                  className={`rounded-full px-2.5 py-1 text-xs ${
                    langFilter === value ? "bg-primary text-white" : "bg-neutral-0 text-neutral-600"
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
                  className={`rounded-full px-2.5 py-1 text-xs ${
                    trustFilter === value ? "bg-primary text-white" : "bg-neutral-0 text-neutral-600"
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
