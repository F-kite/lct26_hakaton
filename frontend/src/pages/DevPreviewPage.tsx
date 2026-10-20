import FileChartBarSolid from "@iconify-react/flowbite/file-chart-bar-solid";
import FileCheckSolid from "@iconify-react/flowbite/file-check-solid";
import FileLineSolid from "@iconify-react/flowbite/file-lines-solid";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { SearchStatusResponse, Signal, SignalSource } from "../api/types";
import Breadcrumbs from "../components/Breadcrumbs";
import Logo from "../components/Logo";
import EmptyState from "../components/results/EmptyState";
import SignalsTable from "../components/results/SignalsTable";
import StatCard from "../components/results/StatCard";
import SearchInput from "../components/search/SearchInput";
import SearchProgressModal from "../components/search/SearchProgressModal";
import StatusStep from "../components/search/StatusStep";
import CaseExamples from "../components/signal/CaseExamples";
import ConfidenceModal from "../components/signal/ConfidenceModal";
import ConfidencePanel from "../components/signal/ConfidencePanel";
import ReasonTags from "../components/signal/ReasonTags";
import SourcesList from "../components/signal/SourcesList";
import NotFoundPage from "./NotFoundPage";
import ResultsPage from "./ResultsPage";
import SearchHomePage from "./SearchHomePage";
import SignalDetailPage from "./SignalDetailPage";

// Dev-витрина: все страницы и компоненты на моковых данных, без бэкенда.
// Доступна по /dev только в `npm run dev` (см. App.tsx).

const sources: SignalSource[] = [
  {
    feed_item_id: 1, title: "Liquid Neural Networks for Adaptive Robot Control",
    url: "https://arxiv.org", source_key: "arxiv", source_name: "arXiv", source_type: "preprint",
    trust_level: "high", language: "EN", published_at: "2026-02-18T00:00:00Z", is_primary: true,
  },
  {
    feed_item_id: 2, title: "Startup raises $12M for liquid-network robotics",
    url: "https://techcrunch.com", source_key: "techcrunch", source_name: "TechCrunch", source_type: "tech_media",
    trust_level: "low", language: "EN", published_at: "2026-03-02T00:00:00Z", is_primary: false,
  },
  {
    feed_item_id: 3, title: "Исследователи ВШЭ разработали адаптивные нейросети для роботов",
    url: "https://www.hse.ru", source_key: "hse_science", source_name: "НИУ ВШЭ", source_type: "university",
    trust_level: "medium", language: "RU", published_at: "2026-03-10T00:00:00Z", is_primary: false,
  },
  {
    feed_item_id: 4, title: "Adaptive control with continuous-time networks",
    url: "https://openalex.org", source_key: "openalex", source_name: "OpenAlex", source_type: "academic_aggregator",
    trust_level: "high", language: "EN", published_at: "2026-01-20T00:00:00Z", is_primary: false,
  },
];

const base = {
  area: null, mention_trend: null, model_version: "trained-tfidf-logreg-v1",
  created_at: "2026-10-01T10:00:00Z",
};

const included1: Signal = {
  ...base, id: 9101, status: "included", is_mainstream: false, stage: "Ранняя стадия", score: 0.78,
  title: "Liquid Neural Networks for Adaptive Robot Control",
  description: "Нейросети с непрерывной динамикой, которые подстраивают свои параметры под меняющуюся среду прямо во время работы.",
  problem: "Классические модели плохо переносятся на новые условия и требуют переобучения при каждом изменении среды.",
  potential_advantage: "Компактные модели адаптируются без переобучения, что снижает затраты на вычисления в роботах.",
  case_example: "Прототип автономного дрона прошёл испытания в лесу без дообучения на новых данных.",
  explanation: {
    predicted_class: "слабый сигнал", enrichment_model: "qwen2.5:3b",
    key_predictors: ["neuromorphic", "adaptive", "robotic", "spiking"],
    rationale: "Обученная модель (TF-IDF + LogisticRegression): класс 'слабый сигнал', P(слабый сигнал)=0.78.",
  },
  sources,
};

const included2: Signal = {
  ...base, id: 9102, status: "included", is_mainstream: false, stage: "Ранняя стадия", score: 0.64,
  title: "Photonic Accelerators for Edge AI Inference",
  description: "Оптические вычислители, выполняющие матричные операции светом вместо электрических сигналов.",
  problem: "Энергопотребление и тепловыделение ограничивают инференс нейросетей на периферийных устройствах.",
  potential_advantage: "Потенциально на порядок меньше энергии на операцию при высокой пропускной способности.",
  case_example: "Не указано в источнике.",
  explanation: {
    predicted_class: "слабый сигнал", enrichment_model: "qwen2.5:3b",
    key_predictors: ["photonic", "energy", "inference"],
  },
  sources: sources.slice(0, 1),
};

const included3: Signal = {
  ...included2, id: 9103, score: 0.58, title: "Neuromorphic Sensors for Low-Power Navigation",
  sources: sources.slice(0, 2),
};

const excludedLow: Signal = {
  ...base, id: 9201, status: "excluded", is_mainstream: false, stage: null, score: 0.43,
  title: "Spiking Networks for Event-Based Vision",
  description: "Обработка потока событий с нейроморфной камеры спайковой сетью.",
  problem: "Обычные камеры избыточны по данным при быстром движении.",
  potential_advantage: "Низкая задержка и энергопотребление.",
  case_example: "Не указано в источнике.",
  explanation: { predicted_class: "слабый сигнал", enrichment_model: "qwen2.5:3b", key_predictors: ["event", "spiking"] },
  sources: sources.slice(0, 1),
};

const excludedMature: Signal = {
  ...base, id: 9202, status: "excluded", is_mainstream: true, stage: null, score: 0.31,
  title: "Large Language Models in Enterprise Search",
  description: null, problem: null, potential_advantage: null, case_example: null,
  explanation: { predicted_class: "зрелая технология", key_predictors: ["llm", "enterprise", "search"] },
  sources: sources.slice(0, 2),
};

const baseStatus: Omit<SearchStatusResponse, "query_id" | "status" | "phase" | "results" | "excluded"> = {
  query_text: "нейроморфные чипы для граничных вычислений",
  sources_processed: 114, candidates_found: 114, signals_above_75: 1, error: null,
};

// Большие id, чтобы не пересечься с реальными запросами, если бэкенд запущен
const Q = { done: 900001, running: 900002, empty: 900003, failed: 900004 };

const previewClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, retry: false, refetchOnWindowFocus: false } },
});

previewClient.setQueryData(["searchStatus", Q.done], {
  ...baseStatus, query_id: Q.done, status: "done", phase: "done",
  results: [included1, included2, included3], excluded: [excludedLow, excludedMature],
} satisfies SearchStatusResponse);
previewClient.setQueryData(["searchStatus", Q.running], {
  ...baseStatus, query_id: Q.running, status: "running", phase: "scoring", results: null, excluded: null,
} satisfies SearchStatusResponse);
previewClient.setQueryData(["searchStatus", Q.empty], {
  ...baseStatus, query_id: Q.empty, status: "done", phase: "done", candidates_found: 0, signals_above_75: 0,
  results: [], excluded: [],
} satisfies SearchStatusResponse);
previewClient.setQueryData(["searchStatus", Q.failed], {
  ...baseStatus, query_id: Q.failed, status: "failed", phase: null,
  error: "Поиск остановлен пользователем", results: null, excluded: null,
} satisfies SearchStatusResponse);
for (const s of [included1, included2, excludedLow, excludedMature]) {
  previewClient.setQueryData(["signal", s.id], s);
}

const noop = () => {};

function Frame({ title, note, height, noRouter, children }: { title: string; note?: string; height: number; noRouter?: boolean; children: ReactNode }) {
  return (
    <section className="mb-10">
      <h3 className="mb-1 font-sans text-base font-medium text-neutral-950">{title}</h3>
      {note && <p className="mb-2 text-xs text-neutral-500">{note}</p>}
      {/* transform создаёт контейнер для position:fixed — модалки остаются внутри рамки */}
      <div
        className="relative overflow-auto rounded-xl border border-neutral-300 bg-neutral-100 [transform:translateZ(0)]"
        style={{ height }}
      >
        {noRouter ? children : <MemoryRouter>{children}</MemoryRouter>}
      </div>
    </section>
  );
}

function PageFrame({ title, path, note }: { title: string; path: string; note?: string }) {
  return (
    <Frame title={title} note={note ?? path} height={820} noRouter>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<SearchHomePage />} />
          <Route path="/results/:queryId" element={<ResultsPage />} />
          <Route path="/results/:queryId/signals/:signalId" element={<SignalDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>
    </Frame>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-6">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">{title}</div>
      <div className="rounded-xl border border-neutral-300 bg-neutral-100 p-4">
        <MemoryRouter>{children}</MemoryRouter>
      </div>
    </div>
  );
}

const NAV = [
  ["pages", "Страницы"],
  ["modals", "Модальные окна"],
  ["components", "Компоненты"],
] as const;

export default function DevPreviewPage() {
  return (
    <QueryClientProvider client={previewClient}>
      <div className="min-h-screen bg-neutral-0">
        <header className="sticky top-0 z-[60] flex items-center gap-6 border-b border-neutral-300 bg-neutral-0/90 px-6 py-3 backdrop-blur">
          <div className="font-sans text-sm font-medium text-neutral-950">Витрина компонентов (dev)</div>
          <nav className="flex gap-4 text-sm">
            {NAV.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="text-link hover:text-link-hover">{label}</a>
            ))}
          </nav>
          <div className="ml-auto text-xs text-neutral-500">
            адаптив (sm:/xl:) зависит от ширины окна браузера, не рамки
          </div>
        </header>

        <main className="mx-auto max-w-360 px-6 py-8">
          <h2 id="pages" className="mb-6 text-2xl text-neutral-950">Страницы</h2>
          <PageFrame title="Главная" path="/" />
          <PageFrame title="Результаты — готово" path={`/results/${Q.done}`} />
          <PageFrame title="Результаты — поиск идёт (модалка прогресса)" path={`/results/${Q.running}`}
            note="поллинг ходит на бэкенд за новыми данными; в ответ остаётся мок" />
          <PageFrame title="Результаты — пусто" path={`/results/${Q.empty}`} />
          <PageFrame title="Результаты — ошибка" path={`/results/${Q.failed}`} />
          <PageFrame title="Карточка сигнала — включённый" path={`/results/${Q.done}/signals/${included1.id}`} />
          <PageFrame title="Карточка сигнала — исключённый, ещё без описания" path={`/results/${Q.done}/signals/${excludedMature.id}`} />
          <PageFrame title="404" path="/nope" />

          <h2 id="modals" className="mb-6 mt-14 text-2xl text-neutral-950">Модальные окна</h2>
          <Frame title="Прогресс поиска — сбор" height={460}>
            <SearchProgressModal queryText="нейроморфные чипы" phase="collecting" onStopConfirm={noop} />
          </Frame>
          <Frame title="Прогресс поиска — скоринг" height={460}>
            <SearchProgressModal queryText="нейроморфные чипы" phase="scoring" onStopConfirm={noop} />
          </Frame>
          <Frame title="Прогресс поиска — формируем ТОП" height={460}>
            <SearchProgressModal queryText="нейроморфные чипы" phase="ranking" onStopConfirm={noop} />
          </Frame>
          <Frame title="Подтверждение остановки" height={460}>
            <SearchProgressModal queryText="нейроморфные чипы" phase="scoring" onStopConfirm={noop} initialConfirming />
          </Frame>
          <Frame title="Как определяется оценка — включённый" height={620}>
            <ConfidenceModal signal={included1} onClose={noop} />
          </Frame>
          <Frame title="Как определяется оценка — исключённый (низкая уверенность)" height={620}>
            <ConfidenceModal signal={excludedLow} onClose={noop} />
          </Frame>

          <h2 id="components" className="mb-6 mt-14 text-2xl text-neutral-950">Компоненты</h2>
          <Block title="Logo"><Logo /></Block>
          <Block title="SearchInput — lg / sm">
            <div className="space-y-4">
              <SearchInput size="lg" onSubmit={noop} />
              <SearchInput size="lg" defaultValue="нейроморфные чипы" onSubmit={noop} />
              <SearchInput size="sm" defaultValue="нейроморфные чипы" onSubmit={noop} />
            </div>
          </Block>
          <Block title="StatusStep — done / active / pending">
            <div className="flex gap-6">
              <StatusStep label="Источники собраны" state="done" />
              <StatusStep label="Проверка стадии" state="active" />
              <StatusStep label="Формируем ТОП-15" state="pending" />
            </div>
          </Block>
          <Block title="StatCard">
            <div className="flex gap-4">
              <StatCard icon={FileChartBarSolid} label="Обработано источников" value={1248} hint="Публикации, патенты и отчёты" />
              <StatCard icon={FileCheckSolid} label="Найдено кандидатов" value={114} hint="Выявлено при анализе источников" />
              <StatCard icon={FileLineSolid} label="Отобрано слабых сигналов" value={15} hint="Лучшие по результатам ранжирования" />
            </div>
          </Block>
          <Block title="SignalsTable — слабые сигналы">
            <div className="overflow-hidden rounded-2xl bg-neutral-0">
              <SignalsTable signals={[included1, included2, included3]} mode="included" onRowClick={noop} />
            </div>
          </Block>
          <Block title="SignalsTable — исключённые">
            <div className="overflow-hidden rounded-2xl bg-neutral-0">
              <SignalsTable signals={[excludedLow, excludedMature]} mode="excluded" onRowClick={noop} />
            </div>
          </Block>
          <Block title="EmptyState"><EmptyState queryText="нейроморфные чипы" onChangeQuery={noop} /></Block>
          <Block title="Breadcrumbs">
            <Breadcrumbs items={[{ label: "Слабые сигналы", to: "/" }, { label: included1.title }]} />
          </Block>
          <Block title="ConfidencePanel — включённый / исключённый">
            <div className="grid grid-cols-2 gap-6">
              <ConfidencePanel signal={included1} />
              <ConfidencePanel signal={excludedLow} />
            </div>
          </Block>
          <Block title="ReasonTags — включённый / исключённый">
            <div className="space-y-4">
              <ReasonTags signal={included1} />
              <ReasonTags signal={excludedMature} />
            </div>
          </Block>
          <Block title="CaseExamples — с текстом / «не указано»">
            <div className="space-y-4">
              <CaseExamples text={included1.case_example} primarySource={sources[0]} />
              <CaseExamples text="Не указано в источнике." primarySource={sources[0]} />
            </div>
          </Block>
          <Block title="SourcesList — 4 источника (RU/EN, разная доверенность)">
            <SourcesList sources={sources} allSourcesHref="#" />
          </Block>
        </main>
      </div>
    </QueryClientProvider>
  );
}
