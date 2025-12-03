"""create auto_reply_templates table

down_revision = "20251201_add_pure_guest_and_intent_labels"
Revision ID: 20251202_add_auto_reply_templates
Revises: 2025xxxx_add_pure_guest_and_intent_labels
Create Date: 2025-12-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251202_add_auto_reply_templates"
down_revision = "2025xxxx_add_pure_guest_and_intent_labels"  # 👈 여기를 실제 이전 revision 값으로 바꿔줄 것
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auto_reply_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        # 활성/비활성 플래그
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        # 운영자용 템플릿 이름
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),

        # Intent 코드 (예: CHECKIN_QUESTION, GENERAL_QUESTION ...)
        sa.Column(
            "intent",
            sa.String(length=64),
            nullable=False,
        ),

        # 언어/로케일
        sa.Column(
            "locale",
            sa.String(length=16),
            nullable=False,
            server_default="ko",
        ),

        # 채널 (airbnb / booking / naver / generic …)
        sa.Column(
            "channel",
            sa.String(length=32),
            nullable=False,
            server_default="generic",
        ),

        # 특정 숙소 전용 템플릿이면 사용 (없으면 글로벌)
        sa.Column(
            "property_code",
            sa.String(length=64),
            nullable=True,
        ),

        # 제목 템플릿 (이메일/메시지 제목)
        sa.Column(
            "subject_template",
            sa.String(length=255),
            nullable=True,
        ),

        # 본문 템플릿 (실제 자동응답 텍스트)
        sa.Column(
            "body_template",
            sa.Text(),
            nullable=False,
        ),

        # 사용되는 플레이스홀더 메타데이터 (["guest_name", "checkin_time"] 등)
        sa.Column(
            "placeholders",
            sa.JSON(),
            nullable=True,
        ),

        # 숫자가 작을수록 높은 우선순위
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),

        # 이 템플릿이 추천되기 위한 최소/최대 intent confidence
        sa.Column(
            "min_intent_confidence",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "max_intent_confidence",
            sa.Float(),
            nullable=True,
        ),

        # 자동발송 관련 설정
        sa.Column(
            "auto_send_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "auto_send_max_confidence",
            sa.Float(),
            nullable=True,
        ),
    )

    # 인덱스 몇 개 추가 (쿼리 패턴에 맞게)
    op.create_index(
        "ix_auto_reply_templates_intent_locale_channel",
        "auto_reply_templates",
        ["intent", "locale", "channel"],
    )
    op.create_index(
        "ix_auto_reply_templates_property_code",
        "auto_reply_templates",
        ["property_code"],
    )
    op.create_index(
        "ix_auto_reply_templates_is_active",
        "auto_reply_templates",
        ["is_active"],
    )

    # server_default 제거 (원하면)
    op.alter_column(
        "auto_reply_templates",
        "is_active",
        server_default=None,
    )
    op.alter_column(
        "auto_reply_templates",
        "locale",
        server_default=None,
    )
    op.alter_column(
        "auto_reply_templates",
        "channel",
        server_default=None,
    )
    op.alter_column(
        "auto_reply_templates",
        "priority",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auto_reply_templates_is_active",
        table_name="auto_reply_templates",
    )
    op.drop_index(
        "ix_auto_reply_templates_property_code",
        table_name="auto_reply_templates",
    )
    op.drop_index(
        "ix_auto_reply_templates_intent_locale_channel",
        table_name="auto_reply_templates",
    )
    op.drop_table("auto_reply_templates")