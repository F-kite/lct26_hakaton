import FileChartBarSolid from "@iconify-react/flowbite/file-chart-bar-solid";
import FileCheckSolid from "@iconify-react/flowbite/file-check-solid";
import FileLineSolid from "@iconify-react/flowbite/file-lines-solid";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useCancelSearch, useCreateSearch, useSearchStatus } from "../api/queries";
import type { Signal } from "../api/types";
import Logo from "../components/Logo";
import EmptyState from "../components/results/EmptyState";
import SignalsTable from "../components/results/SignalsTable";
import StatCard from "../components/results/StatCard";
import SearchInput from "../components/search/SearchInput";
import SearchProgressModal from "../components/search/SearchProgressModal";

type Tab = "included" | "excluded";

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function formatPeriod(from?: string | null, to?: string | null): string {
  if (from && to) return `${formatDate(from)} — ${formatDate(to)}`;
  if (from) return `с ${formatDate(from)}`;
  return `по ${formatDate(to as string)}`;
}

export default function ResultsPage() {
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const createSearch = useCreateSearch();
  const cancelSearch = useCancelSearch();
  const numericQueryId = queryId ? Number(queryId) : null;

  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [tab, setTab] = useState<Tab>("included");

  const { data: status } = useSearchStatus(numericQueryId, pollingEnabled);

  const handleNewSearch = (query: string) => {
    createSearch.mutate({ query, date_from: status?.date_from, date_to: status?.date_to }, {
      onSuccess: (data) => navigate(`/results/${data.query_id}`),
    });
  };

  const handleConfirmStop = () => {
    if (numericQueryId !== null) {
      cancelSearch.mutate(numericQueryId);
    }
    setPollingEnabled(false);
    navigate("/");
  };

  if (!status) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-100 text-neutral-500">
        Загрузка…
      </div>
    );
  }

  if (status.status === "running" || status.status === "pending") {
    return (
      <div className="min-h-screen bg-neutral-100">
        <header className="px-6 pb-3 pt-7 sm:px-10 xl:px-20">
          <div className="mx-auto flex max-w-360 items-center gap-6">
            <Logo />
            <div className="flex-1">
              <SearchInput size="sm" defaultValue={status.query_text} onSubmit={handleNewSearch} />
            </div>
          </div>
        </header>
        <SearchProgressModal
          queryText={status.query_text}
          phase={status.phase ?? "collecting"}
          onStopConfirm={handleConfirmStop}
        />
      </div>
    );
  }

  if (status.status === "failed") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-neutral-100 text-center">
        <p className="text-neutral-700">Поиск завершился с ошибкой: {status.error}</p>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="rounded-full bg-primary px-6 py-2.5 text-sm text-white"
        >
          На главную
        </button>
      </div>
    );
  }

  const included = status.results ?? [];
  const excluded = status.excluded ?? [];
  const activeList = tab === "included" ? included : excluded;

  const goToSignal = (signal: Signal) => {
    navigate(`/results/${numericQueryId}/signals/${signal.id}`);
  };

  return (
    <div className="animate-fade-in min-h-screen bg-neutral-100 pb-16">
      <header className="mx-auto max-w-360 px-6 pb-8 pt-7 sm:px-10">
        <div className="mx-auto flex max-w-360 flex-col gap-6 sm:flex-row sm:justify-between">
          <Logo />
          <div className="min-w-215 ">
            <SearchInput size="sm" defaultValue={status.query_text} onSubmit={handleNewSearch} />
          </div>
        </div>
      </header>

      <main className="mx-auto mt-8 max-w-360 px-6 sm:px-10">
        <h1 className="text-4xl font-bold text-neutral-950">
          Слабые сигналы в {status.query_text}
        </h1>
        {(status.date_from || status.date_to) && (
          <p className="mt-2 text-neutral-600">
            Период публикаций: {formatPeriod(status.date_from, status.date_to)}
          </p>
        )}

        <div className="mt-8 flex flex-col gap-4 sm:flex-row">
          <StatCard
            icon={FileChartBarSolid}
            label="Обработано источников"
            value={status.sources_processed}
            hint="Публикации, патенты и отчёты"
          />
          <StatCard
            icon={FileCheckSolid}
            label="Найдено кандидатов"
            value={status.candidates_found}
            hint="Выявлено при анализе источников"
          />
          <StatCard
            icon={FileLineSolid}
            label="Отобрано слабых сигналов"
            value={included.length}
            hint="Лучшие по результатам ранжирования"
          />
        </div>

        <div className="glass-element mt-4 rounded-xl p-3">
          {activeList.length !== 0 && (
            <div className="flex gap-6 border-b border-neutral-200 px-2 pb-3">
              <button
                type="button"
                onClick={() => setTab("included")}
                className={`border-b-2 pb-1 text-sm font-medium hover:cursor-pointer ${tab === "included"
                  ? "border-link text-link"
                  : "border-transparent text-neutral-900"
                  }`}
              >
                Слабые сигналы <span className={tab === "included" ? "" : "text-neutral-500"}>{included.length}</span>
              </button>
              <button
                type="button"
                onClick={() => setTab("excluded")}
                className={`border-b-2 pb-1 text-sm font-medium hover:cursor-pointer ${tab === "excluded"
                  ? "border-link text-link"
                  : "border-transparent text-neutral-900"
                  }`}
              >
                Исключённые <span className={tab === "excluded" ? "" : "text-neutral-500"}>{excluded.length}</span>
              </button>
            </div>
          )
          }

          {activeList.length === 0 ? (
            <div className="overflow-hidden rounded-xl bg-neutral-0">
              <EmptyState queryText={status.query_text} onChangeQuery={() => navigate("/")} />
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl bg-neutral-0">
              <SignalsTable signals={activeList} mode={tab} onRowClick={goToSignal} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
