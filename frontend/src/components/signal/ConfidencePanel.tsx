import { useState } from "react";

import type { Signal } from "../../api/types";
import ConfidenceModal from "./ConfidenceModal";

export default function ConfidencePanel({ signal }: { signal: Signal }) {
  const [showModal, setShowModal] = useState(false);
  const pct = Math.round(signal.score * 100);
  const predicted = signal.explanation.predicted_class;

  const description =
    signal.status === "excluded"
      ? `Модель считает технологию «${predicted ?? "не слабым сигналом"}» и не относит её к слабым сигналам.`
      : pct >= 80
        ? "Высокая уверенность в классификации как слабого сигнала."
        : "Умеренная уверенность в классификации как слабого сигнала.";

  return (
    <div className="sticky top-6 rounded-2xl bg-primary-50 p-5">
      <div className="text-sm text-neutral-700">Уверенность модели</div>
      <div className="mt-1 font-display text-4xl font-bold text-neutral-950">{pct}%</div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-neutral-0">
        <div
          className={`h-full ${signal.status === "included" ? "bg-success" : "bg-error"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-3 text-sm text-neutral-600">{description}</p>
      <button
        type="button"
        onClick={() => setShowModal(true)}
        className="mt-2 text-sm font-medium text-link hover:text-link-hover"
      >
        Как определяется оценка?
      </button>
      {showModal && <ConfidenceModal signal={signal} onClose={() => setShowModal(false)} />}
    </div>
  );
}
