import { Link } from "react-router-dom";

import type { AnalystsResponse } from "../../api/types";
import SourceCard from "./SourceCard";

const PREVIEW_COUNT = 3;

interface Props {
  data: AnalystsResponse | undefined;
  allHref: string;
}

export default function AnalystReportsBlock({ data, allHref }: Props) {
  if (!data || data.scope === "none") return null;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-neutral-950 text-2xl [-webkit-text-stroke:0.4px_currentColor]">
          Оценки аналитиков <span className="text-primary text-base">{data.reports.length}</span>
        </h3>
        <Link to={allHref} className="text-base font-medium text-black-alpha hover:text-link-hover">
          Смотреть все
        </Link>
      </div>
      {data.scope === "topic" && (
        <p className="mt-2 text-sm text-neutral-500">
          Отчётов именно об этой технологии не найдено — показаны оценки по теме запроса.
        </p>
      )}
      <div className="mt-4 space-y-5">
        {data.reports.slice(0, PREVIEW_COUNT).map((report) => (
          <SourceCard key={report.feed_item_id} source={report} />
        ))}
      </div>
    </div>
  );
}
