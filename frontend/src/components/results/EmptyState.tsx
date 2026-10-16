interface Props {
  queryText: string;
  onChangeQuery: () => void;
}

export default function EmptyState({ queryText, onChangeQuery }: Props) {
  return (
    <div className="rounded-xl bg-neutral-0 p-16 text-center shadow-sm">
      <h3 className="text-4xl font-bold text-neutral-950">Слабые сигналы не выявлены</h3>
      <p className="mx-auto mt-4 max-w-[70%] text-base text-neutral-500">
        По запросу «{queryText}» система обработала источники, но не обнаружила технологий,
        соответствующих критериям слабого сигнала.
      </p>
      <button
        type="button"
        onClick={onChangeQuery}
        className="mt-6 rounded-full bg-primary px-6 py-2.5 text-sm text-white hover:bg-link-hover hover:cursor-pointer"
      >
        Изменить запрос
      </button>
    </div>
  );
}
