# backend/app/services/closing_message_detector.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClosingDetectionResult:
    is_closing: bool
    reason: str


class ClosingMessageDetector:
    """
    게스트 메시지가 '대화를 사실상 종료하는 감사/마무리 메시지'인지 판별하는 컴포넌트.

    현재 구현:
      - LLMClient 의존성을 제거하고, 가벼운 규칙 기반(rule-based) 판별만 수행.
      - 나중에 정교한 LLM 기반 감지가 필요해지면, 이 클래스 내부에 LLM 연동 로직을
        옵션으로 추가(또는 별도 전략 객체 주입)하는 방향으로 확장 가능.
    """

    def __init__(self) -> None:
        # 현재는 별도 초기화할 외부 리소스 없음
        ...

    async def detect(self, text: str) -> ClosingDetectionResult:
        """
        비동기 인터페이스 유지(호출부가 await 하고 있으므로),
        내부에서는 동기 rule-based 로직만 수행.
        """
        if not text or not text.strip():
            return ClosingDetectionResult(False, "empty_or_whitespace")

        t = text.strip()

        # 1) 질문/요청이 명확하면 closing 아님
        question_keywords = ["?", "문의", "궁금", "알려", "가능할까요", "될까요", "혹시", "예약 가능한가요"]
        if any(k in t for k in question_keywords):
            return ClosingDetectionResult(
                is_closing=False,
                reason="question_or_request_keyword_detected",
            )

        # 2) 전형적인 감사/마무리 표현이 포함되면 closing 가능성 높음
        closing_keywords = [
            "감사합니다", "감사해요", "고맙습니다", "고맙어요",
            "덕분에", "수고하셨어요", "수고 많으셨어요",
            "좋은 하루 보내세요", "좋은 밤 되세요",
            "수고하세요", "덕분에 잘", "잘 이용하겠습니다", "잘 이용했어요", "잘 머물렀습니다",
            # 🆕 확인/동의 표현 추가
            "알겠습니다", "알겠어요", "네 알겠", "넵 알겠", "확인했습니다", "확인했어요",
            "네 감사", "넵 감사", "넵!", "네!", "ok", "okay",
        ]
        if any(k in t for k in closing_keywords):
            return ClosingDetectionResult(
                is_closing=True,
                reason="closing_keyword_detected",
            )

        # 3) 도착/체크인 완료 공유 + 추가 질문 없음 → closing 으로 간주
        #    예: "잘 도착했습니다", "체크인 완료했습니다 감사합니다"
        arrival_keywords = ["잘 도착", "체크인 했습니다", "체크인 완료", "잘 들어왔습니다"]
        if any(k in t for k in arrival_keywords):
            return ClosingDetectionResult(
                is_closing=True,
                reason="arrival_completion_message",
            )

        # 그 외는 기본적으로 closing 아님
        return ClosingDetectionResult(
            is_closing=False,
            reason="no_strong_closing_signal",
        )
