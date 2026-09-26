import type { Signal } from "../../api/types";
import { CloseIcon } from "../icons";

interface Props {
  signal: Signal;
  onClose: () => void;
}

export default function ConfidenceModal({ signal, onClose }: Props) {
  const pct = Math.round(signal.score * 100);
  const predictors = signal.explanation.key_predictors ?? [];
  const summary =
    signal.status === "included"
      ? "Вместе эти признаки указывают на раннюю стадию развития — до сформированного рынка и массового внедрения."
      : `Модель посчитала эти признаки более характерными для «${signal.explanation.predicted_class ?? "зрелой технологии"}», чем для зарождающегося сигнала.`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="animate-fade-in relative mx-4 w-full max-w-lg rounded-2xl bg-neutral-0 p-8 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute right-5 top-5 text-neutral-400 hover:text-neutral-900"
        >
          <CloseIcon />
        </button>
        <h3 className="text-xl font-bold text-neutral-950">Как определяется оценка?</h3>
        <p className="mt-3 text-sm leading-relaxed text-neutral-700">
          {pct}% — это степень уверенности модели в том, что технология соответствует признакам
          слабого сигнала. Это не оценка качества или зрелости самой технологии.
        </p>
        {predictors.length > 0 && (
          <>
            <h4 className="mt-5 font-bold text-neutral-950">Что влияет на оценку</h4>
            <ul className="mt-2 space-y-1 text-sm text-neutral-700">
              {predictors.map((p) => (
                <li key={p}>• {p}</li>
              ))}
            </ul>
          </>
        )}
        <div className="mt-5 rounded-xl bg-neutral-50 p-4 text-sm text-neutral-600">{summary}</div>
      </div>
    </div>
  );
}
