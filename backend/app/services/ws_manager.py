# backend/app/services/ws_manager.py
"""
WebSocket Manager - SSE 대체

Windows asyncio 호환성 문제로 SSE 대신 WebSocket 사용
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class WSClient:
    """WebSocket 클라이언트"""
    websocket: WebSocket
    client_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)


class WebSocketManager:
    """
    WebSocket 연결 관리자
    
    - 클라이언트 연결/해제 관리
    - 이벤트 브로드캐스트
    """
    
    def __init__(self):
        self._clients: Dict[str, WSClient] = {}
        self._lock = asyncio.Lock()
    
    @property
    def client_count(self) -> int:
        return len(self._clients)
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """클라이언트 연결"""
        await websocket.accept()
        
        async with self._lock:
            self._clients[client_id] = WSClient(
                websocket=websocket,
                client_id=client_id,
            )
        
        logger.info(f"WS client connected: {client_id[:8]}... (total: {self.client_count})")
        
        # 연결 성공 메시지 전송
        await self._send_to_client(client_id, {
            "type": "connected",
            "client_id": client_id[:8],
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    async def disconnect(self, client_id: str):
        """클라이언트 연결 해제"""
        async with self._lock:
            self._clients.pop(client_id, None)
        logger.info(f"WS client disconnected: {client_id[:8]}... (total: {self.client_count})")
    
    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> bool:
        """특정 클라이언트에게 메시지 전송"""
        client = self._clients.get(client_id)
        if not client:
            return False
        
        try:
            await client.websocket.send_json(data)
            return True
        except Exception as e:
            logger.warning(f"Failed to send to client {client_id[:8]}...: {e}")
            return False
    
    async def broadcast(self, data: Dict[str, Any]) -> int:
        """모든 클라이언트에게 브로드캐스트"""
        if not self._clients:
            return 0
        
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat()
        
        sent_count = 0
        dead_clients: List[str] = []
        
        async with self._lock:
            for client_id, client in self._clients.items():
                try:
                    await client.websocket.send_json(data)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to broadcast to {client_id[:8]}...: {e}")
                    dead_clients.append(client_id)
        
        # 죽은 연결 정리
        for client_id in dead_clients:
            await self.disconnect(client_id)
        
        logger.debug(f"WS broadcast: {data.get('type')} to {sent_count} clients")
        return sent_count
    
    async def broadcast_refresh(self, scope: str = "conversations", reason: str = "scheduler") -> int:
        """새로고침 이벤트 브로드캐스트"""
        return await self.broadcast({
            "type": "refresh",
            "scope": scope,
            "reason": reason,
        })


# 전역 싱글톤
ws_manager = WebSocketManager()
