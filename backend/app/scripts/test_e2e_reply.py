#!/usr/bin/env python3
"""
실제 AutoReplyService 로직을 재활용한 E2E 테스트

전체 파이프라인:
1. 1차 LLM (gpt-4o-mini): 의도 분석 → pack_keys 선택
2. Few-shot 검색: 임베딩 유사도 기반
3. Answer Pack 조회: 선택된 keys에 해당하는 정보
4. 2차 LLM (gpt-4.1): 최종 draft_reply 생성

사용법:
    python -m app.scripts.test_e2e_reply "수건이 몇 개 있나요?" -p 2S214
    python -m app.scripts.test_e2e_reply "바베큐 가능한가요?" -p 2H126
    python -m app.scripts.test_e2e_reply "체크인 시간이 어떻게 되나요?" -p LCN
"""
import argparse
import asyncio
import json
import logging
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService
from app.services.property_answer_pack_service import PropertyAnswerPackService
from app.domain.enums.answer_pack_keys import (
    AnswerPackKey,
    ANSWER_PACK_KEY_DESCRIPTIONS,
    DEFAULT_FALLBACK_KEYS,
)
from app.domain.dtos.answer_pack_dto import AnswerPackResult
from app.adapters.llm_client import get_openai_client

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# 모델 설정 (auto_reply_service.py와 동일)
MODEL_KEY_SELECTOR = "gpt-4o-mini"
MODEL_REPLY_GENERATOR = "gpt-4.1"


class E2EReplyTester:
    """E2E 테스트용 클래스 - AutoReplyService 로직 재활용"""
    
    def __init__(self):
        self.db = SessionLocal()
        self.client = get_openai_client()
        self.embedding_service = EmbeddingService(self.db)
        self.pack_service = PropertyAnswerPackService(self.db)
    
    def close(self):
        self.db.close()
    
    async def determine_required_keys(self, guest_message: str) -> List[AnswerPackKey]:
        """1차 LLM 호출: pack_keys 선택 (auto_reply_service._determine_required_keys 동일)"""
        
        key_descriptions = "\n".join([
            f"- {key.value}: {desc}"
            for key, desc in ANSWER_PACK_KEY_DESCRIPTIONS.items()
        ])
        
        system_prompt = f"""당신은 숙박 게스트 메시지를 분석하여 답변에 필요한 정보 유형을 선택하는 AI입니다.

아래 목록에서 게스트 질문에 답변하기 위해 필요한 key만 선택하세요.
절대로 목록에 없는 key를 만들지 마세요.

사용 가능한 key:
{key_descriptions}

규칙:
1. 게스트 질문에 답변하는 데 꼭 필요한 key만 선택
2. 모호하면 관련 가능성 있는 key 포함
3. 종료 인사, 감사 인사는 key 없이 빈 배열 반환
4. 결제/환불 관련은 선택하지 않음 (별도 처리)

JSON 형식으로 응답:
{{"keys": ["wifi_info", "checkin_info"]}}"""

        user_prompt = f"게스트 메시지:\n{guest_message}"

        try:
            resp = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=MODEL_KEY_SELECTOR,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=200,
            )
            
            raw_content = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
            
            selected_keys = []
            for key_str in parsed.get("keys", []):
                try:
                    key = AnswerPackKey(key_str)
                    selected_keys.append(key)
                except ValueError:
                    logger.warning(f"Invalid pack key: {key_str}")
            
            return selected_keys
            
        except Exception as exc:
            logger.warning(f"KEY_SELECTION_ERROR: {exc}")
            return list(DEFAULT_FALLBACK_KEYS)
    
    def get_filtered_few_shots(
        self,
        guest_message: str,
        pack_keys: List[AnswerPackKey],
        property_code: Optional[str],
    ) -> tuple[str, list]:
        """Few-shot 검색 (auto_reply_service._get_filtered_few_shots 동일)"""
        
        try:
            similar = self.embedding_service.find_similar_answers(
                query_text=guest_message,
                property_code=property_code,
                limit=5,
                min_similarity=0.4,  # 테스트용으로 낮게
            )
            
            if not similar:
                return "", []
            
            # pack_keys 매칭 필터링
            key_values = [k.value for k in pack_keys]
            filtered = []
            
            for ans in similar:
                if hasattr(ans, 'pack_keys') and ans.pack_keys:
                    if any(pk in key_values for pk in ans.pack_keys):
                        filtered.append(ans)
                        if len(filtered) >= 2:
                            break
                elif len(filtered) < 2:
                    filtered.append(ans)
            
            if not filtered:
                filtered = similar[:2]
            
            # 프롬프트 형식으로 변환
            examples = []
            for i, ans in enumerate(filtered[:2], 1):
                examples.append(f"""### 과거 사례 {i} (유사도: {ans.similarity:.0%})
**게스트 메시지:** {ans.guest_message}
**승인된 답변:** {ans.final_answer}""")
            
            return "\n\n".join(examples), filtered[:2]
            
        except Exception as e:
            logger.warning(f"FEW_SHOT_ERROR: {e}")
            return "", []
    
    def build_system_prompt(self) -> str:
        """System Prompt (auto_reply_service._build_system_prompt_v4 동일)"""
        return """ROLE
너는 숙소 운영자를 대신해 게스트에게 실제 사람이 보낸 것처럼 자연스럽고 
신뢰감 있는 답장을 작성한다. 목표는 게스트가 추가 질문 없이, 
이 메시지 하나로 바로 이해하고 행동할 수 있게 하는 것이다.

답변은:
- 짧고 명확해야 하며
- 따뜻하지만 과장되면 안 되고
- 고객센터 공지문이나 AI 같은 말투가 나면 실패다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERNAL CONSIDERATION (출력하지 말 것)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. PROPERTY_INFO에 있는 정보만 사용해서 답변
2. PROPERTY_INFO에 없는 내용은 "확인 후 안내드리겠습니다"
3. 안전 이슈 감지 시: 안부 → 공감 → 조치/안내

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WRITING STYLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
정중하고 부드러운 존댓말을 사용한다.

원칙:
- 문장 끝은 "~습니다", "~입니다", "~세요", "~에요"로 마무리
- 따뜻하지만 격식있는 느낌 유지
- 이모지는 :) 😊 정도만 절제해서 사용 (문장당 최대 1개)

권장 흐름:
① 짧은 인사 ("안녕하세요!")
② 핵심 정보
③ (선택) 부드러운 안내 ("확인 부탁드립니다")
④ 짧은 마무리 ("감사합니다 :)")

금지:
- 반말, 줄임말, "~요~" 같은 과한 친근함
- 앵무새 반복: "~라고 하셨는데", "~라는 말씀 잘 알겠습니다"
- 형식적 표현: "문의 감사드립니다", "안내드립니다", "확인되었습니다"
- 장문 공지문 스타일

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "reply_text": "게스트에게 보낼 최종 답장",
  "outcome": {
    "response_outcome": "ANSWERED_GROUNDED | NEED_FOLLOW_UP | GENERAL_RESPONSE",
    "safety_outcome": "SAFE | SENSITIVE | HIGH_RISK"
  }
}"""

    def build_user_prompt(
        self,
        guest_message: str,
        answer_pack: AnswerPackResult,
        few_shots: str,
        reservation_status: str = "DURING_STAY",
    ) -> str:
        """User Prompt (auto_reply_service._build_user_prompt_v4 동일)"""
        
        prompt_parts = [f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 GUEST_MESSAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{guest_message.strip()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESERVATION_STATUS: {reservation_status}"""]
        
        if few_shots:
            prompt_parts.append(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 FEW_SHOT_EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{few_shots}""")
        
        pack_dict = answer_pack.to_prompt_dict()
        if pack_dict:
            pack_json = json.dumps(pack_dict, ensure_ascii=False, indent=2)
            prompt_parts.append(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 PROPERTY_INFO (선택된 정보만)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{pack_json}

⚠️ 위 정보에 없는 내용은 "확인 후 안내드리겠습니다"로 답변.""")
        
        prompt_parts.append("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
위 정보를 바탕으로 답변을 JSON으로 작성하세요.""")
        
        return "\n".join(prompt_parts)
    
    async def generate_reply(
        self,
        guest_message: str,
        answer_pack: AnswerPackResult,
        few_shots: str,
    ) -> Dict[str, Any]:
        """2차 LLM 호출: 최종 답변 생성"""
        
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(guest_message, answer_pack, few_shots)
        
        try:
            resp = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=MODEL_REPLY_GENERATOR,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )
            
            raw_content = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
            
            return {
                "reply_text": parsed.get("reply_text", ""),
                "outcome": parsed.get("outcome", {}),
                "user_prompt": user_prompt,  # 디버깅용
            }
            
        except Exception as exc:
            logger.error(f"REPLY_GENERATION_ERROR: {exc}")
            return {
                "reply_text": "죄송합니다. 잠시 후 다시 시도해주세요.",
                "outcome": {"response_outcome": "ERROR"},
                "user_prompt": user_prompt,
            }
    
    async def run_e2e_test(
        self,
        guest_message: str,
        property_code: Optional[str] = None,
        show_prompt: bool = False,
    ):
        """전체 E2E 테스트 실행"""
        
        print("\n" + "=" * 70)
        print("🧪 E2E 테스트: AutoReplyService 전체 파이프라인")
        print("=" * 70)
        print(f"\n📨 게스트 메시지: \"{guest_message}\"")
        print(f"🏠 숙소 코드: {property_code or '(미지정)'}")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 1: 1차 LLM - pack_keys 선택
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "-" * 70)
        print("📋 [STEP 1] 1차 LLM 호출 (gpt-4o-mini) - 의도 분석")
        print("-" * 70)
        
        selected_keys = await self.determine_required_keys(guest_message)
        print(f"   ✓ 선택된 pack_keys: {[k.value for k in selected_keys]}")
        
        if not selected_keys:
            selected_keys = list(DEFAULT_FALLBACK_KEYS)
            print(f"   ⚠️ Fallback keys 사용: {[k.value for k in selected_keys]}")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 2: Few-shot 검색
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "-" * 70)
        print("📚 [STEP 2] Few-shot 검색 (임베딩 유사도)")
        print("-" * 70)
        
        few_shots_str, few_shots_raw = self.get_filtered_few_shots(
            guest_message, selected_keys, property_code
        )
        
        if few_shots_raw:
            for i, shot in enumerate(few_shots_raw, 1):
                print(f"\n   [{i}] 유사도: {shot.similarity:.1%} | 숙소: {shot.property_code}")
                print(f"       Q: {shot.guest_message[:50]}...")
                print(f"       A: {shot.final_answer[:50]}...")
        else:
            print("   ❌ Few-shot 없음")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 3: Answer Pack 조회
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "-" * 70)
        print("📦 [STEP 3] Answer Pack 조회")
        print("-" * 70)
        
        if property_code:
            answer_pack = self.pack_service.get_pack(
                property_code=property_code,
                keys=selected_keys,
            )
            
            pack_dict = answer_pack.to_prompt_dict()
            if pack_dict:
                print(f"   ✓ 조회된 정보:")
                for key, value in pack_dict.items():
                    value_str = json.dumps(value, ensure_ascii=False)
                    if len(value_str) > 80:
                        value_str = value_str[:80] + "..."
                    print(f"      - {key}: {value_str}")
            else:
                print("   ⚠️ 반환된 데이터 없음")
        else:
            answer_pack = AnswerPackResult()
            print("   ⚠️ property_code 없음 - Answer Pack 조회 생략")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 4: 2차 LLM - 최종 답변 생성
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "-" * 70)
        print("🤖 [STEP 4] 2차 LLM 호출 (gpt-4.1) - 답변 생성")
        print("-" * 70)
        
        result = await self.generate_reply(guest_message, answer_pack, few_shots_str)
        
        if show_prompt:
            print("\n   📝 User Prompt:")
            print("   " + "-" * 50)
            for line in result["user_prompt"].split("\n"):
                print(f"   {line}")
            print("   " + "-" * 50)
        
        print(f"\n   ✓ Outcome: {result['outcome']}")
        
        # ═══════════════════════════════════════════════════════════════
        # 최종 결과
        # ═══════════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("📤 최종 Draft Reply")
        print("=" * 70)
        print(f"\n{result['reply_text']}")
        print("\n" + "=" * 70)


async def main():
    parser = argparse.ArgumentParser(description="E2E AutoReply 테스트")
    parser.add_argument("message", help="게스트 메시지")
    parser.add_argument("-p", "--property", help="숙소 코드 (예: 2S214, LCN)")
    parser.add_argument("--show-prompt", action="store_true", help="LLM 프롬프트 출력")
    
    args = parser.parse_args()
    
    tester = E2EReplyTester()
    try:
        await tester.run_e2e_test(
            guest_message=args.message,
            property_code=args.property,
            show_prompt=args.show_prompt,
        )
    finally:
        tester.close()


if __name__ == "__main__":
    asyncio.run(main())
