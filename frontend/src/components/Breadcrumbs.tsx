import { Link } from "react-router-dom";

interface Crumb {
  label: string;
  to?: string;
}

export default function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="flex flex-wrap items-center gap-1 text-sm text-neutral-500">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <span className="text-neutral-400">/</span>}
          {item.to ? (
            <Link to={item.to} className="hover:text-link">
              {item.label}
            </Link>
          ) : (
            <span className="text-neutral-900">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
