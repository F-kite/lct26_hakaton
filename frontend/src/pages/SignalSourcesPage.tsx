import { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useCreateSearch, useSignalAnalysts, useSignalSources } from "../api/queries";
import ReportsSummaryCard from "../components/signal/ReportsSummaryCard";
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
      className={`rounded-md px-2 py-1 text-xs whitespace-nowrap hover:cursor-pointer ${
        active ? "bg-primary text-white" : "bg-neutral-50 text-neutral-600 hover:bg-neutral-200"
      }`}
    >
      {children}
    </button>
  );
}

interface Props {
  kind?: "sources" | "analysts";
}

export default function SignalSourcesPage({ kind = "sources" }: Props) {
  const { queryId, signalId } = useParams<{ queryId: string; signalId: string }>();
  const navigate = useNavigate();
  const createSearch = useCreateSearch();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const analystsMode = kind === "analysts";
  const id = signalId ? Number(signalId) : null;
  const sourcesQuery = useSignalSources(analystsMode ? null : id);
  const analystsQuery = useSignalAnalysts(analystsMode ? id : null);
  const { isLoading, isError } = analystsMode ? analystsQuery : sourcesQuery;
  const data = analystsMode
    ? analystsQuery.data && { title: analystsQuery.data.title, sources: analystsQuery.data.reports }
    : sourcesQuery.data;
  const pageTitle = analystsMode ? "Оценки аналитиков" : "Источники и подтверждения";
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
            { label: pageTitle },
          ]}
        />
        <h1 className="mt-4 text-4xl font-bold text-neutral-950">
          {pageTitle}{" "}
          {data && <span className="text-2xl text-primary">{sources.length}</span>}
        </h1>

        {isLoading && <p className="mt-8 text-neutral-500">Загрузка…</p>}
        {isError && <p className="mt-8 text-neutral-700">Не удалось загрузить источники.</p>}

        {data && (
          <div className="mt-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_360px]">
            <div className="space-y-5">
              {analystsMode && analystsQuery.data?.scope === "topic" && (
                <p className="rounded-lg bg-neutral-50 p-3 text-sm text-neutral-600">
                  Отчётов именно об этой технологии не найдено — показаны оценки аналитиков по теме запроса.
                </p>
              )}
              {analystsMode && analystsQuery.data?.scope === "none" && (
                <p className="text-neutral-500">Аналитические отчёты по технологии не найдены.</p>
              )}
              {filtered.map((source) => (
                <SourceCard key={source.feed_item_id} source={source} />
              ))}
              {filtered.length === 0 && sources.length > 0 && (
                <p className="text-neutral-500">Нет источников под выбранные фильтры.</p>
              )}
            </div>

            <div className="order-first space-y-4 lg:sticky lg:top-6 lg:order-none">
            {analystsMode && <ReportsSummaryCard summary={analystsQuery.data?.summary} />}
            <aside className="rounded-2xl p-5 glass-card glass-border-8">
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
                <span className="shrink-0 text-sm text-neutral-950">Язык</span>
                <div className="flex flex-wrap justify-end gap-1">
                  <Chip active={lang === "all"} onClick={() => setLang("all")}>Все {sources.length}</Chip>
                  <Chip active={lang === "RU"} onClick={() => setLang("RU")}>RU {counts.ru}</Chip>
                  <Chip active={lang === "EN"} onClick={() => setLang("EN")}>EN {counts.en}</Chip>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between gap-4">
                <span className="shrink-0 text-sm text-neutral-950">Статус</span>
                <div className="flex flex-wrap justify-end gap-1">
                  <Chip active={trust === "all"} onClick={() => setTrust("all")}>Все {sources.length}</Chip>
                  <Chip active={trust === "high"} onClick={() => setTrust("high")}>Высокая {counts.high}</Chip>
                  <Chip active={trust === "low"} onClick={() => setTrust("low")}>Пониженная {counts.low}</Chip>
                </div>
              </div>
            </aside>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
