from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.domain.intents import MessageIntent
from backend.app.repositories.auto_reply_template_repository import AutoReplyTemplateRepository


async def main() -> None:
    async with async_session_maker() as session:  # 프로젝트의 session factory에 맞게 수정
        repo = AutoReplyTemplateRepository(session)

        # 예: PET_POLICY_QUESTION 기본 템플릿
        await repo.create_template(
            intent=MessageIntent.PET_POLICY_QUESTION,
            template_text=(
                "안녕하세요, 낭그늘 호스트입니다 :)\n\n"
                "문의주신 반려동물 동반 관련 안내드립니다.\n"
                "저희 숙소는 현재 반려동물 동반 입실이 {허용/불가} 합니다.\n"
                "추가 안내가 필요하시면 편하게 말씀 주세요!"
            ),
            locale="ko",
        )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())