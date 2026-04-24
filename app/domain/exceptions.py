class DomainError(Exception):
    """Base para errores de dominio; no representan bugs, sino reglas violadas."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(DomainError):
    def __init__(self, resource: str, identifier):
        super().__init__(f"{resource} con id '{identifier}' no encontrado.", "NOT_FOUND")


class ValidationError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class UnauthorizedError(DomainError):
    def __init__(self, message: str = "No autorizado"):
        super().__init__(message, "UNAUTHORIZED")


class InvalidOrderTransitionError(DomainError):
    def __init__(self, current: str, target: str):
        super().__init__(
            f"Transicion de estado invalida: '{current}' -> '{target}'",
            "INVALID_TRANSITION",
        )


class InsufficientPointsError(DomainError):
    def __init__(self, available: int, requested: int):
        super().__init__(
            f"Puntos insuficientes: disponibles {available}, solicitados {requested}",
            "INSUFFICIENT_POINTS",
        )


class CouponError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "COUPON_ERROR")


class ProductUnavailableError(DomainError):
    def __init__(self, product_id: int):
        super().__init__(
            f"Producto con id '{product_id}' no disponible.",
            "PRODUCT_UNAVAILABLE",
        )


class InvalidModifierError(DomainError):
    def __init__(self, product_id: int, option_id: int):
        super().__init__(
            f"El modificador '{option_id}' no es valido para el producto '{product_id}'.",
            "INVALID_MODIFIER",
        )


class ModifierValidationError(DomainError):
    def __init__(self, group_name: str):
        super().__init__(
            f"El grupo de modificadores '{group_name}' requiere una seleccion valida.",
            "MODIFIER_REQUIRED",
        )


class InvalidQuantityError(DomainError):
    def __init__(self):
        super().__init__("La cantidad solicitada no es valida.", "INVALID_QUANTITY")


class OrderPricingMismatchError(DomainError):
    def __init__(self, field: str):
        super().__init__(
            f"El total calculado para '{field}' no coincide con el valor enviado por el cliente.",
            "ORDER_PRICING_MISMATCH",
        )


class PaymentError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "PAYMENT_ERROR")
