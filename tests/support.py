"""Shared helpers for the payment and admin tests."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import payments  # noqa: E402

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "boot.db"))
import app as store  # noqa: E402
import admin as admin_module  # noqa: E402

ADDRESS = {
    "full_name": "Asha Rawat", "email": "asha@example.com", "phone": "9876543210",
    "address1": "12 Rajpur Road", "address2": "", "city": "Dehradun",
    "state": "Uttarakhand", "pincode": "248001",
}


class StoreCase(unittest.TestCase):
    """A fresh database, a fresh mock gateway and a test client for every test."""

    def setUp(self):
        self.db_file = os.path.join(tempfile.mkdtemp(), "t.db")
        db.init_db(self.db_file)
        self.gw = payments.MockGateway()
        store.app.config.update(TESTING=True, DB_PATH=self.db_file, CSRF_ENABLED=True, GATEWAY=self.gw,
                                ADMIN_USER="boss", ADMIN_PASSWORD="s3cret-pass")
        admin_module._fails.clear()
        self.c = store.app.test_client()
        with self.c.session_transaction() as s:
            s["csrf"] = "tok"

    # ---- small helpers
    def token(self):
        with self.c.session_transaction() as s:
            return s.get("csrf", "tok")

    def post(self, url, client=None, **data):
        client = client or self.c
        with client.session_transaction() as s:
            tok = s.get("csrf", "tok")
        return client.post(url, data={"csrf_token": tok, **data})

    def post_json(self, url, body, client=None):
        client = client or self.c
        with client.session_transaction() as s:
            tok = s.get("csrf", "tok")
        return client.post(url, json=body, headers={"X-CSRF-Token": tok})

    def pid(self, slug):
        return self.sql("SELECT id FROM products WHERE slug = ?", slug)[0]["id"]

    def sql(self, query, *args):
        conn = db.connect(self.db_file)
        rows = conn.execute(query, args).fetchall()
        conn.commit()
        conn.close()
        return rows

    def order(self, number):
        return self.sql("SELECT * FROM orders WHERE order_number = ?", number)[0]

    def stock(self, slug):
        return self.sql("SELECT stock FROM products WHERE slug = ?", slug)[0]["stock"]

    def events(self, number):
        o = self.order(number)
        return self.sql("SELECT * FROM order_events WHERE order_id = ? ORDER BY id", o["id"])

    def make_order(self, slug="hand-grinder-steel", qty=1):
        """Adds to the cart and goes through checkout. Returns the order number (status pending)."""
        self.post(f"/cart/add/{self.pid(slug)}", qty=str(qty))
        r = self.post("/checkout", **ADDRESS)
        assert r.status_code == 302 and "/pay/" in r.headers["Location"], r.get_data(as_text=True)[:300]
        return r.headers["Location"].rsplit("/", 1)[1]

    def pay(self, number):
        """Completes a payment the way Razorpay Checkout would: signed ids sent to /verify."""
        gid = self.order(number)["gateway_order_id"]
        payment_id, sig = self.gw.simulate_payment(gid)
        r = self.post_json(f"/pay/{number}/verify", {
            "razorpay_order_id": gid, "razorpay_payment_id": payment_id, "razorpay_signature": sig})
        return r, payment_id

    def paid_order(self, slug="hand-grinder-steel", qty=1):
        number = self.make_order(slug, qty)
        r, _ = self.pay(number)
        assert r.status_code == 200, r.get_json()
        return number

    def admin_client(self):
        c = store.app.test_client()
        with c.session_transaction() as s:
            s["csrf"] = "tok"
        r = self.post("/admin/login", client=c, username="boss", password="s3cret-pass")
        assert r.status_code == 302, r.get_data(as_text=True)[:200]
        return c
