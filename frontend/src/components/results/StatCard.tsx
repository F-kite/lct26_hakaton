import type { ComponentType } from "react";

interface Props {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  hint: string;
}

export default function StatCard({ icon: Icon, label, value, hint }: Props) {
  return (
    <div className="flex-1 rounded-2xl bg-linear-[-190deg] from-neutral-200 to-neutral-100 to-80% p-2 shadow-sm">
      <div className="h-full rounded-2xl bg-neutral-0 p-5">
        <div className="flex items-center justify-between">
          <span className="text-md text-neutral-950">{label}</span>
          <span className="flex h-10 w-10 items-center justify-center rounded-lg text-neutral-950 bg-muted/8">
            <Icon className="h-6 w-6" />
          </span>
        </div>
        <div className="mt-2 font-display text-4xl font-bold text-primary">
          {value.toLocaleString("ru-RU")}
        </div>
        <div className="mt-1 text-xs text-neutral-500">{hint}</div>
      </div>
    </div>
  );
}
