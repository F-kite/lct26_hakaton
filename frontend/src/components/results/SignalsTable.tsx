import ArrowRight from "@iconify-react/bi/arrow-right";
import { useMemo, useState } from "react";

import type { Signal } from "../../api/types";

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
    <table className="w-full border-collapse border-spacing-0 text-sm">
      <thead>
        <tr className="border-b border-neutral-100 text-left text-neutral-900">
          <th className="px-4 py-4 font-normal">№</th>
          <th className="px-4 py-4 font-normal">Технология</th>
          <th
            className="cursor-pointer select-none px-4 py-4 font-normal"
            onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
          >
            Оценка {sortDir === "desc" ? "↓" : "↑"}
          </th>
          <th className="px-4 py-4 font-normal">{reasonColumnLabel}</th>
          <th className="px-4 py-4 font-normal">Источники</th>
          <th className="px-4 py-4 font-normal">Статус</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((signal, i) => {
          const pct = Math.round(signal.score * 100);
          const tags = (signal.explanation.key_predictors ?? []).slice(0, 2);
          return (
            <tr
              key={signal.id}
              className="border-b border-neutral-100 bg-neutral-0 last:border-b-0"
            >
              <td className="px-5 py-5 text-neutral-950 font-display text-base font-bold">{String(i + 1).padStart(2, "0")}</td>
              <td className="max-w-xs truncate px-4 py-5 font-medium text-neutral-900">
                {signal.title}
              </td>
              <td className="px-4 py-4">
                <div className="relative h-5 w-32 overflow-hidden rounded-sm bg-neutral-200">
                  <div className={`h-full ${barColor}`} style={{ width: `${pct}%` }} />
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium tabular-nums text-neutral-950">
                    {pct}%
                  </span>
                </div>
              </td>
              <td className="px-4 py-5">
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-md bg-neutral-50 px-2.5 py-1 text-xs text-neutral-600"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-5 ">
                <div className="inline-block rounded-md bg-neutral-50 text-neutral-600 text-xs px-2.5 py-1">
                  {signal.sources.length} {signal.sources.length === 1 ? "источник" : "источников"}
                </div>
              </td>
              <td className="px-4 py-5">
                <button
                  type="button"
                  onClick={() => onRowClick(signal)}
                  className="flex items-center gap-1 font-medium text-link hover:text-link-hover hover:cursor-pointer"
                >
                  Отчёт <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
