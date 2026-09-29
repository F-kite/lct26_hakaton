import type { SearchPhase } from "../../api/types";
import StatusStep from "./StatusStep";

interface Props {
  queryText: string;
  phase: SearchPhase;
  onStopClick: () => void;
}

const PHASE_ORDER = ["collecting", "scoring", "ranking", "done"] as const;

function stateFor(stepPhase: (typeof PHASE_ORDER)[number], current: SearchPhase) {
  const currentIdx = PHASE_ORDER.indexOf((current ?? "collecting") as (typeof PHASE_ORDER)[number]);
  const stepIdx = PHASE_ORDER.indexOf(stepPhase);
  if (currentIdx > stepIdx) return "done" as const;
  if (currentIdx === stepIdx) return "active" as const;
  return "pending" as const;
}

export default function SearchProgressModal({ queryText, phase, onStopClick }: Props) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-neutral-950/30 backdrop-blur-sm">
      <div className="animate-fade-in mx-4 w-full max-w-2xl rounded-2xl bg-neutral-0 p-8 text-center shadow-xl">
        <h2 className="text-[32px] font-bold text-neutral-950">{queryText}</h2>
        <p className="mx-auto mt-3 max-w-md text-base text-neutral-600">
          Сопоставляем независимые источники и проверяем, какие технологии находятся на ранней
          стадии развития.
        </p>
        <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-center sm:gap-6">
          <StatusStep label="Источники собраны" state={stateFor("collecting", phase)} />
          <StatusStep label="Проверка стадии" state={stateFor("scoring", phase)} />
          <StatusStep label="Формируем ТОП-15" state={stateFor("ranking", phase)} />
        </div>
        <button
          type="button"
          onClick={onStopClick}
          className="mt-8 rounded-full border bg-neutral-300/20 border-neutral-300 px-6 py-2.5 text-sm text-neutral-600 hover:bg-neutral-50 hover:cursor-pointer"
        >
          Остановить поиск
        </button>
      </div>
    </div>
  );
}
