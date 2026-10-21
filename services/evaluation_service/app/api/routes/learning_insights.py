from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user, require_self_or_admin
from common.models.learning import User
from services.evaluation_service.app.services.learning_insights import build_learning_insights

router = APIRouter()


@router.get("/evaluation/analytics/{user_id}/insights")
def insights(
    user_id: int,
    days: int = Query(30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_self_or_admin(user_id, user)
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    return {"data": build_learning_insights(db, user_id, days)}
