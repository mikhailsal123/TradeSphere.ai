"use client";

import React, {
    createContext,
    useCallback,
    useContext,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import type { TradeSphereTheme } from "../lib/browser-chrome";

export type { TradeSphereTheme };

type ThemeContextValue = {
    theme: TradeSphereTheme;
    setTheme: (t: TradeSphereTheme) => void;
    toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "tradesphere-theme";

function readStoredTheme(): TradeSphereTheme {
    if (typeof window === "undefined") return "dark";
    try {
        const v = localStorage.getItem(STORAGE_KEY);
        if (v === "light" || v === "dark") return v;
    } catch {
        /* ignore */
    }
    return "dark";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    const [theme, setThemeState] = useState<TradeSphereTheme>("dark");
    const skipThemeEffect = useRef(true);

    const applyDom = useCallback((t: TradeSphereTheme) => {
        const root = document.documentElement;
        root.classList.toggle("dark", t === "dark");
        root.dataset.theme = t;
        try {
            localStorage.setItem(STORAGE_KEY, t);
        } catch {
            /* ignore */
        }
        /* Browser chrome (theme-color + canvas) is applied in page.tsx for the active surface. */
    }, []);

    useLayoutEffect(() => {
        const t = readStoredTheme();
        setThemeState(t);
        applyDom(t);
        skipThemeEffect.current = true;
    }, [applyDom]);

    useLayoutEffect(() => {
        if (skipThemeEffect.current) {
            skipThemeEffect.current = false;
            return;
        }
        applyDom(theme);
    }, [theme, applyDom]);

    const setTheme = useCallback((t: TradeSphereTheme) => {
        setThemeState(t);
    }, []);

    const toggleTheme = useCallback(() => {
        setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
    }, []);

    const value = useMemo(
        () => ({ theme, setTheme, toggleTheme }),
        [theme, setTheme, toggleTheme]
    );

    return (
        <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
    );
}

export function useTradeSphereTheme() {
    const ctx = useContext(ThemeContext);
    if (!ctx) {
        throw new Error("useTradeSphereTheme must be used within ThemeProvider");
    }
    return ctx;
}
