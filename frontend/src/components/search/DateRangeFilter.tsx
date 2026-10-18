export interface DateRange {
  dateFrom: string; // YYYY-MM-DD, "" — без границы
  dateTo: string;
}

interface DateRangeFilterProps {
  value: DateRange;
  onChange: (value: DateRange) => void;
}

function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function yearsAgo(years: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return isoDate(d);
}

const PRESETS = [
  { label: "Всё время", range: () => ({ dateFrom: "", dateTo: "" }) },
  { label: "Год", range: () => ({ dateFrom: yearsAgo(1), dateTo: isoDate(new Date()) }) },
  { label: "3 года", range: () => ({ dateFrom: yearsAgo(3), dateTo: isoDate(new Date()) }) },
  { label: "5 лет", range: () => ({ dateFrom: yearsAgo(5), dateTo: isoDate(new Date()) }) },
];

const inputClass =
  "rounded-full bg-neutral-0 px-4 py-2 text-sm text-neutral-900 ring-1 ring-neutral-300 outline-none focus:ring-primary";

export default function DateRangeFilter({ value, onChange }: DateRangeFilterProps) {
  const today = isoDate(new Date());
  const invalid = value.dateFrom !== "" && value.dateTo !== "" && value.dateFrom > value.dateTo;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex flex-wrap items-center justify-center gap-2 text-sm text-neutral-600">
        <span>Период публикаций:</span>
        {PRESETS.map(({ label, range }) => {
          const r = range();
          const active = r.dateFrom === value.dateFrom && r.dateTo === value.dateTo;
          return (
            <button
              key={label}
              type="button"
              onClick={() => onChange(r)}
              className={`rounded-full px-3 py-1 transition-colors hover:cursor-pointer ${
                active ? "bg-primary text-white" : "bg-neutral-0 text-neutral-700 ring-1 ring-neutral-300"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-center gap-2 text-sm text-neutral-600">
        <label className="flex items-center gap-2">
          С
          <input
            type="date"
            value={value.dateFrom}
            max={value.dateTo || today}
            onChange={(e) => onChange({ ...value, dateFrom: e.target.value })}
            className={inputClass}
          />
        </label>
        <label className="flex items-center gap-2">
          По
          <input
            type="date"
            value={value.dateTo}
            min={value.dateFrom || undefined}
            max={today}
            onChange={(e) => onChange({ ...value, dateTo: e.target.value })}
            className={inputClass}
          />
        </label>
      </div>

      {invalid && <p className="text-sm text-error">Дата «С» не может быть позже даты «По»</p>}
    </div>
  );
}

export function isValidRange({ dateFrom, dateTo }: DateRange): boolean {
  return !(dateFrom && dateTo && dateFrom > dateTo);
}
