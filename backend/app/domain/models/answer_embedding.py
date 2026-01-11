# backend/app/domain/models/answer_embedding.py
"""
Answer Embedding 모델

호스트가 승인한 답변을 임베딩하여 저장.
유사한 게스트 메시지에 대해 과거 좋은 답변을 검색하는 데 사용.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class AnswerEmbedding(Base):
    """호스트 승인 답변 임베딩 저장소"""
    
    __tablename__ = "answer_embeddings"
    
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    
    # 원본 텍스트
    guest_message: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 임베딩 벡터 (OpenAI text-embedding-3-small: 1536 차원)
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=False)
    
    # 메타데이터
    property_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    was_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    conversation_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    airbnb_thread_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 🆕 Answer Pack keys (Few-shot 필터링용)
    pack_keys: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    
    def __repr__(self) -> str:
        return f"<AnswerEmbedding {self.id} property={self.property_code}>"
