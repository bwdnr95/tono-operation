from alembic import op
import sqlalchemy as sa

revision = "2025xxxx_add_pure_guest_and_intent_labels"
down_revision = "<이전_revision_id>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ENUM 타입
    intent_label_source_enum = sa.Enum(
        "system",
        "human",
        "ml",
        "corrected",
        name="intent_label_source",
    )
    intent_label_source_enum.create(op.get_bind(), checkfirst=True)

    # incoming_messages 에 pure_guest_message 컬럼 추가
    op.add_column(
        "incoming_messages",
        sa.Column("pure_guest_message", sa.Text(), nullable=True),
    )

    # message_intent_labels 테이블 생성
    op.create_table(
        "message_intent_labels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column(
            "intent",
            sa.Enum(
                "CHECKIN_QUESTION",
                "CHECKOUT_QUESTION",
                "RESERVATION_CHANGE",
                "CANCELLATION",
                "COMPLAINT",
                "LOCATION_QUESTION",
                "AMENITY_QUESTION",
                "PET_POLICY_QUESTION",
                "GENERAL_QUESTION",
                "THANKS_OR_GOOD_REVIEW",
                "OTHER",
                name="message_intent",
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            intent_label_source_enum,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["incoming_messages.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_message_intent_labels_message_id",
        "message_intent_labels",
        ["message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_intent_labels_message_id", table_name="message_intent_labels")
    op.drop_table("message_intent_labels")
    op.drop_column("incoming_messages", "pure_guest_message")
    op.execute("DROP TYPE IF EXISTS intent_label_source")