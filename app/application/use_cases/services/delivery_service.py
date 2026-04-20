from decimal import Decimal
import math

# Coordenadas del local de Yakero (Diaguitas 538, Las Condes)
STORE_LAT = -33.4094
STORE_LON = -70.5799

# Tabla de tarifas por tramo de distancia
DELIVERY_TIERS = [
    (2.0,  Decimal("990")),
    (4.0,  Decimal("1490")),
    (6.0,  Decimal("1990")),
    (8.0,  Decimal("2490")),
    (10.0, Decimal("2990")),
]
MAX_DELIVERY_KM = 10.0
OUT_OF_RANGE_FEE = Decimal("0")  # No disponible


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos puntos geográficos."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class DeliveryFeeService:
    def __init__(
        self,
        store_lat: float = STORE_LAT,
        store_lon: float = STORE_LON,
    ):
        self._lat = store_lat
        self._lon = store_lon

    async def calculate(self, customer_lat: float, customer_lon: float) -> Decimal:
        distance = haversine_km(self._lat, self._lon, customer_lat, customer_lon)
        for max_km, fee in DELIVERY_TIERS:
            if distance <= max_km:
                return fee
        return OUT_OF_RANGE_FEE

    async def is_available(self, customer_lat: float, customer_lon: float) -> bool:
        distance = haversine_km(self._lat, self._lon, customer_lat, customer_lon)
        return distance <= MAX_DELIVERY_KM

    async def get_info(
        self, customer_lat: float, customer_lon: float
    ) -> tuple[float, Decimal, bool]:
        distance = haversine_km(self._lat, self._lon, customer_lat, customer_lon)
        available = distance <= MAX_DELIVERY_KM
        fee = await self.calculate(customer_lat, customer_lon) if available else Decimal("0")
        return round(distance, 2), fee, available
