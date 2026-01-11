#!/usr/bin/env python3
"""
실제 AutoReplyService 로직 테스트

게스트 메시지 → 1차 LLM (의도 분석) → Few-shot 검색 → Answer Pack 조회
전체 파이프라인을 테스트합니다.

사용법:
    python -m app.scripts.test_auto_reply_pipeline "수건이 몇 개 있나요?" --property 2S214
    python -m app.scripts.test_auto_reply_pipeline "바베큐 가능한가요?" --property 2H126
    python -m app.scripts.test_auto_reply_pipeline "체크인 시간이 어떻게 되나요?"
"""
import argparse
import asyncio
import logging
import sys
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService
from app.services.property_answer_pack_service import PropertyAnswerPackService
from app.domain.enums.answer_pack_keys import AnswerPackKey, ANSWER_PACK_KEY_DESCRIPTIONS
from app.adapters.llm_client import get_openai_client

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# 1차 LLM 호출용 프롬프트 (의도 분석)
INTENT_ANALYSIS_PROMPT = """당신은 숙박업 게스트 메시지 분석 전문가입니다.

게스트 메시지를 분석하여 필요한 정보 카테고리(pack_keys)를 선택하세요.

## 사용 가능한 pack_keys:
- checkin_info: 체크인 시간, 방법, 출입 가이드
- checkout_info: 체크아웃 시간
- early_checkin: 얼리체크인 가능 여부, 비용
- late_checkout: 레이트체크아웃 가능 여부, 비용
- luggage_storage: 짐 보관 가능 여부
- location_info: 위치, 주변 정보
- address_detail: 상세 주소
- wifi_info: 와이파이 SSID, 비밀번호
- parking_info: 주차 정보
- room_info: 객실 구성, 수용 인원
- amenities_info: 편의시설 (TV, 빔프로젝터, 수건 등)
- appliance_guide: 에어컨, 난방 사용법
- kitchen_info: 조리 가능 여부, 주방용품
- laundry_info: 세탁기, 건조기 정보
- pool_info: 수영장/온수풀 정보
- bbq_info: 바베큐 정보
- pet_policy: 반려동물 정책
- house_rules: 흡연, 소음, 숙소 규칙
- extra_bedding: 추가 침구 정보

## 게스트 메시지:
{guest_message}

## 응답 형식 (JSON):
{{"pack_keys": ["key1", "key2"], "intent_summary": "간단한 의도 요약"}}
"""


async def analyze_intent(client, guest_message: str) -> dict:
    """1차 LLM 호출: 의도 분석 및 pack_keys 추출"""
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes guest messages."},
                {"role": "user", "content": INTENT_ANALYSIS_PROMPT.format(guest_message=guest_message)}
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"의도 분석 실패: {e}")
        return {"pack_keys": ["checkin_info"], "intent_summary": "분석 실패"}


def get_few_shots(
    embedding_service: EmbeddingService,
    guest_message: str,
    property_code: Optional[str],
    pack_keys: list,
) -> list:
    """Few-shot 예시 검색"""
    similar = embedding_service.find_similar_answers(
        query_text=guest_message,
        property_code=property_code,
        limit=5,
        min_similarity=0.5,
    )
    
    if not similar:
        return []
    
    # pack_keys 매칭 필터링
    filtered = []
    for ans in similar:
        if hasattr(ans, 'pack_keys') and ans.pack_keys:
            if any(pk in pack_keys for pk in ans.pack_keys):
                filtered.append(ans)
                continue
        filtered.append(ans)
    
    return filtered[:3]


async def test_pipeline(
    guest_message: str,
    property_code: Optional[str] = None,
):
    """전체 파이프라인 테스트"""
    db = SessionLocal()
    client = get_openai_client()
    embedding_service = EmbeddingService(db)
    pack_service = PropertyAnswerPackService(db)
    
    try:
        print("\n" + "=" * 70)
        print(f"🧪 테스트 메시지: \"{guest_message}\"")
        print(f"   숙소 코드: {property_code or '(전체)'}")
        print("=" * 70)
        
        # 1. 의도 분석 (1차 LLM)
        print("\n📋 [STEP 1] 의도 분석 (gpt-4o-mini)")
        print("-" * 50)
        intent_result = await analyze_intent(client, guest_message)
        print(f"   의도 요약: {intent_result.get('intent_summary', 'N/A')}")
        print(f"   선택된 pack_keys: {intent_result.get('pack_keys', [])}")
        
        # 2. Few-shot 검색
        print("\n📚 [STEP 2] Few-shot 검색 (임베딩 유사도)")
        print("-" * 50)
        pack_keys = intent_result.get('pack_keys', [])
        few_shots = get_few_shots(embedding_service, guest_message, property_code, pack_keys)
        
        if few_shots:
            for i, shot in enumerate(few_shots, 1):
                print(f"\n   [{i}] 유사도: {shot.similarity:.1%} | 숙소: {shot.property_code}")
                print(f"       게스트: {shot.guest_message[:60]}...")
                print(f"       답변: {shot.final_answer[:60]}...")
        else:
            print("   ❌ Few-shot 없음 (유사도 0.5 이상 결과 없음)")
        
        # 3. Answer Pack 조회
        print("\n📦 [STEP 3] Answer Pack 조회")
        print("-" * 50)
        
        # pack_keys를 AnswerPackKey enum으로 변환
        pack_key_enums = []
        for key in pack_keys:
            try:
                pack_key_enums.append(AnswerPackKey(key))
            except ValueError:
                logger.warning(f"Unknown pack_key: {key}")
        
        if property_code and pack_key_enums:
            answer_pack = pack_service.get_pack(
                property_code=property_code,
                keys=pack_key_enums,
            )
            
            print(f"   요청된 keys: {[k.value for k in pack_key_enums]}")
            print(f"   반환된 데이터:")
            
            # to_prompt_dict() 사용해서 None 아닌 값만 출력
            pack_dict = answer_pack.to_prompt_dict()
            if pack_dict:
                for key, value in pack_dict.items():
                    value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    print(f"      - {key}: {value_str}")
            else:
                print("      (반환된 데이터 없음)")
        else:
            print("   ⚠️ property_code가 없거나 pack_keys가 비어있어 Answer Pack 조회 생략")
        
        # 4. 최종 프롬프트 구성 미리보기
        print("\n📝 [STEP 4] LLM 프롬프트 구성 요소")
        print("-" * 50)
        print(f"   ✓ 게스트 메시지: {len(guest_message)}자")
        print(f"   ✓ Few-shot 예시: {len(few_shots)}개")
        print(f"   ✓ Answer Pack keys: {len(pack_key_enums)}개")
        
        print("\n" + "=" * 70)
        print("✅ 테스트 완료!")
        print("=" * 70 + "\n")
        
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AutoReply 파이프라인 테스트")
    parser.add_argument("message", help="게스트 메시지")
    parser.add_argument("-p", "--property", help="숙소 코드 (예: 2S214, LCN)")
    
    args = parser.parse_args()
    
    asyncio.run(test_pipeline(
        guest_message=args.message,
        property_code=args.property,
    ))


if __name__ == "__main__":
    main()
