// components/chat/RenderContent.tsx - 内容渲染组件（支持代码块）

import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import Ansi from "ansi-to-react";
import { parseCodeBlocks } from "../../utils/parse";
import type { StreamLine, Theme } from "../../types/viewer";

interface RenderContentProps {
    content: string;
    type: StreamLine["type"];
    theme: Theme;
}

export function RenderContent({ content, type, theme }: RenderContentProps) {
    if (type !== "agent" && type !== "user") {
        return <Ansi>{content}</Ansi>;
    }

    const blocks = parseCodeBlocks(content);
    const codeBlockClass = theme === "dark"
        ? "my-2 border border-slate-700 bg-[#0f1419] p-2 text-xs rounded-sm"
        : "my-2 border border-slate-200 bg-white/90 p-2 text-xs rounded-sm";
    const syntaxTheme = theme === "dark" ? oneDark : oneLight;

    return (
        <>
            {blocks.map((block, i) =>
                block.type === "code" ? (
                    <div key={i} className={codeBlockClass}>
                        <SyntaxHighlighter
                            language={block.lang || "text"}
                            style={syntaxTheme}
                            customStyle={{ margin: 0, padding: 0, background: "transparent" }}
                        >
                            {block.content}
                        </SyntaxHighlighter>
                    </div>
                ) : (
                    <span key={i}>{block.content}</span>
                )
            )}
        </>
    );
}
