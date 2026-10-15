import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from math import ceil
from urllib.parse import urlparse

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

import admin
import config
import coupons as coupon_rules
import db
import order_service as svc
import pay
import workflow as wf
from cart_logic import MAX_PER_LINE, STATES, calc_totals, validate_checkout
from db import get_db
from payments import ConfigError, GatewayError, get_gateway

config.load_env()

PER_PAGE = 9
CURRENCY = "₹"

SORTS = {
    "featured":   ("Featured",           "p.rating_count DESC, p.id"),
    "newest":     ("Newest",             "p.added_on DESC, p.id"),
    "price-asc":  ("Price: low to high", "p.price ASC, p.id"),
    "price-desc": ("Price: high to low", "p.price DESC, p.id"),
    "rating":     ("Top rated",          "p.rating DESC, p.rating_count DESC"),
    "name":       ("Name A-Z",           "p.name COLLATE NOCASE ASC"),
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["DB_PATH"] = os.environ.get("DB_PATH", str(db.DB_PATH))
app.config["CSRF_ENABLED"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "") == "1"   # set to 1 behind HTTPS
app.config["ADMIN_USER"] = os.environ.get("ADMIN_USER", "admin")
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "")
app.register_blueprint(pay.bp)
app.register_blueprint(admin.bp)

# Validate payment settings before starting the app.

try:
    from payments import build_gateway_from_env
    app.config["GATEWAY"] = build_gateway_from_env()
except ConfigError as exc:
    raise SystemExit(f"Payment settings problem: {exc}")
# the cart lives in the session cookie; keep it for 30 days so it survives closing the browser
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)


# ---------------------------------------------------------------- database

app.teardown_appcontext(db.close_db)


def ensure_db():
    from pathlib import Path
    path = Path(app.config["DB_PATH"])
    if path.exists():
        conn = db.connect(path)
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        conn.close()
        if {"coupons", "stock_movements", "order_events"} <= tables:
            return
        # Reinitialize the database if it is missing or has an outdated schema.
        db.init_db(path)


@app.cli.command("initdb")
def initdb_command():
    """Reset the database and reload the sample catalog."""
    db.init_db(app.config["DB_PATH"])
    print("Database reset.")


# ---------------------------------------------------------------- helpers

def inr(paise, force_decimals=False):
    """12345600 paise -> '₹1,23,456' using Indian digit grouping."""
    rupees, rem = divmod(int(paise), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"{CURRENCY}{s}" + (f".{rem:02d}" if (rem or force_decimals) else "")


app.jinja_env.filters["inr"] = inr
# totals and receipts always show paise so the columns line up
app.jinja_env.filters["inr2"] = lambda p: inr(p, force_decimals=True)


PHOTO_TYPES = ("jpg", "jpeg", "webp", "png", "svg")


def img_url(name):
    """Use a real photo if one exists in static/img/products, otherwise the drawn illustration."""
    folder = os.path.join(app.static_folder, "img", "products")
    for ext in PHOTO_TYPES:
        if os.path.exists(os.path.join(folder, f"{name}.{ext}")):
            return url_for("static", filename=f"img/products/{name}.{ext}")
    return url_for("static", filename="img/products/placeholder.svg")


app.jinja_env.globals["img_url"] = img_url


def like_escape(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def to_paise(value):
    """Turn a '?min=500' style rupee value into paise, or None if it is junk."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return int(n * 100) if n >= 0 else None


def read_filters(args):
    f = {
        "q": (args.get("q") or "").strip()[:80],
        "category": args.get("category") or "",
        "min": args.get("min") or "",
        "max": args.get("max") or "",
        "in_stock": args.get("in_stock") == "1",
        "sort": args.get("sort") if args.get("sort") in SORTS else "featured",
    }
    try:
        f["page"] = max(1, int(args.get("page", 1)))
    except ValueError:
        f["page"] = 1
    return f


def build_where(f, skip_category=False):
    clauses, params = [], []

    # every word has to match the name, the summary, the description or the category
    for term in f["q"].split():
        like = f"%{like_escape(term)}%"
        clauses.append(
            "(p.name LIKE ? ESCAPE '\\' OR p.summary LIKE ? ESCAPE '\\' "
            "OR p.description LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')"
        )
        params += [like] * 4

    if f["category"] and not skip_category:
        clauses.append("c.slug = ?")
        params.append(f["category"])

    lo, hi = to_paise(f["min"]), to_paise(f["max"])
    if lo is not None:
        clauses.append("p.price >= ?")
        params.append(lo)
    if hi is not None:
        clauses.append("p.price <= ?")
        params.append(hi)
    if f["in_stock"]:
        clauses.append("p.stock > 0")

    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


BASE_SELECT = """
    FROM products p JOIN categories c ON c.id = p.category_id
"""


def search_products(f):
    where, params = build_where(f)
    conn = get_db()

    total = conn.execute("SELECT COUNT(*)" + BASE_SELECT + where, params).fetchone()[0]
    pages = max(1, ceil(total / PER_PAGE))
    page = min(f["page"], pages)

    rows = conn.execute(
        "SELECT p.*, c.name AS category_name, c.slug AS category_slug"
        + BASE_SELECT + where + f" ORDER BY {SORTS[f['sort']][1]} LIMIT ? OFFSET ?",
        params + [PER_PAGE, (page - 1) * PER_PAGE],
    ).fetchall()
    return rows, total, page, pages


def category_counts(f):
    """Counts per category for the current search/price filters, ignoring the chosen category."""
    where, params = build_where(f, skip_category=True)
    conn = get_db()
    counts = {
        r["slug"]: r["n"]
        for r in conn.execute(
            "SELECT c.slug, COUNT(*) AS n" + BASE_SELECT + where + " GROUP BY c.id", params
        )
    }
    cats = conn.execute("SELECT slug, name FROM categories ORDER BY sort_order").fetchall()
    return [{"slug": c["slug"], "name": c["name"], "n": counts.get(c["slug"], 0)} for c in cats]


def price_bounds():
    row = get_db().execute("SELECT MIN(price), MAX(price) FROM products").fetchone()
    return row[0] // 100, -(-row[1] // 100)


def card_dict(row):
    d = dict(row)
    d["on_sale"] = bool(d["compare_at"] and d["compare_at"] > d["price"])
    d["percent_off"] = round(100 - d["price"] * 100 / d["compare_at"]) if d["on_sale"] else 0
    d["is_new"] = d["added_on"] >= "2026-06-01"
    return d


def url_with(**changes):
    """Current shop URL with some query params changed. Empty values are dropped, page resets."""
    args = request.args.to_dict()
    if "page" not in changes:
        args.pop("page", None)
    args.update(changes)
    args = {k: v for k, v in args.items() if v not in (None, "", False)}
    return url_for("shop", **args)


app.jinja_env.globals["url_with"] = url_with


@app.context_processor
def inject_globals():
    return {
        "cart_count": cart_count(),
        "currency": CURRENCY,
        "sorts": SORTS,
        "status_labels": wf.LABELS,
        "test_mode": True,
    }


# ---------------------------------------------------------------- pages

@app.route("/")
def shop():
    f = read_filters(request.args)
    rows, total, page, pages = search_products(f)
    lo, hi = price_bounds()

    ctx = {
        "f": f,
        "products": [card_dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": pages,
        "categories": category_counts(f),
        "all_total": get_db().execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "price_lo": lo,
        "price_hi": hi,
    }
    # the JS asks for just the results block so the page does not reload
    if request.headers.get("X-Partial") == "1":
        return render_template("_partial.html", **ctx)
    return render_template("shop.html", **ctx)


@app.route("/product/<slug>")
def product(slug):
    conn = get_db()
    row = conn.execute(
        "SELECT p.*, c.name AS category_name, c.slug AS category_slug, c.tax_rate " + BASE_SELECT + "WHERE p.slug = ?",
        (slug,),
    ).fetchone()
    if row is None:
        abort(404)
    related = conn.execute(
        "SELECT p.*, c.name AS category_name, c.slug AS category_slug " + BASE_SELECT
        + "WHERE p.category_id = ? AND p.id != ? ORDER BY p.rating DESC LIMIT 4",
        (row["category_id"], row["id"]),
    ).fetchall()
    return render_template(
        "product.html",
        p=card_dict(row),
        specs=json.loads(row["specs"]),
        paragraphs=row["description"].split("\n"),
        related=[card_dict(r) for r in related],
    )


@app.route("/api/products")
def api_products():
    f = read_filters(request.args)
    rows, total, page, pages = search_products(f)
    return jsonify(
        total=total, page=page, pages=pages,
        products=[
            {
                "id": r["id"], "slug": r["slug"], "name": r["name"],
                "category": r["category_name"],
                "price": r["price"] / 100,
                "compare_at": r["compare_at"] / 100 if r["compare_at"] else None,
                "summary": r["summary"], "stock": r["stock"],
                "rating": r["rating"],
                "image": request.host_url.rstrip("/") + img_url(r["image"]),
                "url": url_for("product", slug=r["slug"], _external=True),
            }
            for r in rows
        ],
    )


# ---------------------------------------------------------------- security

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    """Every POST must carry the token from the session (hidden field or header)."""
    if request.method != "POST" or not app.config["CSRF_ENABLED"]:
        return
    if request.endpoint == "pay.webhook":      # authenticated by its own signature instead
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    if not hmac.compare_digest(sent, session.get("csrf", "")):
        abort(400)


# ---------------------------------------------------------------- cart

def get_cart():
    return session.get("cart", {})


def save_cart(cart):
    session["cart"] = cart
    session.permanent = True


def cart_count():
    return sum(get_cart().values())


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def back(default):
    """Go back to the page the user came from, but only if it is on this site."""
    ref = request.referrer
    if ref and urlparse(ref).netloc == request.host:
        return redirect(ref)
    return redirect(default)


def cart_reply(message, ok=True, default="cart"):
    if wants_json():
        return jsonify(ok=ok, message=message, count=cart_count()), (200 if ok else 409)
    flash(message, "ok" if ok else "error")
    return back(url_for(default))


def parse_qty(raw, fallback=1):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def my_reserved():
    """Stock held by this shopper's own unpaid order, so it doesn't look out of stock to them."""
    number = session.get("pending_order")
    if not number:
        return {}
    conn = get_db()
    order = svc.get_order(conn, number)
    if order is None or order["status"] != wf.PENDING:
        return {}
    return {it["product_id"]: it["qty"] for it in svc.get_items(conn, order["id"])}


def sync_pending_order():
    """Tidy the session after the shopper's last order moved on (paid in another tab, expired...)."""
    number = session.get("pending_order")
    if not number:
        return
    order = svc.get_order(get_db(), number)
    if order is not None and order["status"] == wf.PENDING:
        return
    session.pop("pending_order", None)
    if order is not None and order["status"] in (wf.PAID, wf.SHIPPED, wf.DELIVERED):
        save_cart({})                       # Clear the cart after the order is paid.
        session.pop("coupon", None)


def load_cart_lines():
    """
    Turns the {product_id: qty} in the session into full lines using the current
    catalog. Anything that changed since the item was added (sold out, less stock
    than asked for, removed from the shop) is fixed here, and the reasons come back
    as notices so the shopper is told instead of surprised at checkout.
    """
    cart = get_cart()
    if not cart:
        return [], []

    ids = [int(k) for k in cart if str(k).isdigit()]
    if not ids:
        save_cart({})
        return [], []

    marks = ",".join("?" * len(ids))
    rows = get_db().execute(
        "SELECT p.*, c.tax_rate, c.name AS category_name FROM products p "
        f"JOIN categories c ON c.id = p.category_id WHERE p.id IN ({marks})", ids
    ).fetchall()
    by_id = {r["id"]: r for r in rows}

    reserved = my_reserved()
    lines, notices, fixed = [], [], {}
    for key, qty in cart.items():
        row = by_id.get(int(key)) if str(key).isdigit() else None
        if row is None:
            notices.append("An item in your cart is no longer available and was removed.")
            continue
        available = row["stock"] + reserved.get(row["id"], 0)
        if available < 1:
            notices.append(f"{row['name']} went out of stock and was removed from your cart.")
            continue
        qty = max(1, qty)
        allowed = min(available, MAX_PER_LINE)
        if qty > allowed:
            notices.append(f"Only {allowed} of {row['name']} available, so we lowered the quantity.")
            qty = allowed
        fixed[str(row["id"])] = qty
        lines.append({
            "product_id": row["id"], "slug": row["slug"], "name": row["name"],
            "image": row["image"], "unit_price": row["price"], "qty": qty,
            "tax_rate": row["tax_rate"], "stock": allowed,
            "category": row["category_name"],
        })

    if fixed != cart:
        save_cart(fixed)
    return lines, notices


def price_cart(lines, email=None):
    """
    Totals for the cart, with the shopper's coupon applied if it is still valid.
    A coupon that stopped being valid (expired, minimum no longer met...) is dropped and explained.
    """
    base = calc_totals(lines)
    code = session.get("coupon")
    if not code or not lines:
        return base
    coupon, note = coupon_rules.check(get_db(), code, base["subtotal"], email)
    if coupon is None:
        session.pop("coupon", None)
        base["coupon_note"] = note
        return base
    return calc_totals(lines, coupon)


@app.post("/cart/add/<int:product_id>")
def cart_add(product_id):
    p = get_db().execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if p is None:
        abort(404)
    if p["stock"] < 1:
        return cart_reply(f"{p['name']} is out of stock.", ok=False, default="shop")

    cart = get_cart()
    key = str(product_id)
    have = cart.get(key, 0)
    allowed = min(p["stock"], MAX_PER_LINE)
    if have >= allowed:
        return cart_reply(f"You already have the most we can offer of {p['name']} ({allowed}).",
                          ok=False, default="shop")

    want = max(1, parse_qty(request.form.get("qty", 1)))
    cart[key] = min(have + want, allowed)
    save_cart(cart)
    msg = f"Added {p['name']} to your cart."
    if have + want > allowed:
        msg = f"Added {p['name']}. {allowed} is the most we can offer."
    return cart_reply(msg, default="shop")


@app.post("/cart/update/<int:product_id>")
def cart_update(product_id):
    cart = get_cart()
    key = str(product_id)
    if key not in cart:
        return redirect(url_for("cart"))

    qty = parse_qty(request.form.get("qty"), fallback=cart[key])
    if qty <= 0:                     # quantity 0 (or less) means remove
        cart.pop(key)
        save_cart(cart)
        flash("Removed from your cart.", "ok")
        return redirect(url_for("cart"))

    row = get_db().execute("SELECT name, stock FROM products WHERE id = ?", (product_id,)).fetchone()
    allowed = min(row["stock"] + my_reserved().get(product_id, 0), MAX_PER_LINE) if row else 0
    if qty > allowed:
        flash(f"Only {allowed} of {row['name']} available.", "error")
        qty = allowed
    if qty < 1:
        cart.pop(key)
    else:
        cart[key] = qty
    save_cart(cart)
    return redirect(url_for("cart"))


@app.post("/cart/remove/<int:product_id>")
def cart_remove(product_id):
    cart = get_cart()
    if cart.pop(str(product_id), None) is not None:
        save_cart(cart)
        flash("Removed from your cart.", "ok")
    return redirect(url_for("cart"))


@app.post("/cart/clear")
def cart_clear():
    save_cart({})
    session.pop("coupon", None)
    flash("Cart cleared.", "ok")
    return redirect(url_for("cart"))


@app.post("/cart/coupon")
def cart_coupon():
    # the code can be applied from the cart or from the checkout page
    target = "checkout" if request.form.get("next") == "checkout" else "cart"
    if request.form.get("remove"):
        session.pop("coupon", None)
        flash("Coupon removed.", "ok")
        return redirect(url_for(target))

    code = (request.form.get("code") or "").strip()
    lines, _ = load_cart_lines()
    if not code:
        flash("Enter a coupon code.", "error")
    elif not lines:
        flash("Add something to your cart first.", "error")
    else:
        base = calc_totals(lines)
        coupon, note = coupon_rules.check(get_db(), code, base["subtotal"])
        if coupon is None:
            flash(note, "error")
        else:
            session["coupon"] = coupon["code"]
            flash(f"{coupon['code']} applied: {coupon_rules.describe(coupon)}.", "ok")
    return redirect(url_for(target))


@app.route("/cart")
def cart():
    svc.expire_stale_orders(get_db())
    sync_pending_order()
    lines, notices = load_cart_lines()
    for n in notices:
        flash(n, "error")
    had_coupon = session.get("coupon")
    totals = price_cart(lines)
    if had_coupon and not totals["coupon_code"]:
        flash(totals["coupon_note"] or "Your coupon no longer applies.", "error")
    hints = [] if totals["coupon_code"] else coupon_rules.public_hints(get_db())
    return render_template("cart.html", t=totals, hints=hints, describe=coupon_rules.describe)


# ---------------------------------------------------------------- checkout

def cancel_my_pending_order(reason):
    """If the shopper already has an unpaid order open, release it before starting another."""
    number = session.pop("pending_order", None)
    if number:
        try:
            svc.change_status(get_db(), number, wf.CANCELLED, "customer", note=reason)
        except svc.OrderError:
            pass          # already paid or cancelled, nothing to release


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    conn, gateway = get_db(), get_gateway()
    svc.expire_stale_orders(conn)
    sync_pending_order()
    lines, notices = load_cart_lines()
    for n in notices:
        flash(n, "error")

    if not lines:
        if not notices:
            flash("Your cart is empty. Add something before checking out.", "error")
        return redirect(url_for("cart"))

    had_coupon = session.get("coupon")
    totals = price_cart(lines)
    if had_coupon and not totals["coupon_code"]:
        flash(totals["coupon_note"] or "Your coupon no longer applies.", "error")
    values, errors = {}, {}

    if request.method == "POST":
        if notices:
            # Refresh the cart if its contents have changed.
            return redirect(url_for("cart"))
        if had_coupon and not totals["coupon_code"]:
            # Recalculate the total if the coupon is no longer valid.
            return redirect(url_for("checkout"))
        values, errors = validate_checkout(request.form)
        if not errors and totals["coupon_code"]:
            # one-per-customer codes can only be checked once we know the email
            _, note = coupon_rules.check(get_db(), totals["coupon_code"], totals["subtotal"], values["email"])
            if note:
                session.pop("coupon", None)
                flash(f"{note} It was taken off your order.", "error")
                return redirect(url_for("checkout"))
        if not errors:
            cancel_my_pending_order("Replaced by a new checkout.")
            try:
                number = svc.create_pending_order(conn, lines, totals, values)
            except svc.OrderError as exc:
                flash(str(exc), "error")
                return redirect(url_for("cart"))

            order = svc.get_order(conn, number)
            try:
                created = gateway.create_order(totals["total"], number, {"order_number": number})
            except GatewayError as exc:
                # nothing was charged; release the stock again and let them retry
                svc.change_status(conn, number, wf.CANCELLED, "system", note="Payment service unavailable.")
                flash(f"We couldn't start the payment: {exc}. Nothing was charged.", "error")
                return redirect(url_for("checkout"))

            svc.set_gateway_order(conn, order["id"], gateway.name, created["id"])
            session["pending_order"] = number
            session.permanent = True
            return redirect(url_for("pay.pay_page", number=number))
        flash("Please fix the highlighted fields.", "error")

    hints = [] if totals["coupon_code"] else coupon_rules.public_hints(get_db())
    return render_template("checkout.html", t=totals, v=values, errors=errors, states=STATES,
                           hints=hints, describe=coupon_rules.describe)


@app.route("/order/<number>")
def order_confirmation(number):
    conn = get_db()
    svc.expire_stale_orders(conn)
    order = svc.get_order(conn, number)
    if order is None:
        abort(404)
    if order["status"] in (wf.PAID, wf.SHIPPED, wf.DELIVERED) and session.get("pending_order") == number:
        sync_pending_order()

    placed = datetime.fromisoformat(order["created_at"])
    paid = datetime.fromisoformat(order["paid_at"]) if order["paid_at"] else None
    fmt = lambda d: d.strftime("%a %d %b").replace(" 0", " ")
    delivery = None
    if paid:
        delivery = f"{fmt(paid + timedelta(days=3))} to {fmt(paid + timedelta(days=6))}"
    return render_template(
        "order.html", o=order, items=svc.get_items(conn, order["id"]),
        events=[e for e in svc.get_events(conn, order["id"]) if e["kind"] == "status" or e["kind"] == "payment"],
        delivery=delivery, placed=placed, tracker=wf.TRACKER, step=wf.tracker_index(order["status"]),
    )


@app.route("/healthz")
def healthz():
    """Used by Docker's health check. Also proves the database can be read."""
    get_db().execute("SELECT 1 FROM products LIMIT 1").fetchone()
    return jsonify(status="ok")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.endpoint in ("admin.orders", "admin.order", "admin.inventory", "admin.coupons"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(500)
def server_error(_e):
    return render_template("500.html"), 500


@app.errorhandler(400)
def bad_request(_e):
    return render_template("400.html"), 400


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


ensure_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
