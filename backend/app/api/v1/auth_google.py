from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.google_oauth_service import build_google_auth_url, exchange_code_for_tokens

router = APIRouter(prefix="/auth/google", tags=["google-oauth"])


@router.get("/login")
def google_login():
    url = build_google_auth_url()
    return RedirectResponse(url)


@router.get("/callback", response_class=HTMLResponse)
def google_callback(code: str, db: Session = Depends(get_db)):
    exchange_code_for_tokens(db, code=code)
    return HTMLResponse(
        """
        <html>
          <body>
            <h3>Google 연동 완료</h3>
            <p>이 창은 닫아도 됩니다.</p>
          </body>
        </html>
        """
    )