import BrowserEdgeIcon from '@iconify-react/bi/browser-edge';
import FilterFilledIcon from '@iconify-react/carbon/filter-filled';
import FileCheckSolidIcon from '@iconify-react/flowbite/file-check-solid';

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateSearch, useSearchStatus } from "../api/queries";
import Logo from "../components/Logo";
import SearchInput from "../components/search/SearchInput";
import SearchProgressModal from "../components/search/SearchProgressModal";
import StopConfirmModal from "../components/search/StopConfirmModal";

const STEPS = [
  { label: "Анализируем источники", Icon: BrowserEdgeIcon, solid: false },
  { label: "Отделяем новое от шума", Icon: FilterFilledIcon, solid: true },
  { label: "Показываем кейсы и источники", Icon: FileCheckSolidIcon, solid: true },
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
    setPollingEnabled(false);
    setActiveQueryId(null);
    setConfirmingStop(false);
    setStoppedNotice(true);
  };

  const showProgress = activeQueryId !== null && status?.status !== "done";

  return (
    <div className="animate-fade-in flex min-h-screen flex-col bg-neutral-100">
      <header className="px-6 pb-3 pt-7 sm:px-10 xl:px-20">
        <Logo />
      </header>

      {stoppedNotice && (
        <div className="fixed right-6 top-6 z-30 max-w-xs rounded-xl bg-neutral-0 p-4 text-sm text-neutral-700 shadow-lg">
          Поиск остановлен. Измените запрос или запустите анализ заново.
        </div>
      )}

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="text-4xl font-bold text-neutral-950 sm:text-5xl">Что хотите исследовать?</h1>
        <p className="mt-3 text-neutral-500">Введите технологическое направление</p>

        <div className="mt-8 w-full">
          <SearchInput size="lg" onSubmit={handleSubmit} />
        </div>

        <div className="mt-10 flex justify-center gap-3 sm:mt-16 xl:mt-61">
          {STEPS.map(({ label, Icon }) => (
            <div
              key={label}
              className="flex items-center gap-2 rounded-full border border-neutral-300 bg-linear-to-br from-neutral-200 to-neutral-100 to-80% pl-5 pr-1 py-2 text-sm text-neutral-700 shadow-sm"                                                                                        
            >                                                                                               
              {label}
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-full bg-white/40 border border-neutral-100 text-primary`}
              >
                <Icon className="h-6 w-6" />
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
