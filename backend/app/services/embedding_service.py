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
        pack_keys: Optional[List[str]] = None,
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
            pack_keys: 사용된 Answer Pack keys (few-shot 필터링용)
            
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
        
        # pack_keys 저장 (컬럼이 있는 경우)
        if pack_keys and hasattr(answer_embedding, 'pack_keys'):
            answer_embedding.pack_keys = pack_keys
        
        self.db.add(answer_embedding)
        self.db.flush()
        
        logger.info(
            f"답변 임베딩 저장 완료: id={answer_embedding.id}, "
            f"property={property_code}, edited={was_edited}, "
            f"pack_keys={pack_keys}"
        )
        
        return answer_embedding
    
    def find_similar_answers(
        self,
        query_text: str,
        property_code: Optional[str] = None,
        limit: int = 3,
        min_similarity: float = 0.7,
        include_group_pool: bool = True,
    ) -> List[SimilarAnswer]:
        """
        유사한 과거 답변 검색
        
        Args:
            query_text: 검색할 게스트 메시지
            property_code: 특정 숙소로 필터링 (None이면 전체 검색)
            limit: 최대 결과 수
            min_similarity: 최소 유사도 (0.0 ~ 1.0)
            include_group_pool: 그룹 공통 풀도 포함할지 (예: PV-A 검색 시 PV도 포함)
            
        Returns:
            유사도 높은 순으로 정렬된 SimilarAnswer 리스트
        """
        # 쿼리 텍스트 임베딩
        query_embedding = self.create_embedding(query_text)
        # pgvector 형식으로 변환 (공백 없이)
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # SQL 쿼리 - WHERE절에서 similarity 필터링하면 버그 발생
        # ORDER BY만 사용하고 Python에서 필터링
        fetch_limit = limit * 3  # 필터링 후 충분한 결과 확보를 위해 더 많이 조회
        
        if property_code:
            # 그룹 공통 풀 포함 로직
            property_codes = [property_code]
            
            if include_group_pool:
                group_code = self._get_group_code_from_profile(property_code)
                if group_code and group_code != property_code:
                    property_codes.append(group_code)
            
            if len(property_codes) == 1:
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
                    ORDER BY embedding <=> cast(:query_embedding as vector)
                    LIMIT :fetch_limit
                """)
                params = {
                    "query_embedding": embedding_str,
                    "property_code": property_code,
                    "fetch_limit": fetch_limit,
                }
            else:
                # 그룹 공통 풀 포함 (IN 절 사용)
                placeholders = ', '.join([f':pc{i}' for i in range(len(property_codes))])
                sql = text(f"""
                    SELECT 
                        id,
                        guest_message,
                        final_answer,
                        property_code,
                        was_edited,
                        1 - (embedding <=> cast(:query_embedding as vector)) as similarity,
                        CASE WHEN property_code = :exact_property THEN 0 ELSE 1 END as match_priority
                    FROM answer_embeddings
                    WHERE property_code IN ({placeholders})
                    ORDER BY match_priority, embedding <=> cast(:query_embedding as vector)
                    LIMIT :fetch_limit
                """)
                params = {
                    "query_embedding": embedding_str,
                    "exact_property": property_code,
                    "fetch_limit": fetch_limit,
                }
                for i, pc in enumerate(property_codes):
                    params[f"pc{i}"] = pc
                
                logger.info(
                    f"Few-shot 검색 (그룹 풀 포함): property={property_code}, group={property_codes[1]}"
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
                ORDER BY embedding <=> cast(:query_embedding as vector)
                LIMIT :fetch_limit
            """)
            params = {
                "query_embedding": embedding_str,
                "fetch_limit": fetch_limit,
            }
        
        result = self.db.execute(sql, params)
        rows = result.fetchall()
        
        # Python에서 min_similarity 필터링 및 limit 적용
        similar_answers = []
        for row in rows:
            sim = float(row.similarity)
            if sim >= min_similarity:
                similar_answers.append(SimilarAnswer(
                    id=row.id,
                    guest_message=row.guest_message,
                    final_answer=row.final_answer,
                    property_code=row.property_code,
                    was_edited=row.was_edited,
                    similarity=sim,
                ))
                if len(similar_answers) >= limit:
                    break
        
        logger.info(
            f"유사 답변 검색 완료: query_len={len(query_text)}, "
            f"property={property_code}, found={len(similar_answers)}"
        )
        
        return similar_answers
    
    def _get_group_code_from_profile(self, property_code: str) -> Optional[str]:
        """
        property_profile에서 group_code 조회
        
        Args:
            property_code: 숙소 코드
            
        Returns:
            group_code (없으면 None)
        """
        try:
            from app.domain.models.property_profile import PropertyProfile
            
            result = self.db.execute(
                select(PropertyProfile.group_code)
                .where(PropertyProfile.property_code == property_code)
            ).scalar_one_or_none()
            
            return result
        except Exception as e:
            logger.warning(f"group_code 조회 실패: property={property_code}, error={e}")
            return None
    
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
