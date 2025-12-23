// hooks/useSkills.ts - Skills 管理 Hook

import { useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { SkillStatus, SkillsInstallResult } from "../types/skills";

export interface UseSkillsReturn {
    /** Skills 状态列表 */
    skills: SkillStatus[];
    /** 是否正在加载 */
    loading: boolean;
    /** 错误信息 */
    error: string | null;
    /** 内置 skills 版本 */
    version: string | null;
    /** 是否需要更新 */
    updateNeeded: boolean;
    /** 检查 skills 状态 */
    checkStatus: (projectPath: string) => Promise<void>;
    /** 安装 skills */
    installSkills: (projectPath: string, force?: boolean) => Promise<SkillsInstallResult | null>;
    /** 卸载 skills */
    uninstallSkills: (projectPath: string) => Promise<boolean>;
    /** 检查是否需要更新 */
    checkUpdateNeeded: (projectPath: string) => Promise<boolean>;
}

export function useSkills(): UseSkillsReturn {
    const [skills, setSkills] = useState<SkillStatus[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [version, setVersion] = useState<string | null>(null);
    const [updateNeeded, setUpdateNeeded] = useState(false);

    const checkStatus = useCallback(async (projectPath: string) => {
        setLoading(true);
        setError(null);
        try {
            const [statuses, ver] = await Promise.all([
                invoke<SkillStatus[]>("check_skills_status", { projectPath }),
                invoke<string>("get_skills_version"),
            ]);
            setSkills(statuses);
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

    const installSkills = useCallback(
        async (projectPath: string, force = false): Promise<SkillsInstallResult | null> => {
            setLoading(true);
            setError(null);
            try {
                const result = await invoke<SkillsInstallResult>("install_skills", {
                    projectPath,
                    force,
                });
                setSkills(result.skills);
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

    const uninstallSkills = useCallback(async (projectPath: string): Promise<boolean> => {
        setLoading(true);
        setError(null);
        try {
            await invoke("uninstall_skills", { projectPath });
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
            const needed = await invoke<boolean>("check_skills_update_needed", {
                projectPath,
            });
            setUpdateNeeded(needed);
            return needed;
        } catch (e) {
            console.error("检查 skills 更新失败:", e);
            return false;
        }
    }, []);

    return {
        skills,
        loading,
        error,
        version,
        updateNeeded,
        checkStatus,
        installSkills,
        uninstallSkills,
        checkUpdateNeeded,
    };
}
