import { SearchIcon } from "./Icons";

/** A search box that reads as one: the icon, a stronger edge than the filters beside it, and room to type. */
export function SearchField({ value, onChange, placeholder, label, className = "" }: {
  value: string; onChange: (value: string) => void; placeholder: string; label: string; className?: string;
}) {
  return (
    <label className={`relative min-w-0 ${className}`}>
      <SearchIcon size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        aria-label={label} className="vt-input vt-search h-9 w-full pl-9 text-sm" />
    </label>
  );
}
