from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.services.authentication import authenticate

# Commit before sending the response so a failed commit never looks successful.
DB = Annotated[Session, Depends(get_db, scope="function")]


def current_user(request: Request, db: DB):
    return authenticate(db, request.cookies.get("jsi_session"))


CurrentUser = Annotated[User, Depends(current_user)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
