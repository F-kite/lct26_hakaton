import FileChartBarSolid from "@iconify-react/flowbite/file-chart-bar-solid";
import FileCheckSolid from "@iconify-react/flowbite/file-check-solid";
import FileLineSolid from "@iconify-react/flowbite/file-lines-solid";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useCreateSearch, useSearchStatus } from "../api/queries";
import type { Signal } from "../api/types";
import Logo from "../components/Logo";
import EmptyState from "../components/results/EmptyState";
import SignalsTable from "../components/results/SignalsTable";
import StatCard from "../components/results/StatCard";
import SearchInput from "../components/search/SearchInput";
import SearchProgressModal from "../components/search/SearchProgressModal";
import StopConfirmModal from "../components/search/StopConfirmModal";

type Tab = "included" | "excluded";

export default function ResultsPage() {
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const createSearch = useCreateSearch();
  const numericQueryId = queryId ? Number(queryId) : null;

  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [confirmingStop, setConfirmingStop] = useState(false);
  const [tab, setTab] = useState<Tab>("included");

  const { data: status } = useSearchStatus(numericQueryId, pollingEnabled);

  const handleNewSearch = (query: string) => {
    createSearch.mutate(query, {
      onSuccess: (data) => navigate(`/results/${data.query_id}`),
    });
  };

  const handleConfirmStop = () => {
    setPollingEnabled(false);
    setConfirmingStop(false);
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
          onStopClick={() => setConfirmingStop(true)}
        />
        {confirmingStop && (
          <StopConfirmModal onConfirm={handleConfirmStop} onCancel={() => setConfirmingStop(false)} />
        )}
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
        <div className="mx-auto flex max-w-360 flex-col gap-6 sm:flex-row sm:items-center">
          <Logo />
          <div className="flex-1">
            <SearchInput size="sm" defaultValue={status.query_text} onSubmit={handleNewSearch} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-360 px-6 sm:px-10">
        <h1 className="text-3xl font-bold text-neutral-950">
          Слабые сигналы в {status.query_text}
        </h1>

        <div className="mt-6 flex flex-col gap-4 sm:flex-row">
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
          {/* <StatCard
            icon={BadgeCheckSolid}
            label="Высокая уверенность"
            value={status.signals_above_75}
            hint="Сигналы с уверенностью модели выше 75%"
          /> */}
        </div>

        <div className="mt-8 rounded-2xl bg-neutral-200 p-3">
          <div className="flex gap-6 border-b border-neutral-200 px-2 pb-3">
            <button
              type="button"
              onClick={() => setTab("included")}
              className={`border-b-2 pb-1 text-sm font-medium hover:cursor-pointer ${
                tab === "included"
                  ? "border-link text-link"
                  : "border-transparent text-neutral-900"
              }`}
            >
              Слабые сигналы <span className={tab === "included" ? "" : "text-neutral-500"}>{included.length}</span>
            </button>
            <button
              type="button"
              onClick={() => setTab("excluded")}
              className={`border-b-2 pb-1 text-sm font-medium hover:cursor-pointer ${
                tab === "excluded"
                  ? "border-link text-link"
                  : "border-transparent text-neutral-900"
              }`}
            >
              Исключённые <span className={tab === "excluded" ? "" : "text-neutral-500"}>{excluded.length}</span>
            </button>
          </div>

          {activeList.length === 0 ? (
            tab === "included" ? (
              <EmptyState queryText={status.query_text} onChangeQuery={() => navigate("/")} />
            ) : (
              <div className="rounded-2xl bg-neutral-0 p-10 text-center text-sm text-neutral-500">
                Исключённых кандидатов нет.
              </div>
            )
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
