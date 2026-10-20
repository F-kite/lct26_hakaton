import { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useCreateSearch, useSignalSources } from "../api/queries";
import Breadcrumbs from "../components/Breadcrumbs";
import HistoryButton from "../components/history/HistoryButton";
import Logo from "../components/Logo";
import SearchInput from "../components/search/SearchInput";
import SourceCard from "../components/signal/SourceCard";
import { sortSources } from "../components/signal/SourcesList";

type LangFilter = "all" | "RU" | "EN";
type TrustFilter = "all" | "high" | "low";

interface ChipProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function Chip({ active, onClick, children }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-sm whitespace-nowrap hover:cursor-pointer ${
        active ? "bg-primary text-white" : "bg-neutral-50 text-neutral-600 hover:bg-neutral-200"
      }`}
    >
      {children}
    </button>
  );
}

export default function SignalSourcesPage() {
  const { queryId, signalId } = useParams<{ queryId: string; signalId: string }>();
  const navigate = useNavigate();
  const createSearch = useCreateSearch();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { data, isLoading, isError } = useSignalSources(signalId ? Number(signalId) : null);
  const [lang, setLang] = useState<LangFilter>("all");
  const [trust, setTrust] = useState<TrustFilter>("all");

  const sources = useMemo(() => sortSources(data?.sources ?? []), [data]);
  const counts = useMemo(() => {
    const high = sources.filter((s) => s.trust_level === "high").length;
    return {
      ru: sources.filter((s) => s.language === "RU").length,
      en: sources.filter((s) => s.language === "EN").length,
      high,
      low: sources.length - high,
    };
  }, [sources]);

  const filtered = sources.filter(
    (s) =>
      (lang === "all" || s.language === lang) &&
      (trust === "all" || (trust === "high" ? s.trust_level === "high" : s.trust_level !== "high")),
  );

  const handleNewSearch = (query: string) => {
    createSearch.mutate({ query }, {
      onSuccess: (created) => navigate(`/results/${created.query_id}`),
    });
  };

  return (
    <div className="animate-fade-in min-h-screen bg-neutral-100 pb-16">
      <header className="mx-auto max-w-360 px-6 pb-8 pt-7 sm:px-10">
        <div className="mx-auto flex max-w-360 flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <Logo />
          <div className="w-full sm:max-w-215 sm:flex-1">
            <SearchInput size="sm" inputRef={searchInputRef} onSubmit={handleNewSearch} />
          </div>
          <HistoryButton onStartSearch={() => searchInputRef.current?.focus()} />
        </div>
      </header>

      <main className="mx-auto max-w-360 px-6 sm:px-10">
        <Breadcrumbs
          items={[
            { label: "Слабые сигналы", to: `/results/${queryId}` },
            { label: data?.title ?? "Сигнал", to: `/results/${queryId}/signals/${signalId}` },
            { label: "Источники и подтверждения" },
          ]}
        />
        <h1 className="mt-4 text-4xl font-bold text-neutral-950">
          Источники и подтверждения{" "}
          {data && <span className="text-2xl text-primary">{sources.length}</span>}
        </h1>

        {isLoading && <p className="mt-8 text-neutral-500">Загрузка…</p>}
        {isError && <p className="mt-8 text-neutral-700">Не удалось загрузить источники.</p>}

        {data && (
          <div className="mt-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_360px]">
            <div className="space-y-5">
              {filtered.map((source) => (
                <SourceCard key={source.feed_item_id} source={source} />
              ))}
              {filtered.length === 0 && (
                <p className="text-neutral-500">Нет источников под выбранные фильтры.</p>
              )}
            </div>

            <aside className="order-first rounded-2xl p-5 glass-card glass-border-8 lg:sticky lg:top-6 lg:order-none">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-neutral-950">Фильтры</h2>
                <button
                  type="button"
                  onClick={() => {
                    setLang("all");
                    setTrust("all");
                  }}
                  className="text-sm text-neutral-500 hover:text-link hover:cursor-pointer"
                >
                  Сбросить
                </button>
              </div>
              <div className="mt-5 flex items-center justify-between gap-4">
                <span className="text-sm text-neutral-950">Язык</span>
                <div className="flex flex-wrap justify-end gap-1.5">
                  <Chip active={lang === "all"} onClick={() => setLang("all")}>Все {sources.length}</Chip>
                  <Chip active={lang === "RU"} onClick={() => setLang("RU")}>RU {counts.ru}</Chip>
                  <Chip active={lang === "EN"} onClick={() => setLang("EN")}>EN {counts.en}</Chip>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between gap-4">
                <span className="text-sm text-neutral-950">Статус</span>
                <div className="flex flex-wrap justify-end gap-1.5">
                  <Chip active={trust === "all"} onClick={() => setTrust("all")}>Все {sources.length}</Chip>
                  <Chip active={trust === "high"} onClick={() => setTrust("high")}>Высокая {counts.high}</Chip>
                  <Chip active={trust === "low"} onClick={() => setTrust("low")}>Пониженная {counts.low}</Chip>
                </div>
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
