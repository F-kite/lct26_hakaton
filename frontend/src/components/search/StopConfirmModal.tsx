interface Props {
  onConfirm: () => void;
  onCancel: () => void;
}

export default function StopConfirmModal({ onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/40 backdrop-blur-sm">
      <div className="animate-fade-in mx-4 w-full max-w-sm rounded-2xl bg-neutral-0 p-7 text-center shadow-xl">
        <h3 className="text-xl font-bold text-neutral-950">Остановить поиск?</h3>
        <p className="mt-2 text-sm text-neutral-600">
          Анализ ещё не завершён. Если остановить поиск сейчас, текущий прогресс будет потерян.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-full border border-neutral-300 px-5 py-2.5 text-sm text-neutral-700 hover:bg-neutral-50"
          >
            Остановить поиск
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full bg-primary px-5 py-2.5 text-sm text-white hover:bg-link-hover"
          >
            Продолжить поиск
          </button>
        </div>
      </div>
    </div>
  );
}
