import type { ComponentType } from "react";

interface Props {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  hint: string;
  note?: string; // дополнительная строка под подписью
}

export default function StatCard({ icon: Icon, label, value, hint, note }: Props) {
  return (
    <div className="glass-card glass-border-8 flex-1 rounded-xl p-5">
      <div className="flex items-center justify-between">
        <span className="text-base text-neutral-950">{label}</span>
        <span className="flex h-10 w-10 items-center justify-center rounded-xl text-neutral-950 glass-element">
          <Icon className="h-6 w-6" />
        </span>
      </div>
      <div className="mt-2 font-display text-5xl font-bold text-primary">
        {value.toLocaleString("ru-RU")}
      </div>
      <div className="mt-2 text-[13px] text-black-alpha">{hint}</div>
      {note && <div className="mt-1 text-[13px] text-neutral-900">{note}</div>}
    </div>
  );
}
