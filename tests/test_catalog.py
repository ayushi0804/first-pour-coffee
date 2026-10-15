"""Run with:  python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402

DB_FILE = os.path.join(tempfile.mkdtemp(), "test.db")
db.init_db(DB_FILE)
os.environ["DB_PATH"] = DB_FILE

import app as store  # noqa: E402


class CatalogTests(unittest.TestCase):
    def setUp(self):
        store.app.config.update(TESTING=True, DB_PATH=DB_FILE, CSRF_ENABLED=False)
        self.client = store.app.test_client()

    def api(self, **params):
        return self.client.get("/api/products", query_string=params).get_json()

    def test_catalog_size(self):
        self.assertGreaterEqual(self.api()["total"], 8)
        conn = db.connect(DB_FILE)
        cats = conn.execute("SELECT COUNT(DISTINCT category_id) FROM products").fetchone()[0]
        self.assertGreaterEqual(cats, 3)

    def test_category_filter(self):
        data = self.api(category="beans")
        self.assertEqual(data["total"], 5)
        self.assertTrue(all(p["category"] == "Beans" for p in data["products"]))

    def test_price_range(self):
        data = self.api(min=1000, max=2000)
        self.assertGreater(data["total"], 0)
        self.assertTrue(all(1000 <= p["price"] <= 2000 for p in data["products"]))

    def test_search_matches_every_word(self):
        names = [p["name"] for p in self.api(q="ethiopia natural")["products"]]
        self.assertEqual(names, ["Ethiopia Guji Natural, 250 g"])

    def test_search_treats_percent_literally(self):
        self.assertEqual(self.api(q="%")["total"], 0)

    def test_in_stock_only(self):
        self.assertLess(self.api(in_stock=1)["total"], self.api()["total"])

    def test_sort_by_price(self):
        prices = [p["price"] for p in self.api(sort="price-asc")["products"]]
        self.assertEqual(prices, sorted(prices))

    def test_pagination(self):
        first, second = self.api(page=1), self.api(page=2)
        self.assertEqual(first["pages"], 2)
        ids1 = {p["id"] for p in first["products"]}
        ids2 = {p["id"] for p in second["products"]}
        self.assertFalse(ids1 & ids2)

    def test_junk_params_do_not_crash(self):
        self.assertEqual(self.client.get("/?min=abc&max=-5&page=zzz&sort=nope").status_code, 200)

    def test_product_page_and_404(self):
        self.assertEqual(self.client.get("/product/hand-grinder-steel").status_code, 200)
        self.assertEqual(self.client.get("/product/does-not-exist").status_code, 404)

    def test_cart_flow(self):
        self.client.post("/cart/add/1", data={"qty": 2})
        self.assertIn("Ceramic Pour-Over Dripper", self.client.get("/cart").get_data(as_text=True))
        self.client.post("/cart/update/1", data={"qty": 0})
        self.assertIn("Your cart is empty", self.client.get("/cart").get_data(as_text=True))

    def test_cannot_add_sold_out_item(self):
        self.client.post("/cart/add/5")  # brew scale, stock 0
        self.assertIn("Your cart is empty", self.client.get("/cart").get_data(as_text=True))

    def test_indian_price_format(self):
        self.assertEqual(store.inr(145000), "₹1,450")
        self.assertEqual(store.inr(12345600), "₹1,23,456")
        self.assertEqual(store.inr(39900), "₹399")


if __name__ == "__main__":
    unittest.main()
