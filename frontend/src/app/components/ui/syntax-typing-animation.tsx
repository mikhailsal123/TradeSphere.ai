"use client";

import { cn } from "@/lib/utils";
import { motion, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";

export type SyntaxToken = { text: string; className?: string };

type SyntaxTypingAnimationProps = {
    segments: SyntaxToken[];
    className?: string;
    duration?: number;
    delay?: number;
    startOnView?: boolean;
};

function renderHighlighted(segments: SyntaxToken[], charCount: number) {
    let remaining = charCount;
    const nodes: React.ReactNode[] = [];
    let key = 0;
    for (const seg of segments) {
        if (remaining <= 0) break;
        const take = Math.min(seg.text.length, remaining);
        if (take > 0) {
            const chunk = seg.text.slice(0, take);
            nodes.push(
                <span key={key++} className={seg.className}>
                    {chunk}
                </span>
            );
            remaining -= take;
        }
    }
    return nodes;
}

export function SyntaxTypingAnimation({
    segments,
    className,
    duration = 100,
    delay = 0,
    startOnView = false,
}: SyntaxTypingAnimationProps) {
    const fullText = segments.map((s) => s.text).join("");
    const [visibleCount, setVisibleCount] = useState(0);
    const [started, setStarted] = useState(false);
    const ref = useRef<HTMLDivElement | null>(null);
    const isInView = useInView(ref as React.RefObject<Element>, {
        amount: 0.3,
        once: true,
    });

    useEffect(() => {
        if (!startOnView) {
            const t = setTimeout(() => setStarted(true), delay);
            return () => clearTimeout(t);
        }
        if (!isInView) return;
        const t = setTimeout(() => setStarted(true), delay);
        return () => clearTimeout(t);
    }, [delay, startOnView, isInView]);

    useEffect(() => {
        if (!started) return;
        setVisibleCount(0);
        let i = 0;
        const id = setInterval(() => {
            if (i < fullText.length) {
                setVisibleCount(i + 1);
                i++;
            } else {
                clearInterval(id);
            }
        }, duration);
        return () => clearInterval(id);
    }, [started, fullText, duration]);

    return (
        <motion.div
            ref={ref}
            className={cn("whitespace-pre-wrap break-words", className)}
        >
            {renderHighlighted(segments, visibleCount)}
        </motion.div>
    );
}
