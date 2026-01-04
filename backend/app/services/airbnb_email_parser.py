"""
Airbnb Email Parser - LLM 기반 범용 이메일 파서

이메일 형식이 바뀌어도 대응 가능한 LLM 기반 파싱.
정규식 대신 LLM이 이메일 본문을 읽고 구조화된 정보를 추출.

Usage:
    parser = AirbnbEmailParser(api_key="sk-...")
    result = await parser.parse_booking_confirmation(email_body)
    # result.guest_name, result.checkin_date, ...
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


def _get_api_key() -> Optional[str]:
    """설정에서 LLM API 키 가져오기"""
    try:
        from app.core.config import settings
        return settings.LLM_API_KEY
    except Exception:
        import os
        return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")


@dataclass
class ParsedBookingInfo:
    """예약 확정 이메일에서 추출한 정보"""
    guest_name: Optional[str] = None
    checkin_date: Optional[date] = None
    checkout_date: Optional[date] = None
    checkin_time: Optional[str] = None   # "15:00"
    checkout_time: Optional[str] = None  # "11:00"
    guest_count: Optional[int] = None    # 성인
    child_count: Optional[int] = None    # 어린이
    infant_count: Optional[int] = None   # 유아
    pet_count: Optional[int] = None      # 반려동물
    total_price: Optional[int] = None    # 총 금액 (원)
    host_payout: Optional[int] = None    # 호스트 수령액 (원)
    nights: Optional[int] = None         # 박 수
    reservation_code: Optional[str] = None
    listing_name: Optional[str] = None
    raw_response: Optional[str] = None   # 디버깅용


class AirbnbEmailParser:
    """
    LLM 기반 Airbnb 이메일 파서.
    
    이메일 본문을 LLM에게 보내서 구조화된 정보를 추출.
    형식이 바뀌어도 자동 대응 가능.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self._api_key = api_key or _get_api_key()
        self._model = model
    
    async def parse_booking_confirmation(
        self,
        text_body: Optional[str],
        html_body: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> ParsedBookingInfo:
        """
        예약 확정 이메일에서 예약 정보 추출.
        
        Args:
            text_body: 이메일 텍스트 본문
            html_body: 이메일 HTML 본문 (선택)
            subject: 이메일 제목 (선택)
        
        Returns:
            ParsedBookingInfo: 추출된 예약 정보
        """
        if not self._api_key:
            logger.warning("AIRBNB_EMAIL_PARSER: No API key, returning empty result")
            return ParsedBookingInfo()
        
        try:
            # 텍스트 본문 우선 사용 (더 깔끔함)
            email_content = text_body or ""
            if subject:
                email_content = f"제목: {subject}\n\n{email_content}"
            
            # 너무 길면 잘라내기 (토큰 절약)
            if len(email_content) > 4000:
                email_content = email_content[:4000]
            
            raw_response = await self._call_llm(email_content)
            return self._parse_response(raw_response)
            
        except Exception as e:
            logger.warning(f"AIRBNB_EMAIL_PARSER: Parse failed: {e}")
            return ParsedBookingInfo()
    
    async def _call_llm(self, email_content: str) -> str:
        """LLM API 호출"""
        from openai import OpenAI
        
        client = OpenAI(api_key=self._api_key)
        
        system_prompt = self._build_system_prompt()
        user_prompt = f"다음 에어비앤비 이메일에서 예약 정보를 추출해주세요:\n\n{email_content}"
        
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,  # 일관된 추출
            response_format={"type": "json_object"},
        )
        
        return response.choices[0].message.content or "{}"
    
    def _build_system_prompt(self) -> str:
        """시스템 프롬프트"""
        from datetime import date as date_class
        today = date_class.today()
        current_year = today.year
        current_date_str = today.isoformat()
        
        return f"""당신은 에어비앤비 이메일에서 예약 정보를 추출하는 전문가입니다.

## 현재 날짜 정보
오늘 날짜: {current_date_str}
현재 연도: {current_year}

## 추출할 정보
이메일 본문에서 다음 정보를 찾아 JSON으로 반환하세요:

- guest_name: 게스트 이름 (한글, 영어, 중국어, 일본어 등 모든 언어 지원)
- checkin_date: 체크인 날짜 (YYYY-MM-DD 형식) - 숙박 시작일
- checkout_date: 체크아웃 날짜 (YYYY-MM-DD 형식) - 숙박 종료일, 체크인보다 나중 날짜
- checkin_time: 체크인 시간 (HH:MM 형식, 예: "15:00")
- checkout_time: 체크아웃 시간 (HH:MM 형식, 예: "11:00")
- guest_count: 성인 수 (숫자)
- child_count: 어린이 수 (숫자)
- infant_count: 유아 수 (숫자)
- pet_count: 반려동물 수 (숫자)
- total_price: 총 금액 (숫자만, 원 단위)
- host_payout: 호스트 수령액 또는 예상 수입 (숫자만, 원 단위)
- nights: 숙박 일수 (숫자)
- reservation_code: 예약 코드 (예: "HMXBF24T48")
- listing_name: 숙소 이름

## 핵심 규칙 (반드시 준수)
1. **이메일에 명시된 정보만 추출** - 추측/계산/예측 절대 금지
2. **찾을 수 없는 정보는 반드시 null** - 빈 문자열("") 사용 금지
3. **0과 null 구분**: 
   - "성인 2명" (어린이 언급 없음) → child_count: null (모름)
   - "성인 2명, 어린이 0명" → child_count: 0 (명시적으로 0명)
4. 날짜는 반드시 YYYY-MM-DD 형식 (연도 주의!)
5. 금액에서 쉼표, 원 기호 등 제거하고 숫자만
6. "성인 4명" → guest_count: 4
7. 게스트 이름: "OOO님의 예약 요청에 답하세요" → OOO 추출

## 체크인/체크아웃 구분 (매우 중요!)
- 이메일에서 "체크인"과 "체크아웃"이 나란히 표시됨
- 체크인: 첫 번째 날짜 (숙박 시작)
- 체크아웃: 두 번째 날짜 (숙박 종료)
- checkout_date는 반드시 checkin_date보다 나중이어야 함
- 예: "체크인 2026년 2월 2일, 체크아웃 2026년 2월 5일" → checkin: "2026-02-02", checkout: "2026-02-05"

## 연도 처리 규칙 (매우 중요!)
- 이메일에 **연도가 명시된 경우**: 해당 연도 사용 (예: "2026년 2월 5일" → 2026)
- 이메일에 **연도가 없는 경우**: 현재 연도({current_year}) 사용 (예: "12월 29일" → {current_year}-12-29)
- 단, 현재 월보다 이전 월이고 예약이 미래여야 한다면 다음 연도 사용
  (예: 오늘이 12월인데 "1월 5일" 체크인 → 다음 해인 {current_year + 1}년)

## 출력 형식
반드시 JSON만 출력하세요."""

    def _parse_response(self, raw_response: str) -> ParsedBookingInfo:
        """LLM 응답을 ParsedBookingInfo로 변환"""
        try:
            data = json.loads(raw_response)
            
            # 날짜 변환
            checkin_date = None
            checkout_date = None
            
            if data.get("checkin_date"):
                try:
                    parts = data["checkin_date"].split("-")
                    checkin_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, IndexError):
                    pass
            
            if data.get("checkout_date"):
                try:
                    parts = data["checkout_date"].split("-")
                    checkout_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, IndexError):
                    pass
            
            return ParsedBookingInfo(
                guest_name=data.get("guest_name"),
                checkin_date=checkin_date,
                checkout_date=checkout_date,
                checkin_time=data.get("checkin_time"),
                checkout_time=data.get("checkout_time"),
                guest_count=data.get("guest_count"),
                child_count=data.get("child_count"),
                infant_count=data.get("infant_count"),
                pet_count=data.get("pet_count"),
                total_price=data.get("total_price"),
                host_payout=data.get("host_payout"),
                nights=data.get("nights"),
                reservation_code=data.get("reservation_code"),
                listing_name=data.get("listing_name"),
                raw_response=raw_response,
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"AIRBNB_EMAIL_PARSER: JSON parse error: {e}")
            return ParsedBookingInfo(raw_response=raw_response)


# Sync wrapper for non-async contexts
def parse_booking_confirmation_sync(
    text_body: Optional[str],
    html_body: Optional[str] = None,
    subject: Optional[str] = None,
    openai_client=None,
) -> ParsedBookingInfo:
    """
    동기 버전 - asyncio가 불편한 곳에서 사용.
    
    Args:
        text_body: 이메일 텍스트 본문
        html_body: 이메일 HTML 본문
        subject: 이메일 제목
        openai_client: OpenAI 클라이언트 (DI, 없으면 싱글톤 사용)
    """
    # DI 또는 싱글톤
    if openai_client is None:
        try:
            from app.adapters.llm_client import get_openai_client
            openai_client = get_openai_client()
        except Exception:
            pass
    
    if not openai_client:
        logger.warning("AIRBNB_EMAIL_PARSER: No OpenAI client, returning empty result")
        return ParsedBookingInfo()
    
    try:
        # 이메일 내용 준비
        email_content = text_body or ""
        if subject:
            email_content = f"제목: {subject}\n\n{email_content}"
        
        if len(email_content) > 4000:
            email_content = email_content[:4000]
        
        # 현재 날짜 정보 (년도 추론용)
        from datetime import date as date_class
        today = date_class.today()
        current_year = today.year
        current_date_str = today.isoformat()
        
        system_prompt = f"""당신은 에어비앤비 이메일에서 예약 정보를 추출하는 전문가입니다.

## 현재 날짜 정보
오늘 날짜: {current_date_str}
현재 연도: {current_year}

## 추출할 정보
이메일 본문에서 다음 정보를 찾아 JSON으로 반환하세요:

- guest_name: 게스트 이름 (한글, 영어, 중국어, 일본어 등 모든 언어 지원)
- checkin_date: 체크인 날짜 (YYYY-MM-DD 형식) - 숙박 시작일
- checkout_date: 체크아웃 날짜 (YYYY-MM-DD 형식) - 숙박 종료일, 체크인보다 나중 날짜
- checkin_time: 체크인 시간 (HH:MM 형식, 예: "15:00")
- checkout_time: 체크아웃 시간 (HH:MM 형식, 예: "11:00")
- guest_count: 성인 수 (숫자)
- child_count: 어린이 수 (숫자)
- infant_count: 유아 수 (숫자)
- pet_count: 반려동물 수 (숫자)
- total_price: 총 금액 (숫자만, 원 단위)
- host_payout: 호스트 수령액 또는 예상 수입 (숫자만, 원 단위)
- nights: 숙박 일수 (숫자)
- reservation_code: 예약 코드 (예: "HMXBF24T48")
- listing_name: 숙소 이름

## 핵심 규칙 (반드시 준수)
1. **이메일에 명시된 정보만 추출** - 추측/계산/예측 절대 금지
2. **찾을 수 없는 정보는 반드시 null** - 빈 문자열("") 사용 금지
3. **0과 null 구분**: 
   - "성인 2명" (어린이 언급 없음) → child_count: null (모름)
   - "성인 2명, 어린이 0명" → child_count: 0 (명시적으로 0명)
4. 날짜는 반드시 YYYY-MM-DD 형식 (연도 주의!)
5. 금액에서 쉼표, 원 기호 등 제거하고 숫자만
6. "성인 4명" → guest_count: 4
7. 게스트 이름: "OOO님의 예약 요청에 답하세요" → OOO 추출

## 체크인/체크아웃 구분 (매우 중요!)
- 이메일에서 "체크인"과 "체크아웃"이 나란히 표시됨
- 체크인: 첫 번째 날짜 (숙박 시작)
- 체크아웃: 두 번째 날짜 (숙박 종료)
- checkout_date는 반드시 checkin_date보다 나중이어야 함
- 예: "체크인 2026년 2월 2일, 체크아웃 2026년 2월 5일" → checkin: "2026-02-02", checkout: "2026-02-05"

## 연도 처리 규칙 (매우 중요!)
- 이메일에 **연도가 명시된 경우**: 해당 연도 사용 (예: "2026년 2월 5일" → 2026)
- 이메일에 **연도가 없는 경우**: 현재 연도({current_year}) 사용 (예: "12월 29일" → {current_year}-12-29)
- 단, 현재 월보다 이전 월이고 예약이 미래여야 한다면 다음 연도 사용
  (예: 오늘이 12월인데 "1월 5일" 체크인 → 다음 해인 {current_year + 1}년)

## 출력 형식
반드시 JSON만 출력하세요."""
        
        user_prompt = f"다음 에어비앤비 이메일에서 예약 정보를 추출해주세요:\n\n{email_content}"
        
        # 파싱용 모델 사용 (비용 절감)
        from app.core.config import settings
        model = settings.LLM_MODEL_PARSER
        
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        
        raw_response = response.choices[0].message.content or "{}"
        
        # JSON 파싱
        data = json.loads(raw_response)
        
        # 날짜 변환
        checkin_date = None
        checkout_date = None
        
        if data.get("checkin_date"):
            try:
                parts = data["checkin_date"].split("-")
                checkin_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        
        if data.get("checkout_date"):
            try:
                parts = data["checkout_date"].split("-")
                checkout_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        
        return ParsedBookingInfo(
            guest_name=data.get("guest_name"),
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            checkin_time=data.get("checkin_time"),
            checkout_time=data.get("checkout_time"),
            guest_count=data.get("guest_count"),
            child_count=data.get("child_count"),
            infant_count=data.get("infant_count"),
            pet_count=data.get("pet_count"),
            total_price=data.get("total_price"),
            host_payout=data.get("host_payout"),
            nights=data.get("nights"),
            reservation_code=data.get("reservation_code"),
            listing_name=data.get("listing_name"),
            raw_response=raw_response,
        )
        
    except Exception as e:
        logger.warning(f"AIRBNB_EMAIL_PARSER: Parse failed: {e}")
        return ParsedBookingInfo()
