#!/usr/bin/env python3
"""
DB 임베딩 vs 새로 생성한 임베딩 비교 테스트
"""
from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService
from sqlalchemy import text
import numpy as np

db = SessionLocal()
svc = EmbeddingService(db)

test_text = "수건은 몇개 비치되어있나요?"

print(f"테스트 텍스트: \"{test_text}\"")
print("-" * 50)

# 1. 새로 생성한 임베딩
print("1. 새 임베딩 생성 중...")
new_emb = svc.create_embedding(test_text)
print(f"   새 임베딩 첫 5개: {new_emb[:5]}")

# 2. DB에 저장된 같은 텍스트의 임베딩
print("\n2. DB에서 임베딩 조회 중...")
result = db.execute(text("""
    SELECT embedding::text, guest_message
    FROM answer_embeddings 
    WHERE guest_message = :msg
    LIMIT 1
"""), {"msg": test_text}).fetchone()

if result:
    db_emb_str = result[0]
    db_emb = [float(x) for x in db_emb_str.strip('[]').split(',')]
    
    print(f"   DB 임베딩 첫 5개: {db_emb[:5]}")
    
    # 유사도 계산
    sim = np.dot(new_emb, db_emb) / (np.linalg.norm(new_emb) * np.linalg.norm(db_emb))
    print(f"\n📊 DB 임베딩 vs 새 임베딩 유사도: {sim:.6f}")
    
    if sim > 0.99:
        print("   ✅ 정상 - 임베딩 일치")
    elif sim > 0.8:
        print("   ⚠️ 약간 다름 - OpenAI 모델 버전 차이?")
    else:
        print("   ❌ 심각한 불일치 - 임베딩 저장 문제!")
else:
    print("   ❌ DB에 해당 텍스트 없음")
    
    # 비슷한 텍스트로 재시도
    print("\n3. 비슷한 텍스트로 재시도...")
    result2 = db.execute(text("""
        SELECT embedding::text, guest_message
        FROM answer_embeddings 
        WHERE guest_message ILIKE '%수건%몇%'
        LIMIT 1
    """)).fetchone()
    
    if result2:
        db_emb_str = result2[0]
        db_msg = result2[1]
        db_emb = [float(x) for x in db_emb_str.strip('[]').split(',')]
        
        print(f"   찾은 텍스트: \"{db_msg[:50]}...\"")
        print(f"   DB 임베딩 첫 5개: {db_emb[:5]}")
        
        # 해당 텍스트로 새 임베딩 생성
        new_emb2 = svc.create_embedding(db_msg)
        sim2 = np.dot(new_emb2, db_emb) / (np.linalg.norm(new_emb2) * np.linalg.norm(db_emb))
        print(f"\n📊 DB 임베딩 vs 새 임베딩 유사도: {sim2:.6f}")
        
        if sim2 > 0.99:
            print("   ✅ 정상 - 임베딩 일치")
        elif sim2 > 0.8:
            print("   ⚠️ 약간 다름")
        else:
            print("   ❌ 심각한 불일치!")

db.close()
