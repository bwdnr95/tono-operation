# backend/app/api/v1/events.py
"""
실시간 이벤트 API (WebSocket + SSE fallback)

WebSocket을 기본으로 사용하고, SSE는 비활성화
"""
import asyncio
import uuid
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import logging

from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 실시간 이벤트
    
    이벤트 타입:
    - connected: 연결 성공
    - refresh: 데이터 새로고침 필요 (scope: conversations, dashboard, all)
    """
    client_id = str(uuid.uuid4())
    
    try:
        await ws_manager.connect(websocket, client_id)
        
        # 연결 유지 (클라이언트 메시지 대기)
        while True:
            try:
                # 클라이언트로부터 메시지 대기 (ping/pong 용도)
                data = await websocket.receive_text()
                
                # ping 메시지에 pong 응답
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                logger.info(f"WS client {client_id[:8]}... disconnected normally")
                break
            except Exception as e:
                logger.warning(f"WS error for {client_id[:8]}...: {e}")
                break
                
    except Exception as e:
        logger.error(f"WS connection error: {e}")
    finally:
        await ws_manager.disconnect(client_id)


@router.get("/stream")
async def event_stream(request: Request):
    """
    SSE 엔드포인트 (비활성화됨 - WebSocket 사용 권장)
    """
    async def generate():
        yield "event: disabled\ndata: {\"message\": \"Use WebSocket instead: /api/v1/events/ws\"}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Connection": "close"},
    )


@router.get("/status")
async def get_status():
    """연결 상태 조회"""
    return {
        "websocket_clients": ws_manager.client_count,
    }


@router.post("/broadcast-test")
async def broadcast_test(scope: str = "conversations", reason: str = "test"):
    """테스트용 브로드캐스트"""
    count = await ws_manager.broadcast_refresh(scope=scope, reason=reason)
    return {
        "sent_to": count,
        "scope": scope,
        "reason": reason,
    }

