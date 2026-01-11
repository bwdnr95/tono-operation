#!/usr/bin/env python3
"""
두 문장 간 임베딩 유사도 직접 측정

사용법:
    python -m app.scripts.test_similarity_direct "문장1" "문장2"
    
예시:
    python -m app.scripts.test_similarity_direct "수건이 몇 개 있나요?" "수건은 몇개 비치되어있나요?"
"""
import sys
import numpy as np
from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService


def cosine_similarity(v1, v2):
    """코사인 유사도 계산"""
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))


def test_similarity(text1: str, text2: str):
    db = SessionLocal()
    svc = EmbeddingService(db)
    
    try:
        print(f"\n문장 1: \"{text1}\"")
        print(f"문장 2: \"{text2}\"")
        print("-" * 50)
        
        emb1 = svc.create_embedding(text1)
        emb2 = svc.create_embedding(text2)
        
        sim = cosine_similarity(emb1, emb2)
        
        print(f"\n📊 코사인 유사도: {sim:.4f} ({sim*100:.1f}%)")
        
        if sim >= 0.7:
            print("   ✅ Few-shot 활용 가능 (>=0.7)")
        elif sim >= 0.5:
            print("   ⚠️ 경계선 (0.5~0.7)")
        else:
            print("   ❌ 유사도 낮음 (<0.5)")
        
        # DB에서 text1으로 검색했을 때 결과
        print(f"\n📋 \"{text1[:20]}...\"로 DB 검색:")
        results = svc.find_similar_answers(
            query_text=text1,
            limit=5,
            min_similarity=0.3,  # 낮게 설정해서 전부 보기
        )
        
        for i, r in enumerate(results[:5], 1):
            print(f"   [{i}] {r.similarity:.3f} - {r.guest_message[:40]}...")
            
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        test_similarity(sys.argv[1], sys.argv[2])
    else:
        # 기본 테스트
        test_similarity(
            "수건이 몇 개 있나요?",
            "수건은 몇개 비치되어있나요?"
        )
