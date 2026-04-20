import mercadopago
from decimal import Decimal
from ...config import settings
from ...domain.models.entities import Order
from ...domain.exceptions import PaymentError


class MercadoPagoService:
    def __init__(self):
        self._sdk = mercadopago.SDK(settings.mp_access_token)

    async def create_preference(self, order: Order, back_urls: dict) -> str:
        """
        Crea una preferencia de pago en MercadoPago y retorna el preference_id.
        El frontend redirige al usuario a esta preferencia.
        """
        items = [
            {
                "id": str(item.product_id or item.promotion_id),
                "title": item.product_name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "currency_id": "CLP",
            }
            for item in order.items
        ]

        # Agregar delivery como ítem separado si aplica
        if order.delivery_fee > 0:
            items.append({
                "id": "delivery",
                "title": "Costo de envío",
                "quantity": 1,
                "unit_price": float(order.delivery_fee),
                "currency_id": "CLP",
            })

        preference_data = {
            "items": items,
            "payer": {
                "email": order.guest_email or "",
            },
            "back_urls": {
                "success": back_urls.get("success", settings.mp_back_url_success),
                "failure": back_urls.get("failure", settings.mp_back_url_failure),
                "pending": back_urls.get("pending", settings.mp_back_url_pending),
            },
            "auto_return": "approved",
            "notification_url": f"{settings.api_base_url}/webhooks/mercadopago",
            "external_reference": str(order.id),
            "metadata": {
                "order_id": order.id,
                "yakero_source": "ecommerce",
            },
        }

        response = self._sdk.preference().create(preference_data)

        if response["status"] not in (200, 201):
            raise PaymentError(
                f"Error al crear preferencia de pago: {response.get('response')}"
            )

        return response["response"]["id"]

    def verify_webhook_signature(self, data: str, signature: str) -> bool:
        """
        Valida la firma HMAC del webhook de MercadoPago.
        MercadoPago envía x-signature en el header.
        """
        import hmac
        import hashlib
        expected = hmac.new(
            settings.mp_webhook_secret.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
