// hooks/useSidecar.ts - cc-spec sidecar 调用 Hook

import { useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";

export interface SidecarResult {
    success: boolean;
    stdout: string;
    stderr: string;
    exit_code: number | null;
}

export interface StreamCallbacks {
    onStdout?: (line: string) => void;
    onStderr?: (line: string) => void;
    onDone?: (exitCode: number) => void;
}

export function useSidecar() {
    const [loading, setLoading] = useState(false);
    const [available, setAvailable] = useState<boolean | null>(null);
    const [version, setVersion] = useState<string | null>(null);

    // 检查 sidecar 是否可用
    const checkAvailable = useCallback(async () => {
        try {
            const result = await invoke<boolean>("check_sidecar_available");
            setAvailable(result);
            return result;
        } catch {
            setAvailable(false);
            return false;
        }
    }, []);

    // 获取版本
    const getVersion = useCallback(async () => {
        try {
            const result = await invoke<string>("get_ccspec_version");
            setVersion(result);
            return result;
        } catch {
            setVersion(null);
            return null;
        }
    }, []);

    // 执行命令（同步）
    const runCommand = useCallback(
        async (
            args: string[],
            workingDir?: string
        ): Promise<SidecarResult> => {
            setLoading(true);
            try {
                const result = await invoke<SidecarResult>("run_ccspec_command", {
                    args,
                    workingDir,
                });
                return result;
            } finally {
                setLoading(false);
            }
        },
        []
    );

    // 执行命令（流式）
    const runStream = useCallback(
        async (
            args: string[],
            callbacks: StreamCallbacks,
            workingDir?: string
        ): Promise<void> => {
            const eventId = crypto.randomUUID();
            const unlisteners: UnlistenFn[] = [];

            try {
                setLoading(true);

                // 监听 stdout
                if (callbacks.onStdout) {
                    const unlisten = await listen<string>(
                        `ccspec:stdout:${eventId}`,
                        (event) => callbacks.onStdout?.(event.payload)
                    );
                    unlisteners.push(unlisten);
                }

                // 监听 stderr
                if (callbacks.onStderr) {
                    const unlisten = await listen<string>(
                        `ccspec:stderr:${eventId}`,
                        (event) => callbacks.onStderr?.(event.payload)
                    );
                    unlisteners.push(unlisten);
                }

                // 监听完成事件
                const donePromise = new Promise<number>((resolve) => {
                    listen<number>(`ccspec:done:${eventId}`, (event) => {
                        callbacks.onDone?.(event.payload);
                        resolve(event.payload);
                    }).then((unlisten) => unlisteners.push(unlisten));
                });

                // 启动流式命令
                await invoke("run_ccspec_stream", {
                    args,
                    workingDir,
                    eventId,
                });

                // 等待完成
                await donePromise;
            } finally {
                // 清理监听器
                for (const unlisten of unlisteners) {
                    unlisten();
                }
                setLoading(false);
            }
        },
        []
    );

    // 便捷方法：初始化项目
    const init = useCallback(
        async (projectPath: string, levels?: string[]) => {
            const args = ["init", "--project", projectPath];
            if (levels && levels.length > 0) {
                args.push("--levels", levels.join(","));
            }
            return runCommand(args);
        },
        [runCommand]
    );

    // 便捷方法：列出变更
    const listChanges = useCallback(
        async (projectPath: string) => {
            return runCommand(["list", "--project", projectPath]);
        },
        [runCommand]
    );

    // 便捷方法：查看变更详情
    const gotoChange = useCallback(
        async (projectPath: string, changeId: string) => {
            return runCommand(["goto", changeId, "--project", projectPath]);
        },
        [runCommand]
    );

    return {
        // 状态
        loading,
        available,
        version,
        // 基础方法
        checkAvailable,
        getVersion,
        runCommand,
        runStream,
        // 便捷方法
        init,
        listChanges,
        gotoChange,
    };
}
