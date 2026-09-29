import type { SignalSource } from "../../api/types";

interface Props {
  text: string | null;
  // Источник, чей текст реально стал этим кейс-примером (is_primary=true)
  primarySource: SignalSource | null;
}

// LLM пишет эту фразу буквально в текст case_example, когда в источнике нет факта применения технологии
const NOT_FOUND_RE = /^не указано в источнике\.?$/i;

export default function CaseExamples({ text, primarySource }: Props) {
  if (!text) return null;

  const displayText = NOT_FOUND_RE.test(text.trim())
    ? "В найденных источниках применение не подтверждено."
    : text;

  return (
    <div className="rounded-2xl bg-neutral-0 p-6 shadow-sm">
      <h3 className="font-bold text-neutral-950  [-webkit-text-stroke:0.4px_currentColor]">Где это уже проявилось</h3>
      <p className="mt-3 rounded-xl bg-neutral-50 p-4 text-sm leading-relaxed text-neutral-700">
        {displayText}
      </p>
      {primarySource && (
        <p className="mt-2 text-xs text-neutral-500">
          Источник:{" "}
          <a
            href={primarySource.url}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-link hover:text-link-hover"
          >
            {primarySource.source_name}
          </a>
        </p>
      )}
    </div>
  );
}
