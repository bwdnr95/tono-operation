from typing import Optional

from app.domain.intents import Intent
from backend.app.domain.email_message import IncomingMessage, ClassificationResult
from app.services.reply_policy import build_reply_decision
from .base import MessageClassifier


class KeywordClassifier(MessageClassifier):
    """
    v0.2 키워드 기반 분류기.
    - Intent: 대분류
    - sub_intent: 세부 유형
    """

    def classify(self, message: IncomingMessage) -> ClassificationResult:
        text = (message.raw_message or "").lower()

        def has(*keywords: str) -> bool:
            return any(k in text for k in keywords)

        intent = Intent.OTHER
        sub_intent: Optional[str] = None
        confidence = 0.5

        # ---- CHECKIN 계열 ----
        if has(
            "early check-in",
            "early check in",
            "얼리 체크인",
            "조기 체크인",
            "일찍 들어가",
            "체크인 시간 앞당겨",
            "조금 일찍",
            "early checkin",
        ):
            intent = Intent.CHECKIN
            sub_intent = "early_checkin"
            confidence = 0.9

        elif has(
            "짐 보관",
            "캐리어 보관",
            "luggage",
            "leave my bags",
            "drop my bags",
            "보관해둘 수",
            "can i leave my bags",
            "can we leave our bags",
        ):
            intent = Intent.CHECKIN
            sub_intent = "luggage_storage"
            confidence = 0.9

        elif has(
            "check in",
            "check-in",
            "체크인",
            "입실",
            "도어락",
            "door lock",
            "비밀번호",
            "비번",
        ):
            intent = Intent.CHECKIN
            sub_intent = "checkin_general"
            confidence = 0.85

        # ---- CHECKOUT ----
        elif has("check out", "check-out", "체크아웃", "퇴실"):
            intent = Intent.CHECKOUT
            sub_intent = "checkout_general"
            confidence = 0.9

        # ---- LOCATION / PARKING ----
        elif has("위치", "가는 길", "how to get", "where", "오시는 길", "주소", "address"):
            intent = Intent.LOCATION
            sub_intent = "directions"
            confidence = 0.85

        elif has("주차", "parking", "park my car", "주차장", "주차 가능", "차를 세울", "parking lot"):
            intent = Intent.LOCATION
            sub_intent = "parking"
            confidence = 0.85

        # ---- AMENITIES ----
        elif has("수건", "towel", "이불", "침구", "베개", "linens"):
            intent = Intent.TOWEL_LINEN
            sub_intent = "towel_linen_request"
            confidence = 0.8

        elif has("온수", "hot water", "보일러", "난방", "heater", "히터", "따뜻", "뜨거운 물"):
            intent = Intent.HOT_WATER_HEATING
            sub_intent = "hot_water_heating_issue"
            confidence = 0.85

        # ---- COMPLAINT / REFUND / CHANGE ----
        elif has("소음", "noise", "시끄럽", "층간소음", "loud", "noisy"):
            intent = Intent.NOISE
            sub_intent = "noise_complaint"
            confidence = 0.9

        elif has(
            "취소",
            "cancel",
            "환불",
            "refund",
            "예약 변경",
            "change my dates",
            "날짜 변경",
            "change reservation",
            "modify reservation",
        ):
            intent = Intent.REFUND_CHANGE
            sub_intent = "refund_or_change"
            confidence = 0.9

        else:
            intent = Intent.OTHER
            sub_intent = None
            confidence = 0.5

        # 인텐트별 기본 정책
        decision = build_reply_decision(intent)
        auto_reply = decision.auto_reply
        need_human = decision.need_human

        # 안전장치: confidence 낮으면 자동응답 막기
        if confidence < 0.7:
            auto_reply = False
            need_human = True

        return ClassificationResult(
            intent=intent,
            confidence=confidence,
            auto_reply=auto_reply,
            need_human=need_human,
            reply_text=decision.reply_text,
            sub_intent=sub_intent,
        )