interface Props {
  onConfirm: () => void;
  onCancel: () => void;
}

export default function StopConfirmModal({ onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/40 backdrop-blur-sm">
      <div className="animate-fade-in mx-4 my-2 w-full max-w-md rounded-2xl bg-neutral-0 p-7 text-center shadow-xl">
        <h3 className="text-3xl mt-4 font-bold text-neutral-950">Остановить поиск?</h3>
        <p className="mt-4 text-base text-neutral-600">
          Анализ ещё не завершён. Если остановить поиск сейчас, текущий прогресс будет потерян.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <button
            type="button"
            onClick={onConfirm}
            className="shrink-0 text-base whitespace-nowrap rounded-full border border-neutral-300 px-5 py-2.5 text-neutral-700 hover:bg-neutral-50"
          >
            Остановить поиск
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="shrink-0 whitespace-nowrap rounded-full bg-primary px-5 py-2.5 text-base text-white hover:bg-link-hover"
          >
            Продолжить поиск
          </button>
        </div>
      </div>
    </div>
  );
}
