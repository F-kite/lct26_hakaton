import { useState } from "react";

import type { Signal } from "../../api/types";
import ConfidenceModal from "./ConfidenceModal";

export default function ConfidencePanel({ signal }: { signal: Signal }) {
  const [showModal, setShowModal] = useState(false);
  const pct = Math.round(signal.score * 100);
  const predicted = signal.explanation.predicted_class;
  const isWeakSignalClass = predicted === "слабый сигнал";

  const description =
    signal.status === "excluded"
      ? isWeakSignalClass
        ? `Модель распознала признаки слабого сигнала, но с уверенностью всего ${pct}% — ниже порога, необходимого для попадания в выдачу.`
        : `Модель отнесла технологию к классу «${predicted ?? "не слабым сигналом"}» и не считает её слабым сигналом.`
      : pct >= 80
        ? "Высокая уверенность в классификации как слабого сигнала."
        : "Умеренная уверенность в классификации как слабого сигнала.";

  return (
    <div className="sticky top-6 rounded-xl p-5 glass-card glass-border-8 [--glass-fill:var(--color-primary-50)]">
      <div className="text-sm text-neutral-700">Уверенность модели</div>
      <div className="mt-4 font-display text-4xl font-bold text-neutral-950">{pct}%</div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-neutral-0">
        <div
          className={`h-full ${signal.status === "included" ? "bg-success" : "bg-error"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-3 text-sm text-neutral-950">{description}</p>
      <button
        type="button"
        onClick={() => setShowModal(true)}
        className="mt-4 text-sm font-medium text-link hover:text-link-hover hover:cursor-pointer"
      >
        Как определяется оценка?
      </button>
      {showModal && <ConfidenceModal signal={signal} onClose={() => setShowModal(false)} />}
    </div>
  );
}
