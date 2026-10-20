import { useRetrySummary, useSearchSummary } from "../../api/queries";
import type { SummarySignal } from "../../api/types";

interface Props {
  queryId: number;
  onOpenSignal: (signalId: number) => void;
}

function pluralQueries(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "запрос";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "запроса";
  return "запросов";
}

function SignalLink({ signal, onOpen }: { signal: SummarySignal; onOpen: (id: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(signal.signal_id)}
      className="text-left text-base font-medium text-neutral-950 hover:text-link-hover hover:cursor-pointer"
    >
      {signal.title}
    </button>
  );
}

export default function SearchSummary({ queryId, onOpenSignal }: Props) {
  const { data, isError } = useSearchSummary(queryId, true);
  const retry = useRetrySummary(queryId);

  // без GigaChat или без сигналов блок не показываем
  if (isError || !data || data.status === "disabled" || data.status === "empty") return null;

  let body: React.ReactNode;
  if (data.status === "failed") {
    body = (
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-base text-neutral-600">Не удалось сформировать вывод.</p>
        <button
          type="button"
          onClick={() => retry.mutate()}
          disabled={retry.isPending}
          className="rounded-full bg-primary px-5 py-2 text-sm text-white hover:bg-link-hover hover:cursor-pointer disabled:opacity-60"
        >
          Повторить
        </button>
      </div>
    );
  } else if (data.status !== "done") {
    const ahead = data.queue_position ?? 0;
    body = (
      <div>
        <p className="text-base text-neutral-600">
          {data.status === "queued" && ahead > 0
            ? `В очереди: перед вами ${ahead} ${pluralQueries(ahead)}…`
            : "Формируем вывод по найденным сигналам…"}
        </p>
        <div className="mt-4 space-y-2.5" aria-hidden>
          <div className="h-3.5 w-full animate-pulse rounded bg-neutral-200" />
          <div className="h-3.5 w-11/12 animate-pulse rounded bg-neutral-200" />
          <div className="h-3.5 w-3/5 animate-pulse rounded bg-neutral-200" />
        </div>
      </div>
    );
  } else {
    body = (
      <>
        <p className="text-base leading-relaxed text-neutral-900">{data.overview}</p>
        <div className="mt-6 grid gap-6 lg:grid-cols-[2fr_1fr]">
          {data.key_signals.length > 0 && (
            <section>
              <h3 className="text-lg font-bold text-neutral-950">Ключевые сигналы</h3>
              <ul className="mt-3 space-y-4">
                {data.key_signals.map((s) => (
                  <li key={s.signal_id}>
                    <SignalLink signal={s} onOpen={onOpenSignal} />
                    {s.reason && <p className="mt-1 text-sm text-neutral-600">{s.reason}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <h3 className="text-lg font-bold text-neutral-950">Самые уверенные</h3>
            <ul className="mt-3 space-y-3">
              {data.top_signals.map((s) => (
                <li key={s.signal_id} className="flex items-start justify-between gap-4">
                  <SignalLink signal={s} onOpen={onOpenSignal} />
                  <span className="shrink-0 font-display text-lg font-bold text-primary">
                    {Math.round(s.score * 100)}%
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </>
    );
  }

  return (
    <section className="glass-card glass-border-8 mt-4 rounded-xl p-6" aria-live="polite">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-2xl font-bold text-neutral-950">Итоги поиска</h2>
        <span className="rounded-md bg-neutral-50 px-2.5 py-1 text-sm text-neutral-600">
          Сгенерировано ИИ{data.model ? ` · ${data.model}` : ""}
        </span>
      </div>
      {body}
    </section>
  );
}
