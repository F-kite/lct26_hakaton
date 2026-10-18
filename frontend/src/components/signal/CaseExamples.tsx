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
    <div className="rounded-xl p-5 glass-card glass-border-8">
      <h3 className="font-bold text-neutral-950  [-webkit-text-stroke:0.4px_currentColor]">Где это уже проявилось:</h3>
      <div className="mt-3 rounded-lg bg-neutral-100/50 border border-neutral-200 p-3 text-sm leading-relaxed text-neutral-600">
        {primarySource && (
          <a
            href={primarySource.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-neutral-950 hover:text-link-hover"
          >
            {primarySource.source_name}
          </a>
        )}
        <p>
          {displayText}
        </p>
      </div>

    </div>
  );
}
