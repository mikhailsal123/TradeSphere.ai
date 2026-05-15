"use client";

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

type Step = {
    id: string;
    label: string;
    title: React.ReactNode;
    body: string;
};

const STEPS: Step[] = [
    {
        id: "allocate",
        label: "Allocate",
        title: (
            <>
                <span className="text-[#96ebbf]">Allocate</span> your portfolio
            </>
        ),
        body: "Set up your cash balance, trading frequency, and stock positions. Select the time interval that works best with your trading approach.",
    },
    {
        id: "simulate",
        label: "Simulate",
        title: (
            <>
                <span className="text-[#96ebbf]">Simulate</span> with rules or code
            </>
        ),
        body: "Run historical backtests with visual rules, or compile Python from Strategy Studio. Watch performance unfold on charts as the engine walks your strategy through real market data.",
    },
    {
        id: "analyze",
        label: "Analyze",
        title: (
            <>
                <span className="text-[#96ebbf]">Analyze</span> and refine
            </>
        ),
        body: "Stack results against benchmarks, inspect plots, and lean on AI-assisted commentary to find what worked, what broke, and what to tweak next—without another engineering sprint.",
    },
    {
        id: "launch",
        label: "Launch",
        title: (
            <>
                <span className="text-[#96ebbf]">Launch</span> when you are ready
            </>
        ),
        body: "Take the same stack from simulation to Live Trading: start a run, watch status, and stop cleanly—without relearning a separate system.",
    },
];

/**
 * Pick the last panel whose top has crossed an early activation threshold.
 * This lets the alternating layout swap before the next step is fully reached,
 * so the rail is already on the correct side as that step enters view.
 */
function pickActiveStepIndex(panels: HTMLDivElement[]): number {
    if (panels.length === 0) return 0;
    const activationLine = window.innerHeight * 0.55;
    let active = 0;

    for (let i = 0; i < panels.length; i++) {
        if (panels[i].getBoundingClientRect().top <= activationLine) {
            active = i;
        }
    }

    return active;
}

type LandingCapabilityScrollProps = {
    theme: "light" | "dark";
};

export function LandingCapabilityScroll({ theme }: LandingCapabilityScrollProps) {
    const [active, setActive] = useState(0);
    const stepRefs = useRef<(HTMLDivElement | null)[]>([]);

    const setRef = useCallback((el: HTMLDivElement | null, i: number) => {
        stepRefs.current[i] = el;
    }, []);

    const measureActive = useCallback(() => {
        const nodes = stepRefs.current.filter(Boolean) as HTMLDivElement[];
        if (nodes.length !== STEPS.length) return;
        const next = pickActiveStepIndex(nodes);
        setActive((prev) => (prev === next ? prev : next));
    }, []);

    useLayoutEffect(() => {
        const id = requestAnimationFrame(() => {
            measureActive();
        });
        return () => cancelAnimationFrame(id);
    }, [measureActive]);

    useEffect(() => {
        let raf = 0;
        const schedule = () => {
            if (raf) cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => {
                raf = 0;
                measureActive();
            });
        };
        schedule();
        window.addEventListener("scroll", schedule, { passive: true });
        window.addEventListener("resize", schedule);
        return () => {
            window.removeEventListener("scroll", schedule);
            window.removeEventListener("resize", schedule);
            if (raf) cancelAnimationFrame(raf);
        };
    }, [measureActive]);

    const isDark = theme === "dark";
    const sectionBg = isDark ? "bg-[#070708]" : "bg-zinc-50";
    const borderMuted = isDark ? "border-zinc-800/80" : "border-zinc-200";
    const eyebrow = isDark ? "text-zinc-500" : "text-zinc-500";
    const titleMuted = isDark ? "text-zinc-100" : "text-slate-900";
    const bodyMuted = isDark ? "text-zinc-400" : "text-slate-600";
    const railMuted = isDark ? "text-zinc-600" : "text-zinc-400";
    const railActive = "text-[#96ebbf]";
    const cardBg = isDark ? "bg-zinc-900/40" : "bg-white/80";
    const cardBorder = isDark ? "border-zinc-800/90" : "border-zinc-200/90";

    return (
        <section
            id="landing-capability-section"
            className={`relative scroll-mt-24 border-t ${borderMuted} ${sectionBg} px-4 py-16 sm:px-6 sm:py-20 md:py-24`}
            aria-labelledby="landing-capability-heading"
        >
            <div className="mx-auto max-w-6xl">
                <p className={`text-center text-xs font-medium uppercase tracking-[0.2em] ${eyebrow}`}>
                    What is TradeSphere?
                </p>
                <h2
                    id="landing-capability-heading"
                    className={`mx-auto mt-3 max-w-3xl scroll-mt-28 text-center text-2xl font-medium leading-snug tracking-tight sm:text-3xl md:text-[2rem] ${titleMuted}`}
                >
                    TradeSphere is a platform where you can write, test, and ship strategies with{" "}
                    <span className="text-[#96ebbf]">production-level quality</span>.
                </h2>

                <div className="mt-8 space-y-4 md:mt-10 md:space-y-0">
                    {STEPS.map((s, i) => {
                        const on = i === active;
                        const railOnRight = i % 2 === 1;

                        const rail = (
                            <ol
                                className={`flex flex-row gap-2 overflow-x-auto pb-1 md:flex-col md:gap-0 md:overflow-visible md:pb-0 ${railOnRight ? "md:items-end" : ""}`}
                            >
                                {STEPS.map((railStep, railIndex) => {
                                    const railIsActive = railIndex === active;
                                    return (
                                        <li key={railStep.id} className="shrink-0 md:shrink">
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    stepRefs.current[railIndex]?.scrollIntoView({
                                                        behavior: "smooth",
                                                        block: "center",
                                                    })
                                                }
                                                className={`flex w-full items-baseline gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-500 md:border-0 md:px-0 md:py-4 ${railOnRight ? "md:justify-end md:text-right" : ""} ${
                                                    railIsActive
                                                        ? `border-[#96ebbf]/35 bg-[#96ebbf]/[0.07] md:bg-transparent ${railActive}`
                                                        : `${isDark ? "border-zinc-800 bg-zinc-900/30" : "border-zinc-200 bg-white/60"} md:border-transparent md:bg-transparent ${railMuted} ${isDark ? "hover:text-zinc-300" : "hover:text-slate-700"}`
                                                } `}
                                            >
                                                <span
                                                    className={`font-mono text-sm tabular-nums transition-colors duration-500 ${
                                                        railIsActive ? railActive : ""
                                                    }`}
                                                >
                                                    {String(railIndex + 1).padStart(2, "0")}
                                                </span>
                                                <span className="text-sm font-medium tracking-tight">
                                                    {railStep.label}
                                                </span>
                                            </button>
                                            {railIndex < STEPS.length - 1 ? (
                                                <div
                                                    className={`hidden h-6 w-px md:block ${isDark ? "bg-zinc-800" : "bg-zinc-200"} ${railOnRight ? "ml-auto mr-5" : "ml-5"}`}
                                                    aria-hidden
                                                />
                                            ) : null}
                                        </li>
                                    );
                                })}
                            </ol>
                        );

                        return (
                            <div
                                key={s.id}
                                id={i === 0 ? "landing-step-allocate" : undefined}
                                ref={(el) => setRef(el, i)}
                                className="min-h-[min(56vh,420px)] scroll-mt-28 md:grid md:min-h-[58vh] md:grid-cols-12 md:gap-12 lg:gap-16"
                            >
                                <div
                                    className={`md:col-span-4 md:flex md:items-center ${railOnRight ? "md:order-2" : "md:order-1"}`}
                                >
                                    <div
                                        className={`transition-all duration-700 ease-out motion-reduce:transition-none ${
                                            on
                                                ? "translate-y-0 opacity-100"
                                                : "pointer-events-none translate-y-3 opacity-0"
                                        }`}
                                    >
                                        {rail}
                                    </div>
                                </div>

                                <div
                                    className={`mt-6 md:col-span-8 md:mt-0 md:flex md:items-center ${railOnRight ? "md:order-1" : "md:order-2"}`}
                                >
                                    <div
                                        className={`flex w-full max-w-2xl flex-col justify-center rounded-2xl border p-6 transition-all duration-700 motion-reduce:transition-none sm:p-8 md:min-h-[16rem] md:p-10 ${cardBorder} ${cardBg} ${
                                            on
                                                ? "translate-y-0 opacity-100 shadow-[0_0_0_1px_rgba(150,235,191,0.12)]"
                                                : `translate-y-3 opacity-40 motion-reduce:translate-y-0 motion-reduce:opacity-100 md:translate-y-4 md:opacity-35 motion-reduce:md:opacity-100 ${isDark ? "shadow-none" : "shadow-sm"}`
                                        }`}
                                    >
                                        <p
                                            className={`font-mono text-xs uppercase tracking-[0.18em] ${isDark ? "text-zinc-500" : "text-zinc-500"}`}
                                        >
                                            Step {i + 1}
                                        </p>
                                        <h3
                                            className={`mt-3 text-xl font-medium leading-snug tracking-tight sm:text-2xl md:text-[1.65rem] ${titleMuted}`}
                                        >
                                            {s.title}
                                        </h3>
                                        <p className={`mt-4 max-w-xl text-[0.95rem] font-light leading-relaxed sm:text-base ${bodyMuted}`}>
                                            {s.body}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
