import type { ComponentType } from "react";

interface Props {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  hint: string;
}

export default function StatCard({ icon: Icon, label, value, hint }: Props) {
  return (
    <div className="flex-1 rounded-2xl bg-neutral-0 p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-sm text-neutral-600">{label}</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-950 text-white">
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="mt-2 font-display text-4xl font-bold text-primary">
        {value.toLocaleString("ru-RU")}
      </div>
      <div className="mt-1 text-xs text-neutral-500">{hint}</div>
    </div>
  );
}
