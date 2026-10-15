"""Gateway classes and the payment flow, using the local mock gateway (no network)."""
import base64
import hashlib
import hmac
import io
import json
import urllib.error

from support import StoreCase, ADDRESS, store
import payments
import order_service as svc
import workflow as wf


def hex_hmac(secret, message):
    if isinstance(message, str):
        message = message.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class FakeResponse:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class RazorpayGatewayTests(StoreCase):
    def make(self, opener=None):
        return payments.RazorpayGateway("rzp_test_abc123", "topsecret", "whsecret", opener=opener)

    def test_live_keys_are_refused(self):
        with self.assertRaises(payments.ConfigError):
            payments.RazorpayGateway("rzp_live_abc123", "secret")
        with self.assertRaises(payments.ConfigError):
            payments.RazorpayGateway("", "secret")

    def test_payment_signature_matches_razorpays_formula(self):
        gw = self.make()
        good = hex_hmac("topsecret", "order_X|pay_Y")                 # HMAC-SHA256(secret, order|payment)
        self.assertTrue(gw.verify_payment_signature("order_X", "pay_Y", good))
        self.assertFalse(gw.verify_payment_signature("order_X", "pay_Z", good))
        self.assertFalse(gw.verify_payment_signature("order_X", "pay_Y", good[:-1] + "0"))
        self.assertFalse(gw.verify_payment_signature("order_X", "pay_Y", ""))
        self.assertFalse(gw.verify_payment_signature("", "pay_Y", good))

    def test_webhook_uses_the_webhook_secret_on_the_raw_body(self):
        gw = self.make()
        body = b'{"event":"payment.captured"}'
        self.assertTrue(gw.verify_webhook(body, hex_hmac("whsecret", body)))
        self.assertFalse(gw.verify_webhook(body, hex_hmac("topsecret", body)))   # key secret is the wrong one
        self.assertFalse(gw.verify_webhook(body + b" ", hex_hmac("whsecret", body)))
        no_secret = payments.RazorpayGateway("rzp_test_abc123", "topsecret", "")
        self.assertFalse(no_secret.verify_webhook(body, hex_hmac("", body)))

    def test_create_order_request_shape(self):
        seen = {}

        def opener(req, timeout):
            seen["url"], seen["method"] = req.full_url, req.get_method()
            seen["auth"], seen["body"] = req.get_header("Authorization"), json.loads(req.data)
            return FakeResponse({"id": "order_ABC", "amount": 181000, "currency": "INR"})

        out = self.make(opener).create_order(181000, "FP-TESTRECEIPT", {"order_number": "FP-TESTRECEIPT"})
        self.assertEqual(out["id"], "order_ABC")
        self.assertEqual(seen["url"], "https://api.razorpay.com/v1/orders")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["auth"], "Basic " + base64.b64encode(b"rzp_test_abc123:topsecret").decode())
        self.assertEqual(seen["body"]["amount"], 181000)
        self.assertEqual(seen["body"]["currency"], "INR")
        self.assertEqual(seen["body"]["receipt"], "FP-TESTRECEIPT")

    def test_refund_request_shape(self):
        seen = {}

        def opener(req, timeout):
            seen["url"], seen["body"] = req.full_url, json.loads(req.data)
            return FakeResponse({"id": "rfnd_1"})

        self.assertEqual(self.make(opener).refund("pay_9", 5000)["id"], "rfnd_1")
        self.assertTrue(seen["url"].endswith("/payments/pay_9/refund"))
        self.assertEqual(seen["body"]["amount"], 5000)

    def test_api_errors_become_gateway_errors(self):
        def http_error(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(
                json.dumps({"error": {"description": "Authentication failed"}}).encode()))

        def down(req, timeout):
            raise urllib.error.URLError("no route")

        with self.assertRaisesRegex(payments.GatewayError, "Authentication failed"):
            self.make(http_error).create_order(100, "r")
        with self.assertRaisesRegex(payments.GatewayError, "Could not reach"):
            self.make(down).create_order(100, "r")

    def test_browser_config_never_contains_the_secret(self):
        cfg = self.make().checkout_config("order_ABC", 1000)
        text = json.dumps(cfg)
        self.assertIn("rzp_test_abc123", text)
        self.assertNotIn("topsecret", text)
        self.assertNotIn("whsecret", text)

    def test_mock_endpoint_is_off_when_real_gateway_is_used(self):
        store.app.config["GATEWAY"] = self.make(lambda req, timeout: FakeResponse({"id": "order_R1"}))
        number = self.make_order()
        r = self.post(f"/pay/{number}/mock", outcome="success")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.order(number)["status"], "pending")


class PaymentFlowTests(StoreCase):
    def test_checkout_creates_a_pending_order_with_a_gateway_order(self):
        before = self.stock("hand-grinder-steel")
        number = self.make_order()
        o = self.order(number)
        self.assertEqual(o["status"], "pending")
        self.assertTrue(o["gateway_order_id"].startswith("order_"))
        self.assertEqual(o["gateway"], "mock")
        self.assertEqual(self.stock("hand-grinder-steel"), before - 1)         # stock held
        self.assertEqual(self.gw.orders[o["gateway_order_id"]]["amount"], o["total"])
        self.assertIn("1", self.page_text("/cart"))                              # cart is kept until paid

    def page_text(self, url):
        return self.c.get(url).get_data(as_text=True)

    def test_pay_page_shows_test_mode_and_amount(self):
        number = self.make_order()
        html = self.page_text(f"/pay/{number}")
        self.assertIn("TEST MODE", html)
        self.assertIn("Local payment simulator", html)

    def test_successful_payment_marks_order_paid_and_clears_cart(self):
        number = self.make_order()
        r, payment_id = self.pay(number)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        o = self.order(number)
        self.assertEqual(o["status"], "paid")
        self.assertEqual(o["payment_id"], payment_id)
        self.assertIsNotNone(o["paid_at"])
        self.assertIn("Your cart is empty", self.page_text("/cart"))
        kinds = [e["kind"] for e in self.events(number)]
        self.assertEqual(kinds, ["created", "gateway_order", "payment"])

    def test_bad_signature_is_rejected(self):
        number = self.make_order()
        gid = self.order(number)["gateway_order_id"]
        payment_id, _ = self.gw.simulate_payment(gid)
        r = self.post_json(f"/pay/{number}/verify", {
            "razorpay_order_id": gid, "razorpay_payment_id": payment_id, "razorpay_signature": "0" * 64})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.order(number)["status"], "pending")
        self.assertIn("bad_payment", [e["kind"] for e in self.events(number)])

    def test_signature_for_another_order_is_rejected(self):
        number = self.make_order()
        other_gid = self.gw.create_order(999, "other")["id"]
        payment_id, sig_for_other = self.gw.simulate_payment(other_gid)
        r = self.post_json(f"/pay/{number}/verify", {
            "razorpay_payment_id": payment_id, "razorpay_signature": sig_for_other})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.order(number)["status"], "pending")

    def test_browser_cannot_name_a_different_gateway_order(self):
        number = self.make_order()
        r, _ = self.pay(number)                                   # a legitimate payment first
        self.assertEqual(r.status_code, 200)
        number2 = self.make_order("guji-natural-250")
        gid2 = self.order(number2)["gateway_order_id"]
        pid, sig = self.gw.simulate_payment(gid2)
        r = self.post_json(f"/pay/{number2}/verify", {
            "razorpay_order_id": self.order(number)["gateway_order_id"],
            "razorpay_payment_id": pid, "razorpay_signature": sig})
        self.assertEqual(r.status_code, 400)

    def test_payment_for_the_wrong_amount_is_rejected(self):
        number = self.make_order()
        gid = self.order(number)["gateway_order_id"]
        payment_id, sig = self.gw.simulate_payment(gid)
        self.gw.payments[payment_id]["amount"] = 100              # gateway says only Rs 1 was paid
        r = self.post_json(f"/pay/{number}/verify", {
            "razorpay_order_id": gid, "razorpay_payment_id": payment_id, "razorpay_signature": sig})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.order(number)["status"], "pending")

    def test_verifying_twice_does_not_pay_twice(self):
        number = self.make_order()
        gid = self.order(number)["gateway_order_id"]
        payment_id, sig = self.gw.simulate_payment(gid)
        body = {"razorpay_order_id": gid, "razorpay_payment_id": payment_id, "razorpay_signature": sig}
        self.assertEqual(self.post_json(f"/pay/{number}/verify", body).status_code, 200)
        self.assertEqual(self.post_json(f"/pay/{number}/verify", body).status_code, 200)
        self.assertEqual([e["kind"] for e in self.events(number)].count("payment"), 1)

    def test_failed_payment_leaves_order_open_for_a_retry(self):
        number = self.make_order()
        self.post_json(f"/pay/{number}/failed", {"description": "Card declined"})
        o = self.order(number)
        self.assertEqual(o["status"], "pending")
        self.assertEqual(o["payment_attempts"], 1)
        self.assertIn("payment_failed", [e["kind"] for e in self.events(number)])
        r, _ = self.pay(number)                                   # second try works
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.order(number)["status"], "paid")

    def test_simulator_failure_button(self):
        number = self.make_order()
        self.post(f"/pay/{number}/mock", outcome="fail")
        self.assertEqual(self.order(number)["status"], "pending")
        self.assertEqual(self.order(number)["payment_attempts"], 1)

    def test_customer_can_cancel_an_unpaid_order(self):
        before = self.stock("hand-grinder-steel")
        number = self.make_order()
        self.post(f"/pay/{number}/cancel")
        self.assertEqual(self.order(number)["status"], "cancelled")
        self.assertEqual(self.stock("hand-grinder-steel"), before)  # stock is back
        self.assertIn("Hand Grinder", self.page_text("/cart"))        # items still in the cart

    def test_someone_else_cannot_cancel_my_order(self):
        number = self.make_order()
        stranger = store.app.test_client()
        with stranger.session_transaction() as s:
            s["csrf"] = "tok"
        self.assertEqual(self.post(f"/pay/{number}/cancel", client=stranger).status_code, 403)
        self.assertEqual(self.order(number)["status"], "pending")

    def test_own_reserved_stock_does_not_empty_the_cart(self):
        slug = "huila-washed-250"                                    # only 3 in stock
        number = self.make_order(slug, qty=3)
        self.assertEqual(self.stock(slug), 0)                         # all held by this order
        html = self.page_text("/cart")
        self.assertIn("Colombia Huila", html)
        self.assertNotIn("sold out", html.lower().replace("sold out right now", ""))

    def test_starting_a_second_checkout_releases_the_first(self):
        before = self.stock("hand-grinder-steel")
        first = self.make_order()
        r = self.post("/checkout", **ADDRESS)
        second = r.headers["Location"].rsplit("/", 1)[1]
        self.assertEqual(self.order(first)["status"], "cancelled")
        self.assertEqual(self.order(second)["status"], "pending")
        self.assertEqual(self.stock("hand-grinder-steel"), before - 1)

    def test_unpaid_orders_expire_and_return_stock(self):
        before = self.stock("hand-grinder-steel")
        number = self.make_order()
        self.sql("UPDATE orders SET expires_at = '2000-01-01T00:00:00' WHERE order_number = ?", number)
        self.page_text("/cart")                                      # any page load sweeps expired orders
        self.assertEqual(self.order(number)["status"], "cancelled")
        self.assertEqual(self.stock("hand-grinder-steel"), before)
        self.assertIn("not completed in time", self.order(number)["cancel_reason"])

    def test_payment_after_expiry_is_refunded(self):
        number = self.make_order()
        self.sql("UPDATE orders SET expires_at = '2000-01-01T00:00:00' WHERE order_number = ?", number)
        self.page_text("/cart")                                      # expires it
        r, payment_id = self.pay(number)                             # customer pays anyway, too late
        self.assertEqual(r.status_code, 409)
        o = self.order(number)
        self.assertEqual(o["status"], "cancelled")
        self.assertEqual(o["refund_status"], "refunded")
        self.assertIn(payment_id, self.gw.refunds)
        self.assertIn("late_payment", [e["kind"] for e in self.events(number)])

    def test_gateway_outage_at_checkout_cancels_cleanly(self):
        class Down(payments.MockGateway):
            def create_order(self, *a, **k):
                raise payments.GatewayError("Could not reach Razorpay.")
        store.app.config["GATEWAY"] = Down()
        before = self.stock("hand-grinder-steel")
        self.post(f"/cart/add/{self.pid('hand-grinder-steel')}")
        r = self.post("/checkout", **ADDRESS)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/checkout"))
        self.assertEqual(self.sql("SELECT status FROM orders")[0]["status"], "cancelled")
        self.assertEqual(self.stock("hand-grinder-steel"), before)

    def test_paid_order_page_shows_progress(self):
        number = self.paid_order()
        html = self.page_text(f"/order/{number}")
        self.assertIn("tracker", html)
        self.assertIn("Paid", html)


class WebhookTests(StoreCase):
    def send(self, event, payment, event_id="evt_1", signature=None):
        body = json.dumps({"event": event, "payload": {"payment": {"entity": payment}}}).encode()
        sig = self.gw.sign_webhook(body) if signature is None else signature
        return self.c.post("/webhooks/razorpay", data=body, content_type="application/json",
                           headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id})

    def test_webhook_marks_an_order_paid_without_the_browser(self):
        number = self.make_order()
        o = self.order(number)
        r = self.send("payment.captured", {"id": "pay_web1", "order_id": o["gateway_order_id"], "amount": o["total"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.order(number)["status"], "paid")
        self.assertEqual(self.order(number)["payment_id"], "pay_web1")

    def test_webhook_needs_no_csrf_token_but_needs_a_valid_signature(self):
        number = self.make_order()
        o = self.order(number)
        r = self.send("payment.captured", {"id": "pay_x", "order_id": o["gateway_order_id"], "amount": o["total"]},
                      signature="deadbeef")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.order(number)["status"], "pending")

    def test_duplicate_webhook_is_ignored(self):
        number = self.make_order()
        o = self.order(number)
        payment = {"id": "pay_dup", "order_id": o["gateway_order_id"], "amount": o["total"]}
        self.send("payment.captured", payment, event_id="evt_same")
        again = self.send("payment.captured", payment, event_id="evt_same")
        self.assertIn("duplicate", again.get_json()["message"])
        self.assertEqual([e["kind"] for e in self.events(number)].count("payment"), 1)

    def test_webhook_and_browser_together_pay_once(self):
        number = self.make_order()
        r, payment_id = self.pay(number)
        o = self.order(number)
        self.send("order.paid", {"id": payment_id, "order_id": o["gateway_order_id"], "amount": o["total"]}, "evt_2")
        self.assertEqual([e["kind"] for e in self.events(number)].count("payment"), 1)
        self.assertEqual(self.order(number)["status"], "paid")

    def test_webhook_with_wrong_amount_does_not_pay_the_order(self):
        number = self.make_order()
        o = self.order(number)
        self.send("payment.captured", {"id": "pay_low", "order_id": o["gateway_order_id"], "amount": 100})
        self.assertEqual(self.order(number)["status"], "pending")
        self.assertIn("bad_payment", [e["kind"] for e in self.events(number)])

    def test_webhook_for_unknown_order_is_acknowledged(self):
        r = self.send("payment.captured", {"id": "pay_z", "order_id": "order_unknown", "amount": 100})
        self.assertEqual(r.status_code, 200)

    def test_failed_payment_event_is_logged(self):
        number = self.make_order()
        o = self.order(number)
        self.send("payment.failed", {"id": "pay_f", "order_id": o["gateway_order_id"], "error_description": "Bank said no"})
        self.assertIn("Bank said no", [e["note"] for e in self.events(number)])
        self.assertEqual(self.order(number)["status"], "pending")


class WorkflowRuleTests(StoreCase):
    def test_allowed_and_blocked_transitions(self):
        self.assertTrue(wf.can_transition("pending", "paid"))
        self.assertTrue(wf.can_transition("paid", "shipped"))
        self.assertTrue(wf.can_transition("shipped", "delivered"))
        self.assertTrue(wf.can_transition("paid", "cancelled"))
        self.assertFalse(wf.can_transition("pending", "shipped"))
        self.assertFalse(wf.can_transition("paid", "delivered"))
        self.assertFalse(wf.can_transition("shipped", "cancelled"))
        self.assertFalse(wf.can_transition("delivered", "shipped"))
        self.assertFalse(wf.can_transition("cancelled", "paid"))

    def test_admin_buttons_per_status(self):
        self.assertEqual(wf.admin_next_steps("pending"), ["cancelled"])
        self.assertEqual(wf.admin_next_steps("paid"), ["shipped", "cancelled"])
        self.assertEqual(wf.admin_next_steps("shipped"), ["delivered"])
        self.assertEqual(wf.admin_next_steps("delivered"), [])
        self.assertEqual(wf.admin_next_steps("cancelled"), [])

    def test_service_refuses_to_mark_paid_by_hand(self):
        number = self.make_order()
        import db
        conn = db.connect(self.db_file)
        with self.assertRaises(svc.OrderError):
            svc.change_status(conn, number, "paid", "admin")
        conn.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
