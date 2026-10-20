import type { SignalSource } from "../../api/types";

interface Props {
  text: string | null;
  manifestations?: string[] | null;
  primarySource: SignalSource | null;
}

const NOT_FOUND_RE = /^не указано в источнике\.?$/i;
const NOT_CONFIRMED = "В найденных источниках применение не подтверждено.";

export default function CaseExamples({ text, manifestations = null, primarySource }: Props) {
  const facts = manifestations ?? (text && !NOT_FOUND_RE.test(text.trim()) ? [text] : []);
  if (manifestations === null && !text) return null;

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
        {facts.length === 0 ? (
          <p>{NOT_CONFIRMED}</p>
        ) : (
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
