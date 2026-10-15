"""
Payment gateways.

RazorpayGateway talks to the real Razorpay API, using TEST keys only.
MockGateway behaves the same way but lives in memory, so the whole checkout
can be run and tested with no account and no internet.

The rest of the app only ever calls the small set of methods on these classes.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.error
import urllib.request

from flask import current_app

API_BASE = "https://api.razorpay.com/v1"


class GatewayError(Exception):
    """Something went wrong talking to the payment provider."""


class ConfigError(Exception):
    """The payment settings are not safe or not complete."""


def _sign(secret, message):
    if isinstance(message, str):
        message = message.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class RazorpayGateway:
    name = "razorpay"

    def __init__(self, key_id, key_secret, webhook_secret="", opener=None):
        # This project is for test mode only. Refuse anything that is not a test key.
        if not key_id.startswith("rzp_test_"):
            raise ConfigError("RAZORPAY_KEY_ID must be a test key (it starts with rzp_test_). "
                              "Live keys are not allowed in this project.")
        if not key_secret:
            raise ConfigError("RAZORPAY_KEY_SECRET is missing.")
        self.key_id = key_id
        self._secret = key_secret
        self._webhook_secret = webhook_secret
        self._open = opener or urllib.request.urlopen     # swapped out in tests

    # --- HTTP -------------------------------------------------------------
    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        token = base64.b64encode(f"{self.key_id}:{self._secret}".encode()).decode()
        req = urllib.request.Request(
            API_BASE + path, data=body, method=method,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"},
        )
        try:
            with self._open(req, timeout=15) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("error", {}).get("description")
            except Exception:
                detail = None
            raise GatewayError(detail or f"Razorpay returned HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise GatewayError("Could not reach Razorpay. Check your internet connection.")

    # --- what the app uses -------------------------------------------------
    def create_order(self, amount, receipt, notes=None):
        """amount is in paise. Returns the Razorpay order (its 'id' is what Checkout needs)."""
        data = self._request("POST", "/orders", {
            "amount": int(amount), "currency": "INR",
            "receipt": receipt[:40], "notes": notes or {},
        })
        if "id" not in data:
            raise GatewayError("Razorpay did not return an order id.")
        return data

    def verify_payment_signature(self, order_id, payment_id, signature):
        """Checkout gives us a signature = HMAC_SHA256(key_secret, order_id|payment_id)."""
        if not (order_id and payment_id and signature):
            return False
        expected = _sign(self._secret, f"{order_id}|{payment_id}")
        return hmac.compare_digest(expected, str(signature))

    def verify_webhook(self, raw_body, signature):
        """Webhooks are signed with the separate webhook secret over the raw request body."""
        if not (self._webhook_secret and signature):
            return False
        return hmac.compare_digest(_sign(self._webhook_secret, raw_body), signature)

    def fetch_payment(self, payment_id):
        return self._request("GET", f"/payments/{payment_id}")

    def refund(self, payment_id, amount, notes=None):
        data = self._request("POST", f"/payments/{payment_id}/refund",
                             {"amount": int(amount), "speed": "normal", "notes": notes or {}})
        if "id" not in data:
            raise GatewayError("Razorpay did not return a refund id.")
        return data

    def checkout_config(self, gateway_order_id, amount):
        # only the public key id ever reaches the browser
        return {"mode": "razorpay", "key": self.key_id, "order_id": gateway_order_id,
                "amount": int(amount), "currency": "INR"}


class MockGateway:
    """A stand-in for Razorpay that needs no network. Same methods, same signatures."""
    name = "mock"
    key_id = "rzp_test_mock"

    def __init__(self, secret="mock-key-secret", webhook_secret="mock-webhook-secret"):
        self._secret = secret
        self._webhook_secret = webhook_secret
        self.orders, self.payments, self.refunds = {}, {}, {}

    def create_order(self, amount, receipt, notes=None):
        oid = "order_mock" + secrets.token_hex(6)
        self.orders[oid] = {"id": oid, "amount": int(amount), "currency": "INR", "receipt": receipt}
        return self.orders[oid]

    def verify_payment_signature(self, order_id, payment_id, signature):
        if not (order_id and payment_id and signature):
            return False
        return hmac.compare_digest(_sign(self._secret, f"{order_id}|{payment_id}"), str(signature))

    def verify_webhook(self, raw_body, signature):
        if not signature:
            return False
        return hmac.compare_digest(_sign(self._webhook_secret, raw_body), signature)

    def fetch_payment(self, payment_id):
        if payment_id not in self.payments:
            raise GatewayError("Payment not found.")
        return self.payments[payment_id]

    def refund(self, payment_id, amount, notes=None):
        pay = self.payments.get(payment_id)
        if pay is None and not payment_id.startswith("pay_mock"):
            raise GatewayError("Payment not found.")
        if payment_id in self.refunds:
            raise GatewayError("The payment has already been fully refunded.")
        if pay is not None and int(amount) > pay["amount"]:
            raise GatewayError("The refund amount is more than the payment.")
        self.refunds[payment_id] = {"id": "rfnd_mock" + secrets.token_hex(5), "amount": int(amount)}
        return self.refunds[payment_id]

    def checkout_config(self, gateway_order_id, amount):
        return {"mode": "mock", "key": self.key_id, "order_id": gateway_order_id,
                "amount": int(amount), "currency": "INR"}

    # --- helpers only the mock has (used by the local simulator and the tests) ---
    def simulate_payment(self, order_id, success=True):
        """Pretend a customer paid. Returns (payment_id, signature)."""
        order = self.orders.get(order_id)
        amount = order["amount"] if order else 0
        pid = "pay_mock" + secrets.token_hex(6)
        self.payments[pid] = {"id": pid, "order_id": order_id, "amount": amount,
                              "status": "captured" if success else "failed"}
        return pid, _sign(self._secret, f"{order_id}|{pid}")

    def sign_webhook(self, raw_body):
        return _sign(self._webhook_secret, raw_body)


def build_gateway_from_env():
    """Real Razorpay if test keys are set, otherwise the local mock."""
    key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
    secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
    if key_id or secret:
        return RazorpayGateway(key_id, secret, os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip())
    return MockGateway()


def get_gateway():
    gw = current_app.config.get("GATEWAY")
    if gw is None:
        gw = current_app.config["GATEWAY"] = build_gateway_from_env()
    return gw
