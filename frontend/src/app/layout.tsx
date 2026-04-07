import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { ThemeProvider } from "./providers";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
});

const geistMono = Geist_Mono({
    variable: "--font-geist-mono",
    subsets: ["latin"],
});

export const metadata: Metadata = {
    title: "TradeSphere.ai",
    description: "AI-Powered Trading Platform - Become Your Own Hedge Fund",
};

const themeBootScript = `(function(){try{var t=localStorage.getItem("tradesphere-theme")||"dark";if(t!=="light"&&t!=="dark")t="dark";document.documentElement.classList.toggle("dark",t==="dark");document.documentElement.dataset.theme=t;}catch(e){}})();`;

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body
                className={`${geistSans.variable} ${geistMono.variable} ${geistSans.className} min-h-screen antialiased`}
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