/**
 * WebSocket Hook
 * Manages WebSocket connection for real-time updates
 */
import {useEffect, useRef, useCallback, useState} from 'react';
import { logger } from '@/lib/logger';
import {Message} from '@/types/chat';

interface WebSocketOptions {
    projectId: string;
    onMessage?: (message: Message) => void;
    onStatus?: (status: string, data?: any, requestId?: string) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    onError?: (error: Error) => void;
}

export function useWebSocket({
                                 projectId,
                                 onMessage,
                                 onStatus,
                                 onConnect,
                                 onDisconnect,
                                 onError
                             }: WebSocketOptions) {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const connectionAttemptsRef = useRef(0);
    const shouldReconnectRef = useRef(true);
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            return;
        }

        // Don't reconnect if we're intentionally disconnecting
        if (!shouldReconnectRef.current) {
            return;
        }

        try {
            const wsUrl = process.env.NEXT_PUBLIC_WS_BASE || 'ws://localhost:8080';
            const fullUrl = `${wsUrl}/api/chat/${projectId}`;
            const ws = new WebSocket(fullUrl);

            ws.onopen = () => {
                setIsConnected(true);
                connectionAttemptsRef.current = 0;
                // Start lightweight keepalive pings to prevent idle timeouts
                if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
                pingIntervalRef.current = setInterval(() => {
                    try {
                        if (ws.readyState === WebSocket.OPEN) {
                            ws.send('ping');
                        }
                    } catch {}
                }, 25000);
                onConnect?.();
            };

            ws.onmessage = (event) => {
                try {
                    if (event.data === 'pong') {
                        return;
                    }

                    const data = JSON.parse(event.data);

                    if (data.type === 'message' && onMessage && data.data) {
                        onMessage(data.data);
                    } else if (data.type === 'preview_error' && onMessage) {
                        onMessage(data);
                    } else if (data.type === 'preview_success' && onMessage) {
                        onMessage(data);
                    } else if ((data.type === 'project_status' || data.type === 'status') && onStatus) {
                        onStatus('project_status', data.data || {status: data.status, message: data.message});
                    } else if (data.type === 'act_start' && onStatus) {
                        onStatus('act_start', data.data, data.data?.request_id);
                    } else if (data.type === 'chat_start' && onStatus) {
                        onStatus('chat_start', data.data, data.data?.request_id);
                    } else if (data.type === 'act_complete' && onStatus) {
                        onStatus('act_complete', data.data, data.data?.request_id);
                    } else if (data.type === 'chat_complete' && onStatus) {
                        onStatus('chat_complete', data.data, data.data?.request_id);
                    } else {
                    }
                } catch (error) {
                    logger.debug('Failed to parse WebSocket message:', error as any);
                }
            };

            ws.onerror = (error) => {
                logger.debug('❌ WebSocket error:', error as any);
                logger.debug('❌ WebSocket readyState:', ws.readyState);
                logger.debug('❌ WebSocket URL:', ws.url);
                onError?.(new Error(`WebSocket connection error to ${ws.url}`));
            };

            ws.onclose = () => {
                setIsConnected(false);
                onDisconnect?.();

                // Stop keepalive pings
                if (pingIntervalRef.current) {
                    clearInterval(pingIntervalRef.current);
                    pingIntervalRef.current = null;
                }

                // Only reconnect if we should and haven't exceeded attempts
                if (shouldReconnectRef.current) {
                    const attempts = connectionAttemptsRef.current + 1;
                    connectionAttemptsRef.current = attempts;

                    if (attempts < 5) {
                        const delay = Math.min(1000 * Math.pow(2, attempts), 10000);
                        reconnectTimeoutRef.current = setTimeout(() => {
                            connect();
                        }, delay);
                    }
                }
            };

            wsRef.current = ws;
        } catch (error) {
            logger.debug('Failed to create WebSocket connection:', error as any);
            onError?.(error as Error);
        }
    }, [projectId, onMessage, onStatus, onConnect, onDisconnect, onError]);

    const disconnect = useCallback(() => {
        shouldReconnectRef.current = false;

        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
        }

        // Stop keepalive pings
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        setIsConnected(false);
    }, []);

    const sendMessage = useCallback((data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket is not connected');
        }
    }, []);

    useEffect(() => {
        shouldReconnectRef.current = true;
        connectionAttemptsRef.current = 0;
        // Delay initial connect slightly to avoid React StrictMode double-invocation churn
        const timer = setTimeout(() => {
            connect();
        }, 200);

        return () => {
            clearTimeout(timer);
            disconnect();
        };
    }, [projectId]);

    return {
        isConnected,
        connect,
        disconnect,
        sendMessage
    };
}