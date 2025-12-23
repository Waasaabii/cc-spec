// hooks/useConcurrency.ts - 并发状态管理 Hook

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

export interface ConcurrencyStatus {
    cc_running: number;
    cx_running: number;
    cc_max: number;
    cx_max: number;
    cc_queued: number;
    cx_queued: number;
    total_running: number;
    total_max: number;
    can_start_cc: boolean;
    can_start_cx: boolean;
}

export function useConcurrency(refreshInterval = 2000) {
    const [status, setStatus] = useState<ConcurrencyStatus>({
        cc_running: 0,
        cx_running: 0,
        cc_max: 1,
        cx_max: 5,
        cc_queued: 0,
        cx_queued: 0,
        total_running: 0,
        total_max: 6,
        can_start_cc: true,
        can_start_cx: true,
    });
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        try {
            const result = await invoke<{
                cc_running: number;
                cx_running: number;
                cc_max: number;
                cx_max: number;
                cc_queued: number;
                cx_queued: number;
                total_running: number;
                total_max: number;
            }>("get_concurrency_status");

            setStatus({
                ...result,
                can_start_cc: result.cc_running < result.cc_max && result.total_running < result.total_max,
                can_start_cx: result.cx_running < result.cx_max && result.total_running < result.total_max,
            });
        } catch {
            // 保持现有状态
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
        const interval = setInterval(refresh, refreshInterval);
        return () => clearInterval(interval);
    }, [refresh, refreshInterval]);

    return {
        status,
        loading,
        refresh,
        canStartCC: status.can_start_cc,
        canStartCX: status.can_start_cx,
        isAtCapacity: status.total_running >= status.total_max,
        hasQueuedTasks: status.cc_queued > 0 || status.cx_queued > 0,
    };
}

