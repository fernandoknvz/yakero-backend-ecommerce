from abc import ABC, abstractmethod
from typing import Optional
from ..models.entities import User, Address, Product, Category, Order, Promotion, Coupon, CheckoutSession, Payment
from ..models.enums import OrderStatus


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]: ...
    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]: ...
    @abstractmethod
    async def create(self, user: User) -> User: ...
    @abstractmethod
    async def update(self, user: User) -> User: ...
    @abstractmethod
    async def add_points(self, user_id: int, points: int) -> None: ...


class AddressRepository(ABC):
    @abstractmethod
    async def get_by_user(self, user_id: int) -> list[Address]: ...
    @abstractmethod
    async def get_by_id(self, address_id: int) -> Optional[Address]: ...
    @abstractmethod
    async def create(self, address: Address) -> Address: ...
    @abstractmethod
    async def update(self, address: Address) -> Address: ...
    @abstractmethod
    async def delete(self, address_id: int) -> None: ...
    @abstractmethod
    async def set_default(self, user_id: int, address_id: int) -> None: ...


class ProductRepository(ABC):
    @abstractmethod
    async def get_all_active(self) -> list[Product]: ...
    @abstractmethod
    async def get_by_id(self, product_id: int) -> Optional[Product]: ...
    @abstractmethod
    async def get_by_category(self, category_id: int) -> list[Product]: ...
    @abstractmethod
    async def get_by_slug(self, slug: str) -> Optional[Product]: ...
    @abstractmethod
    async def search(self, query: str) -> list[Product]: ...


class CategoryRepository(ABC):
    @abstractmethod
    async def get_all_active(self) -> list[Category]: ...
    @abstractmethod
    async def get_by_id(self, category_id: int) -> Optional[Category]: ...


class OrderRepository(ABC):
    @abstractmethod
    async def get_by_id(self, order_id: int) -> Optional[Order]: ...
    @abstractmethod
    async def get_by_user(self, user_id: int, skip: int = 0, limit: int = 20) -> list[Order]: ...
    @abstractmethod
    async def get_pending_for_pos(self) -> list[Order]: ...
    @abstractmethod
    async def create(self, order: Order) -> Order: ...
    @abstractmethod
    async def update_status(self, order_id: int, status: OrderStatus) -> Order: ...
    @abstractmethod
    async def update_payment(
        self,
        order_id: int,
        payment_provider: str,
        payment_status: str,
        mp_payment_id: str,
        mp_status: str,
        paid_at=None,
    ) -> Order: ...
    @abstractmethod
    async def update_mp_preference(
        self,
        order_id: int,
        preference_id: str,
        payment_provider: str,
        payment_status: str,
    ) -> Order: ...
    @abstractmethod
    async def get_by_mp_preference(self, preference_id: str) -> Optional[Order]: ...


class CheckoutSessionRepository(ABC):
    @abstractmethod
    async def create(self, session: CheckoutSession) -> CheckoutSession: ...
    @abstractmethod
    async def get_by_id(self, session_id: int) -> Optional[CheckoutSession]: ...
    @abstractmethod
    async def get_by_external_reference(self, external_reference: str) -> Optional[CheckoutSession]: ...
    @abstractmethod
    async def update_preference(
        self,
        session_id: int,
        preference_id: str,
        init_point: Optional[str],
        sandbox_init_point: Optional[str],
    ) -> CheckoutSession: ...
    @abstractmethod
    async def update_status(
        self,
        session_id: int,
        status: str,
        created_order_id: Optional[int] = None,
    ) -> CheckoutSession: ...


class PaymentRepository(ABC):
    @abstractmethod
    async def get_by_provider_payment_id(self, provider: str, provider_payment_id: str) -> Optional[Payment]: ...
    @abstractmethod
    async def get_by_checkout_session_id(self, checkout_session_id: int) -> list[Payment]: ...
    @abstractmethod
    async def upsert(self, payment: Payment) -> Payment: ...
    @abstractmethod
    async def attach_order(self, payment_id: int, order_id: int) -> Payment: ...


class PromotionRepository(ABC):
    @abstractmethod
    async def get_all_active(self) -> list[Promotion]: ...
    @abstractmethod
    async def get_by_id(self, promotion_id: int) -> Optional[Promotion]: ...


class CouponRepository(ABC):
    @abstractmethod
    async def get_by_code(self, code: str) -> Optional[Coupon]: ...
    @abstractmethod
    async def increment_uses(self, coupon_id: int) -> None: ...
