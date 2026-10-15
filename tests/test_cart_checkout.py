"""Week 2 tests: cart rules, totals/tax maths, checkout and orders.

Run with:  python -m unittest discover tests
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cart_logic as cl  # noqa: E402
import db  # noqa: E402
import payments  # noqa: E402

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "boot.db"))
import app as store  # noqa: E402

ADDRESS = {
    "full_name": "Asha Rawat", "email": "asha@example.com", "phone": "98765 43210",
    "address1": "12 Rajpur Road", "address2": "", "city": "Dehradun",
    "state": "Uttarakhand", "pincode": "248001", "payment_method": "cod",
}


WELCOME10 = {"code": "WELCOME10", "kind": "percent", "value": 10, "max_discount": 50000, "min_subtotal": 0}
FLAT100 = {"code": "FLAT100", "kind": "flat", "value": 10000, "max_discount": None, "min_subtotal": 99900}


def line(price_rupees, qty=1, tax=18):
    return {"unit_price": price_rupees * 100, "qty": qty, "tax_rate": tax}


class TotalsTests(unittest.TestCase):
    def test_single_item_adds_gst_and_shipping(self):
        t = cl.calc_totals([line(1450)])
        self.assertEqual(t["subtotal"], 145000)
        self.assertEqual(t["tax"], 26100)            # 18% of 1450
        self.assertEqual(t["shipping"], 9900)        # under 1500, so shipping is charged
        self.assertEqual(t["total"], 145000 + 26100 + 9900)

    def test_changing_quantity_recalculates_everything(self):
        one = cl.calc_totals([line(1450, qty=1)])
        two = cl.calc_totals([line(1450, qty=2)])
        self.assertEqual(two["subtotal"], 290000)
        self.assertEqual(two["tax"], 52200)
        self.assertEqual(two["shipping"], 0)         # crossed the free-shipping line
        self.assertEqual(two["total"], 290000 + 52200)
        self.assertNotEqual(one["total"], two["total"])

    def test_changing_tax_rate_changes_total(self):
        at_18 = cl.calc_totals([line(1000, tax=18)])
        at_5 = cl.calc_totals([line(1000, tax=5)])
        self.assertEqual(at_18["tax"], 18000)
        self.assertEqual(at_5["tax"], 5000)
        self.assertEqual(at_18["total"] - at_5["total"], 13000)

    def test_mixed_rates_are_split_by_rate(self):
        t = cl.calc_totals([line(1000, tax=18), line(500, tax=5)])
        self.assertEqual(dict(t["tax_lines"]), {5: 2500, 18: 18000})
        self.assertEqual(t["tax"], 20500)

    def test_tax_rounds_half_up_to_the_paisa(self):
        t = cl.calc_totals([{"unit_price": 1050, "qty": 1, "tax_rate": 5}])   # 52.5 paise
        self.assertEqual(t["tax"], 53)

    def test_discount_is_taxed_after_discount(self):
        t = cl.calc_totals([line(2000, tax=18)], WELCOME10)
        self.assertEqual(t["discount"], 20000)
        self.assertEqual(t["tax"], 32400)            # 18% of 1800, not of 2000

    def test_discount_shares_add_up_exactly(self):
        lines = [{"unit_price": 33333, "qty": 1, "tax_rate": 18},
                 {"unit_price": 77777, "qty": 3, "tax_rate": 5},
                 {"unit_price": 12345, "qty": 7, "tax_rate": 12}]
        t = cl.calc_totals(lines, WELCOME10)
        self.assertEqual(sum(l["discount"] for l in t["lines"]), t["discount"])

    def test_coupon_cap_and_minimum(self):
        self.assertEqual(cl.calc_totals([line(10000)], WELCOME10)["discount"], 50000)     # capped at 500
        self.assertEqual(cl.calc_totals([line(500)], FLAT100)["discount"], 0)             # below the minimum
        self.assertEqual(cl.calc_totals([line(1500)], FLAT100)["discount"], 10000)
        self.assertEqual(cl.calc_totals([line(500)])["discount"], 0)                      # no coupon

    def test_flat_coupon_never_exceeds_the_subtotal(self):
        big = {"code": "BIG", "kind": "flat", "value": 500000, "max_discount": None, "min_subtotal": 0}
        t = cl.calc_totals([line(100)], big)
        self.assertEqual(t["discount"], 10000)
        self.assertEqual(t["tax"], 0)

    def test_free_shipping_boundary(self):
        self.assertEqual(cl.calc_totals([{"unit_price": 150000, "qty": 1, "tax_rate": 0}])["shipping"], 0)
        self.assertEqual(cl.calc_totals([{"unit_price": 149999, "qty": 1, "tax_rate": 0}])["shipping"], 9900)

    def test_empty_cart_is_all_zero(self):
        t = cl.calc_totals([])
        self.assertEqual((t["subtotal"], t["shipping"], t["tax"], t["total"]), (0, 0, 0, 0))


class ValidationTests(unittest.TestCase):
    def test_good_form(self):
        clean, errors = cl.validate_checkout(ADDRESS)
        self.assertEqual(errors, {})
        self.assertEqual(clean["phone"], "9876543210")

    def test_plus_91_prefix_is_accepted(self):
        _, errors = cl.validate_checkout({**ADDRESS, "phone": "+91 98765-43210"})
        self.assertNotIn("phone", errors)

    def test_bad_values_are_reported(self):
        _, errors = cl.validate_checkout({**ADDRESS, "email": "nope", "pincode": "12", "state": "", "phone": "123"})
        self.assertEqual(set(errors), {"email", "pincode", "state", "phone"})

    def test_blank_form(self):
        _, errors = cl.validate_checkout({})
        self.assertIn("full_name", errors)
        self.assertIn("address1", errors)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.db_file = os.path.join(tempfile.mkdtemp(), "t.db")
        db.init_db(self.db_file)
        store.app.config.update(TESTING=True, DB_PATH=self.db_file, CSRF_ENABLED=True,
                                GATEWAY=payments.MockGateway())
        self.gw = store.app.config["GATEWAY"]
        self.c = store.app.test_client()
        with self.c.session_transaction() as s:
            s["csrf"] = "tok"

    # helpers
    def post(self, url, **data):
        return self.c.post(url, data={"csrf_token": "tok", **data})

    def pid(self, slug):
        conn = db.connect(self.db_file)
        row = conn.execute("SELECT id FROM products WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        return row["id"]

    def sql(self, query, *args):
        conn = db.connect(self.db_file)
        rows = conn.execute(query, args).fetchall()
        conn.commit()
        conn.close()
        return rows

    def page(self, url):
        return self.c.get(url).get_data(as_text=True)

    # cart behaviour
    def test_cart_persists_across_requests(self):
        self.post(f"/cart/add/{self.pid('ceramic-dripper-02')}")
        self.assertIn("Ceramic Pour-Over Dripper", self.page("/cart"))
        self.assertIn("Ceramic Pour-Over Dripper", self.page("/cart"))

    def test_adding_twice_increases_quantity(self):
        pid = self.pid("ceramic-dripper-02")
        self.post(f"/cart/add/{pid}")
        self.post(f"/cart/add/{pid}", qty="2")
        with self.c.session_transaction() as s:
            self.assertEqual(s["cart"], {str(pid): 3})

    def test_update_quantity_changes_totals(self):
        pid = self.pid("ceramic-dripper-02")
        self.post(f"/cart/add/{pid}")
        self.assertIn("₹1,810.00", self.page("/cart"))              # 1450 + 18% GST + 99 shipping
        self.post(f"/cart/update/{pid}", qty="2")
        self.assertIn("₹3,422.00", self.page("/cart"))              # 2900 + 522 GST, free shipping

    def test_quantity_zero_removes_last_item_and_shows_empty_cart(self):
        pid = self.pid("ceramic-dripper-02")
        self.post(f"/cart/add/{pid}")
        self.post(f"/cart/update/{pid}", qty="0")
        self.assertIn("Your cart is empty", self.page("/cart"))

    def test_negative_and_junk_quantities(self):
        pid = self.pid("ceramic-dripper-02")
        self.post(f"/cart/add/{pid}")
        self.post(f"/cart/update/{pid}", qty="abc")                 # junk: keep what we had
        with self.c.session_transaction() as s:
            self.assertEqual(s["cart"], {str(pid): 1})
        self.post(f"/cart/update/{pid}", qty="-4")                  # negative: remove
        with self.c.session_transaction() as s:
            self.assertEqual(s["cart"], {})

    def test_cannot_go_over_stock(self):
        pid = self.pid("huila-washed-250")                          # stock 3 in the seed data
        self.post(f"/cart/add/{pid}", qty="50")
        with self.c.session_transaction() as s:
            self.assertEqual(s["cart"], {str(pid): 3})
        self.post(f"/cart/update/{pid}", qty="9")
        with self.c.session_transaction() as s:
            self.assertEqual(s["cart"], {str(pid): 3})

    def test_sold_out_item_cannot_be_added(self):
        self.post(f"/cart/add/{self.pid('brew-scale-timer')}")
        self.assertIn("Your cart is empty", self.page("/cart"))

    def test_item_that_sells_out_is_dropped_with_a_message(self):
        pid = self.pid("ceramic-dripper-02")
        self.post(f"/cart/add/{pid}")
        self.sql("UPDATE products SET stock = 0 WHERE id = ?", pid)
        html = self.page("/cart")
        self.assertIn("went out of stock", html)
        self.assertIn("Your cart is empty", html)

    def test_remove_and_clear(self):
        a, b = self.pid("ceramic-dripper-02"), self.pid("guji-natural-250")
        self.post(f"/cart/add/{a}")
        self.post(f"/cart/add/{b}")
        self.post(f"/cart/remove/{a}")
        with self.c.session_transaction() as s:
            self.assertEqual(s["cart"], {str(b): 1})
        self.post("/cart/clear")
        self.assertIn("Your cart is empty", self.page("/cart"))

    def test_tax_rate_change_shows_up_in_cart(self):
        pid = self.pid("guji-natural-250")                          # beans, 5% GST
        self.post(f"/cart/add/{pid}", qty="3")                      # 3 x 720 = 2160
        self.assertIn("GST 5%", self.page("/cart"))
        self.sql("UPDATE categories SET tax_rate = 12 WHERE slug = 'beans'")
        html = self.page("/cart")
        self.assertIn("GST 12%", html)
        self.assertIn("₹2,419.20", html)                            # 2160 + 259.20

    def test_coupon_apply_and_remove(self):
        self.post(f"/cart/add/{self.pid('hand-grinder-steel')}")    # 5200
        self.post("/cart/coupon", code="welcome10")
        html = self.page("/cart")
        self.assertIn("Discount (WELCOME10)", html)
        self.post("/cart/coupon", remove="1")
        self.assertNotIn("Discount (", self.page("/cart"))

    def test_bad_coupon_is_rejected(self):
        self.post(f"/cart/add/{self.pid('hand-grinder-steel')}")
        self.post("/cart/coupon", code="FREEEE")
        self.assertNotIn("Discount (", self.page("/cart"))

    # checkout
    def test_empty_cart_cannot_check_out(self):
        r = self.c.get("/checkout")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/cart"))
        r = self.post("/checkout", **ADDRESS)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM orders")[0]["n"], 0)

    def test_checkout_page_shows_summary(self):
        self.post(f"/cart/add/{self.pid('hand-grinder-steel')}")
        html = self.page("/checkout")
        self.assertIn("Shipping address", html)
        self.assertIn("Hand Grinder, Steel Burrs", html)

    def test_invalid_form_keeps_values_and_creates_no_order(self):
        self.post(f"/cart/add/{self.pid('hand-grinder-steel')}")
        r = self.post("/checkout", **{**ADDRESS, "pincode": "12"})
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Enter a 6-digit PIN code.", html)
        self.assertIn("Asha Rawat", html)                            # what they typed is kept
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM orders")[0]["n"], 0)

    def test_full_flow_places_order(self):
        dripper, guji = self.pid("ceramic-dripper-02"), self.pid("guji-natural-250")
        self.post(f"/cart/add/{dripper}", qty="2")
        self.post(f"/cart/add/{guji}")
        before = {r["id"]: r["stock"] for r in self.sql("SELECT id, stock FROM products")}

        r = self.post("/checkout", **ADDRESS)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/pay/", r.headers["Location"])
        number = r.headers["Location"].rsplit("/", 1)[1]

        order = self.sql("SELECT * FROM orders WHERE order_number = ?", number)[0]
        self.assertEqual(order["status"], "pending")                 # not paid yet
        # 2 x 1450 at 18% + 1 x 720 at 5% ; subtotal 3620 is over 1500 so shipping is free
        self.assertEqual(order["subtotal"], 362000)
        self.assertEqual(order["tax"], 52200 + 3600)
        self.assertEqual(order["shipping"], 0)
        self.assertEqual(order["total"], 362000 + 52200 + 3600)
        self.assertEqual(order["phone"], "9876543210")
        items = self.sql("SELECT * FROM order_items WHERE order_id = ?", order["id"])
        self.assertEqual(sorted(i["qty"] for i in items), [1, 2])

        after = {r["id"]: r["stock"] for r in self.sql("SELECT id, stock FROM products")}
        self.assertEqual(before[dripper] - after[dripper], 2)         # stock is held right away
        self.assertEqual(before[guji] - after[guji], 1)

        # pay with the simulator
        r = self.post(f"/pay/{number}/mock", outcome="success")
        self.assertTrue(r.headers["Location"].endswith(f"/order/{number}"))
        self.assertEqual(self.sql("SELECT status FROM orders WHERE order_number = ?", number)[0]["status"], "paid")

        page = self.page(f"/order/{number}")
        self.assertIn(number, page)
        self.assertIn("Asha", page)
        self.assertIn("Dehradun", page)
        self.assertIn("Your cart is empty", self.page("/cart"))       # cart is emptied once paid

    def test_resubmitting_replaces_the_unpaid_order(self):
        pid = self.pid("hand-grinder-steel")
        stock = self.sql("SELECT stock FROM products WHERE id = ?", pid)[0]["stock"]
        self.post(f"/cart/add/{pid}")
        self.post("/checkout", **ADDRESS)
        self.post("/checkout", **ADDRESS)
        statuses = sorted(r["status"] for r in self.sql("SELECT status FROM orders"))
        self.assertEqual(statuses, ["cancelled", "pending"])           # only one open order
        self.assertEqual(self.sql("SELECT stock FROM products WHERE id = ?", pid)[0]["stock"], stock - 1)

    def test_stock_change_during_checkout_blocks_the_order(self):
        pid = self.pid("huila-washed-250")
        self.post(f"/cart/add/{pid}", qty="3")
        self.sql("UPDATE products SET stock = 1 WHERE id = ?", pid)
        r = self.post("/checkout", **ADDRESS)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/cart"))
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM orders")[0]["n"], 0)
        self.assertEqual(self.sql("SELECT stock FROM products WHERE id = ?", pid)[0]["stock"], 1)

    def test_order_keeps_the_price_paid(self):
        pid = self.pid("hand-grinder-steel")
        self.post(f"/cart/add/{pid}")
        number = self.post("/checkout", **ADDRESS).headers["Location"].rsplit("/", 1)[1]
        self.sql("UPDATE products SET price = 999900 WHERE id = ?", pid)
        self.assertIn("₹5,200.00", self.page(f"/order/{number}"))

    def test_unknown_order_is_404(self):
        self.assertEqual(self.c.get("/order/DB-NOPE1234").status_code, 404)

    def test_post_without_csrf_token_is_rejected(self):
        r = self.c.post(f"/cart/add/{self.pid('hand-grinder-steel')}")
        self.assertEqual(r.status_code, 400)

    def test_ajax_add_returns_json_with_new_count(self):
        pid = self.pid("hand-grinder-steel")
        r = self.c.post(f"/cart/add/{pid}", headers={"X-Requested-With": "fetch", "X-CSRF-Token": "tok"})
        self.assertEqual(r.get_json()["count"], 1)


if __name__ == "__main__":
    unittest.main()
