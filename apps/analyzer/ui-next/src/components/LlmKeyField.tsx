"use client";

import { useEffect, useRef, useState } from "react";
import { KeyRound } from "lucide-react";
import { LLM_CHANGED, readRemember, writeRemember } from "@/lib/llmChoice";

/** "••••••••ab12": never show more than the last four characters. */
function mask(key: string): string {
  return key.length >= 12 ? `••••••••${key.slice(-4)}` : "••••••••";
}

/**
 * API key input that does not keep the key on screen.
 *
 * Once a key is set the field collapses to a masked chip (Replace / Remove); the
 * stored value is never put back into an input. The key lives for this browser
 * session unless the visitor ticks "Remember on this device".
 */
export default function LlmKeyField({
  id,
  value,
  onChange,
  disabled,
  className,
}: {
  id: string;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const [focused, setFocused] = useState(false);
  const [remember, setRemember] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setRemember(readRemember());
    const sync = () => setRemember(readRemember());
    window.addEventListener(LLM_CHANGED, sync);
    return () => window.removeEventListener(LLM_CHANGED, sync);
  }, []);

  const showChip = Boolean(value) && !focused;

  return (
    <div className="flex flex-col gap-2">
      {showChip ? (
        <div className="flex max-w-sm items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          <KeyRound className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="font-mono" aria-label="A key is set">
            {mask(value)}
          </span>
          <span className="ml-auto flex gap-3 text-xs">
            <button
              type="button"
              disabled={disabled}
              className="underline hover:no-underline disabled:opacity-50"
              onClick={() => {
                onChange("");
                setFocused(true);
                setTimeout(() => inputRef.current?.focus(), 0);
              }}
            >
              Replace
            </button>
            <button
              type="button"
              disabled={disabled}
              className="underline hover:no-underline disabled:opacity-50"
              onClick={() => onChange("")}
            >
              Remove
            </button>
          </span>
        </div>
      ) : (
        <input
          id={id}
          ref={inputRef}
          type="password"
          autoComplete="new-password"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value.trim())}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          disabled={disabled}
          placeholder="sk-…"
          className={
            className ??
            "w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 outline-none focus:border-sky-600"
          }
        />
      )}
      <label className="flex max-w-md items-start gap-2 text-xs text-slate-600">
        <input
          type="checkbox"
          checked={remember}
          onChange={(event) => {
            setRemember(event.target.checked);
            writeRemember(event.target.checked);
          }}
          className="mt-0.5"
        />
        <span>
          Remember on this device. Off (default): the key is dropped when you close this tab.
        </span>
      </label>
    </div>
  );
}
