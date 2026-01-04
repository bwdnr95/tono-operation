# backend/app/domain/models/complaint.py
"""
Complaint 도메인 모델

게스트가 제기한 불만/문제를 기록하는 테이블.
숙소별 문제 패턴 분석, 운영 개선에 활용.

생성 시점: 게스트 메시지 수신 시 LLM이 불만/문제 감지하면 생성
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base import Base


# ─────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────

class ComplaintCategory(str, Enum):
    """불만/문제 카테고리"""
    
    # 시설 관련
    facility = "facility"                  # 시설 고장/문제 (일반)
    hot_water = "hot_water"                # 온수 문제
    heating_cooling = "heating_cooling"    # 냉난방 문제
    wifi = "wifi"                          # 와이파이 문제
    appliance = "appliance"                # 가전제품 문제
    plumbing = "plumbing"                  # 배관/수도 문제
    electrical = "electrical"              # 전기 문제
    door_lock = "door_lock"                # 도어락/잠금장치 문제
    
    # 청결 관련
    cleanliness = "cleanliness"            # 청소 불만 (일반)
    bedding = "bedding"                    # 침구류 문제
    bathroom = "bathroom"                  # 화장실 청결
    kitchen = "kitchen"                    # 주방 청결
    
    # 환경 관련
    noise = "noise"                        # 소음
    smell = "smell"                        # 냄새
    pest = "pest"                          # 벌레/해충
    temperature = "temperature"            # 실내 온도 문제
    
    # 안전 관련
    safety = "safety"                      # 안전 문제
    security = "security"                  # 보안 문제
    
    # 정보/기대 불일치
    description_mismatch = "description_mismatch"  # 숙소 설명과 다름
    amenity_missing = "amenity_missing"            # 어메니티 누락
    
    # 서비스 관련
    communication = "communication"        # 소통 문제
    access = "access"                      # 출입/접근 문제
    
    # 기타
    other = "other"                        # 기타
    
    @classmethod
    def facility_related(cls) -> set[str]:
        """시설 관련 카테고리"""
        return {
            cls.facility.value,
            cls.hot_water.value,
            cls.heating_cooling.value,
            cls.wifi.value,
            cls.appliance.value,
            cls.plumbing.value,
            cls.electrical.value,
            cls.door_lock.value,
        }
    
    @classmethod
    def cleanliness_related(cls) -> set[str]:
        """청결 관련 카테고리"""
        return {
            cls.cleanliness.value,
            cls.bedding.value,
            cls.bathroom.value,
            cls.kitchen.value,
        }


class ComplaintSeverity(str, Enum):
    """심각도"""
    low = "low"           # 불편하지만 이용 가능
    medium = "medium"     # 불편함, 조치 필요
    high = "high"         # 심각한 불편, 즉시 조치
    critical = "critical" # 이용 불가, 긴급 대응


class ComplaintStatus(str, Enum):
    """처리 상태"""
    open = "open"               # 접수됨 (미처리)
    in_progress = "in_progress" # 처리 중
    resolved = "resolved"       # 해결됨
    dismissed = "dismissed"     # 기각/해당없음


# ─────────────────────────────────────────────────────────────
# SQLAlchemy Model
# ─────────────────────────────────────────────────────────────

class Complaint(Base):
    """
    게스트 불만/문제 기록
    
    게스트 메시지에서 불만/문제가 감지되면 자동 생성.
    숙소별 문제 패턴 분석, 운영 개선에 활용.
    """
    __tablename__ = "complaints"
    
    # PK
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 관계
    conversation_id = Column(
        PGUUID(as_uuid=True), 
        ForeignKey("conversations.id", ondelete="CASCADE"), 
        nullable=False,
        index=True,
    )
    provenance_message_id = Column(
        Integer, 
        ForeignKey("incoming_messages.id", ondelete="SET NULL"), 
        nullable=True,
    )
    
    # 분류
    category = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default=ComplaintSeverity.medium.value)
    
    # 내용
    description = Column(Text, nullable=False)  # "온수가 안 나와요"
    evidence_quote = Column(Text, nullable=True)  # 게스트 원문 인용
    
    # 상태
    status = Column(String(32), nullable=False, default=ComplaintStatus.open.value, index=True)
    resolution_note = Column(Text, nullable=True)  # 해결 방법/결과
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(64), nullable=True)  # "system" | "host" | host_id
    
    # 메타
    extraction_confidence = Column(Float, nullable=False, default=0.0)
    property_code = Column(String(64), nullable=False, index=True)
    
    # 타임스탬프
    reported_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)  # 신고 시점
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<Complaint {self.id} category={self.category} status={self.status}>"
    
    # ─────────────────────────────────────────────────────────
    # 비즈니스 로직
    # ─────────────────────────────────────────────────────────
    
    def resolve(self, note: str, resolved_by: str = "host") -> None:
        """Complaint 해결 처리"""
        self.status = ComplaintStatus.resolved.value
        self.resolution_note = note
        self.resolved_at = datetime.utcnow()
        self.resolved_by = resolved_by
    
    def dismiss(self, reason: str, dismissed_by: str = "host") -> None:
        """Complaint 기각 (해당없음)"""
        self.status = ComplaintStatus.dismissed.value
        self.resolution_note = reason
        self.resolved_at = datetime.utcnow()
        self.resolved_by = dismissed_by
    
    def start_progress(self) -> None:
        """처리 중 상태로 변경"""
        self.status = ComplaintStatus.in_progress.value
    
    @property
    def is_open(self) -> bool:
        """미처리 상태인지"""
        return self.status in (ComplaintStatus.open.value, ComplaintStatus.in_progress.value)
    
    @property
    def is_facility_related(self) -> bool:
        """시설 관련 문제인지"""
        return self.category in ComplaintCategory.facility_related()
    
    @property
    def is_cleanliness_related(self) -> bool:
        """청결 관련 문제인지"""
        return self.category in ComplaintCategory.cleanliness_related()


# ─────────────────────────────────────────────────────────────
# Label 매핑 (UI 표시용)
# ─────────────────────────────────────────────────────────────

COMPLAINT_CATEGORY_LABELS = {
    "facility": "시설 문제",
    "hot_water": "온수",
    "heating_cooling": "냉난방",
    "wifi": "와이파이",
    "appliance": "가전제품",
    "plumbing": "배관/수도",
    "electrical": "전기",
    "door_lock": "도어락",
    "cleanliness": "청소",
    "bedding": "침구류",
    "bathroom": "화장실",
    "kitchen": "주방",
    "noise": "소음",
    "smell": "냄새",
    "pest": "벌레/해충",
    "temperature": "실내 온도",
    "safety": "안전",
    "security": "보안",
    "description_mismatch": "설명과 다름",
    "amenity_missing": "어메니티 누락",
    "communication": "소통",
    "access": "출입/접근",
    "other": "기타",
}

COMPLAINT_SEVERITY_LABELS = {
    "low": "낮음",
    "medium": "보통",
    "high": "높음",
    "critical": "긴급",
}

COMPLAINT_STATUS_LABELS = {
    "open": "접수됨",
    "in_progress": "처리 중",
    "resolved": "해결됨",
    "dismissed": "기각",
}
