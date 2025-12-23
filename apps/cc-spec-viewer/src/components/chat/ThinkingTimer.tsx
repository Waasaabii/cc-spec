// components/chat/ThinkingTimer.tsx - 思考中计时器组件

import { useEffect, useState } from "react";
import { fmtElapsedCompact } from "../../utils/format";

export function ThinkingTimer({ startTime }: { startTime?: number }) {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        if (!startTime) return;
        const interval = setInterval(() => {
            setElapsed(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);
        return () => clearInterval(interval);
    }, [startTime]);

    if (!startTime) return null;

    return (
        <span className="status-indicator font-mono text-[10px] bg-purple-500/15 px-2.5 py-0.5 rounded-full border border-purple-500/30 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(192,132,252,0.6)] animate-pulse"></span>
            <span className="thinking-shimmer">Working</span>
            <span className="text-purple-300 tabular-nums">{fmtElapsedCompact(elapsed)}</span>
        </span>
    );
}
