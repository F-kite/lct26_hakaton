import { useMemo, useState } from "react";

import type { Signal } from "../../api/types";
import { ArrowRightIcon } from "../icons";

interface Props {
  signals: Signal[];
  mode: "included" | "excluded";
  onRowClick: (signal: Signal) => void;
}

export default function SignalsTable({ signals, mode, onRowClick }: Props) {
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(
    () =>
      [...signals].sort((a, b) => (sortDir === "desc" ? b.score - a.score : a.score - b.score)),
    [signals, sortDir],
  );

  const barColor = mode === "included" ? "bg-success" : "bg-error";
  const reasonColumnLabel = mode === "included" ? "Ключевые предикторы" : "Причина исключения";

  return (
    <table className="w-full border-separate border-spacing-0 text-sm">
      <thead>
        <tr className="text-left text-neutral-500">
          <th className="px-4 py-3 font-normal">№</th>
          <th className="px-4 py-3 font-normal">Технология</th>
          <th
            className="cursor-pointer select-none px-4 py-3 font-normal"
            onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
          >
            Оценка {sortDir === "desc" ? "↓" : "↑"}
          </th>
          <th className="px-4 py-3 font-normal">{reasonColumnLabel}</th>
          <th className="px-4 py-3 font-normal">Источники</th>
          <th className="px-4 py-3 font-normal">Статус</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((signal, i) => {
          const pct = Math.round(signal.score * 100);
          const tags = (signal.explanation.key_predictors ?? []).slice(0, 2);
          return (
            <tr key={signal.id} className="border-t border-neutral-100 bg-neutral-0">
              <td className="px-4 py-4 text-neutral-500">{String(i + 1).padStart(2, "0")}</td>
              <td className="max-w-xs truncate px-4 py-4 font-medium text-neutral-900">
                {signal.title}
              </td>
              <td className="px-4 py-4">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-24 overflow-hidden rounded-full bg-neutral-200">
                    <div className={`h-full ${barColor}`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="tabular-nums text-neutral-700">{pct}%</span>
                </div>
              </td>
              <td className="px-4 py-4">
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs text-neutral-600"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-4 text-neutral-600">
                {signal.sources.length} {signal.sources.length === 1 ? "источник" : "источников"}
              </td>
              <td className="px-4 py-4">
                <button
                  type="button"
                  onClick={() => onRowClick(signal)}
                  className="flex items-center gap-1 font-medium text-link hover:text-link-hover"
                >
                  Отчёт <ArrowRightIcon className="h-3.5 w-3.5" />
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
