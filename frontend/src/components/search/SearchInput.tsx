import ArrowRightBoldIcon from '@iconify-react/ep/arrow-right-bold';
import Search from "@iconify-react/famicons/search";
import X from "@iconify-react/bi/x";
import SearchThin from "@iconify-react/bi/search";
import RecentlyViewed from "@iconify-react/carbon/recently-viewed";
import { useMemo, useState } from "react";

import { SUGGESTIONS } from "../../data/suggestions";
import { findMatch, useSearchHistory } from "../../lib/history";
import Highlight from "./Highlight";

const RECENT_LIMIT = 5;
const HISTORY_MATCH_LIMIT = 3;
const TOTAL_LIMIT = 6;

interface Option {
  kind: "history" | "suggestion";
  text: string;
}

interface SearchInputProps {
  size?: "lg" | "sm";
  defaultValue?: string;
  placeholder?: string;
  inputRef?: React.Ref<HTMLInputElement>;
  onSubmit: (query: string) => void;
}

export default function SearchInput({
  size = "lg",
  defaultValue = "",
  placeholder = "Например, технологии в ИИ",
  inputRef,
  onSubmit,
}: SearchInputProps) {
  const [value, setValue] = useState(defaultValue);
  const [focused, setFocused] = useState(false);
  // список прячется после выбора варианта / Esc и снова открывается при вводе
  const [dismissed, setDismissed] = useState(false);
  const [active, setActive] = useState(-1);
  const history = useSearchHistory();

  const options = useMemo<Option[]>(() => {
    const seen = new Set<string>();
    const recent: string[] = [];
    for (const e of history.entries) {
      const key = e.query.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        recent.push(e.query);
      }
    }

    const input = value.trim();
    if (!input) {
      return recent.slice(0, RECENT_LIMIT).map((text) => ({ kind: "history", text }));
    }
    const lowered = input.toLowerCase();
    const fromHistory = recent
      .filter((q) => q.toLowerCase() !== lowered && findMatch(q, input) !== -1)
      .slice(0, HISTORY_MATCH_LIMIT)
      .map((text): Option => ({ kind: "history", text }));
    const fromSuggestions = SUGGESTIONS
      .filter((s) => !seen.has(s.toLowerCase()) && s.toLowerCase() !== lowered && findMatch(s, input) !== -1)
      .map((text): Option => ({ kind: "suggestion", text }));
    return [...fromHistory, ...fromSuggestions].slice(0, TOTAL_LIMIT);
  }, [history.entries, value]);

  const open = focused && !dismissed && options.length > 0;

  const choose = (text: string) => {
    setValue(text);
    setDismissed(true);
    setActive(-1);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (open && active >= 0) {
      choose(options[active].text);
      return;
    }
    const trimmed = value.trim();
    if (trimmed) {
      setDismissed(true);
      onSubmit(trimmed);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (e.key === "Escape") {
      setDismissed(true);
      setActive(-1);
    }
  };

  const isLg = size === "lg";
  const hasValue = value.length > 0;
  const showClear = !focused && hasValue;
  const showMutedArrow = focused && !hasValue;
  const buttonSize = "h-12 w-12";

  return (
    <div className="relative">
      {open && (
        <div
          role="listbox"
          className="absolute inset-x-0 top-0 z-20 rounded-4xl glass-element pt-19 pb-3 text-left"
        >
          {options.map((option, i) => {
            const Icon = option.kind === "history" ? RecentlyViewed : SearchThin;
            return (
              <button
                key={`${option.kind}:${option.text}`}
                type="button"
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(option.text)}
                className={`flex w-full items-center gap-3 px-6 py-2.5 text-left hover:cursor-pointer ${
                  isLg ? "text-base" : "text-sm"
                } ${i === active ? "bg-neutral-0/60" : ""}`}
              >
                <Icon className="h-4 w-4 shrink-0 text-neutral-500" />
                <Highlight text={option.text} input={value} />
              </button>
            );
          })}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className={`relative z-30 flex items-center rounded-full transition-shadow  glass-card glass-border-[4.5px] h-16 pl-6 pr-2`}
      >
        <input
          ref={inputRef}
          type="text"
          value={value}
          placeholder={placeholder}
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          onChange={(e) => {
            setValue(e.target.value);
            setDismissed(false);
            setActive(-1);
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            setFocused(true);
            setDismissed(false);
          }}
          onBlur={() => {
            setFocused(false);
            setActive(-1);
          }}
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
    </div>
  );
}
