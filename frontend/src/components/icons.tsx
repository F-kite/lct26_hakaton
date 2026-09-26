// Простые line-иконки взамен unicode-глифов (▤ ☑ ▽ ⟳ ⚲) — те рендерились
// произвольным системным шрифтом и не совпадали с иконками из макета.

type IconProps = { className?: string };

export function SearchIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <circle cx="11" cy="11" r="7" strokeLinecap="round" />
      <path d="M21 21l-4.35-4.35" strokeLinecap="round" />
    </svg>
  );
}

export function ArrowRightIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function RefreshIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path
        d="M4 10a8 8 0 0 1 14.5-4.5M20 14a8 8 0 0 1-14.5 4.5"
        strokeLinecap="round"
      />
      <path d="M18.5 3.5v4h-4M5.5 20.5v-4h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function FilterIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M4 5h16l-6 7.5V19l-4 2v-8.5L4 5Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function DocumentCheckIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M7 3h7l4 4v14H7V3Z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9.5 13.5l2 2 3.5-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BarChartIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M6 20V11M12 20V4M18 20v-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ChecklistIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8.5 12.5l2 2 4.5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ReportIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M7 3h7l4 4v14H7V3Z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 12h5M10 16h5M10 8h2" strokeLinecap="round" />
    </svg>
  );
}

export function CheckIcon({ className = "h-3 w-3" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}>
      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function CloseIcon({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
    </svg>
  );
}
