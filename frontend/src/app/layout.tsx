import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { THEME_BOOT_SCRIPT } from "../lib/browser-chrome";
import { ThemeProvider } from "./providers";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
});

export const metadata: Metadata = {
    title: "TradeSphere.ai",
    description: "AI-Powered Trading Platform",
};

const themeBootScript = THEME_BOOT_SCRIPT;

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body
                className={`${geistSans.variable} ${geistSans.className} min-h-screen antialiased`}
                suppressHydrationWarning
            >
                <Script
                    id="tradesphere-theme-boot"
                    strategy="beforeInteractive"
                    dangerouslySetInnerHTML={{ __html: themeBootScript }}
                />
                <ThemeProvider>{children}</ThemeProvider>
            </body>
        </html>
    );
}