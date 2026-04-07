"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Dancing_Script, Newsreader } from "next/font/google";
import { SyntaxTypingAnimation } from "./components/ui/syntax-typing-animation";
import { mainDemoSyntaxSegments } from "./main-demo-segments";
import { ThemeToggle } from "./components/theme-toggle";
import { useTradeSphereTheme } from "./providers";

function flaskIframeSrc(baseUrl: string, theme: "light" | "dark"): string {
    const base = baseUrl.trim().replace(/\/$/, "");
    if (!base) return "";
    const sep = base.includes("?") ? "&" : "?";
    return `${base}${sep}embed=1&theme=${encodeURIComponent(theme)}`;
}

function flaskBackendBaseUrl(): string {
    if (process.env.NODE_ENV === "development") {
        return (
            process.env.NEXT_PUBLIC_FLASK_DEV_URL?.trim() ||
            "http://127.0.0.1:5002"
        );
    }
    return process.env.NEXT_PUBLIC_FLASK_BACKEND_URL?.trim() || "";
}

const wallStreetTagline = Newsreader({
    subsets: ["latin"],
    weight: ["600", "700", "800"],
});

const tradeSphereScript = Dancing_Script({
    subsets: ["latin"],
    weight: ["600", "700"],
});

/** Logo palette: forest → emerald → lime (same in light & dark). */
const tradeSphereBrandWordmark =
    "bg-[linear-gradient(105deg,#1B4F32,#2ECC71,#ADFF2F,#D4EF22,#2ECC71,#1B4F32)] bg-clip-text text-transparent drop-shadow-[0_0_28px_rgba(46,204,113,0.45)]";

const MainPage = () => {
    const { theme } = useTradeSphereTheme();
    const [animationKey, setAnimationKey] = useState(0);
    const [showTradingPlatform, setShowTradingPlatform] = useState(false);
    const [iframeSrc, setIframeSrc] = useState("");
    const iframeRef = useRef<HTMLIFrameElement>(null);

    const pushThemeToIframe = useCallback(() => {
        const w = iframeRef.current?.contentWindow;
        if (w) {
            w.postMessage({ type: "tradesphere-theme", theme }, "*");
        }
    }, [theme]);

    const handleLaunchPlatform = () => {
        const backendBase = flaskBackendBaseUrl();
        setIframeSrc(flaskIframeSrc(backendBase, theme));
        setShowTradingPlatform(true);
    };

    useEffect(() => {
        const interval = setInterval(() => {
            setAnimationKey((prev) => prev + 1);
        }, 13000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (!showTradingPlatform) return;
        pushThemeToIframe();
    }, [theme, showTradingPlatform, pushThemeToIframe]);

    const executeBtnStyle =
        theme === "dark"
            ? {
                  background:
                      "linear-gradient(black, black) padding-box, linear-gradient(90deg, #1B4F32, #2ECC71, #ADFF2F, #D4EF22) border-box",
              }
            : {
                  background:
                      "linear-gradient(#ffffff, #ffffff) padding-box, linear-gradient(90deg, #1B4F32, #2ECC71, #ADFF2F, #D4EF22) border-box",
              };

    const shellBg = showTradingPlatform
        ? theme === "dark"
            ? "bg-black text-zinc-100"
            : "bg-gradient-to-b from-sky-100/90 via-white to-indigo-50 text-slate-900"
        : "bg-transparent";

    return (
        <div
            className={`min-h-screen font-sans transition-colors duration-300 ${shellBg}`}
        >
            <ThemeToggle className="fixed right-5 top-5 z-50" />

            {!showTradingPlatform ? (
                <>
                    <div className="pointer-events-none fixed inset-0 z-0">
                        <video
                            className="h-full w-full object-cover"
                            autoPlay
                            muted
                            loop
                            playsInline
                            preload="auto"
                            aria-hidden
                        >
                            <source src="/animate-2.mp4" type="video/mp4" />
                        </video>
                        <div
                            className={`absolute inset-0 ${
                                theme === "dark"
                                    ? "bg-gradient-to-b from-black/60 via-black/45 to-black/65"
                                    : "bg-gradient-to-b from-black/20 via-black/10 to-black/25"
                            }`}
                            aria-hidden
                        />
                    </div>
                    <div
                        className={`relative z-10 flex w-full flex-col items-center px-4 pt-10 pb-36 sm:pt-12 sm:pb-40 md:pt-14 md:pb-44 ${
                            theme === "dark" ? "text-zinc-100" : "text-slate-900"
                        }`}
                    >
                        <div className="mb-8 w-full text-center">
                            <h1
                                className={`mb-3 text-6xl leading-none sm:mb-4 sm:text-7xl md:mb-5 md:text-7xl lg:text-8xl ${tradeSphereScript.className} ${tradeSphereBrandWordmark}`}
                            >
                                TradeSphere
                            </h1>
                            <p
                                className={`${wallStreetTagline.className} tradesphere-brand-shimmer mb-6 text-xl font-semibold italic leading-snug tracking-[0.06em] sm:text-2xl`}
                            >
                                Become your own Hedge Fund
                            </p>
                            <button
                                type="button"
                                onClick={handleLaunchPlatform}
                                className={`${wallStreetTagline.className} execute-trades-btn rounded-full border-2 border-transparent px-10 py-3.5 text-lg font-semibold italic tracking-[0.06em] transition-all duration-200 ${
                                    theme === "dark"
                                        ? "text-white shadow-lg shadow-emerald-900/40 hover:shadow-xl hover:shadow-emerald-500/25"
                                        : "text-emerald-950 shadow-lg shadow-emerald-500/30 hover:shadow-xl hover:shadow-lime-400/25"
                                }`}
                                style={executeBtnStyle}
                            >
                                Execute Trades
                            </button>
                        </div>
                        <div
                            className={`w-full max-w-3xl overflow-hidden rounded-xl border px-6 py-6 font-mono shadow-2xl backdrop-blur-md sm:px-8 sm:py-8 ${
                                theme === "dark"
                                    ? "border-white/10 bg-zinc-950/50"
                                    : "border-white/60 bg-white/80"
                            }`}
                        >
                            <SyntaxTypingAnimation
                                key={animationKey}
                                segments={mainDemoSyntaxSegments}
                                className={`ts-syntax-typing text-left font-mono text-sm md:text-base ${theme === "dark" ? "text-slate-200" : "text-zinc-800"}`}
                                duration={140}
                            />
                        </div>
                    </div>

                    {/*
                      LANDING_SLOGAN_RAIL — fixed to viewport bottom (never flex-pushed).
                      Revert: remove this block & optional pb-* on main column above.
                    */}
                    <div
                        className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-3 sm:pb-6"
                        data-landing-slogan-rail
                    >
                        <div className="mx-auto w-full max-w-3xl px-2">
                            <div className="flex items-center gap-4 sm:gap-6">
                                <div
                                    className="h-px min-w-[2rem] flex-1 bg-gradient-to-r from-transparent via-emerald-400/50 to-lime-300/35"
                                    aria-hidden
                                />
                                <p
                                    className={`${wallStreetTagline.className} shrink-0 text-center text-xl font-semibold italic leading-snug tracking-[0.06em] text-white sm:text-2xl md:text-3xl`}
                                >
                                    Trading Made Simple
                                </p>
                                <div
                                    className="h-px min-w-[2rem] flex-1 bg-gradient-to-l from-transparent via-emerald-400/50 to-lime-300/35"
                                    aria-hidden
                                />
                            </div>
                        </div>
                    </div>
                </>
            ) : (
                <div className="flex h-screen flex-col">
                    <div
                        className={`flex items-center border-b px-6 py-4 backdrop-blur-md ${
                            theme === "dark"
                                ? "border-zinc-900 bg-black/95 text-zinc-100"
                                : "border-sky-200/90 bg-white/95 text-slate-800"
                        }`}
                    >
                        <div className="flex items-center gap-4">
                            <button
                                type="button"
                                onClick={() => setShowTradingPlatform(false)}
                                className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
                                    theme === "dark"
                                        ? "border-zinc-800 bg-zinc-950 text-zinc-200 hover:border-zinc-600 hover:bg-zinc-900 hover:text-white"
                                        : "border-sky-300 bg-white text-slate-700 shadow-sm hover:border-sky-500 hover:bg-sky-50"
                                }`}
                            >
                                <svg
                                    className="h-5 w-5"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M15 19l-7-7 7-7"
                                    />
                                </svg>
                                <span>Back to main page</span>
                            </button>
                            <h2
                                className={`text-2xl sm:text-3xl ${tradeSphereScript.className} ${tradeSphereBrandWordmark}`}
                            >
                                TradeSphere
                            </h2>
                        </div>
                    </div>

                    <div
                        className={`flex-1 ${theme === "dark" ? "bg-black" : "bg-sky-50/90"}`}
                    >
                        {iframeSrc ? (
                            <iframe
                                ref={iframeRef}
                                src={iframeSrc}
                                onLoad={pushThemeToIframe}
                                className="h-full w-full border-0"
                                title="TradeSphere"
                                sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-top-navigation allow-modals"
                            />
                        ) : (
                            <div
                                className={`flex h-full items-center justify-center p-8 text-center ${theme === "dark" ? "text-zinc-400" : "text-slate-600"}`}
                            >
                                <div
                                    className={`max-w-md rounded-lg border p-6 text-sm ${
                                        theme === "dark"
                                            ? "border-zinc-800 bg-zinc-950 text-zinc-300"
                                            : "border-sky-400/50 bg-sky-100 text-slate-800"
                                    }`}
                                >
                                    <p
                                        className={
                                            theme === "dark"
                                                ? "font-medium text-zinc-100"
                                                : "font-medium text-slate-800"
                                        }
                                    >
                                        Trading platform URL not configured
                                    </p>
                                    <p className="mt-2">
                                        On Render, set{" "}
                                        <code
                                            className={`rounded px-1 py-0.5 text-xs ${
                                                theme === "dark"
                                                    ? "bg-zinc-900 text-cyan-200"
                                                    : "bg-white text-slate-800"
                                            }`}
                                        >
                                            NEXT_PUBLIC_FLASK_BACKEND_URL
                                        </code>{" "}
                                        on the <strong>Next.js</strong> service
                                        to your <strong>Flask</strong> service URL
                                        (build again after changing). For local
                                        production builds, run{" "}
                                        <code
                                            className={`rounded px-1 py-0.5 text-xs ${
                                                theme === "dark"
                                                    ? "bg-zinc-900 text-cyan-200"
                                                    : "bg-white text-slate-800"
                                            }`}
                                        >
                                            ./set_next_iframe_backend_url.sh
                                        </code>
                                        .
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default MainPage;
