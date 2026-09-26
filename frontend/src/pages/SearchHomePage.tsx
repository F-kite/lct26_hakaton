import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateSearch, useSearchStatus } from "../api/queries";
import Logo from "../components/Logo";
import { DocumentCheckIcon, FilterIcon, RefreshIcon } from "../components/icons";
import SearchInput from "../components/search/SearchInput";
import SearchProgressModal from "../components/search/SearchProgressModal";
import StopConfirmModal from "../components/search/StopConfirmModal";

const STEPS = [
  { label: "Анализируем источники", Icon: RefreshIcon, solid: false },
  { label: "Отделяем новое от шума", Icon: FilterIcon, solid: true },
  { label: "Показываем кейсы и источники", Icon: DocumentCheckIcon, solid: true },
];

export default function SearchHomePage() {
  const navigate = useNavigate();
  const createSearch = useCreateSearch();

  const [activeQueryId, setActiveQueryId] = useState<number | null>(null);
  const [queryText, setQueryText] = useState("");
  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [confirmingStop, setConfirmingStop] = useState(false);
  const [stoppedNotice, setStoppedNotice] = useState(false);

  const { data: status } = useSearchStatus(activeQueryId, pollingEnabled);

  useEffect(() => {
    if (status?.status === "done") {
      navigate(`/results/${activeQueryId}`);
    }
  }, [status?.status, activeQueryId, navigate]);

  const handleSubmit = (query: string) => {
    setQueryText(query);
    setStoppedNotice(false);
    setPollingEnabled(true);
    createSearch.mutate(query, {
      onSuccess: (data) => setActiveQueryId(data.query_id),
    });
  };

  const handleConfirmStop = () => {
    // Только UI-отмена: прекращаем поллинг, пайплайн на бэкенде
    // доработает в фоне без видимого эффекта для пользователя.
    setPollingEnabled(false);
    setActiveQueryId(null);
    setConfirmingStop(false);
    setStoppedNotice(true);
  };

  const showProgress = activeQueryId !== null && status?.status !== "done";

  return (
    <div className="animate-fade-in min-h-screen bg-neutral-100">
      <header className="px-6 py-6 sm:px-10">
        <Logo />
      </header>

      {stoppedNotice && (
        <div className="fixed right-6 top-6 z-30 max-w-xs rounded-xl bg-neutral-0 p-4 text-sm text-neutral-700 shadow-lg">
          Поиск остановлен. Измените запрос или запустите анализ заново.
        </div>
      )}

      <main className="mx-auto flex max-w-3xl flex-col items-center px-6 pt-24 text-center sm:pt-32">
        <h1 className="text-4xl font-bold text-neutral-950 sm:text-5xl">Что хотите исследовать?</h1>
        <p className="mt-3 text-neutral-500">Введите технологическое направление</p>

        <div className="mt-8 w-full">
          <SearchInput size="lg" onSubmit={handleSubmit} />
        </div>

        <div className="mt-10 flex flex-wrap justify-center gap-3">
          {STEPS.map(({ label, Icon, solid }) => (
            <div
              key={label}
              className="flex items-center gap-2 rounded-full bg-neutral-0 px-4 py-2 text-sm text-neutral-700 shadow-sm"
            >
              {label}
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full ${
                  solid ? "bg-primary text-white" : "bg-primary-50 text-primary"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
            </div>
          ))}
        </div>
      </main>

      {showProgress && (
        <SearchProgressModal
          queryText={queryText}
          phase={status?.phase ?? "collecting"}
          onStopClick={() => setConfirmingStop(true)}
        />
      )}

      {confirmingStop && (
        <StopConfirmModal onConfirm={handleConfirmStop} onCancel={() => setConfirmingStop(false)} />
      )}
    </div>
  );
}
