"use client";

import { useState } from "react";
import { useTradeSphereTheme } from "../providers";

/**
 * Expressive theme toggle.
 *
 * The two icons (sun + moon) are layered on top of each other and cross-fade with
 * a springy rotate-and-scale transition. A warm amber tint blooms behind the sun
 * and a deep indigo tint behind the moon. On every click we also fire a one-shot
 * brand-green ripple "ping" so the act of toggling feels tactile rather than instant.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
    const { theme, toggleTheme } = useTradeSphereTheme();
    const [pulse, setPulse] = useState(false);
    const isDark = theme === "dark";

    const handleClick = () => {
        toggleTheme();
        // Replay the ripple each click by remounting (key on the pulse counter).
        setPulse(false);
        requestAnimationFrame(() => {
            setPulse(true);
            window.setTimeout(() => setPulse(false), 750);
        });
    };

    return (
        <button
            type="button"
            onClick={handleClick}
            className={`group inline-flex h-11 w-11 cursor-pointer items-center justify-center overflow-hidden rounded-full border shadow-md transition-all duration-300 ease-out hover:scale-110 hover:shadow-lg active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#96ebbf]/60 ${
                isDark
                    ? "border-slate-600 bg-slate-900/90 text-amber-100 hover:border-cyan-500/40"
                    : "border-slate-200 bg-white text-amber-600 hover:border-sky-300/70"
            } ${className}`}
            aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            title={isDark ? "Light mode" : "Dark mode"}
        >
            {/* Warm sun / cool moon tint behind the icon — fades when the theme flips. */}
            <span
                aria-hidden
                className={`absolute inset-0 transition-opacity duration-500 ease-out ${
                    isDark
                        ? "bg-gradient-to-br from-indigo-900/55 via-slate-900/0 to-cyan-900/35 opacity-100"
                        : "bg-gradient-to-br from-amber-200/70 via-orange-100/0 to-amber-300/55 opacity-100"
                }`}
            />

            {/* One-shot brand-green ripple on click. Two staggered rings for depth. */}
            {pulse && (
                <>
                    <span
                        aria-hidden
                        className="pointer-events-none absolute inset-0 rounded-full bg-[#96ebbf]/35 animate-ping"
                    />
                    <span
                        aria-hidden
                        className="pointer-events-none absolute inset-1.5 rounded-full bg-[#96ebbf]/25 animate-ping"
                        style={{ animationDelay: "90ms" }}
                    />
                </>
            )}

            {/* SUN — visible in light mode, rotates/scales/fades out when going dark. */}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                aria-hidden
                className={`absolute h-5 w-5 transition-[transform,opacity] duration-[550ms] ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                    isDark
                        ? "-rotate-90 scale-50 opacity-0"
                        : "rotate-0 scale-100 opacity-100"
                }`}
            >
                <circle cx="12" cy="12" r="4" strokeWidth={2} />
                <g strokeWidth={2} strokeLinecap="round">
                    <path d="M12 3v1.6" />
                    <path d="M12 19.4V21" />
                    <path d="M3 12h1.6" />
                    <path d="M19.4 12H21" />
                    <path d="M5.5 5.5l1.13 1.13" />
                    <path d="M17.37 17.37l1.13 1.13" />
                    <path d="M18.5 5.5l-1.13 1.13" />
                    <path d="M6.63 17.37L5.5 18.5" />
                </g>
            </svg>

            {/* MOON — visible in dark mode, comes in with the opposite rotation. */}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                aria-hidden
                className={`absolute h-5 w-5 transition-[transform,opacity] duration-[550ms] ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                    isDark
                        ? "rotate-0 scale-100 opacity-100"
                        : "rotate-90 scale-50 opacity-0"
                }`}
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                />
                {/* Tiny twinkling stars — only visible while the moon is shown. */}
                <circle cx="6" cy="7" r="0.55" fill="currentColor" stroke="none" className="ts-toggle-star" />
                <circle cx="17" cy="5" r="0.7" fill="currentColor" stroke="none" className="ts-toggle-star ts-toggle-star--delay-1" />
                <circle cx="18.5" cy="13" r="0.5" fill="currentColor" stroke="none" className="ts-toggle-star ts-toggle-star--delay-2" />
            </svg>
        </button>
    );
}
