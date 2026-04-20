class DomainError(Exception):
    """Base para errores de dominio — no son bugs, son reglas de negocio violadas."""
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
            f"Transición de estado inválida: '{current}' → '{target}'",
            "INVALID_TRANSITION"
        )


class InsufficientPointsError(DomainError):
    def __init__(self, available: int, requested: int):
        super().__init__(
            f"Puntos insuficientes: disponibles {available}, solicitados {requested}",
            "INSUFFICIENT_POINTS"
        )


class CouponError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "COUPON_ERROR")


class ModifierValidationError(DomainError):
    def __init__(self, group_name: str):
        super().__init__(
            f"El grupo de modificadores '{group_name}' requiere una selección válida.",
            "MODIFIER_REQUIRED"
        )


class PaymentError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "PAYMENT_ERROR")
