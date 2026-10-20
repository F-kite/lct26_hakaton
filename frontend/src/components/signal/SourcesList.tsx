import { useMemo } from "react";
import { Link } from "react-router-dom";

import type { SignalSource } from "../../api/types";
import { isAssessment } from "../../lib/sourceLabels";
import SourceCard from "./SourceCard";

const PREVIEW_COUNT = 3;

export function sortSources<T extends SignalSource>(sources: T[]): T[] {
  return [...sources].sort(
    (a, b) =>
      Number(b.is_primary) - Number(a.is_primary) ||
      new Date(b.published_at ?? 0).getTime() - new Date(a.published_at ?? 0).getTime(),
  );
}

interface SourcesListProps {
  sources: SignalSource[];
  allSourcesHref: string;
}

export default function SourcesList({ sources, allSourcesHref }: SourcesListProps) {
  const sorted = useMemo(() => sortSources(sources.filter((s) => !isAssessment(s.relation))), [sources]);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-neutral-950 text-2xl [-webkit-text-stroke:0.4px_currentColor]">
          Источники и подтверждения <span className="text-primary text-base">{sorted.length}</span>
        </h3>
        {sorted.length > 0 && (
          <Link
            to={allSourcesHref}
            className="text-base font-medium text-black-alpha hover:text-link-hover"
          >
            Смотреть все
          </Link>
        )}
      </div>

      <div className="mt-4 space-y-5">
        {sorted.slice(0, PREVIEW_COUNT).map((source) => (
          <SourceCard key={source.feed_item_id} source={source} />
        ))}
      </div>
    </div>
  );
}
