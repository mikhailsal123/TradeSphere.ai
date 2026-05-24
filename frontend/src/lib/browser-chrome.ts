export type TradeSphereTheme = "light" | "dark";

export type BrowserChromeSurface = "landing" | "platform";

/**
 * Single source of truth for surfaces shown at the top of the viewport.
 * Landing = hero + capability section + footer canvas (#070708 / zinc-50).
 * Platform = page canvas behind panels (#0c0c0f / #eef2f7); nav strip stays #1f1f26 in page.tsx.
 */
export const TS_SURFACE_COLORS: Record<
    TradeSphereTheme,
    Record<BrowserChromeSurface, string>
> = {
    light: {
        landing: "#fafafa",
        platform: "#eef2f7",
    },
    dark: {
        landing: "#070708",
        platform: "#0c0c0f",
    },
};

export function browserChromeColor(
    theme: TradeSphereTheme,
    surface: BrowserChromeSurface,
): string {
    return TS_SURFACE_COLORS[theme][surface];
}

export function applyBrowserChrome(
    theme: TradeSphereTheme,
    surface: BrowserChromeSurface,
): void {
    if (typeof document === "undefined") return;

    const color = browserChromeColor(theme, surface);
    const root = document.documentElement;

    root.dataset.theme = theme;
    root.dataset.chromeSurface = surface;
    root.style.colorScheme = theme;

    let themeMeta = document.querySelector(
        'meta[name="theme-color"]',
    ) as HTMLMetaElement | null;
    if (!themeMeta) {
        themeMeta = document.createElement("meta");
        themeMeta.name = "theme-color";
        document.head.appendChild(themeMeta);
    }
    themeMeta.content = color;
}

/** Theme + landing chrome before React — keep in sync with TS_SURFACE_COLORS. */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem("tradesphere-theme")||"dark";if(t!=="light"&&t!=="dark")t="dark";var chrome={light:{landing:"#fafafa",platform:"#eef2f7"},dark:{landing:"#070708",platform:"#0c0c0f"}};var c=chrome[t].landing;document.documentElement.classList.toggle("dark",t==="dark");document.documentElement.dataset.theme=t;document.documentElement.dataset.chromeSurface="landing";document.documentElement.style.colorScheme=t;var m=document.querySelector('meta[name="theme-color"]');if(!m){m=document.createElement("meta");m.name="theme-color";document.head.appendChild(m);}m.content=c;}catch(e){}})();`;
