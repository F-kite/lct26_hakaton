import ArrowRightBoldIcon from '@iconify-react/ep/arrow-right-bold';
import Search from "@iconify-react/famicons/search";
import X from "@iconify-react/bi/x";
import { useState } from "react";

interface SearchInputProps {
  size?: "lg" | "sm";
  defaultValue?: string;
  placeholder?: string;
  onSubmit: (query: string) => void;
}

export default function SearchInput({
  size = "lg",
  defaultValue = "",
  placeholder = "Например, технологии в ИИ",
  onSubmit,
}: SearchInputProps) {
  const [value, setValue] = useState(defaultValue);
  const [focused, setFocused] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed) onSubmit(trimmed);
  };

  const isLg = size === "lg";
  const hasValue = value.length > 0;
  const showClear = !focused && hasValue;
  const showMutedArrow = focused && !hasValue;
  const buttonSize = "h-12 w-12";

  return (
    <form
      onSubmit={handleSubmit}
      className={`relative flex items-center rounded-full transition-shadow  glass-card glass-border-[4.5px] h-16 pl-6 pr-2`} 
    >
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className={`flex-1 bg-transparent outline-none text-neutral-950 placeholder:text-neutral-500 ${
          isLg ? "text-lg" : "text-base"
        }`}
      />

      {showClear ? (
        <button
          type="button"
          aria-label="Очистить"
          onClick={() => setValue("")}
          className={`flex items-center justify-center rounded-full text-black-alpha transition-colors hover:cursor-pointer ${buttonSize}`}
        >
          <X className="h-6 w-6" />
        </button>
      ) : (
        <button
          type="submit"
          aria-label="Найти"
          onMouseDown={(e) => e.preventDefault()}
          className={`flex items-center justify-center rounded-full transition-colors hover:cursor-pointer ${buttonSize} ${
            showMutedArrow
              ? "bg-muted-15 text-white"
              : "bg-primary text-white hover:bg-link-hover active:bg-pressed"
          }`}
        >
          {focused ? <ArrowRightBoldIcon className="h-5 w-5" /> : <Search className="h-5 w-5" />}
        </button>
      )}
    </form>
  );
}
