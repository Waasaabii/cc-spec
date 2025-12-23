// components/chat/TranslateButton.tsx - 翻译按钮组件

import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { Theme } from "../../types/viewer";

interface TranslateButtonProps {
    text: string;
    theme: Theme;
}

export function TranslateButton({ text, theme }: TranslateButtonProps) {
    const [isTranslating, setIsTranslating] = useState(false);
    const [translated, setTranslated] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showTranslated, setShowTranslated] = useState(false);

    const handleTranslate = async () => {
        if (translated) {
            setShowTranslated(!showTranslated);
            return;
        }

        setIsTranslating(true);
        setError(null);
        try {
            const result = await invoke<string>("translate_text", { text });
            setTranslated(result);
            setShowTranslated(true);
        } catch (err) {
            setError(String(err));
        } finally {
            setIsTranslating(false);
        }
    };

    const buttonClass = `
        inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium
        transition-colors cursor-pointer
        ${showTranslated
            ? theme === "dark"
                ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                : "bg-blue-100 text-blue-700 border border-blue-200"
            : theme === "dark"
            ? "text-slate-500 hover:text-slate-300 hover:bg-slate-700/50"
            : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
        }
    `;

    return (
        <div className="inline-flex items-center">
            <button
                onClick={handleTranslate}
                disabled={isTranslating}
                className={buttonClass}
                title={showTranslated ? "Show original" : "Translate to Chinese"}
            >
                {isTranslating ? (
                    <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                ) : (
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                    </svg>
                )}
                <span>{showTranslated ? "ZH" : "EN"}</span>
            </button>

            {error && (
                <span className={`ml-2 text-[10px] ${theme === "dark" ? "text-rose-400" : "text-rose-600"}`}>
                    {error.length > 30 ? error.slice(0, 30) + "..." : error}
                </span>
            )}
        </div>
    );
}

interface TranslatableTextProps {
    text: string;
    theme: Theme;
    className?: string;
}

export function TranslatableText({ text, theme, className = "" }: TranslatableTextProps) {
    const [translated, setTranslated] = useState<string | null>(null);
    const [showTranslated, setShowTranslated] = useState(false);
    const [isTranslating, setIsTranslating] = useState(false);

    const handleToggle = async () => {
        if (translated) {
            setShowTranslated(!showTranslated);
            return;
        }

        setIsTranslating(true);
        try {
            const result = await invoke<string>("translate_text", { text });
            setTranslated(result);
            setShowTranslated(true);
        } catch (err) {
            console.error("Translation failed:", err);
        } finally {
            setIsTranslating(false);
        }
    };

    return (
        <span className={`group relative ${className}`}>
            <span className={showTranslated ? "opacity-50" : ""}>
                {showTranslated && translated ? translated : text}
            </span>
            <button
                onClick={handleToggle}
                disabled={isTranslating}
                className={`
                    ml-1 opacity-0 group-hover:opacity-100 transition-opacity
                    inline-flex items-center justify-center w-4 h-4 rounded
                    ${theme === "dark" ? "hover:bg-slate-700" : "hover:bg-slate-200"}
                `}
                title={showTranslated ? "Show original" : "Translate"}
            >
                {isTranslating ? (
                    <span className="w-2 h-2 border border-current border-t-transparent rounded-full animate-spin" />
                ) : (
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                    </svg>
                )}
            </button>
        </span>
    );
}
