import { useState } from "react";

import type { SearchPhase } from "../../api/types";
import StatusStep from "./StatusStep";
import StopConfirmContent from "./StopConfirmModal";

interface Props {
  queryText: string;
  phase: SearchPhase;
  onStopConfirm: () => void;
  initialConfirming?: boolean;
}

const PHASE_ORDER = ["collecting", "scoring", "ranking", "done"] as const;

function stateFor(stepPhase: (typeof PHASE_ORDER)[number], current: SearchPhase) {
  const currentIdx = PHASE_ORDER.indexOf((current ?? "collecting") as (typeof PHASE_ORDER)[number]);
  const stepIdx = PHASE_ORDER.indexOf(stepPhase);
  if (currentIdx > stepIdx) return "done" as const;
  if (currentIdx === stepIdx) return "active" as const;
  return "pending" as const;
}

export default function SearchProgressModal({ queryText, phase, onStopConfirm, initialConfirming = false }: Props) {
  const [confirming, setConfirming] = useState(initialConfirming);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-neutral-950/30 rounded-xl">
      <div className="animate-fade-in glass-frame mx-4 w-fit max-w-156.25 rounded-xl p-2">
        <div className="rounded-xl bg-neutral-0 px-4 py-2 text-center">
          {confirming ? (
            <StopConfirmContent onConfirm={onStopConfirm} onCancel={() => setConfirming(false)} />
          ) : (
            <div className="w-xl max-w-full">
          <div className="px-6">
            <h2 className="mt-4 text-[32px] font-bold text-neutral-950">{queryText}</h2>
            <p className="mx-auto mt-4 max-w-md text-base text-neutral-600">
              Сопоставляем независимые источники и проверяем, какие технологии находятся на ранней
              стадии развития.
            </p>
          </div>
          <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-center sm:gap-5">
            <StatusStep label="Источники собраны" state={stateFor("collecting", phase)} />
            <StatusStep label="Проверка стадии" state={stateFor("scoring", phase)} />
            <StatusStep label="Формируем ТОП-15" state={stateFor("ranking", phase)} />
          </div>
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-7 mb-2 rounded-full border  bg-neutral-200/20 border-neutral-300 glass-element px-6 py-2.5 
            text-md text-neutral-600 hover:bg-neutral-50 hover:cursor-pointer"
          >
            Остановить поиск
          </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
