"""Admin area: sign in, order list, and the status workflow."""
from support import StoreCase, store
import payments


class AdminAccessTests(StoreCase):
    def test_admin_is_off_without_a_password(self):
        store.app.config["ADMIN_PASSWORD"] = ""
        html = self.c.get("/admin/login").get_data(as_text=True)
        self.assertIn("switched off", html)
        r = self.post("/admin/login", username="boss", password="anything")
        self.assertNotEqual(r.status_code, 302)

    def test_pages_need_a_login(self):
        number = self.make_order()
        for url in ("/admin/orders", f"/admin/orders/{number}"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/admin/login", r.headers["Location"])
        r = self.post(f"/admin/orders/{number}/status", to="cancelled")
        self.assertEqual(r.status_code, 302)                       # bounced to login, nothing changed
        self.assertEqual(self.order(number)["status"], "pending")

    def test_wrong_password(self):
        r = self.post("/admin/login", username="boss", password="nope")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Wrong username or password", r.get_data(as_text=True))
        self.assertEqual(self.c.get("/admin/orders").status_code, 302)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.post("/admin/login", username="boss", password="nope")
        r = self.post("/admin/login", username="boss", password="s3cret-pass")   # even the right one is blocked
        self.assertEqual(r.status_code, 429)

    def test_login_works_and_token_rotates(self):
        c = self.admin_client()
        self.assertEqual(c.get("/admin/orders").status_code, 200)
        with c.session_transaction() as s:
            self.assertNotEqual(s["csrf"], "tok")

    def test_login_redirect_only_stays_inside_admin(self):
        r = self.post("/admin/login?next=https://evil.example", username="boss", password="s3cret-pass")
        self.assertTrue(r.headers["Location"].endswith("/admin/orders"))

    def test_sign_out(self):
        c = self.admin_client()
        self.post("/admin/logout", client=c)
        self.assertEqual(c.get("/admin/orders").status_code, 302)

    def test_admin_posts_need_csrf(self):
        number = self.paid_order()
        c = self.admin_client()
        r = c.post(f"/admin/orders/{number}/status", data={"to": "shipped"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.order(number)["status"], "paid")


class AdminOrderListTests(StoreCase):
    def test_list_filter_and_search(self):
        paid = self.paid_order("guji-natural-250")
        pending = self.make_order("hand-grinder-steel")   # a new checkout would cancel an older unpaid one
        c = self.admin_client()
        html = c.get("/admin/orders").get_data(as_text=True)
        self.assertIn(pending, html)
        self.assertIn(paid, html)
        only_paid = c.get("/admin/orders?status=paid").get_data(as_text=True)
        self.assertIn(paid, only_paid)
        self.assertNotIn(pending, only_paid)
        found = c.get(f"/admin/orders?q={paid[:6]}").get_data(as_text=True)
        self.assertIn(paid, found)
        self.assertIn("No orders here", c.get("/admin/orders?q=zzzzzz").get_data(as_text=True))

    def test_dashboard_numbers(self):
        self.paid_order("guji-natural-250")
        self.make_order("hand-grinder-steel")          # left unpaid on purpose
        import db, order_service as svc
        conn = db.connect(self.db_file)
        stats = svc.dashboard_stats(conn)
        conn.close()
        self.assertEqual(stats["counts"]["pending"], 1)
        self.assertEqual(stats["to_ship"], 1)
        self.assertGreater(stats["revenue"], 0)


class AdminWorkflowTests(StoreCase):
    def test_full_lifecycle_pending_to_delivered(self):
        number = self.make_order()
        self.assertEqual(self.order(number)["status"], "pending")
        r, _ = self.pay(number)
        self.assertEqual(self.order(number)["status"], "paid")

        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="shipped", carrier="Delhivery", tracking="DL123456")
        o = self.order(number)
        self.assertEqual(o["status"], "shipped")
        self.assertEqual((o["carrier"], o["tracking_number"]), ("Delhivery", "DL123456"))
        self.assertIsNotNone(o["shipped_at"])
        # the customer can see the tracking details
        page = self.c.get(f"/order/{number}").get_data(as_text=True)
        self.assertIn("DL123456", page)

        self.post(f"/admin/orders/{number}/status", client=c, to="delivered")
        o = self.order(number)
        self.assertEqual(o["status"], "delivered")
        self.assertIsNotNone(o["delivered_at"])

        trail = [(e["from_status"], e["to_status"]) for e in self.events(number) if e["kind"] in ("status", "payment")]
        self.assertEqual(trail, [("pending", "paid"), ("paid", "shipped"), ("shipped", "delivered")])
        actors = {e["actor"] for e in self.events(number)}
        self.assertTrue({"customer", "gateway", "admin"} <= actors)

    def test_cannot_skip_steps(self):
        pending = self.make_order()
        c = self.admin_client()
        self.post(f"/admin/orders/{pending}/status", client=c, to="shipped")
        self.assertEqual(self.order(pending)["status"], "pending")      # unpaid orders can't ship
        self.post(f"/admin/orders/{pending}/status", client=c, to="delivered")
        self.assertEqual(self.order(pending)["status"], "pending")

        paid = self.paid_order("guji-natural-250")
        self.post(f"/admin/orders/{paid}/status", client=c, to="delivered")
        self.assertEqual(self.order(paid)["status"], "paid")             # must ship first

    def test_admin_cannot_mark_an_order_paid(self):
        number = self.make_order()
        c = self.admin_client()
        r = self.post(f"/admin/orders/{number}/status", client=c, to="paid")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.order(number)["status"], "pending")

    def test_finished_orders_cannot_move_again(self):
        number = self.paid_order()
        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="shipped")
        self.post(f"/admin/orders/{number}/status", client=c, to="delivered")
        for target in ("shipped", "cancelled"):
            self.post(f"/admin/orders/{number}/status", client=c, to=target)
        self.assertEqual(self.order(number)["status"], "delivered")

    def test_shipped_orders_cannot_be_cancelled(self):
        number = self.paid_order()
        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="shipped")
        self.post(f"/admin/orders/{number}/status", client=c, to="cancelled", reason="changed mind")
        self.assertEqual(self.order(number)["status"], "shipped")

    def test_cancelling_a_paid_order_refunds_and_restocks(self):
        slug = "hand-grinder-steel"
        before = self.stock(slug)
        number = self.paid_order(slug)
        self.assertEqual(self.stock(slug), before - 1)
        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="cancelled", reason="Out of packaging")
        o = self.order(number)
        self.assertEqual(o["status"], "cancelled")
        self.assertEqual(o["cancel_reason"], "Out of packaging")
        self.assertEqual(o["refund_status"], "refunded")
        self.assertIn(o["payment_id"], self.gw.refunds)
        self.assertEqual(self.gw.refunds[o["payment_id"]]["amount"], o["total"])
        self.assertEqual(self.stock(slug), before)

    def test_cancelling_an_unpaid_order_needs_no_refund(self):
        number = self.make_order()
        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="cancelled")
        o = self.order(number)
        self.assertEqual((o["status"], o["refund_status"]), ("cancelled", "none"))
        self.assertEqual(self.gw.refunds, {})

    def test_failed_refund_can_be_retried(self):
        number = self.paid_order()
        original = self.gw.refund
        state = {"fail": True}

        def flaky(payment_id, amount, notes=None):
            if state["fail"]:
                raise payments.GatewayError("Gateway timeout")
            return original(payment_id, amount, notes)

        self.gw.refund = flaky
        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="cancelled")
        self.assertEqual(self.order(number)["refund_status"], "failed")
        self.assertIn("Refund failed: Gateway timeout", [e["note"] for e in self.events(number)])

        state["fail"] = False
        self.post(f"/admin/orders/{number}/refund", client=c)
        self.assertEqual(self.order(number)["refund_status"], "refunded")

    def test_refund_is_not_issued_twice(self):
        number = self.paid_order()
        c = self.admin_client()
        self.post(f"/admin/orders/{number}/status", client=c, to="cancelled")
        self.post(f"/admin/orders/{number}/refund", client=c)           # nothing left to refund
        self.assertEqual(len(self.gw.refunds), 1)

    def test_admin_order_page_shows_the_right_buttons(self):
        number = self.paid_order()
        c = self.admin_client()
        html = c.get(f"/admin/orders/{number}").get_data(as_text=True)
        self.assertIn("Mark as shipped", html)
        self.assertIn("Cancel and refund order", html)
        self.assertNotIn("Mark as delivered", html)
        self.post(f"/admin/orders/{number}/status", client=c, to="shipped")
        html = c.get(f"/admin/orders/{number}").get_data(as_text=True)
        self.assertIn("Mark as delivered", html)
        self.assertNotIn("Mark as shipped", html)

    def test_unknown_order_is_404(self):
        c = self.admin_client()
        self.assertEqual(c.get("/admin/orders/DB-NOTREAL1").status_code, 404)


if __name__ == "__main__":
    import unittest
    unittest.main()
