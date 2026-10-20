import RecentlyViewed from "@iconify-react/carbon/recently-viewed";
import { useState } from "react";

import HistoryModal from "./HistoryModal";

interface Props {
  /** «Начать поиск» в пустой истории — закрыть модалку и поставить фокус в поиск. */
  onStartSearch: () => void;
}

export default function HistoryButton({ onStartSearch }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex shrink-0 items-center gap-3 rounded-2xl glass-element [--glass-line:var(--color-neutral-0)]
          px-5 py-3 font-display text-[15px] text-neutral-950 [-webkit-text-stroke:0.4px_currentColor] shadow-[0_4px_14px_rgb(0_0_0/0.06)]
          hover:[--glass-via:var(--color-neutral-50)] hover:cursor-pointer"
      >
        <RecentlyViewed className="h-5 w-5 text-neutral-500" />
        История запросов
      </button>
      {open && (
        <HistoryModal
          onClose={() => setOpen(false)}
          onStartSearch={() => {
            setOpen(false);
            onStartSearch();
          }}
        />
      )}
    </>
  );
}
