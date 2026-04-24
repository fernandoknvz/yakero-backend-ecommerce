from datetime import UTC, datetime
from passlib.context import CryptContext
from ....domain.models.entities import User
from ....domain.models.enums import UserRole
from ....domain.repositories.interfaces import UserRepository
from ....domain.exceptions import ValidationError, UnauthorizedError
from ...dtos.schemas import RegisterInput, LoginInput

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
)


class RegisterUserUseCase:
    def __init__(self, user_repo: UserRepository):
        self._repo = user_repo

    async def execute(self, data: RegisterInput) -> User:
        existing = await self._repo.get_by_email(data.email)
        if existing:
            raise ValidationError("Ya existe una cuenta con ese email.")

        user = User(
            id=None,
            email=data.email.lower(),
            password_hash=pwd_context.hash(data.password),
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            phone=data.phone,
            role=UserRole.CUSTOMER,
            is_active=True,
            is_guest=False,
            points_balance=0,
            created_at=datetime.now(UTC),
        )
        return await self._repo.create(user)


class LoginUserUseCase:
    def __init__(self, user_repo: UserRepository):
        self._repo = user_repo

    async def execute(self, data: LoginInput) -> User:
        user = await self._repo.get_by_email(data.email.lower())
        if not user or not pwd_context.verify(data.password, user.password_hash):
            raise UnauthorizedError("Credenciales incorrectas.")
        if not user.is_active:
            raise UnauthorizedError("Cuenta desactivada.")
        return user
