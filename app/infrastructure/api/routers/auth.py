from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.repositories.sql_repositories import SQLUserRepository
from ...database.session import get_db
from ..errors import domain_error_to_http
from ....application.dtos.schemas import LoginInput, RegisterInput, TokenResponse, UserOut
from ....application.use_cases.auth.auth_use_cases import LoginUserUseCase, RegisterUserUseCase
from ....auth import create_access_token, get_current_user
from ....domain.exceptions import DomainError
from ....domain.models.entities import User


router = APIRouter(prefix="/auth", tags=["Autenticacion"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterInput, db: AsyncSession = Depends(get_db)):
    try:
        user = await RegisterUserUseCase(SQLUserRepository(db)).execute(data)
        token = create_access_token(user.id, user.role)
        return TokenResponse(access_token=token, user_id=user.id, role=user.role)
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginInput, db: AsyncSession = Depends(get_db)):
    try:
        user = await LoginUserUseCase(SQLUserRepository(db)).execute(data)
        token = create_access_token(user.id, user.role)
        return TokenResponse(access_token=token, user_id=user.id, role=user.role)
    except DomainError as exc:
        raise domain_error_to_http(exc)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
