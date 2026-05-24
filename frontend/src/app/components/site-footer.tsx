"use client";

import { useTradeSphereTheme } from "../providers";

/** Document-flow footer — sits at the end of the page layout (scroll to see). Same on landing and platform. */
export function SiteFooter() {
    const { theme } = useTradeSphereTheme();

    return (
        <footer
            className={`ts-site-footer relative z-20 flex w-full shrink-0 flex-col gap-4 border-t px-6 py-3 ${
                theme === "dark" ? "border-zinc-700/60" : "border-[#96ebbf]"
            }`}
            style={{ backgroundColor: "#070708" }}
            data-ts-site-footer
            data-landing-slogan-rail
        >
            <div className="flex w-full flex-row flex-wrap items-center gap-x-6 gap-y-3">
                <img
                    src="/media/tradesphere-logo.png?v=3"
                    alt="TradeSphere"
                    className="block h-10 w-auto shrink-0 select-none opacity-90 sm:h-12"
                    draggable={false}
                    loading="eager"
                    decoding="sync"
                />
                <nav
                    aria-label="Footer"
                    className="flex min-w-0 flex-1 flex-wrap items-center justify-center gap-x-3 gap-y-2 text-[0.62rem] font-light uppercase tracking-[0.14em] text-zinc-400/90 sm:text-[0.68rem]"
                >
                    <a href="#top" className="transition-colors duration-150 hover:text-[#96ebbf]">
                        Home
                    </a>
                    <span aria-hidden className="text-zinc-600">
                        ·
                    </span>
                    <a
                        href="mailto:michael.saleev@example.com"
                        className="transition-colors duration-150 hover:text-[#96ebbf]"
                    >
                        Contact
                    </a>
                    <span aria-hidden className="text-zinc-600">
                        ·
                    </span>
                    <a href="#top" className="transition-colors duration-150 hover:text-[#96ebbf]">
                        About
                    </a>
                </nav>
            </div>
            <p className="w-full text-left text-[0.62rem] font-light uppercase leading-snug tracking-[0.14em] text-zinc-400/90 sm:text-[0.68rem]">
                &copy; 2026 MICHAEL SALEEV. ALL RIGHTS RESERVED.
            </p>
        </footer>
    );
}
