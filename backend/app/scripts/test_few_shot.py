# backend/app/scripts/test_few_shot.py
"""
Few-shot 유사도 검색 테스트

실제 게스트 메시지로 유사한 과거 답변을 찾아보고,
few-shot으로 사용할 만한 품질인지 확인

사용법:
    python -m app.scripts.test_few_shot
    
    # 특정 메시지로 테스트
    python -m app.scripts.test_few_shot "수건 몇 개 있어요?"
    
    # 특정 숙소로 필터링
    python -m app.scripts.test_few_shot "수건 몇 개 있어요?" --property 2NH1
"""
from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# 테스트용 샘플 게스트 메시지들
SAMPLE_MESSAGES = [
    "수건 몇 개 있어요?",
    "체크인 시간이 어떻게 되나요?",
    "주차장 있나요?",
    "숙소 주소 알려주세요",
    "얼리 체크인 가능한가요?",
    "침대가 몇 개인가요?",
    "와이파이 비밀번호가 뭔가요?",
    "바베큐 가능한가요?",
]


def test_few_shot(
    message: str = None,
    property_code: str = None,
    top_k: int = 3,
):
    """
    Few-shot 유사도 검색 테스트
    """
    db = SessionLocal()
    embedding_service = EmbeddingService(db)
    
    try:
        messages_to_test = [message] if message else SAMPLE_MESSAGES
        
        for test_msg in messages_to_test:
            logger.info("=" * 70)
            logger.info(f"🔍 테스트 메시지: \"{test_msg}\"")
            if property_code:
                logger.info(f"   (숙소 필터: {property_code})")
            logger.info("-" * 70)
            
            # find_similar_answers로 raw 결과 확인
            results = embedding_service.find_similar_answers(
                query_text=test_msg,
                property_code=property_code,
                limit=top_k,
                min_similarity=0.5,  # 테스트용으로 낮게
            )
            
            if not results:
                logger.info("   ❌ 유사한 결과 없음")
                continue
            
            for i, r in enumerate(results, 1):
                logger.info(f"\n   [{i}] 유사도: {r.similarity:.3f}")
                logger.info(f"       숙소: {r.property_code or 'N/A'}")
                logger.info(f"       수정됨: {r.was_edited}")
                logger.info(f"       Guest: {r.guest_message[:80]}...")
                logger.info(f"       Answer: {r.final_answer[:80]}...")
            
            # few-shot 프롬프트 형태로도 출력
            few_shot_prompt = embedding_service.find_similar_for_few_shot(
                guest_message=test_msg,
                property_code=property_code,
                limit=top_k,
            )
            
            if few_shot_prompt:
                logger.info(f"\n   📋 Few-shot 프롬프트 형태:")
                logger.info(few_shot_prompt[:500] + "..." if len(few_shot_prompt) > 500 else few_shot_prompt)
        
        logger.info("\n" + "=" * 70)
        logger.info("테스트 완료!")
        
    except Exception as e:
        logger.error(f"테스트 실패: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    message = None
    property_code = None
    
    args = sys.argv[1:]
    
    # 인자 파싱
    i = 0
    while i < len(args):
        if args[i] == "--property" and i + 1 < len(args):
            property_code = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            message = args[i]
            i += 1
        else:
            i += 1
    
    test_few_shot(message=message, property_code=property_code)
