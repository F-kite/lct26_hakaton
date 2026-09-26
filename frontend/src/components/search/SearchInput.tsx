import { useState } from "react";

import { ArrowRightIcon, CloseIcon, SearchIcon } from "../icons";

interface SearchInputProps {
  size?: "lg" | "sm";
  defaultValue?: string;
  placeholder?: string;
  onSubmit: (query: string) => void;
}

/**
 * Поле поиска — состояния default/focus/typing/typed из макета
 * (frontend_mockup/State_field_*.png). Автокомплит в макете — декоративный
 * плейсхолдер ("Value" x4, без реального источника данных) — намеренно не
 * реализован, показывать выдуманные подсказки не стали.
 */
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

  return (
    <form
      onSubmit={handleSubmit}
      className={`relative flex items-center rounded-full bg-neutral-0 shadow-sm ring-1 transition-shadow ${
        focused ? "ring-primary/40" : "ring-neutral-300"
      } ${isLg ? "h-16 pl-6 pr-2" : "h-11 pl-4 pr-1.5"}`}
    >
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className={`flex-1 bg-transparent outline-none text-neutral-900 placeholder:text-neutral-500 ${
          isLg ? "text-lg" : "text-sm"
        }`}
      />
      {value && (
        <button
          type="button"
          aria-label="Очистить"
          onClick={() => setValue("")}
          className="mr-1 flex items-center justify-center text-neutral-500 hover:text-neutral-900 px-1"
        >
          <CloseIcon />
        </button>
      )}
      <button
        type="submit"
        aria-label="Найти"
        className={`flex items-center justify-center rounded-full bg-primary text-white hover:bg-link-hover active:bg-pressed transition-colors ${
          isLg ? "h-12 w-12" : "h-8 w-8"
        }`}
      >
        {value ? <ArrowRightIcon className="h-5 w-5" /> : <SearchIcon className="h-5 w-5" />}
      </button>
    </form>
  );
}
