from dataclasses import dataclass


@dataclass
class GatewayOrder:
    gateway_order_id: str
    amount_paise: int
    currency: str = "INR"


class RazorpayAdapter:
    """
    Placeholder adapter. Replace create_order/verify_signature with actual
    Razorpay SDK integration in deployment.
    """

    def create_order(self, receipt: str, amount_paise: int) -> GatewayOrder:
        return GatewayOrder(gateway_order_id=f"mock_{receipt}", amount_paise=amount_paise)

    def verify_signature(self, payload: dict) -> bool:
        return bool(payload.get("gateway_payment_id"))
