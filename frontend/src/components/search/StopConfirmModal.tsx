interface Props {
  onConfirm: () => void;
  onCancel: () => void;
}

export default function StopConfirmContent({ onConfirm, onCancel }: Props) {
  return (
    <div className="max-w-110">
      <h3 className="text-[32px] mt-4 font-bold text-neutral-950">Остановить поиск?</h3>
      <p className="mt-4 text-base text-neutral-600">
        Анализ ещё не завершён. Если остановить поиск сейчас, текущий прогресс будет потерян.
      </p>
      <div className="mt-8 mb-2 flex justify-center gap-5">
        <button
          type="button"
          onClick={onConfirm}
          className="shrink-0 text-base whitespace-nowrap rounded-full border
             border-neutral-300 px-5 py-2.5 text-neutral-600 hover:bg-neutral-50 bg-neutral-200/20 glass-element
            text-md hover:cursor-pointer "
        >
          Остановить поиск
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="shrink-0 whitespace-nowrap rounded-full bg-primary px-5 py-2.5 text-base 
           text-white hover:bg-link-hover hover:cursor-pointer"
        >
          Продолжить поиск
        </button>
      </div>
    </div>
  );
}
