"""add origin and intent fields to incoming_messages

Revision ID: 2025xxxx_add_origin_and_intent
Revises: <이전_revision_id>
Create Date: 2025-xx-xx xx:xx:xx.XXX
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2025xxxx_add_origin_and_intent"
down_revision = "<이전_revision_id>"  # 실제 값으로 교체
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) ENUM 타입 생성 (Postgres 기준)
    message_actor_enum = sa.Enum(
        "guest",
        "host",
        "system",
        "unknown",
        name="message_actor",
    )
    message_actionability_enum = sa.Enum(
        "needs_reply",
        "outgoing_copy",
        "system_notification",
        "fyi",
        "unknown",
        name="message_actionability",
    )
    message_intent_enum = sa.Enum(
        # MessageIntent Enum 이름 기준 (CHECKIN_QUESTION 등) → DB에는 name이 저장됨
        "CHECKIN_QUESTION",
        "CHECKOUT_QUESTION",
        "RESERVATION_CHANGE",
        "CANCELLATION",
        "COMPLAINT",
        "LOCATION_QUESTION",
        "AMENITY_QUESTION",
        "GENERAL_QUESTION",
        "THANKS_OR_GOOD_REVIEW",
        "OTHER",
        name="message_intent",
    )

    message_actor_enum.create(op.get_bind(), checkfirst=True)
    message_actionability_enum.create(op.get_bind(), checkfirst=True)
    message_intent_enum.create(op.get_bind(), checkfirst=True)

    # 2) 컬럼 추가
    op.add_column(
        "incoming_messages",
        sa.Column(
            "sender_actor",
            message_actor_enum,
            nullable=True,  # 기존 데이터 때문에 우선 nullable=True 로 추가
        ),
    )
    op.add_column(
        "incoming_messages",
        sa.Column(
            "actionability",
            message_actionability_enum,
            nullable=True,
        ),
    )
    op.add_column(
        "incoming_messages",
        sa.Column(
            "intent",
            message_intent_enum,
            nullable=True,
        ),
    )
    op.add_column(
        "incoming_messages",
        sa.Column(
            "intent_confidence",
            sa.Float(),
            nullable=True,
        ),
    )

    # 3) 기존 데이터에 대해 기본값 세팅 (원하면 여기서 UPDATE)
    # 예: 모두 UNKNOWN으로 초기화
    op.execute(
        "UPDATE incoming_messages "
        "SET sender_actor = 'unknown', actionability = 'unknown' "
        "WHERE sender_actor IS NULL OR actionability IS NULL"
    )

    # 4) 이제 NOT NULL 로 바꾸고 싶다면 (선택)
    op.alter_column(
        "incoming_messages",
        "sender_actor",
        existing_type=message_actor_enum,
        nullable=False,
    )
    op.alter_column(
        "incoming_messages",
        "actionability",
        existing_type=message_actionability_enum,
        nullable=False,
    )


def downgrade() -> None:
    # 컬럼 삭제 전에 NOT NULL → NULL 허용으로 되돌릴 필요가 있을 수도 있지만,
    # 보통은 바로 drop 해도 무방.
    op.drop_column("incoming_messages", "intent_confidence")
    op.drop_column("incoming_messages", "intent")
    op.drop_column("incoming_messages", "actionability")
    op.drop_column("incoming_messages", "sender_actor")

    # ENUM 타입 삭제
    op.execute("DROP TYPE IF EXISTS message_intent")
    op.execute("DROP TYPE IF EXISTS message_actionability")
    op.execute("DROP TYPE IF EXISTS message_actor")