import hmac
import hashlib
import razorpay
from app.config import get_settings
from logging import getLogger

logger = getLogger(__name__)


class RazorpayService:
    def __init__(self):
        settings = get_settings()
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        if not self.key_id or not self.key_secret:
            raise ValueError(
                "Razorpay credentials not configured. "
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env"
            )
        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))

    def create_order(
        self, amount_paise: int, receipt: str, notes: dict | None = None
    ) -> dict:
        """Create a Razorpay order. Returns the order dict with 'id'."""
        data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
        }
        if notes:
            data["notes"] = notes
        order = self.client.order.create(data=data)
        logger.info(f"Razorpay order created: {order['id']} for {amount_paise} paise")
        return order

    def verify_payment(
        self, order_id: str, payment_id: str, signature: str
    ) -> bool:
        """Verify Razorpay payment signature. Returns True if valid."""
        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def verify_webhook(self, body_bytes: bytes, signature: str) -> bool:
        """Verify Razorpay webhook signature using HMAC-SHA256."""
        if not self.webhook_secret:
            logger.warning("Webhook secret not configured — rejecting webhook")
            return False
        expected = hmac.new(
            self.webhook_secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def fetch_order(self, order_id: str) -> dict:
        """Fetch order details from Razorpay."""
        return self.client.order.fetch(order_id)
