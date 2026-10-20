import type { ReportsSummary } from "../../api/types";

const ROWS: { key: "stage" | "first_applications" | "mass_adoption"; label: string }[] = [
  { key: "stage", label: "Стадия развития" },
  { key: "first_applications", label: "Первые применения" },
  { key: "mass_adoption", label: "Массовое внедрение" },
];

export default function ReportsSummaryCard({ summary }: { summary: ReportsSummary | undefined }) {
  return (
    <div className="rounded-xl p-5 glass-card glass-border-8 [--glass-fill:var(--color-primary-50)]">
      <div className="text-sm font-medium text-neutral-950">Сводная оценка из отчётов</div>

      {!summary || summary.status === "pending" ? (
        <div className="mt-4 space-y-3" aria-label="Готовим сводную оценку">
          {ROWS.map((r) => (
            <div key={r.key} className="h-4 animate-pulse rounded bg-neutral-0/70" />
          ))}
        </div>
      ) : summary.status === "none" ? (
        <p className="mt-3 text-sm text-neutral-600">Аналитические отчёты по технологии не найдены.</p>
      ) : (
        <>
          <dl className="mt-2 divide-y divide-neutral-300">
            {ROWS.map((r) => {
              const field = summary[r.key];
              return (
                <div key={r.key} className="py-3" title={field?.basis ?? undefined}>
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-neutral-600">{r.label}</dt>
                    <dd className="text-right text-sm font-medium text-neutral-950">{field?.value ?? "Нет данных"}</dd>
                  </div>
                  {field?.basis && <p className="mt-1 text-xs text-neutral-500">{field.basis}</p>}
                </div>
              );
            })}
          </dl>
          <div className="mt-1 text-xs text-neutral-500">Сгенерировано ИИ · {summary.model}</div>
        </>
      )}
    </div>
  );
}
