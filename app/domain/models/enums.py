from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pendiente"
    PAID = "pagado"
    PREPARING = "en_preparacion"
    READY = "listo"
    DISPATCHED = "despachado"
    DELIVERED = "entregado"
    CANCELLED = "cancelado"
    VOIDED = "anulado"


class PaymentStatus(str, Enum):
    PENDING = "pendiente"
    PAID = "pagado"
    REJECTED = "rechazado"
    REFUNDED = "reembolso"


class DeliveryType(str, Enum):
    DELIVERY = "delivery"
    PICKUP = "retiro"


class TicketTag(str, Enum):
    COCINA_SUSHI = "cocina_sushi"
    COCINA_SANDWICH = "cocina_sandwich"
    CAJA = "caja"
    NONE = "ninguna"


class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    POS_SERVICE = "pos_service"  # token de servicio para el POS


class ModifierType(str, Enum):
    SINGLE = "single"      # elige una opción (proteína)
    MULTIPLE = "multiple"  # puede elegir varias (salsas)


class PromotionType(str, Enum):
    BUNDLE = "bundle"        # N piezas configurables
    FIXED_DISCOUNT = "fixed" # descuento fijo en pesos
    PERCENT = "percent"      # descuento porcentual
    COUPON = "coupon"        # cupón de descuento
