from ....domain.repositories.interfaces import UserRepository


class PointsService:
    def __init__(self, user_repo: UserRepository):
        self._repo = user_repo

    async def award_on_payment(
        self, user_id: int, order_id: int, points: int
    ) -> None:
        """Acredita puntos al usuario tras un pago exitoso."""
        await self._repo.add_points(user_id, points)
