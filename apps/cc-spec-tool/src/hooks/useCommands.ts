// hooks/useCommands.ts - Commands 管理 Hook

import { useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { CommandStatus, CommandsInstallResult } from "../types/commands";

export interface UseCommandsReturn {
    /** Commands 状态列表 */
    commands: CommandStatus[];
    /** 是否正在加载 */
    loading: boolean;
    /** 错误信息 */
    error: string | null;
    /** 内置 commands 版本 */
    version: string | null;
    /** 是否需要更新 */
    updateNeeded: boolean;
    /** 检查 commands 状态 */
    checkStatus: (projectPath: string) => Promise<void>;
    /** 安装 commands */
    installCommands: (projectPath: string, force?: boolean) => Promise<CommandsInstallResult | null>;
    /** 卸载 commands */
    uninstallCommands: (projectPath: string) => Promise<boolean>;
    /** 检查是否需要更新 */
    checkUpdateNeeded: (projectPath: string) => Promise<boolean>;
}

export function useCommands(): UseCommandsReturn {
    const [commands, setCommands] = useState<CommandStatus[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [version, setVersion] = useState<string | null>(null);
    const [updateNeeded, setUpdateNeeded] = useState(false);

    const checkStatus = useCallback(async (projectPath: string) => {
        setLoading(true);
        setError(null);
        try {
            const [statuses, ver] = await Promise.all([
                invoke<CommandStatus[]>("check_commands_status", { projectPath }),
                invoke<string>("get_commands_version"),
            ]);
            setCommands(statuses);
            setVersion(ver);

            // 检查是否有未安装或版本过旧的
            const needsUpdate = statuses.some(
                (s) => !s.installed || s.version !== ver
            );
            setUpdateNeeded(needsUpdate);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, []);

    const installCommands = useCallback(
        async (projectPath: string, force = false): Promise<CommandsInstallResult | null> => {
            setLoading(true);
            setError(null);
            try {
                const result = await invoke<CommandsInstallResult>("install_commands", {
                    projectPath,
                    force,
                });
                setCommands(result.commands);
                setUpdateNeeded(false);
                return result;
            } catch (e) {
                const msg = e instanceof Error ? e.message : String(e);
                setError(msg);
                return null;
            } finally {
                setLoading(false);
            }
        },
        []
    );

    const uninstallCommands = useCallback(async (projectPath: string): Promise<boolean> => {
        setLoading(true);
        setError(null);
        try {
            await invoke("uninstall_commands", { projectPath });
            // 刷新状态
            await checkStatus(projectPath);
            return true;
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            return false;
        } finally {
            setLoading(false);
        }
    }, [checkStatus]);

    const checkUpdateNeeded = useCallback(async (projectPath: string): Promise<boolean> => {
        try {
            const needed = await invoke<boolean>("check_commands_update_needed", {
                projectPath,
            });
            setUpdateNeeded(needed);
            return needed;
        } catch (e) {
            console.error("检查 commands 更新失败:", e);
            return false;
        }
    }, []);

    return {
        commands,
        loading,
        error,
        version,
        updateNeeded,
        checkStatus,
        installCommands,
        uninstallCommands,
        checkUpdateNeeded,
    };
}
