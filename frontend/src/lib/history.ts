import { useSyncExternalStore } from "react";

// История поисков без авторизации — только в этом браузере (localStorage).
// Хранятся id запросов: результаты лежат в БД и открываются по /results/:id.

export interface HistoryEntry {
  id: number;
  query: string;
  createdAt: string; // ISO
}

export type HistorySnapshot =
  | { ok: true; entries: HistoryEntry[] }
  | { ok: false; entries: [] };

const STORAGE_KEY = "lct.searchHistory.v1";
const MAX_ENTRIES = 50;
const CHANGE_EVENT = "search-history-change";

function isEntry(value: unknown): value is HistoryEntry {
  const e = value as HistoryEntry;
  return (
    typeof e === "object" && e !== null &&
    typeof e.id === "number" && typeof e.query === "string" && typeof e.createdAt === "string"
  );
}

// useSyncExternalStore требует стабильный снимок — пересобираем только при смене строки
const ERROR_SNAPSHOT: HistorySnapshot = { ok: false, entries: [] };
const EMPTY_SNAPSHOT: HistorySnapshot = { ok: true, entries: [] };
let cachedRaw: string | null | undefined;
let cachedSnapshot: HistorySnapshot = EMPTY_SNAPSHOT;

function readSnapshot(): HistorySnapshot {
  let raw: string | null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    return ERROR_SNAPSHOT;
  }
  if (raw === cachedRaw) return cachedSnapshot;
  cachedRaw = raw;
  if (raw === null) {
    cachedSnapshot = EMPTY_SNAPSHOT;
    return cachedSnapshot;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    cachedSnapshot = Array.isArray(parsed) ? { ok: true, entries: parsed.filter(isEntry) } : ERROR_SNAPSHOT;
  } catch {
    cachedSnapshot = ERROR_SNAPSHOT;
  }
  return cachedSnapshot;
}

function write(entries: HistoryEntry[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // приватный режим / переполнение — история просто не сохранится
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function addHistoryEntry(id: number, query: string) {
  const current = readSnapshot().entries.filter((e) => e.id !== id);
  write([{ id, query, createdAt: new Date().toISOString() }, ...current]);
}

export function removeHistoryEntry(id: number) {
  write(readSnapshot().entries.filter((e) => e.id !== id));
}

/** Повторная попытка после ошибки чтения: сбрасываем кэш, чтобы перечитать хранилище. */
export function retryHistory() {
  cachedRaw = undefined;
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange); // изменения из других вкладок
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useSearchHistory(): HistorySnapshot {
  return useSyncExternalStore(subscribe, readSnapshot);
}

/** Начало любого слова в тексте совпадает с введённым (регистр не важен). */
export function findMatch(text: string, input: string): number {
  const needle = input.trim().toLowerCase();
  if (!needle) return -1;
  const haystack = text.toLowerCase();
  let idx = haystack.indexOf(needle);
  while (idx !== -1) {
    if (idx === 0 || /[\s\-«"(]/.test(haystack[idx - 1])) return idx;
    idx = haystack.indexOf(needle, idx + 1);
  }
  return -1;
}
