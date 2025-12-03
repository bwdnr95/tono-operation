"""add property_profiles table"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251203_01"
down_revision = None  # 실제 프로젝트의 최신 revision id로 교체
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("property_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="ko-KR"),
        sa.Column("checkin_from", sa.String(length=32), nullable=True),
        sa.Column("checkin_to", sa.String(length=32), nullable=True),
        sa.Column("checkout_until", sa.String(length=32), nullable=True),
        sa.Column("parking_info", sa.Text(), nullable=True),
        sa.Column("pet_policy", sa.Text(), nullable=True),
        sa.Column("smoking_policy", sa.Text(), nullable=True),
        sa.Column("noise_policy", sa.Text(), nullable=True),
        sa.Column("amenities", sa.JSON(), nullable=True),
        sa.Column("address_summary", sa.Text(), nullable=True),
        sa.Column("location_guide", sa.Text(), nullable=True),
        sa.Column("access_guide", sa.Text(), nullable=True),
        sa.Column("house_rules", sa.Text(), nullable=True),
        sa.Column("space_overview", sa.Text(), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_property_profiles_property_code",
        "property_profiles",
        ["property_code"],
        unique=True,
    )
    op.create_index(
        "ix_property_profiles_is_active",
        "property_profiles",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_property_profiles_is_active", table_name="property_profiles")
    op.drop_index("ix_property_profiles_property_code", table_name="property_profiles")
    op.drop_table("property_profiles")
