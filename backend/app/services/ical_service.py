"""
iCal Service

iCal 파일 파싱 및 차단 날짜 동기화
- Airbnb iCal URL에서 데이터 fetch
- VEVENT 파싱하여 차단 날짜 추출
- DB에 저장/업데이트
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional
from dataclasses import dataclass

import httpx
from icalendar import Calendar
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.domain.models.ical_blocked_date import IcalBlockedDate
from app.domain.models.property_profile import PropertyProfile

logger = logging.getLogger(__name__)


@dataclass
class BlockedDateEntry:
    """파싱된 차단 날짜 엔트리"""
    blocked_date: date
    summary: Optional[str] = None
    uid: Optional[str] = None


class IcalService:
    """
    iCal 서비스
    
    - fetch: URL에서 iCal 데이터 가져오기
    - parse: iCal 데이터 파싱하여 차단 날짜 추출
    - sync: 특정 property의 iCal 동기화
    - sync_all: 모든 property iCal 동기화
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def fetch_ical(self, url: str, timeout: float = 10.0) -> Optional[str]:
        """
        iCal URL에서 데이터 fetch
        
        Args:
            url: iCal URL
            timeout: 요청 타임아웃 (초) - 기본 10초
        
        Returns:
            iCal 데이터 문자열, 실패시 None
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=timeout, follow_redirects=True)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException:
            logger.error(f"ICAL_SERVICE: Timeout fetching iCal: {url}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"ICAL_SERVICE: Failed to fetch iCal: {url}, error: {e}")
            return None
        except Exception as e:
            logger.error(f"ICAL_SERVICE: Unexpected error fetching iCal: {e}")
            return None
    
    def parse_ical(self, ical_data: str) -> list[BlockedDateEntry]:
        """
        iCal 데이터 파싱하여 차단 날짜 추출
        
        Args:
            ical_data: iCal 데이터 문자열
        
        Returns:
            BlockedDateEntry 리스트
        """
        blocked_dates = []
        
        try:
            cal = Calendar.from_ical(ical_data)
            
            for component in cal.walk():
                if component.name == "VEVENT":
                    # DTSTART, DTEND 추출
                    dtstart = component.get("DTSTART")
                    dtend = component.get("DTEND")
                    summary = str(component.get("SUMMARY", "")) or None
                    uid = str(component.get("UID", "")) or None
                    
                    if not dtstart:
                        continue
                    
                    # date로 변환
                    start_date = self._to_date(dtstart.dt)
                    end_date = self._to_date(dtend.dt) if dtend else start_date
                    
                    if not start_date:
                        continue
                    
                    # end_date는 exclusive (체크아웃 날짜처럼)
                    # start_date부터 end_date-1까지가 실제 차단 날짜
                    current = start_date
                    while current < (end_date or start_date):
                        blocked_dates.append(BlockedDateEntry(
                            blocked_date=current,
                            summary=summary,
                            uid=uid,
                        ))
                        current = date(
                            current.year,
                            current.month,
                            current.day + 1 if current.day < 28 else 1
                        )
                        # 날짜 증가 (간단하게)
                        from datetime import timedelta
                        current = start_date + timedelta(days=(current - start_date).days + 1)
                        if current >= (end_date or date(9999, 12, 31)):
                            break
                    
        except Exception as e:
            logger.error(f"ICAL_SERVICE: Failed to parse iCal: {e}")
        
        return blocked_dates
    
    def _to_date(self, dt) -> Optional[date]:
        """datetime 또는 date를 date로 변환"""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.date()
        if isinstance(dt, date):
            return dt
        return None
    
    def parse_ical_v2(self, ical_data: str) -> list[BlockedDateEntry]:
        """
        iCal 데이터 파싱 (개선 버전)
        - 최대 365일까지만 파싱 (무한 루프 방지)
        """
        blocked_dates = []
        MAX_DAYS_PER_EVENT = 365  # 1년 이상 이벤트는 365일까지만
        
        try:
            cal = Calendar.from_ical(ical_data)
            
            for component in cal.walk():
                if component.name == "VEVENT":
                    dtstart = component.get("DTSTART")
                    dtend = component.get("DTEND")
                    summary = str(component.get("SUMMARY", "")) or None
                    uid = str(component.get("UID", "")) or None
                    
                    if not dtstart:
                        continue
                    
                    start_date = self._to_date(dtstart.dt)
                    end_date = self._to_date(dtend.dt) if dtend else None
                    
                    if not start_date:
                        continue
                    
                    # end_date가 없으면 1일짜리 이벤트
                    if not end_date:
                        end_date = start_date
                    
                    # 최대 날짜 제한 (무한 루프 방지)
                    from datetime import timedelta
                    max_end_date = start_date + timedelta(days=MAX_DAYS_PER_EVENT)
                    if end_date > max_end_date:
                        logger.warning(
                            f"ICAL_SERVICE: Event too long, truncating: "
                            f"{start_date} ~ {end_date} → {start_date} ~ {max_end_date}"
                        )
                        end_date = max_end_date
                    
                    # iCal에서 DTEND는 exclusive
                    # 예: DTSTART=1월5일, DTEND=1월8일 → 5, 6, 7일 차단
                    current = start_date
                    while current < end_date:
                        blocked_dates.append(BlockedDateEntry(
                            blocked_date=current,
                            summary=summary,
                            uid=uid,
                        ))
                        current = current + timedelta(days=1)
                    
        except Exception as e:
            logger.error(f"ICAL_SERVICE: Failed to parse iCal: {e}")
        
        return blocked_dates
    
    async def sync_property(self, property_code: str) -> int:
        """
        특정 property의 iCal 동기화
        
        Args:
            property_code: 숙소 코드
        
        Returns:
            동기화된 차단 날짜 수
        """
        # 1. property_profile에서 ical_url 가져오기
        stmt = select(PropertyProfile).where(
            PropertyProfile.property_code == property_code,
            PropertyProfile.is_active == True,
        )
        profile = self.db.execute(stmt).scalar_one_or_none()
        
        if not profile or not profile.ical_url:
            logger.warning(f"ICAL_SERVICE: No iCal URL for property: {property_code}")
            return 0
        
        # 2. iCal fetch
        ical_data = await self.fetch_ical(profile.ical_url)
        if not ical_data:
            return 0
        
        # 3. 파싱
        blocked_entries = self.parse_ical_v2(ical_data)
        
        # 4. 기존 데이터 삭제 후 새로 삽입 (full replace)
        self.db.execute(
            delete(IcalBlockedDate).where(
                IcalBlockedDate.property_code == property_code
            )
        )
        
        # 5. 새 데이터 삽입
        for entry in blocked_entries:
            self.db.add(IcalBlockedDate(
                property_code=property_code,
                blocked_date=entry.blocked_date,
                summary=entry.summary,
                uid=entry.uid,
            ))
        
        # 6. last_synced_at 업데이트
        profile.ical_last_synced_at = datetime.now(timezone.utc)
        
        self.db.flush()
        
        logger.info(
            f"ICAL_SERVICE: Synced property={property_code}, "
            f"blocked_dates={len(blocked_entries)}"
        )
        
        return len(blocked_entries)
    
    async def sync_all(self) -> dict[str, int]:
        """
        모든 property iCal 동기화
        
        Returns:
            {property_code: 동기화된 날짜 수} 딕셔너리
        """
        # iCal URL이 있는 모든 property 조회
        stmt = select(PropertyProfile).where(
            PropertyProfile.is_active == True,
            PropertyProfile.ical_url.isnot(None),
        )
        profiles = self.db.execute(stmt).scalars().all()
        
        results = {}
        for profile in profiles:
            count = await self.sync_property(profile.property_code)
            results[profile.property_code] = count
        
        return results
    
    def get_blocked_dates(
        self,
        property_code: str,
        start_date: date,
        end_date: date,
    ) -> list[IcalBlockedDate]:
        """
        특정 기간의 차단 날짜 조회
        
        Args:
            property_code: 숙소 코드
            start_date: 시작일 (inclusive)
            end_date: 종료일 (exclusive)
        
        Returns:
            IcalBlockedDate 리스트
        """
        stmt = (
            select(IcalBlockedDate)
            .where(
                IcalBlockedDate.property_code == property_code,
                IcalBlockedDate.blocked_date >= start_date,
                IcalBlockedDate.blocked_date < end_date,
            )
            .order_by(IcalBlockedDate.blocked_date)
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def is_date_blocked(self, property_code: str, check_date: date) -> bool:
        """특정 날짜가 차단되어 있는지 확인"""
        stmt = select(IcalBlockedDate.id).where(
            IcalBlockedDate.property_code == property_code,
            IcalBlockedDate.blocked_date == check_date,
        ).limit(1)
        return self.db.execute(stmt).scalar_one_or_none() is not None
