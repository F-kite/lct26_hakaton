import ChevronRight from "@iconify-react/bi/chevron-right";
import SearchThin from "@iconify-react/bi/search";
import X from "@iconify-react/bi/x";
import RecentlyViewed from "@iconify-react/carbon/recently-viewed";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { findMatch, retryHistory, useSearchHistory, type HistoryEntry } from "../../lib/history";
import Highlight from "../search/Highlight";

interface Props {
  onClose: () => void;
  onStartSearch: () => void;
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function groupLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(d) === dayKey(today)) return "Сегодня";
  if (dayKey(d) === dayKey(yesterday)) return "Вчера";
  return d.toLocaleDateString("ru-RU");
}

function formatEntryDate(d: Date): string {
  const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return `${date}  ${time}`;
}

function groupByDay(entries: HistoryEntry[]): { label: string; entries: HistoryEntry[] }[] {
  const groups: { key: string; label: string; entries: HistoryEntry[] }[] = [];
  for (const entry of entries) {
    const d = new Date(entry.createdAt);
    const key = dayKey(d);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.entries.push(entry);
    else groups.push({ key, label: groupLabel(d), entries: [entry] });
  }
  return groups;
}

function Centered({ title, text, action, onAction }: { title: string; text?: string; action: string; onAction: () => void }) {
  return (
    <div className="flex flex-col items-center px-10 py-24 text-center">
      <h3 className="text-[32px] font-bold leading-tight text-neutral-950">{title}</h3>
      {text && <p className="mt-3 max-w-95 text-sm text-neutral-500">{text}</p>}
      <button
        type="button"
        onClick={onAction}
        className="mt-6 rounded-full bg-primary px-8 py-2.5 text-base text-white hover:bg-link-hover hover:cursor-pointer"
      >
        {action}
      </button>
    </div>
  );
}

export default function HistoryModal({ onClose, onStartSearch }: Props) {
  const navigate = useNavigate();
  const history = useSearchHistory();
  const [filter, setFilter] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const groups = useMemo(() => {
    const visible = filter.trim()
      ? history.entries.filter((e) => findMatch(e.query, filter) !== -1)
      : history.entries;
    return groupByDay(visible);
  }, [history.entries, filter]);

  const open = (entry: HistoryEntry) => {
    onClose();
    navigate(`/results/${entry.id}`);
  };

  let body: React.ReactNode;
  if (!history.ok) {
    body = <Centered title="Не удалось загрузить историю" action="Повторить" onAction={retryHistory} />;
  } else if (history.entries.length === 0) {
    body = (
      <Centered
        title="История запросов пуста"
        text="Здесь будут отображаться ваши предыдущие исследования. Начните поиск, чтобы сохранить первый запрос."
        action="Начать поиск"
        onAction={onStartSearch}
      />
    );
  } else {
    body = (
      <div className="flex h-[min(720px,80vh)] flex-col">
        <div className="px-7 pt-8">
          <h3 className="text-[32px] font-bold leading-tight text-neutral-950">История запросов</h3>
          <p className="mt-2 text-sm text-secondary">Вернитесь к предыдущим исследованиям</p>
          <div className="relative mt-5">
            <SearchThin className="pointer-events-none absolute left-5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Поиск по истории запросов"
              autoFocus
              className="h-12 w-full rounded-full border border-neutral-300 bg-neutral-50 pl-12 pr-5 text-sm
                text-neutral-950 outline-none placeholder:text-neutral-500"
            />
          </div>
        </div>

        <div className="mt-4 flex-1 overflow-y-auto px-7 pb-6">
          {groups.length === 0 ? (
            <p className="mt-10 text-center text-sm text-neutral-500">
              Совпадений не найдено. Попробуйте изменить запрос.
            </p>
          ) : (
            groups.map((group) => (
              <section key={group.label} className="mt-3 first:mt-0">
                <h4 className="font-display text-lg text-secondary">{group.label}</h4>
                <ul className="mt-1">
                  {group.entries.map((entry) => (
                    <li key={entry.id}>
                      <button
                        type="button"
                        onClick={() => open(entry)}
                        className="-mx-2 flex w-[calc(100%+1rem)] items-center gap-3 rounded-lg px-2 py-2 text-left
                          hover:bg-neutral-50 hover:cursor-pointer"
                      >
                        <RecentlyViewed className="h-4 w-4 shrink-0 self-start mt-1 text-neutral-500" />
                        <span className="flex-1">
                          <span className="block text-base">
                            <Highlight text={entry.query} input={filter} />
                          </span>
                          <span className="mt-0.5 block whitespace-pre text-sm text-neutral-500">
                            {formatEntryDate(new Date(entry.createdAt))}
                          </span>
                        </span>
                        <ChevronRight className="h-4 w-4 shrink-0 text-neutral-500" />
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/30"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="История запросов"
        className="animate-fade-in relative mx-4 w-full max-w-130"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glass-frame rounded-xl p-2">
          <div className="rounded-xl bg-neutral-0">{body}</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute right-2 top-1 flex h-10 w-10 items-center justify-center rounded-full glass-frame
            [--glass-blur:3px] text-white hover:bg-neutral-0/15 hover:cursor-pointer sm:-right-10 sm:-top-10"
        >
          <X className="h-8 w-8" />
        </button>
      </div>
    </div>
  );
}
