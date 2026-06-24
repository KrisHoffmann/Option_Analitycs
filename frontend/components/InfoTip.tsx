"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { GLOSSARY, type GlossaryKey } from "@/lib/glossary";

const POP_WIDTH = 280;
const MARGIN = 8;

/** A small "i" info trigger that opens a non-modal popover explaining one term.
 *  Reused across all three views. Accessible: real <button>, aria-describedby,
 *  opens on hover/focus, closes on leave/blur/Escape/outside-click/scroll. The
 *  popover is position:fixed so the chain table's overflow can't clip it. */
export default function InfoTip({ k }: { k: GlossaryKey }) {
  const entry = GLOSSARY[k];
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, above: false });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const id = `infotip-${k}`;

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    let left = r.left + r.width / 2 - POP_WIDTH / 2;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - POP_WIDTH - MARGIN));
    // Flip above the icon when there isn't room below it.
    const above = window.innerHeight - r.bottom < 170 && r.top > 170;
    const top = above ? r.top - 6 : r.bottom + 6;
    setCoords({ top, left, above });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onScroll = () => setOpen(false);
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || popRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <span className="infotip">
      <button
        ref={triggerRef}
        type="button"
        className="infotip-trigger"
        aria-label={`What is ${entry.term}?`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.3" />
          <circle cx="8" cy="4.6" r="0.95" fill="currentColor" />
          <rect x="7.2" y="6.7" width="1.6" height="5" rx="0.8" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <div
          ref={popRef}
          id={id}
          role="tooltip"
          className={`infotip-pop${coords.above ? " above" : ""}`}
          style={{ top: coords.top, left: coords.left, width: POP_WIDTH }}
        >
          <span className="infotip-term">{entry.term}</span>
          <span className="infotip-body">{entry.body}</span>
        </div>
      )}
    </span>
  );
}
