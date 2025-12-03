from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class AutoReplyRecommendation(BaseModel):
    """
    Intent 기반 자동응답 추천 결과 DTO.

    FE 메시지 상세 우측 패널에 그대로 내려줄 수 있는 형태로 설계.
    """

    model_config = ConfigDict(from_attributes=True)

    template_id: int = Field(..., description="추천에 사용된 AutoReplyTemplate ID")
    intent: str = Field(..., description="템플릿이 대응하는 intent 코드")
    locale: str = Field(..., description="템플릿의 로케일 (e.g. ko-KR)")
    channel: str = Field(..., description="템플릿 채널 (airbnb 등)")

    name: str = Field(..., description="템플릿 내부 관리용 이름")
    preview_subject: Optional[str] = Field(
        None,
        description="렌더링된 subject (없으면 None)",
    )
    preview_body: str = Field(
        ...,
        description="게스트/숙소 컨텍스트까지 일부 반영된 응답 본문 Preview",
    )

    score: float = Field(
        ...,
        description="추천 스코어 (0~1 정규화 권장)",
    )

    auto_send_suggested: bool = Field(
        ...,
        description="이 응답을 자동 발송 후보로 추천할지 여부",
    )

    reason: str = Field(
        ...,
        description="추천/스코어링에 대한 간단한 설명 (FE Tooltips/Debug 용도)",
    )
