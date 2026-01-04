# backend/app/services/embedding_service.py
"""
Embedding Service

OpenAI API를 사용하여 텍스트를 임베딩하고,
pgvector를 사용하여 유사한 과거 답변을 검색합니다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from openai import OpenAI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.models.answer_embedding import AnswerEmbedding
from app.adapters.llm_client import get_openai_client

logger = logging.getLogger(__name__)

# OpenAI 임베딩 모델
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


@dataclass
class SimilarAnswer:
    """유사 답변 검색 결과"""
    id: UUID
    guest_message: str
    final_answer: str
    property_code: Optional[str]
    was_edited: bool
    similarity: float  # 1.0 = 완전 동일, 0.0 = 완전 다름


class EmbeddingService:
    """임베딩 생성 및 유사도 검색 서비스"""
    
    def __init__(self, db: Session, openai_client: Optional[OpenAI] = None):
        self.db = db
        self.openai_client = openai_client or get_openai_client()
        if not self.openai_client:
            raise ValueError("OpenAI client not available. Check LLM_API_KEY in settings.")
    
    def create_embedding(self, text: str) -> List[float]:
        """
        텍스트를 임베딩 벡터로 변환
        
        Args:
            text: 임베딩할 텍스트
            
        Returns:
            1536차원 벡터
        """
        try:
            response = self.openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            raise
    
    def store_answer(
        self,
        guest_message: str,
        final_answer: str,
        property_code: Optional[str] = None,
        was_edited: bool = False,
        conversation_id: Optional[UUID] = None,
        airbnb_thread_id: Optional[str] = None,
    ) -> AnswerEmbedding:
        """
        답변을 임베딩하여 저장
        
        Args:
            guest_message: 게스트 메시지 원문
            final_answer: 호스트가 승인한 최종 답변
            property_code: 숙소 코드
            was_edited: AI 초안이 수정되었는지 여부
            conversation_id: 대화 ID
            airbnb_thread_id: 에어비앤비 스레드 ID
            
        Returns:
            저장된 AnswerEmbedding 객체
        """
        # 게스트 메시지를 기준으로 임베딩 생성
        embedding = self.create_embedding(guest_message)
        
        answer_embedding = AnswerEmbedding(
            guest_message=guest_message,
            final_answer=final_answer,
            embedding=embedding,
            property_code=property_code,
            was_edited=was_edited,
            conversation_id=conversation_id,
            airbnb_thread_id=airbnb_thread_id,
        )
        
        self.db.add(answer_embedding)
        self.db.flush()
        
        logger.info(
            f"답변 임베딩 저장 완료: id={answer_embedding.id}, "
            f"property={property_code}, edited={was_edited}"
        )
        
        return answer_embedding
    
    def find_similar_answers(
        self,
        query_text: str,
        property_code: Optional[str] = None,
        limit: int = 3,
        min_similarity: float = 0.7,
    ) -> List[SimilarAnswer]:
        """
        유사한 과거 답변 검색
        
        Args:
            query_text: 검색할 게스트 메시지
            property_code: 특정 숙소로 필터링 (None이면 전체 검색)
            limit: 최대 결과 수
            min_similarity: 최소 유사도 (0.0 ~ 1.0)
            
        Returns:
            유사도 높은 순으로 정렬된 SimilarAnswer 리스트
        """
        # 쿼리 텍스트 임베딩
        query_embedding = self.create_embedding(query_text)
        embedding_str = str(query_embedding)
        
        # pgvector cosine distance: 0 = 동일, 2 = 완전 반대
        # similarity = 1 - distance (cosine distance는 0~1 범위)
        
        # SQL 쿼리 구성 - bindparams 사용
        if property_code:
            sql = text("""
                SELECT 
                    id,
                    guest_message,
                    final_answer,
                    property_code,
                    was_edited,
                    1 - (embedding <=> cast(:query_embedding as vector)) as similarity
                FROM answer_embeddings
                WHERE property_code = :property_code
                AND 1 - (embedding <=> cast(:query_embedding as vector)) >= :min_similarity
                ORDER BY embedding <=> cast(:query_embedding as vector)
                LIMIT :limit
            """).bindparams(
                query_embedding=embedding_str,
                property_code=property_code,
                min_similarity=min_similarity,
                limit=limit,
            )
        else:
            sql = text("""
                SELECT 
                    id,
                    guest_message,
                    final_answer,
                    property_code,
                    was_edited,
                    1 - (embedding <=> cast(:query_embedding as vector)) as similarity
                FROM answer_embeddings
                WHERE 1 - (embedding <=> cast(:query_embedding as vector)) >= :min_similarity
                ORDER BY embedding <=> cast(:query_embedding as vector)
                LIMIT :limit
            """).bindparams(
                query_embedding=embedding_str,
                min_similarity=min_similarity,
                limit=limit,
            )
        
        result = self.db.execute(sql)
        rows = result.fetchall()
        
        similar_answers = [
            SimilarAnswer(
                id=row.id,
                guest_message=row.guest_message,
                final_answer=row.final_answer,
                property_code=row.property_code,
                was_edited=row.was_edited,
                similarity=float(row.similarity),
            )
            for row in rows
        ]
        
        logger.info(
            f"유사 답변 검색 완료: query_len={len(query_text)}, "
            f"property={property_code}, found={len(similar_answers)}"
        )
        
        return similar_answers
    
    def find_similar_for_few_shot(
        self,
        guest_message: str,
        property_code: Optional[str] = None,
        limit: int = 3,
    ) -> str:
        """
        Few-shot 프롬프트용 유사 예시 생성
        
        Args:
            guest_message: 새 게스트 메시지
            property_code: 숙소 코드
            limit: 예시 수
            
        Returns:
            프롬프트에 삽입할 예시 문자열
        """
        similar = self.find_similar_answers(
            query_text=guest_message,
            property_code=property_code,
            limit=limit,
            min_similarity=0.65,  # few-shot은 조금 낮은 threshold
        )
        
        if not similar:
            return ""
        
        examples = []
        for i, ans in enumerate(similar, 1):
            examples.append(f"""
### 과거 사례 {i} (유사도: {ans.similarity:.0%})
**게스트 메시지:** {ans.guest_message}
**승인된 답변:** {ans.final_answer}
""")
        
        return "\n".join(examples)
    
    def get_stats(self) -> dict:
        """임베딩 저장소 통계"""
        total = self.db.execute(
            select(AnswerEmbedding)
        ).scalars().all()
        
        edited_count = sum(1 for a in total if a.was_edited)
        
        # 숙소별 카운트
        property_counts = {}
        for a in total:
            code = a.property_code or "unknown"
            property_counts[code] = property_counts.get(code, 0) + 1
        
        return {
            "total_embeddings": len(total),
            "edited_count": edited_count,
            "unedited_count": len(total) - edited_count,
            "by_property": property_counts,
        }
