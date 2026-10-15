"""
Fills the store with sample orders so the admin screens have something to show.

    python run.py --demo           (or)       python tools/demo_data.py

Orders are created through the same functions the real checkout uses, so stock,
coupon counts and the event log all stay consistent. Payments are recorded directly
(no gateway is contacted), so it is safe to run with real Razorpay test keys set.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coupons as coupon_rules  # noqa: E402
import db  # noqa: E402
import order_service as svc  # noqa: E402
from cart_logic import calc_totals  # noqa: E402

PEOPLE = [
    ("Asha Rawat", "asha.rawat@example.com", "9876543210", "12 Rajpur Road", "Dehradun", "Uttarakhand", "248001"),
    ("Rohan Mehta", "rohan.mehta@example.com", "9811122233", "44 Linking Road, Bandra", "Mumbai", "Maharashtra", "400050"),
    ("Priya Nair", "priya.nair@example.com", "9847011223", "8 MG Road", "Kochi", "Kerala", "682016"),
    ("Karan Singh", "karan.singh@example.com", "9876501234", "21 Sector 17", "Chandigarh", "Chandigarh", "160017"),
    ("Meera Iyer", "meera.iyer@example.com", "9840099887", "5 Besant Nagar 2nd Ave", "Chennai", "Tamil Nadu", "600090"),
    ("Vikram Joshi", "vikram.joshi@example.com", "9822334455", "17 Koregaon Park", "Pune", "Maharashtra", "411001"),
    ("Sana Khan", "sana.khan@example.com", "9899887766", "9 Hauz Khas Village", "New Delhi", "Delhi", "110016"),
    ("Dev Patel", "dev.patel@example.com", "9825012345", "30 CG Road", "Ahmedabad", "Gujarat", "380009"),
]

# (person, [(product slug, qty)], coupon, days ago, how far it got)
ORDERS = [
    (1, [("hand-grinder-steel", 1), ("guji-natural-250", 2)], "WELCOME10", 14, "delivered"),
    (2, [("gooseneck-kettle-800", 1)], None, 12, "delivered"),
    (3, [("chikmagalur-washed-250", 3), ("cone-filter-papers-02", 2)], None, 9, "delivered"),
    (4, [("ceramic-dripper-02", 1), ("cone-filter-papers-02", 1)], "FLAT100", 8, "delivered"),
    (5, [("stoneware-mug-300", 2), ("araku-honey-250", 2)], None, 6, "delivered"),
    (0, [("glass-french-press-600", 1), ("monsooned-malabar-250", 2)], None, 4, "shipped"),
    (6, [("travel-press-brewer", 1), ("guji-natural-250", 1)], None, 3, "shipped"),
    (7, [("insulated-tumbler-350", 1)], None, 2, "shipped"),
    (1, [("double-wall-glass-cups", 1), ("chikmagalur-washed-250", 1)], None, 1, "paid"),
    (2, [("hand-grinder-steel", 1), ("ceramic-dripper-02", 1), ("guji-natural-250", 2)], "FIRSTPOUR20", 1, "paid"),
    (4, [("airtight-bean-canister", 1)], None, 0, "paid"),
    (3, [("travel-press-brewer", 1)], None, 0, "pending"),
    (5, [("gooseneck-kettle-800", 1), ("stoneware-mug-300", 1)], None, 7, "refunded"),
    (6, [("araku-honey-250", 1)], None, 5, "cancelled"),
]


def _lines(conn, picks):
    lines = []
    for slug, qty in picks:
        p = conn.execute("SELECT p.*, c.tax_rate FROM products p JOIN categories c ON c.id = p.category_id "
                         "WHERE p.slug = ?", (slug,)).fetchone()
        lines.append({"product_id": p["id"], "name": p["name"], "image": p["image"], "unit_price": p["price"],
                      "qty": qty, "tax_rate": p["tax_rate"]})
    return lines


def _stamp(dt):
    return dt.isoformat(timespec="seconds")


def run(app):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        try:
            if conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]:
                print("Demo data skipped: the store already has orders.")
                return
            now = datetime.now()
            for idx, (person, picks, code, days_ago, outcome) in enumerate(ORDERS):
                name, email, phone, addr, city, state, pin = PEOPLE[person]
                created = now - timedelta(days=days_ago, hours=idx % 5, minutes=7 * idx)
                if days_ago == 0:
                    created = now - timedelta(minutes=3 + idx)
                lines = _lines(conn, picks)
                coupon = coupon_rules.find(conn, code) if code else None
                totals = calc_totals(lines, coupon)
                info = {"full_name": name, "email": email, "phone": phone, "address1": addr, "address2": "",
                        "city": city, "state": state, "pincode": pin}
                number = svc.create_pending_order(conn, lines, totals, info, now=created)
                order = svc.get_order(conn, number)
                svc.set_gateway_order(conn, order["id"], "demo", f"order_demo{order['id']:04d}")
                if outcome == "pending":
                    continue
                if outcome == "cancelled":
                    svc.change_status(conn, number, "cancelled", "customer", note="Changed my mind.",
                                      now=_stamp(created + timedelta(hours=2)))
                    continue
                paid_at = created + timedelta(minutes=9)
                svc.mark_paid(conn, order["id"], f"pay_demo{order['id']:04d}", "checkout", _stamp(paid_at))
                if outcome == "refunded":
                    svc.change_status(conn, number, "cancelled", "admin", note="Out of packaging for this item.",
                                      now=_stamp(created + timedelta(days=1)))
                    with svc.transaction(conn):
                        conn.execute("UPDATE orders SET refund_status = 'refunded', refund_id = ? WHERE id = ?",
                                     (f"rfnd_demo{order['id']:04d}", order["id"]))
                        svc.add_event(conn, order["id"], "refund", "Refunded through the gateway.", "admin",
                                      now=_stamp(created + timedelta(days=1, minutes=2)))
                    continue
                if outcome in ("shipped", "delivered"):
                    svc.change_status(conn, number, "shipped", "admin", carrier=["Delhivery", "Blue Dart", "India Post"][idx % 3],
                                      tracking=f"FP{1000000 + idx * 7919}", now=_stamp(created + timedelta(days=1)))
                if outcome == "delivered":
                    svc.change_status(conn, number, "delivered", "admin", now=_stamp(created + timedelta(days=3)))

            # a restock, so the stock history has something besides orders
            p = conn.execute("SELECT id FROM products WHERE slug = 'chikmagalur-washed-250'").fetchone()
            svc.adjust_stock(conn, p["id"], 24, "Delivery from the roaster", "admin", _stamp(now - timedelta(days=10)))
            print(f"Demo data added: {len(ORDERS)} orders.")
        finally:
            conn.close()


if __name__ == "__main__":
    import app as store
    run(store.app)
