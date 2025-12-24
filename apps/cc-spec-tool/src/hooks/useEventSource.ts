// hooks/useEventSource.ts - SSE 事件源 Hook

import { useState, useEffect, useRef, useCallback } from "react";

export type ConnectionState = "connecting" | "connected" | "error";

export interface UseEventSourceOptions {
    url: string;
    onMessage?: (event: MessageEvent) => void;
    onOpen?: () => void;
    onError?: () => void;
    reconnectDelay?: number;
    autoReconnect?: boolean;
}

export function useEventSource(options: UseEventSourceOptions) {
    const {
        url,
        onMessage,
        onOpen,
        onError,
        reconnectDelay = 3000,
        autoReconnect = true,
    } = options;

    const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<number | null>(null);

    const disconnect = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
    }, []);

    const connect = useCallback(() => {
        disconnect();
        setConnectionState("connecting");

        const source = new EventSource(url);
        eventSourceRef.current = source;

        source.onopen = () => {
            setConnectionState("connected");
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
            onOpen?.();
        };

        source.onerror = () => {
            setConnectionState("error");
            source.close();
            eventSourceRef.current = null;
            onError?.();

            if (autoReconnect && !reconnectTimerRef.current) {
                reconnectTimerRef.current = window.setTimeout(() => {
                    reconnectTimerRef.current = null;
                    connect();
                }, reconnectDelay);
            }
        };

        source.onmessage = (event) => {
            onMessage?.(event);
        };

        return source;
    }, [url, onMessage, onOpen, onError, reconnectDelay, autoReconnect, disconnect]);

    const addEventListener = useCallback((type: string, listener: (event: MessageEvent) => void) => {
        eventSourceRef.current?.addEventListener(type, listener as EventListener);
        return () => {
            eventSourceRef.current?.removeEventListener(type, listener as EventListener);
        };
    }, []);

    useEffect(() => {
        connect();
        return disconnect;
    }, [url]); // 只在 URL 变化时重新连接

    return {
        connectionState,
        connect,
        disconnect,
        addEventListener,
        eventSource: eventSourceRef.current,
    };
}
