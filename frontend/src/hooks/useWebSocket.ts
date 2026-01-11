// src/hooks/useWebSocket.ts
/**
 * WebSocket 기반 실시간 이벤트 Hook
 * 
 * 서버에서 실시간 이벤트를 수신하여 자동으로 데이터를 갱신합니다.
 */
import { useEffect, useRef, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://172.30.1.75:8000/api/v1";

export interface WebSocketEvent {
  type: 'connected' | 'refresh' | 'pong';
  timestamp?: string;
  scope?: 'conversations' | 'dashboard' | 'all';
  reason?: 'scheduler' | 'manual' | 'new_message';
  client_id?: string;
}

export interface UseWebSocketOptions {
  /** refresh 이벤트 수신 시 콜백 */
  onRefresh?: (scope: string, reason: string) => void;
  /** 연결 성공 시 콜백 */
  onConnected?: () => void;
  /** 연결 끊김 시 콜백 */
  onDisconnected?: () => void;
  /** 에러 발생 시 콜백 */
  onError?: (error: Event) => void;
  /** 자동 재연결 활성화 (기본: true) */
  autoReconnect?: boolean;
  /** 재연결 딜레이 ms (기본: 3000) */
  reconnectDelay?: number;
  /** 활성화 여부 (기본: true) */
  enabled?: boolean;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    onRefresh,
    onConnected,
    onDisconnected,
    onError,
    autoReconnect = true,
    reconnectDelay = 3000,
    enabled = true,
  } = options;

  // 콜백을 ref로 저장 (재연결 시 최신 콜백 사용)
  const callbacksRef = useRef({ onRefresh, onConnected, onDisconnected, onError });
  callbacksRef.current = { onRefresh, onConnected, onDisconnected, onError };

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // 이미 연결 중이면 스킵
    if (wsRef.current?.readyState === WebSocket.OPEN || 
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // WebSocket URL 생성 (http -> ws, https -> wss)
    const baseUrl = API_BASE_URL.replace(/\/+$/, "").replace(/^http/, "ws");
    const url = `${baseUrl}/events/ws`;
    console.log('[WebSocket] Connecting to:', url);

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] Connected');
        
        // 30초마다 ping 전송 (연결 유지)
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent;
          
          switch (data.type) {
            case 'connected':
              console.log('[WebSocket] Server confirmed:', data.client_id);
              callbacksRef.current.onConnected?.();
              break;
              
            case 'refresh':
              console.log('[WebSocket] Refresh:', data.scope, data.reason);
              callbacksRef.current.onRefresh?.(data.scope || 'all', data.reason || 'unknown');
              break;
              
            case 'pong':
              // ping 응답, 무시
              break;
          }
        } catch (e) {
          console.warn('[WebSocket] Parse error:', event.data);
        }
      };

      ws.onerror = (error) => {
        console.warn('[WebSocket] Error:', error);
        callbacksRef.current.onError?.(error);
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Closed:', event.code, event.reason);
        callbacksRef.current.onDisconnected?.();
        
        // ping interval 정리
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // 자동 재연결
        if (autoReconnect && mountedRef.current) {
          console.log(`[WebSocket] Reconnecting in ${reconnectDelay}ms...`);
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay);
        }
      };
    } catch (e) {
      console.error('[WebSocket] Create failed:', e);
    }
  }, [autoReconnect, reconnectDelay]);

  useEffect(() => {
    if (!enabled) return;

    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [enabled, connect]);

  return {
    isConnected: wsRef.current?.readyState === WebSocket.OPEN,
  };
}
