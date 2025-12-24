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
        return """당신은 에어비앤비 이메일에서 예약 정보를 추출하는 전문가입니다.

## 추출할 정보
이메일 본문에서 다음 정보를 찾아 JSON으로 반환하세요:

- guest_name: 게스트 이름 (예: "서현 윤", "John Smith")
- checkin_date: 체크인 날짜 (YYYY-MM-DD 형식) - 숙박 시작일
- checkout_date: 체크아웃 날짜 (YYYY-MM-DD 형식) - 숙박 종료일, 체크인보다 나중 날짜
- checkin_time: 체크인 시간 (HH:MM 형식, 예: "15:00")
- checkout_time: 체크아웃 시간 (HH:MM 형식, 예: "11:00")
- guest_count: 성인 수 (숫자)
- child_count: 어린이 수 (숫자, 없으면 0)
- infant_count: 유아 수 (숫자, 없으면 0)
- pet_count: 반려동물 수 (숫자, 없으면 0)
- total_price: 총 금액 (숫자만, 원 단위)
- host_payout: 호스트 수령액 (숫자만, 원 단위)
- nights: 숙박 일수 (숫자)
- reservation_code: 예약 코드 (예: "HMXBF24T48")
- listing_name: 숙소 이름

## 중요 규칙
1. 찾을 수 없는 정보는 null로 표시
2. 날짜는 반드시 YYYY-MM-DD 형식 (연도 주의!)
3. 금액에서 쉼표, 원 기호 등 제거하고 숫자만
4. "성인 4명" → guest_count: 4
5. "2026년 2월 2일" → "2026-02-02" (연도 정확히!)

## 체크인/체크아웃 구분 (매우 중요!)
- 이메일에서 "체크인"과 "체크아웃"이 나란히 표시됨
- 체크인: 첫 번째 날짜 (숙박 시작)
- 체크아웃: 두 번째 날짜 (숙박 종료)
- checkout_date는 반드시 checkin_date보다 나중이어야 함
- 예: "체크인 2026년 2월 2일, 체크아웃 2026년 2월 5일" → checkin: "2026-02-02", checkout: "2026-02-05"

## 출력 형식
반드시 JSON만 출력하세요:
{
  "guest_name": "...",
  "checkin_date": "YYYY-MM-DD",
  "checkout_date": "YYYY-MM-DD",
  "checkin_time": "HH:MM",
  "checkout_time": "HH:MM",
  "guest_count": 0,
  "child_count": 0,
  "infant_count": 0,
  "pet_count": 0,
  "total_price": 0,
  "host_payout": 0,
  "nights": 0,
  "reservation_code": "...",
  "listing_name": "..."
}"""

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
    api_key: Optional[str] = None,
) -> ParsedBookingInfo:
    """
    동기 버전 - asyncio가 불편한 곳에서 사용.
    
    내부적으로 OpenAI 동기 API 사용.
    """
    api_key = api_key or _get_api_key()
    if not api_key:
        logger.warning("AIRBNB_EMAIL_PARSER: No API key, returning empty result")
        return ParsedBookingInfo()
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # 이메일 내용 준비
        email_content = text_body or ""
        if subject:
            email_content = f"제목: {subject}\n\n{email_content}"
        
        if len(email_content) > 4000:
            email_content = email_content[:4000]
        
        system_prompt = """당신은 에어비앤비 이메일에서 예약 정보를 추출하는 전문가입니다.

## 추출할 정보
이메일 본문에서 다음 정보를 찾아 JSON으로 반환하세요:

- guest_name: 게스트 이름 (예: "서현 윤", "John Smith")
- checkin_date: 체크인 날짜 (YYYY-MM-DD 형식) - 숙박 시작일
- checkout_date: 체크아웃 날짜 (YYYY-MM-DD 형식) - 숙박 종료일, 체크인보다 나중 날짜
- checkin_time: 체크인 시간 (HH:MM 형식, 예: "15:00")
- checkout_time: 체크아웃 시간 (HH:MM 형식, 예: "11:00")
- guest_count: 성인 수 (숫자)
- child_count: 어린이 수 (숫자, 없으면 0)
- infant_count: 유아 수 (숫자, 없으면 0)
- pet_count: 반려동물 수 (숫자, 없으면 0)
- total_price: 총 금액 (숫자만, 원 단위)
- host_payout: 호스트 수령액 (숫자만, 원 단위)
- nights: 숙박 일수 (숫자)
- reservation_code: 예약 코드 (예: "HMXBF24T48")
- listing_name: 숙소 이름

## 중요 규칙
1. 찾을 수 없는 정보는 null로 표시
2. 날짜는 반드시 YYYY-MM-DD 형식 (연도 주의!)
3. 금액에서 쉼표, 원 기호 등 제거하고 숫자만
4. "성인 4명" → guest_count: 4
5. "2026년 2월 2일" → "2026-02-02" (연도 정확히!)

## 체크인/체크아웃 구분 (매우 중요!)
- 이메일에서 "체크인"과 "체크아웃"이 나란히 표시됨
- 체크인: 첫 번째 날짜 (숙박 시작)
- 체크아웃: 두 번째 날짜 (숙박 종료)
- checkout_date는 반드시 checkin_date보다 나중이어야 함
- 예: "체크인 2026년 2월 2일, 체크아웃 2026년 2월 5일" → checkin: "2026-02-02", checkout: "2026-02-05"

## 출력 형식
반드시 JSON만 출력하세요."""
        
        user_prompt = f"다음 에어비앤비 이메일에서 예약 정보를 추출해주세요:\n\n{email_content}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
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
