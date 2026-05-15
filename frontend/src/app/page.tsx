"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { DM_Sans } from "next/font/google";
import { SyntaxTypingAnimation } from "./components/ui/syntax-typing-animation";
import { mainDemoSyntaxSegments } from "./main-demo-segments";
import { LandingCapabilityScroll } from "./components/landing-capability-scroll";
import { SiteFooter } from "./components/site-footer";
import { ThemeToggle } from "./components/theme-toggle";
import { useTradeSphereTheme } from "./providers";

function flaskIframeSrc(
    baseUrl: string,
    theme: "light" | "dark",
    path: string = "/",
): string {
    const base = baseUrl.trim().replace(/\/$/, "");
    if (!base) return "";
    const normalizedPath = path.startsWith("/") ? path : `/${path}`
    const target = `${base}${normalizedPath === "/" ? "" : normalizedPath}`;
    const sep = target.includes("?") ? "&" : "?";
    return `${target}${sep}embed=1&theme=${encodeURIComponent(theme)}`;
}

type PlatformView = "dashboard" | "studio" | "live_trading";

function flaskBackendBaseUrl(): string {
    if (process.env.NODE_ENV === "development") {
        return (
            process.env.NEXT_PUBLIC_FLASK_DEV_URL?.trim() ||
            "http://127.0.0.1:5002"
        );
    }
    return process.env.NEXT_PUBLIC_FLASK_BACKEND_URL?.trim() || "";
}

/** DM Sans — landing UI (tagline, CTA, rail); pairs cleanly with the script wordmark. */
const landingSans = DM_Sans({
    subsets: ["latin"],
    weight: ["300", "400", "500"],
});

/** Slightly longer than native `scrollIntoView(smooth)` (~400–600ms). */
const HEADLINE_SCROLL_DURATION_MS = 1200;

function easeInOutCubic(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

const MainPage = () => {
    const { theme } = useTradeSphereTheme();
    const [animationKey, setAnimationKey] = useState(0);
    const [showTradingPlatform, setShowTradingPlatform] = useState(false);
    const [iframeSrc, setIframeSrc] = useState("");
    const [activeView, setActiveView] = useState<PlatformView>("dashboard");
    const iframeRef = useRef<HTMLIFrameElement>(null);
    const headlineScrollGen = useRef(0);

    const pushThemeToIframe = useCallback(() => {
        const w = iframeRef.current?.contentWindow;
        if (w) {
            w.postMessage({ type: "tradesphere-theme", theme }, "*");
        }
    }, [theme]);

    const navigateTo = useCallback(
        (view: PlatformView, opts?: { invite?: boolean }) => {
            const backendBase = flaskBackendBaseUrl();
            const path =
                view === "studio"
                    ? "/strategy_studio"
                    : view === "live_trading"
                        ? "/live_trading"
                        : "/";
            const base = flaskIframeSrc(backendBase, theme, path);
            if (!base) {
                setActiveView(view);
                return;
            }
            // Append a per-click nonce so React always sees a new src string,
            // even when the iframe DOM is already on this path because the
            // user got there via an in-iframe link (Open Studio / back arrow).
            // Without this, React would shallow-compare the same string and
            // skip re-applying `src`, leaving the iframe stuck on the wrong
            // page. Flask ignores `_n`.
            //
            // `invite=1` is added ONLY when launching the dashboard from the
            // landing page — never for header taps or in-iframe links. The
            // dashboard reads this query to decide whether to show Teeby's
            // greeting bubble (we want it to greet the user on first arrival
            // from the landing, not on every navigation).
            const sep = base.includes("?") ? "&" : "?";
            const tail = opts?.invite ? `&invite=1` : "";
            setIframeSrc(`${base}${sep}_n=${Date.now()}${tail}`);
            setActiveView(view);
        },
        [theme],
    );

    const handleLaunchPlatform = () => {
        navigateTo("dashboard", { invite: true });
        setShowTradingPlatform(true);
    };

    const scrollToCapabilityHeadline = useCallback(() => {
        const el = document.getElementById("landing-capability-heading");
        if (!el) return;
        const reduce =
            typeof window !== "undefined" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (reduce) {
            el.scrollIntoView({ behavior: "auto", block: "start" });
            return;
        }

        headlineScrollGen.current += 1;
        const gen = headlineScrollGen.current;

        const marginTop = parseFloat(getComputedStyle(el).scrollMarginTop) || 0;
        const startY = window.scrollY;
        const rect = el.getBoundingClientRect();
        const rawEnd = startY + rect.top - marginTop;
        const maxScroll = Math.max(
            0,
            document.documentElement.scrollHeight - window.innerHeight,
        );
        const endY = Math.max(0, Math.min(rawEnd, maxScroll));
        const delta = endY - startY;
        if (Math.abs(delta) < 2) return;

        const t0 = performance.now();

        const tick = (now: number) => {
            if (headlineScrollGen.current !== gen) return;
            const elapsed = now - t0;
            const t = Math.min(1, elapsed / HEADLINE_SCROLL_DURATION_MS);
            const eased = easeInOutCubic(t);
            window.scrollTo(0, startY + delta * eased);
            if (t < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }, []);

    useEffect(() => {
        const interval = setInterval(() => {
            setAnimationKey((prev) => prev + 1);
        }, 16000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (!showTradingPlatform) return;
        pushThemeToIframe();
    }, [theme, showTradingPlatform, pushThemeToIframe]);

    // The Flask pages postMessage their identity on every load (incl. in-iframe
    // link clicks like the dashboard's "Open Studio" or the studio's back
    // arrow), so the top nav can stay in sync without us round-tripping
    // through `navigateTo`.
    useEffect(() => {
        const onMessage = (e: MessageEvent) => {
            const d = e.data;
            if (d && d.type === "tradesphere-landing-home") {
                setShowTradingPlatform(false);
                queueMicrotask(() => {
                    document.getElementById("top")?.scrollIntoView({
                        behavior: "smooth",
                        block: "start",
                    });
                });
                return;
            }
            if (
                d &&
                d.type === "tradesphere-view" &&
                (d.view === "dashboard" ||
                    d.view === "studio" ||
                    d.view === "live_trading")
            ) {
                setActiveView(d.view);
            }
        };
        window.addEventListener("message", onMessage);
        return () => window.removeEventListener("message", onMessage);
    }, []);

    const executeBtnStyle =
        theme === "dark"
            ? {
                  background:
                      "linear-gradient(black, black) padding-box, linear-gradient(90deg, #96ebbf, #96ebbf, #96ebbf, #96ebbf) border-box",
              }
            : {
                  background:
                      "linear-gradient(#96ebbf, #96ebbf) padding-box, linear-gradient(90deg, #96ebbf, #96ebbf, #96ebbf, #96ebbf) border-box",
              };

    const shellBg = showTradingPlatform
        ? theme === "dark"
            ? "bg-[#141417] text-zinc-100"
            : "bg-white text-slate-900"
        : "bg-transparent";

    return (
        <div
            className={`min-h-screen transition-colors duration-300 ${shellBg} ${
                showTradingPlatform ? "font-sans" : landingSans.className
            }`}
        >
            <ThemeToggle
                className={
                    showTradingPlatform
                        ? "fixed right-5 top-[1.25rem] z-50 sm:top-[1.75rem] md:top-[2rem]"
                        : "fixed right-5 top-5 z-50"
                }
            />

            {!showTradingPlatform ? (
                <>
                    <section id="top" className="relative min-h-[100dvh] overflow-hidden">
                        {/* Solid page fill; upper band is covered by the rounded video. */}
                        <div
                            className={`pointer-events-none absolute inset-0 z-0 ${
                                theme === "dark" ? "bg-[#0c0c0f]" : "bg-white"
                            }`}
                            aria-hidden
                        />
                        <div
                            className="absolute left-[calc(0.75rem-0.6rem)] right-[calc(0.75rem-0.6rem)] top-2 z-0 h-[90dvh] max-h-[90dvh] overflow-hidden rounded-2xl sm:left-[calc(1rem-0.6rem)] sm:right-[calc(1rem-0.6rem)] sm:top-3 sm:rounded-3xl md:left-[calc(1.25rem-0.6rem)] md:right-[calc(1.25rem-0.6rem)]"
                        >
                            <video
                                className="pointer-events-none h-full w-full object-cover"
                                autoPlay
                                muted
                                loop
                                playsInline
                                preload="auto"
                                aria-hidden
                            >
                                <source
                                    src="/media/landing-background-loop.mp4"
                                    type="video/mp4"
                                />
                            </video>
                            <div
                                className={`pointer-events-none absolute inset-0 ${
                                    theme === "dark"
                                        ? "bg-gradient-to-b from-black/60 via-black/45 to-black/65"
                                        : "bg-gradient-to-b from-black/20 via-black/10 to-black/25"
                                }`}
                                aria-hidden
                            />
                            <div className="pointer-events-none absolute left-3 top-3 z-10 sm:left-4 sm:top-4 md:left-5 md:top-5">
                                <img
                                    src="/media/tradesphere-logo.png?v=3"
                                    alt="TradeSphere"
                                    className="block h-12 w-auto select-none drop-shadow-md sm:h-14 md:h-16"
                                    draggable={false}
                                />
                            </div>
                        </div>
                        {/* Hero: lorem + CTA (left), code (right); tagline sits inside video frame above footer. */}
                        <div
                            className={`pointer-events-none absolute left-[calc(0.75rem-0.6rem)] right-[calc(0.75rem-0.6rem)] top-2 z-10 flex h-[90dvh] max-h-[90dvh] flex-col rounded-2xl sm:left-[calc(1rem-0.6rem)] sm:right-[calc(1rem-0.6rem)] sm:top-3 sm:rounded-3xl md:left-[calc(1.25rem-0.6rem)] md:right-[calc(1.25rem-0.6rem)]`}
                        >
                            <div className="flex min-h-0 flex-1 translate-y-7 flex-col justify-center gap-10 px-4 py-6 sm:gap-12 sm:px-5 sm:py-8 lg:flex-row lg:items-center lg:justify-between lg:gap-8 lg:px-8 lg:py-4">
                                <div className="pointer-events-auto flex min-h-0 w-full max-w-md translate-x-2 -translate-y-2 flex-col items-stretch justify-center self-center text-left sm:translate-x-3 sm:-translate-y-3 sm:ml-8 md:translate-x-4 lg:max-w-lg lg:flex-1 lg:-translate-y-5 lg:self-auto lg:pl-8 lg:ml-16">
                                    <div className="translate-y-2 space-y-3 sm:translate-y-3">
                                        <h1 className="text-[1.725rem] font-bold leading-[1.15] tracking-tight text-white drop-shadow-sm sm:text-[2.15625rem] md:text-[2.5875rem]">
                                            Portfolio Strategy Lab that suits your needs
                                        </h1>
                                        <p className="text-[1.00625rem] font-light leading-relaxed text-white/90 sm:text-[1.0925rem]">
                                            Seamlessly build, execute, and refine trading strategies that earn your
                                            confidence before a dollar is on the line.
                                        </p>
                                    </div>
                                    <div className="mt-6 flex w-full translate-y-4 justify-center sm:mt-7 sm:translate-y-5">
                                        <button
                                            type="button"
                                            onClick={handleLaunchPlatform}
                                            className={`execute-trades-btn cursor-pointer rounded-full border-2 border-transparent px-10 py-3.5 text-lg font-light tracking-[0.06em] transition-all duration-200 shadow-lg hover:shadow-xl ${
                                                theme === "dark"
                                                    ? "text-white shadow-[#96ebbf]/55"
                                                    : "text-[#0a3d24] shadow-[#96ebbf]/45"
                                            }`}
                                            style={executeBtnStyle}
                                        >
                                            <span className="relative z-10">Execute Trades</span>
                                        </button>
                                    </div>
                                </div>
                                <div className="pointer-events-auto flex min-h-0 w-full translate-x-2 flex-col items-end justify-center self-center -translate-y-2 sm:translate-x-3 sm:-translate-y-3 md:translate-x-4 lg:mt-0 lg:flex-1 lg:-translate-y-5 lg:pr-1 xl:pr-3">
                                    <div
                                        className={`flex h-56 w-full max-w-3xl translate-y-2 shrink-0 flex-col overflow-hidden rounded-xl border font-mono shadow-2xl backdrop-blur-md sm:h-60 sm:translate-y-3 md:h-64 lg:ml-auto ${
                                            theme === "dark"
                                                ? "border-white/10 bg-zinc-950/50"
                                                : "border-white/60 bg-white/80"
                                        }`}
                                    >
                                        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-6 sm:px-8 sm:py-8">
                                            <SyntaxTypingAnimation
                                                key={animationKey}
                                                segments={mainDemoSyntaxSegments}
                                                className={`ts-syntax-typing text-left font-mono text-sm md:text-base ${theme === "dark" ? "text-slate-200" : "text-zinc-800"}`}
                                                duration={110}
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="pointer-events-auto shrink-0 translate-y-14 px-4 pb-8 pt-5 sm:translate-y-[4.25rem] sm:pb-10 sm:pt-7">
                                <div className="pointer-events-none mx-auto flex max-w-3xl translate-y-2 items-center gap-4 sm:translate-y-2.5 sm:gap-6">
                                    <div
                                        className={`h-px min-w-[2rem] flex-1 ${
                                            theme === "dark"
                                                ? "bg-gradient-to-r from-transparent via-[#96ebbf]/55 to-[#96ebbf]/40"
                                                : "bg-gradient-to-r from-transparent via-[#96ebbf]/65 to-[#96ebbf]/45"
                                        }`}
                                        aria-hidden
                                    />
                                    <p className="tradesphere-brand-shimmer shrink-0 text-center text-xl font-light leading-snug tracking-[-0.01em] sm:text-2xl md:text-3xl">
                                        Become your own Hedge Fund
                                    </p>
                                    <div
                                        className={`h-px min-w-[2rem] flex-1 ${
                                            theme === "dark"
                                                ? "bg-gradient-to-l from-transparent via-[#96ebbf]/55 to-[#96ebbf]/40"
                                                : "bg-gradient-to-l from-transparent via-[#96ebbf]/65 to-[#96ebbf]/45"
                                        }`}
                                        aria-hidden
                                    />
                                </div>
                                <div className="mt-3.5 flex justify-center sm:mt-4.5">
                                    <button
                                        type="button"
                                        onClick={scrollToCapabilityHeadline}
                                        aria-label="Scroll to: Build, test, and ship strategies"
                                        className={`group flex h-12 w-12 shrink-0 items-center justify-center rounded-full border backdrop-blur-sm transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#96ebbf]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent sm:h-14 sm:w-14 ${
                                            theme === "dark"
                                                ? "border-white/25 bg-black/30 text-white hover:border-[#96ebbf]/55 hover:bg-[#96ebbf]/15"
                                                : "border-white/55 bg-white/25 text-slate-900 hover:border-[#96ebbf]/70 hover:bg-white/45"
                                        }`}
                                    >
                                        <svg
                                            className="h-5 w-5 transition-transform duration-300 group-hover:translate-y-0.5 motion-reduce:group-hover:translate-y-0 sm:h-6 sm:w-6"
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            strokeWidth="2"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            aria-hidden
                                        >
                                            <path d="M12 5v12" />
                                            <path d="M8 14l4 4 4-4" />
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </section>

                    <LandingCapabilityScroll theme={theme} />

                    <SiteFooter />
                </>
            ) : (
                <div className="flex h-screen flex-col">
                        <div
                            className={`relative flex min-h-[5rem] items-center justify-end border-b pb-3 pr-20 backdrop-blur-md sm:min-h-[6rem] md:min-h-[6.75rem] ${
                            theme === "dark"
                                ? "border-[#96ebbf]/60 bg-[#141417]/95 text-zinc-100"
                                : "border-[#96ebbf]/60 bg-white/95 text-slate-800"
                        }`}
                    >
                        <button
                            type="button"
                            onClick={() => setShowTradingPlatform(false)}
                            aria-label="Return to main page"
                            title="Return to main page"
                            className="group absolute left-[0.9rem] top-[1.25rem] z-20 flex cursor-pointer items-center rounded-md p-0 transition-transform duration-150 hover:scale-[1.02] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#96ebbf]/60 sm:left-[1.4rem] sm:top-[1.75rem] md:left-[1.9rem] md:top-[2rem]"
                        >
                            <img
                                src="/media/tradesphere-logo.png?v=3"
                                alt="TradeSphere — back to main page"
                                className="block h-12 w-auto select-none drop-shadow-md transition-opacity duration-150 group-hover:opacity-90 sm:h-14 md:h-16"
                                draggable={false}
                            />
                        </button>
                        <nav
                            aria-label="Site navigation"
                            className="absolute left-1/2 top-[calc(1.25rem+1.5rem)] z-10 hidden -translate-x-1/2 -translate-y-1/2 items-center gap-5 text-[0.95rem] font-normal tracking-tight sm:flex sm:top-[calc(1.75rem+1.75rem)] md:top-[calc(2rem+2rem)]"
                        >
                            <button
                                type="button"
                                onClick={() => navigateTo("dashboard")}
                                aria-current={activeView === "dashboard" ? "page" : undefined}
                                className={`cursor-pointer transition-colors duration-150 hover:text-[#96ebbf] ${
                                    activeView === "dashboard"
                                        ? "text-[#96ebbf]"
                                        : theme === "dark"
                                            ? "text-zinc-300/85"
                                            : "text-slate-600/85"
                                }`}
                            >
                                Dashboard
                            </button>
                            <span aria-hidden className={theme === "dark" ? "text-zinc-600" : "text-slate-300"}>
                                ·
                            </span>
                            <button
                                type="button"
                                onClick={() => navigateTo("studio")}
                                aria-current={activeView === "studio" ? "page" : undefined}
                                className={`cursor-pointer transition-colors duration-150 hover:text-[#96ebbf] ${
                                    activeView === "studio"
                                        ? "text-[#96ebbf]"
                                        : theme === "dark"
                                            ? "text-zinc-300/85"
                                            : "text-slate-600/85"
                                }`}
                            >
                                Studio
                            </button>
                            <span aria-hidden className={theme === "dark" ? "text-zinc-600" : "text-slate-300"}>
                                ·
                            </span>
                            <button
                                type="button"
                                onClick={() => navigateTo("live_trading")}
                                aria-current={activeView === "live_trading" ? "page" : undefined}
                                className={`cursor-pointer transition-colors duration-150 hover:text-[#96ebbf] ${
                                    activeView === "live_trading"
                                        ? "text-[#96ebbf]"
                                        : theme === "dark"
                                            ? "text-zinc-300/85"
                                            : "text-slate-600/85"
                                }`}
                            >
                                Live Trading
                            </button>
                            <span aria-hidden className={theme === "dark" ? "text-zinc-600" : "text-slate-300"}>
                                ·
                            </span>
                            <button
                                type="button"
                                onClick={() => setShowTradingPlatform(false)}
                                className={`cursor-pointer transition-colors duration-150 hover:text-[#96ebbf] ${
                                    theme === "dark" ? "text-zinc-300/85" : "text-slate-600/85"
                                }`}
                            >
                                About
                            </button>
                            <span aria-hidden className={theme === "dark" ? "text-zinc-600" : "text-slate-300"}>
                                ·
                            </span>
                            <a
                                href="mailto:michael.saleev@example.com"
                                className={`transition-colors duration-150 hover:text-[#96ebbf] ${
                                    theme === "dark" ? "text-zinc-300/85" : "text-slate-600/85"
                                }`}
                            >
                                Contact
                            </a>
                        </nav>
                    </div>

                    <div
                        className={`flex min-h-0 flex-1 basis-0 flex-col ${theme === "dark" ? "bg-[#141417]" : "bg-white"}`}
                    >
                        {iframeSrc ? (
                            <div className="relative min-h-0 flex-1 basis-0">
                                <iframe
                                    ref={iframeRef}
                                    src={iframeSrc}
                                    onLoad={pushThemeToIframe}
                                    className="absolute inset-0 h-full w-full border-0 align-top"
                                    title="TradeSphere"
                                    sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-top-navigation allow-modals"
                                />
                            </div>
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
