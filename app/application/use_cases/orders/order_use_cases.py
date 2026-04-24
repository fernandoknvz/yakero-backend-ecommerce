from ....domain.models.entities import Order
from ....domain.models.enums import OrderStatus, PaymentStatus
from ....domain.repositories.interfaces import OrderRepository
from ....domain.exceptions import NotFoundError, InvalidOrderTransitionError
from ...dtos.schemas import PosStatusUpdateInput
from datetime import UTC, datetime


class UpdateOrderStatusUseCase:
    """
    Usado por el POS para actualizar el estado de un pedido.
    Valida que la transición sea permitida según las reglas de dominio.
    """
    def __init__(self, order_repo: OrderRepository):
        self._repo = order_repo

    async def execute(
        self, order_id: int, data: PosStatusUpdateInput
    ) -> Order:
        order = await self._repo.get_by_id(order_id)
        if not order:
            raise NotFoundError("Pedido", order_id)
        if not order.can_transition_to(data.status):
            raise InvalidOrderTransitionError(order.status, data.status)
        return await self._repo.update_status(order_id, data.status)


class GetOrderUseCase:
    def __init__(self, order_repo: OrderRepository):
        self._repo = order_repo

    async def execute(self, order_id: int, user_id: int | None = None) -> Order:
        order = await self._repo.get_by_id(order_id)
        if not order:
            raise NotFoundError("Pedido", order_id)
        # Un usuario autenticado solo puede ver sus propios pedidos.
        if user_id and order.user_id and order.user_id != user_id:
            raise NotFoundError("Pedido", order_id)
        # Un invitado no debe poder consultar pedidos asociados a usuarios registrados.
        if user_id is None and order.user_id is not None:
            raise NotFoundError("Pedido", order_id)
        return order


class GetUserOrdersUseCase:
    def __init__(self, order_repo: OrderRepository):
        self._repo = order_repo

    async def execute(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> list[Order]:
        return await self._repo.get_by_user(user_id, skip, limit)


class ConfirmPaymentUseCase:
    """
    Ejecutado por el webhook de MercadoPago.
    Idempotente: si ya está pagado, no hace nada.
    """
    def __init__(self, order_repo: OrderRepository):
        self._repo = order_repo

    async def execute(
        self,
        preference_id: str,
        mp_payment_id: str,
        mp_status: str,
    ) -> Order | None:
        order = await self._repo.get_by_mp_preference(preference_id)
        if not order:
            return None

        # idempotencia: ya procesado
        if order.mp_payment_id == mp_payment_id:
            return order

        updated = await self._repo.update_payment(
            order.id,
            "mercadopago",
            PaymentStatus.PAID.value if mp_status == "approved" else PaymentStatus.PENDING.value,
            mp_payment_id,
            mp_status,
            paid_at=datetime.now(UTC) if mp_status == "approved" else None,
        )

        # Si el pago fue aprobado, transicionar a PAID → PREPARING automáticamente
        if mp_status == "approved" and updated.can_transition_to(OrderStatus.PAID):
            updated = await self._repo.update_status(updated.id, OrderStatus.PAID)

        return updated
