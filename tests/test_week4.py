"""Inventory, coupons and the final polish: stock rules, coupon rules, admin screens, run.py."""
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from support import StoreCase, ADDRESS, store
import coupons as coupon_rules
import db
import order_service as svc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run as run_script  # noqa: E402


def cart_text(case):
    return case.c.get("/cart").get_data(as_text=True)


class StockTests(StoreCase):
    def test_stock_drops_when_an_order_is_placed_and_is_logged(self):
        slug = "hand-grinder-steel"
        before = self.stock(slug)
        number = self.make_order(slug, qty=2)
        self.assertEqual(self.stock(slug), before - 2)
        move = self.sql("SELECT * FROM stock_movements WHERE order_id = ?", self.order(number)["id"])[0]
        self.assertEqual((move["delta"], move["kind"], move["stock_after"]), (-2, "order", before - 2))

    def test_cancelling_returns_stock_and_logs_it(self):
        slug = "hand-grinder-steel"
        before = self.stock(slug)
        number = self.make_order(slug, qty=2)
        self.post(f"/pay/{number}/cancel")
        self.assertEqual(self.stock(slug), before)
        kinds = [m["kind"] for m in self.sql("SELECT kind FROM stock_movements WHERE product_id = ? ORDER BY id",
                                             self.pid(slug))]
        self.assertEqual(kinds, ["order", "cancel"])

    def test_buying_the_last_units_shows_out_of_stock(self):
        slug = "huila-washed-250"                          # 3 in the seed data
        self.paid_order(slug, qty=3)
        self.assertEqual(self.stock(slug), 0)
        product = self.c.get(f"/product/{slug}").get_data(as_text=True)
        self.assertIn("Out of stock", product)
        self.assertNotIn(f"/cart/add/{self.pid(slug)}", product)      # no way to add this one
        shop = self.c.get("/?category=beans").get_data(as_text=True)
        self.assertIn("badge-out", shop)
        self.assertIn("Out of stock", shop)

    def test_out_of_stock_product_cannot_be_added(self):
        slug = "brew-scale-timer"                           # 0 in the seed data
        self.post(f"/cart/add/{self.pid(slug)}")
        self.assertIn("Your cart is empty", cart_text(self))

    def test_stock_never_goes_negative_when_two_people_want_the_last_one(self):
        slug = "huila-washed-250"
        self.sql("UPDATE products SET stock = 1 WHERE slug = ?", slug)
        lines = [{"product_id": self.pid(slug), "name": "Huila", "image": "huila-washed", "unit_price": 68000,
                  "qty": 1, "tax_rate": 5}]
        conn = db.connect(self.db_file)
        from cart_logic import calc_totals

        def attempt():
            mine = [dict(l) for l in lines]
            return svc.create_pending_order(conn, mine, calc_totals(mine), dict(ADDRESS))

        attempt()
        with self.assertRaises(svc.OrderError):
            attempt()
        conn.close()
        self.assertEqual(self.stock(slug), 0)

    def test_expired_order_returns_stock(self):
        slug = "hand-grinder-steel"
        before = self.stock(slug)
        number = self.make_order(slug)
        self.sql("UPDATE orders SET expires_at = '2000-01-01T00:00:00' WHERE order_number = ?", number)
        self.c.get("/cart")
        self.assertEqual(self.stock(slug), before)


class AdminInventoryTests(StoreCase):
    def test_inventory_needs_login(self):
        self.assertEqual(self.c.get("/admin/inventory").status_code, 302)
        r = self.post("/admin/inventory/hand-grinder-steel/adjust", delta="5")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.stock("hand-grinder-steel"), 8)

    def test_restock_and_correction(self):
        slug = "hand-grinder-steel"
        c = self.admin_client()
        before = self.stock(slug)
        self.post(f"/admin/inventory/{slug}/adjust", client=c, delta="12", reason="Delivery from supplier")
        self.assertEqual(self.stock(slug), before + 12)
        self.post(f"/admin/inventory/{slug}/adjust", client=c, delta="-2", reason="Broken in storage")
        self.assertEqual(self.stock(slug), before + 10)
        moves = self.sql("SELECT * FROM stock_movements WHERE product_id = ? ORDER BY id", self.pid(slug))
        self.assertEqual([(m["kind"], m["delta"], m["actor"]) for m in moves],
                         [("restock", 12, "admin"), ("adjustment", -2, "admin")])
        self.assertEqual(moves[0]["reason"], "Delivery from supplier")

    def test_cannot_remove_more_than_is_in_stock(self):
        slug = "huila-washed-250"                           # 3 in stock
        c = self.admin_client()
        self.post(f"/admin/inventory/{slug}/adjust", client=c, delta="-4")
        self.assertEqual(self.stock(slug), 3)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM stock_movements")[0]["n"], 0)

    def test_junk_and_zero_changes_are_refused(self):
        slug = "hand-grinder-steel"
        c = self.admin_client()
        before = self.stock(slug)
        for bad in ("0", "abc", "", "99999999", "1.5"):
            self.post(f"/admin/inventory/{slug}/adjust", client=c, delta=bad)
        self.assertEqual(self.stock(slug), before)

    def test_filters_and_dashboard(self):
        c = self.admin_client()
        out = c.get("/admin/inventory?show=out").get_data(as_text=True)
        self.assertIn("Digital Brew Scale", out)
        self.assertNotIn("Hand Grinder", out)
        low = c.get("/admin/inventory?show=low").get_data(as_text=True)
        self.assertIn("Colombia Huila", low)
        self.assertNotIn("Digital Brew Scale", low)
        orders = c.get("/admin/orders").get_data(as_text=True)
        self.assertIn("1 out, 1 low on stock", orders)

    def test_product_history_page_links_orders(self):
        slug = "hand-grinder-steel"
        number = self.make_order(slug)
        c = self.admin_client()
        html = c.get(f"/admin/inventory/{slug}").get_data(as_text=True)
        self.assertIn(f"Order {number}", html)
        self.assertEqual(c.get("/admin/inventory/not-a-product").status_code, 404)


class CouponRuleTests(StoreCase):
    def add(self, slug="hand-grinder-steel", qty=1):
        self.post(f"/cart/add/{self.pid(slug)}", qty=str(qty))

    def apply(self, code, **extra):
        self.post("/cart/coupon", code=code, **extra)
        return cart_text(self)

    def test_percentage_coupon(self):
        self.add("guji-natural-250")                            # 720, so 10% is well under the cap
        html = self.apply("WELCOME10")
        self.assertIn("Discount (WELCOME10)", html)
        self.assertIn("−₹72.00", html)

    def test_percentage_coupon_is_capped(self):
        self.add()                                              # 5200: 10% would be 520, the cap is 500
        self.assertIn("−₹500.00", self.apply("WELCOME10"))

    def test_percentage_coupon_respects_its_cap(self):
        self.add(qty=2)                                         # 10400, 20% would be 2080
        html = self.apply("FIRSTPOUR20")
        self.assertIn("−₹1,000.00", html)

    def test_flat_coupon_and_minimum(self):
        self.add("cone-filter-papers-02")                       # 399, under the 999 minimum
        self.assertIn("Spend at least ₹999", self.apply("FLAT100"))
        self.assertNotIn("Discount (", cart_text(self))
        self.add("hand-grinder-steel")
        self.assertIn("−₹100.00", self.apply("FLAT100"))

    def test_codes_are_not_case_sensitive(self):
        self.add()
        self.assertIn("Discount (WELCOME10)", self.apply("  welcome10 "))

    def test_unknown_expired_inactive_and_future_codes(self):
        self.add()
        self.assertIn("isn&#39;t valid", self.apply("NOPE"))
        self.assertIn("has expired", self.apply("SUMMER25"))
        self.sql("UPDATE coupons SET active = 0 WHERE code = 'WELCOME10'")
        self.assertIn("switched off", self.apply("WELCOME10"))
        self.sql("UPDATE coupons SET active = 1, starts_on = ? WHERE code = 'WELCOME10'",
                 (date.today() + timedelta(days=3)).isoformat())
        self.assertIn("starts on", self.apply("WELCOME10"))
        self.assertNotIn("Discount (", cart_text(self))

    def test_usage_limit(self):
        self.add()
        self.sql("UPDATE coupons SET max_uses = 5, used_count = 5 WHERE code = 'WELCOME10'")
        self.assertIn("fully redeemed", self.apply("WELCOME10"))

    def test_only_one_coupon_at_a_time(self):
        self.add(qty=2)
        self.apply("WELCOME10")
        html = self.apply("FLAT100")
        self.assertIn("Discount (FLAT100)", html)
        self.assertNotIn("Discount (WELCOME10)", html)

    def test_coupon_is_dropped_when_the_cart_falls_below_its_minimum(self):
        self.add("hand-grinder-steel")
        self.apply("FLAT100")
        self.post(f"/cart/remove/{self.pid('hand-grinder-steel')}")
        self.add("cone-filter-papers-02")
        html = cart_text(self)
        self.assertNotIn("Discount (", html)

    def test_cart_lists_public_coupons_as_hints(self):
        self.add()
        html = cart_text(self)
        self.assertIn("WELCOME10", html)
        self.assertIn("FIRSTPOUR20", html)
        self.assertNotIn("SUMMER25", html)                      # expired and not public

    def test_coupon_applies_through_checkout(self):
        self.add()
        self.apply("WELCOME10")
        html = self.c.get("/checkout").get_data(as_text=True)
        self.assertIn("Discount (WELCOME10)", html)
        number = self.post("/checkout", **ADDRESS).headers["Location"].rsplit("/", 1)[1]
        o = self.order(number)
        self.assertEqual((o["coupon_code"], o["discount"]), ("WELCOME10", 50000))     # 10% capped at 500
        self.assertEqual(self.sql("SELECT used_count FROM coupons WHERE code = 'WELCOME10'")[0]["used_count"], 1)
        # the total charged includes the discount: (5200 - 500) + 18% GST
        self.assertEqual(o["total"], 470000 + 84600)

    def test_coupon_can_be_applied_on_the_checkout_page(self):
        self.add()
        self.post("/cart/coupon", code="WELCOME10", next="checkout")
        self.assertIn("Discount (WELCOME10)", self.c.get("/checkout").get_data(as_text=True))

    def test_cancelling_gives_the_coupon_use_back(self):
        self.add()
        self.apply("WELCOME10")
        number = self.post("/checkout", **ADDRESS).headers["Location"].rsplit("/", 1)[1]
        self.assertEqual(self.sql("SELECT used_count FROM coupons WHERE code = 'WELCOME10'")[0]["used_count"], 1)
        self.post(f"/pay/{number}/cancel")
        self.assertEqual(self.sql("SELECT used_count FROM coupons WHERE code = 'WELCOME10'")[0]["used_count"], 0)

    def test_expired_unpaid_order_gives_the_coupon_use_back(self):
        self.add()
        self.apply("WELCOME10")
        number = self.post("/checkout", **ADDRESS).headers["Location"].rsplit("/", 1)[1]
        self.sql("UPDATE orders SET expires_at = '2000-01-01T00:00:00' WHERE order_number = ?", number)
        self.c.get("/cart")
        self.assertEqual(self.sql("SELECT used_count FROM coupons WHERE code = 'WELCOME10'")[0]["used_count"], 0)

    def test_once_per_customer(self):
        self.add()
        self.apply("WELCOME10")
        number = self.post("/checkout", **ADDRESS).headers["Location"].rsplit("/", 1)[1]
        self.pay(number)
        # same email comes back
        self.add("guji-natural-250", qty=3)
        self.apply("WELCOME10")                                 # looks fine in the cart (email unknown yet)
        r = self.post("/checkout", **ADDRESS)
        self.assertTrue(r.headers["Location"].endswith("/checkout"))
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM orders")[0]["n"], 1)      # nothing new was placed
        self.assertNotIn("Discount (", self.c.get("/checkout").get_data(as_text=True))
        # a different email can use it
        self.add("guji-natural-250", qty=3)
        self.apply("WELCOME10")
        other = {**ADDRESS, "email": "someone.else@example.com"}
        r = self.post("/checkout", **other)
        self.assertIn("/pay/", r.headers["Location"])

    def test_cancelled_orders_do_not_count_against_once_per_customer(self):
        self.add()
        self.apply("WELCOME10")
        number = self.post("/checkout", **ADDRESS).headers["Location"].rsplit("/", 1)[1]
        self.post(f"/pay/{number}/cancel")
        self.add()
        self.apply("WELCOME10")
        self.assertIn("/pay/", self.post("/checkout", **ADDRESS).headers["Location"])

    def test_last_use_goes_to_whoever_checks_out_first(self):
        self.sql("UPDATE coupons SET max_uses = 1 WHERE code = 'WELCOME10'")
        # two shoppers both applied the code while it was still free
        second = store.app.test_client()
        with second.session_transaction() as s:
            s["csrf"] = "tok"
        for client in (self.c, second):
            self.post(f"/cart/add/{self.pid('hand-grinder-steel')}", client=client)
            self.post("/cart/coupon", client=client, code="WELCOME10")
        first_try = self.post("/checkout", **ADDRESS)
        self.assertIn("/pay/", first_try.headers["Location"])
        other = {**ADDRESS, "email": "other@example.com"}
        late = self.post("/checkout", client=second, **other)
        self.assertTrue(late.headers["Location"].endswith("/checkout"))              # bounced, not charged less
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM orders")[0]["n"], 1)
        self.assertEqual(self.sql("SELECT used_count FROM coupons WHERE code = 'WELCOME10'")[0]["used_count"], 1)

    def test_describe(self):
        conn = db.connect(self.db_file)
        self.assertEqual(coupon_rules.describe(coupon_rules.find(conn, "WELCOME10")), "10% off, up to ₹500")
        self.assertEqual(coupon_rules.describe(coupon_rules.find(conn, "FLAT100")), "₹100 off orders over ₹999")
        conn.close()


class AdminCouponTests(StoreCase):
    form = {"code": "monsoon15", "kind": "percent", "value": "15", "max_discount": "400", "min_subtotal": "1000",
            "max_uses": "20", "starts_on": "", "expires_on": "", "description": "Rainy day offer"}

    def test_coupons_need_login(self):
        self.assertEqual(self.c.get("/admin/coupons").status_code, 302)
        self.post("/admin/coupons", **self.form)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM coupons WHERE code = 'MONSOON15'")[0]["n"], 0)

    def test_list_shows_state_of_each_coupon(self):
        c = self.admin_client()
        html = c.get("/admin/coupons").get_data(as_text=True)
        self.assertIn("WELCOME10", html)
        self.assertIn("Expired", html)                           # SUMMER25
        self.assertIn("Live", html)

    def test_create_a_coupon_and_use_it(self):
        c = self.admin_client()
        r = self.post("/admin/coupons", client=c, once_per_customer="1", public="1", **self.form)
        self.assertEqual(r.status_code, 302)
        row = self.sql("SELECT * FROM coupons WHERE code = 'MONSOON15'")[0]
        self.assertEqual((row["kind"], row["value"], row["max_discount"], row["min_subtotal"], row["max_uses"]),
                         ("percent", 15, 40000, 100000, 20))
        self.assertEqual((row["once_per_customer"], row["public"]), (1, 1))
        # a shopper can now use it
        self.post(f"/cart/add/{self.pid('hand-grinder-steel')}")
        self.post("/cart/coupon", code="MONSOON15")
        self.assertIn("Discount (MONSOON15)", cart_text(self))

    def test_flat_coupon_value_is_stored_in_paise(self):
        c = self.admin_client()
        self.post("/admin/coupons", client=c, code="TAKE250", kind="flat", value="250", min_subtotal="", max_discount="",
                  max_uses="", starts_on="", expires_on="")
        row = self.sql("SELECT * FROM coupons WHERE code = 'TAKE250'")[0]
        self.assertEqual((row["kind"], row["value"], row["min_subtotal"]), ("flat", 25000, 0))

    def test_bad_forms_are_rejected_with_messages(self):
        c = self.admin_client()
        cases = [
            ({"code": "WELCOME10"}, "already exists"),
            ({"code": "no spaces!"}, "3 to 20"),
            ({"code": "AB"}, "3 to 20"),
            ({"value": "150"}, "out of range"),
            ({"value": "12.5"}, "whole numbers"),
            ({"value": ""}, "Enter a value"),
            ({"value": "abc"}, "must be a number"),
            ({"starts_on": "2030-05-10", "expires_on": "2030-05-01"}, "before the start"),
            ({"expires_on": "not-a-date"}, "date picker"),
            ({"kind": "bogus"}, "Choose"),
        ]
        for change, message in cases:
            r = self.post("/admin/coupons", client=c, **{**self.form, **change})
            self.assertEqual(r.status_code, 200, change)
            self.assertIn(message, r.get_data(as_text=True), change)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM coupons WHERE code = 'MONSOON15'")[0]["n"], 0)

    def test_switch_off_and_on(self):
        c = self.admin_client()
        cid = self.sql("SELECT id FROM coupons WHERE code = 'WELCOME10'")[0]["id"]
        self.post(f"/admin/coupons/{cid}/toggle", client=c)
        self.assertEqual(self.sql("SELECT active FROM coupons WHERE id = ?", cid)[0]["active"], 0)
        self.post(f"/admin/coupons/{cid}/toggle", client=c)
        self.assertEqual(self.sql("SELECT active FROM coupons WHERE id = ?", cid)[0]["active"], 1)
        self.assertEqual(self.post("/admin/coupons/9999/toggle", client=c).status_code, 404)


class PolishTests(StoreCase):
    def test_health_check(self):
        r = self.c.get("/healthz")
        self.assertEqual((r.status_code, r.get_json()["status"]), (200, "ok"))

    def test_security_headers(self):
        r = self.c.get("/")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertIn("Referrer-Policy", r.headers)

    def test_admin_pages_are_not_cached(self):
        c = self.admin_client()
        self.assertEqual(c.get("/admin/orders").headers["Cache-Control"], "no-store")

    def test_store_name_and_favicon(self):
        html = self.c.get("/").get_data(as_text=True)
        self.assertIn("First Pour Coffee Co.", html)
        self.assertNotIn("Daybreak", html)
        self.assertIn("favicon.svg", html)

    def test_error_pages(self):
        self.assertIn("couldn't find", self.c.get("/nope").get_data(as_text=True))
        with store.app.test_request_context():
            body, code = store.server_error(None)
        self.assertEqual(code, 500)
        self.assertIn("Something went wrong", body)

    def test_order_numbers_use_the_new_prefix(self):
        self.assertTrue(self.make_order().startswith("FP-"))


class RunScriptTests(StoreCase):
    def test_bootstrap_creates_env_with_fresh_secrets(self):
        d = Path(tempfile.mkdtemp())
        example = d / ".env.example"
        example.write_text("# comment\nSECRET_KEY=change-this-too\nADMIN_PASSWORD=change-me-please\nOTHER=keep\n")
        env = d / ".env"
        creds = run_script.bootstrap_env(env, example)
        text = env.read_text()
        self.assertEqual(creds["user"], "admin")
        self.assertIn(f"ADMIN_PASSWORD={creds['password']}", text)
        self.assertNotIn("change-me-please", text)
        self.assertNotIn("change-this-too", text)
        self.assertIn("# comment", text)
        self.assertIn("OTHER=keep", text)
        self.assertGreaterEqual(len(creds["password"]), 10)

    def test_bootstrap_never_overwrites_an_existing_env(self):
        d = Path(tempfile.mkdtemp())
        (d / ".env.example").write_text("SECRET_KEY=x\nADMIN_PASSWORD=y\n")
        (d / ".env").write_text("SECRET_KEY=mine\nADMIN_PASSWORD=mine\n")
        self.assertIsNone(run_script.bootstrap_env(d / ".env", d / ".env.example"))
        self.assertIn("mine", (d / ".env").read_text())

    def test_each_bootstrap_makes_different_secrets(self):
        d1, d2 = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        for d in (d1, d2):
            (d / ".env.example").write_text("SECRET_KEY=x\nADMIN_PASSWORD=y\n")
        a = run_script.bootstrap_env(d1 / ".env", d1 / ".env.example")
        b = run_script.bootstrap_env(d2 / ".env", d2 / ".env.example")
        self.assertNotEqual(a["password"], b["password"])


class DemoDataTests(StoreCase):
    def test_demo_data_is_consistent_and_idempotent(self):
        from tools import demo_data
        demo_data.run(store.app)
        counts = {r["status"]: r["n"] for r in self.sql("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")}
        self.assertEqual(sum(counts.values()), len(demo_data.ORDERS))
        self.assertTrue({"pending", "paid", "shipped", "delivered", "cancelled"} <= set(counts))
        # nothing went negative, and every product's stock matches its movement log
        for p in self.sql("SELECT id, stock FROM products"):
            self.assertGreaterEqual(p["stock"], 0)
        demo_data.run(store.app)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM orders")[0]["n"], len(demo_data.ORDERS))


if __name__ == "__main__":
    import unittest
    unittest.main()
