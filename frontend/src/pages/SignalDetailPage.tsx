import { useNavigate, useParams } from "react-router-dom";

import { useCreateSearch, useSignalDetail } from "../api/queries";
import Breadcrumbs from "../components/Breadcrumbs";
import Logo from "../components/Logo";
import CaseExamples from "../components/signal/CaseExamples";
import ConfidencePanel from "../components/signal/ConfidencePanel";
import ReasonTags from "../components/signal/ReasonTags";
import SourcesList from "../components/signal/SourcesList";
import SearchInput from "../components/search/SearchInput";

export default function SignalDetailPage() {
  const { queryId, signalId } = useParams<{ queryId: string; signalId: string }>();
  const navigate = useNavigate();
  const createSearch = useCreateSearch();
  const { data: signal, isLoading } = useSignalDetail(signalId ? Number(signalId) : null);

  const handleNewSearch = (query: string) => {
    createSearch.mutate(query, {
      onSuccess: (data) => navigate(`/results/${data.query_id}`),
    });
  };

  if (isLoading || !signal) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-100 text-neutral-500">
        Загрузка…
      </div>
    );
  }

  const enriched = Boolean(signal.explanation.enrichment_model);
  const primarySource = signal.sources.find((s) => s.is_primary) ?? signal.sources[0] ?? null;

  return (
    <div className="animate-fade-in min-h-screen bg-neutral-100 pb-16">
      <header className="flex flex-col gap-6 px-6 py-6 sm:flex-row sm:items-center sm:px-10">
        <Logo />
        <div className="flex-1">
          <SearchInput size="sm" onSubmit={handleNewSearch} />
        </div>
      </header>

      <main className="mx-auto max-w-360 px-6 sm:px-10">
        <Breadcrumbs
          items={[
            { label: "Слабые сигналы", to: `/results/${queryId}` },
            { label: signal.title },
          ]}
        />

        <div className="mt-4 rounded-2xl bg-neutral-0 p-8 shadow-sm">
          <h1 className="text-3xl font-bold text-link">{signal.title}</h1>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6">
            <div className="rounded-2xl bg-neutral-0 p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-neutral-950">О технологии</h3>
                {enriched && (
                  <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs text-neutral-500">
                    Резюме сгенерировано ИИ
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-neutral-700">
                {signal.description ?? "Не указано в источнике."}
              </p>

              <h3 className="mt-5 font-bold text-neutral-950">Какую проблему решает</h3>
              <p className="mt-2 text-sm leading-relaxed text-neutral-700">
                {signal.description ?? "Не указано в источнике."}
              </p>

              <h3 className="mt-5 font-bold text-neutral-950">Потенциальное преимущество</h3>
              <p className="mt-2 text-sm leading-relaxed text-neutral-700">
                {signal.potential_advantage ?? "Не указано в источнике."}
              </p>
            </div>

            <ReasonTags signal={signal} />
            <CaseExamples text={signal.case_example} primarySource={primarySource} />
            <SourcesList sources={signal.sources} enriched={enriched} />
          </div>

          <div>
            <ConfidencePanel signal={signal} />
          </div>
        </div>
      </main>
    </div>
  );
}
