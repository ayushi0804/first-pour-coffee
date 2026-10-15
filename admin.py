"""Admin routes for login, orders, inventory, and coupons."""

import hmac
import secrets
import time
from datetime import date
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, session, url_for)

import coupons as coupon_rules
import order_service as svc
import workflow as wf
from db import get_db
from payments import get_gateway

bp = Blueprint("admin", __name__, url_prefix="/admin")

CARRIERS = ["India Post", "Delhivery", "Blue Dart", "DTDC", "Ecom Express", "Other"]
MAX_FAILS, WINDOW = 5, 300          # 5 wrong passwords per 5 minutes, per address
_fails = {}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _locked_out(ip):
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < WINDOW]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS


@bp.route("/login", methods=["GET", "POST"])
def login():
    password = current_app.config.get("ADMIN_PASSWORD") or ""
    username = current_app.config.get("ADMIN_USER") or "admin"
    if not password:
        return render_template("admin_login.html", disabled=True)

    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _locked_out(ip):
            flash("Too many attempts. Try again in a few minutes.", "error")
            return render_template("admin_login.html", disabled=False), 429
        ok_user = hmac.compare_digest(request.form.get("username", ""), username)
        ok_pass = hmac.compare_digest(request.form.get("password", ""), password)
        if ok_user and ok_pass:
            _fails.pop(ip, None)
            session["admin"] = True
            session["csrf"] = secrets.token_hex(16)        # fresh token after signing in
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/admin") else url_for("admin.orders"))
        _fails.setdefault(ip, []).append(time.time())
        flash("Wrong username or password.", "error")
    return render_template("admin_login.html", disabled=False)


@bp.post("/logout")
def logout():
    session.pop("admin", None)
    flash("Signed out.", "ok")
    return redirect(url_for("admin.login"))


@bp.route("/")
@admin_required
def index():
    return redirect(url_for("admin.orders"))


@bp.route("/orders")
@admin_required
def orders():
    conn = get_db()
    svc.expire_stale_orders(conn)
    status = request.args.get("status", "")
    q = (request.args.get("q") or "").strip()[:60]
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    rows, total, page, pages = svc.list_orders(conn, status, q, page)
    return render_template("admin_orders.html", rows=rows, total=total, page=page, pages=pages,
                           status=status, q=q, stats=svc.dashboard_stats(conn), statuses=wf.STATUSES,
                           labels=wf.LABELS)


@bp.route("/orders/<number>")
@admin_required
def order(number):
    conn = get_db()
    svc.expire_stale_orders(conn)
    o = svc.get_order(conn, number)
    if o is None:
        abort(404)
    return render_template("admin_order.html", o=o, items=svc.get_items(conn, o["id"]),
                           events=svc.get_events(conn, o["id"]), next_steps=wf.admin_next_steps(o["status"]),
                           carriers=CARRIERS, labels=wf.LABELS)


@bp.post("/orders/<number>/status")
@admin_required
def change_status(number):
    conn = get_db()
    to = request.form.get("to", "")
    if to not in wf.ADMIN_CAN_SET:
        abort(400)
    try:
        svc.change_status(conn, number, to, "admin",
                          note=request.form.get("reason", ""),
                          carrier=request.form.get("carrier", ""),
                          tracking=request.form.get("tracking", ""))
    except svc.OrderError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.order", number=number))

    flash(f"Order {number} is now {wf.LABELS[to].lower()}.", "ok")
    if to == wf.CANCELLED:
        o = svc.get_order(conn, number)
        if o["refund_status"] == "pending":
            if svc.try_refund(conn, get_gateway(), number, "admin"):
                flash("The payment was refunded through the gateway.", "ok")
            else:
                flash("The refund did not go through. Use \"Retry refund\" below.", "error")
    return redirect(url_for("admin.order", number=number))


@bp.post("/orders/<number>/refund")
@admin_required
def retry_refund(number):
    if svc.try_refund(get_db(), get_gateway(), number, "admin"):
        flash("Refund completed.", "ok")
    else:
        flash("The refund did not go through. Check the event log for the reason.", "error")
    return redirect(url_for("admin.order", number=number))


# ---------------------------------------------------------------- inventory

@bp.route("/inventory")
@admin_required
def inventory():
    conn = get_db()
    show = request.args.get("show", "")
    q = (request.args.get("q") or "").strip()[:60]
    all_rows = svc.list_inventory(conn)
    return render_template(
        "admin_inventory.html", rows=svc.list_inventory(conn, show, q), show=show, q=q,
        low=svc.LOW_STOCK, total=len(all_rows),
        n_low=sum(1 for r in all_rows if 0 < r["stock"] <= svc.LOW_STOCK),
        n_out=sum(1 for r in all_rows if r["stock"] == 0))


@bp.route("/inventory/<slug>")
@admin_required
def product_stock(slug):
    conn = get_db()
    p = conn.execute("SELECT p.*, c.name AS category_name FROM products p JOIN categories c ON c.id = p.category_id "
                     "WHERE p.slug = ?", (slug,)).fetchone()
    if p is None:
        abort(404)
    return render_template("admin_stock.html", p=p, moves=svc.stock_movements(conn, p["id"]), low=svc.LOW_STOCK)


@bp.post("/inventory/<slug>/adjust")
@admin_required
def adjust(slug):
    conn = get_db()
    p = conn.execute("SELECT id, name FROM products WHERE slug = ?", (slug,)).fetchone()
    if p is None:
        abort(404)
    try:
        delta = int(request.form.get("delta", "0"))
    except ValueError:
        flash("Enter a whole number.", "error")
        return redirect(request.referrer or url_for("admin.inventory"))
    if abs(delta) > 10000:
        flash("That change is too large.", "error")
        return redirect(request.referrer or url_for("admin.inventory"))
    reason = request.form.get("reason", "").strip() or ("Restock" if delta > 0 else "Correction")
    try:
        new_stock = svc.adjust_stock(conn, p["id"], delta, reason)
    except svc.OrderError as exc:
        flash(str(exc), "error")
    else:
        flash(f"{p['name']}: stock is now {new_stock}.", "ok")
    target = request.form.get("back")
    return redirect(url_for("admin.product_stock", slug=slug) if target == "detail" else url_for("admin.inventory"))


# ---------------------------------------------------------------- coupons

@bp.route("/coupons", methods=["GET", "POST"])
@admin_required
def coupons():
    conn = get_db()
    values, errors = {}, {}
    if request.method == "POST":
        values, errors = coupon_rules.validate_new(request.form, conn)
        if not errors:
            svc.create_coupon(conn, values)
            flash(f"Coupon {values['code']} created.", "ok")
            return redirect(url_for("admin.coupons"))
        flash("Please fix the highlighted fields.", "error")
        values = {k: request.form.get(k, "") for k in request.form}
    today = date.today().isoformat()
    rows = []
    for c in svc.list_coupons(conn):
        if not c["active"]:
            state = "off"
        elif c["expires_on"] and today > c["expires_on"]:
            state = "expired"
        elif c["starts_on"] and today < c["starts_on"]:
            state = "scheduled"
        elif c["max_uses"] is not None and c["used_count"] >= c["max_uses"]:
            state = "used up"
        else:
            state = "live"
        rows.append({**c, "state": state, "summary": coupon_rules.describe(c)})
    return render_template("admin_coupons.html", rows=rows, v=values, errors=errors)


@bp.post("/coupons/<int:coupon_id>/toggle")
@admin_required
def toggle_coupon(coupon_id):
    conn = get_db()
    c = conn.execute("SELECT code, active FROM coupons WHERE id = ?", (coupon_id,)).fetchone()
    if c is None:
        abort(404)
    svc.set_coupon_active(conn, coupon_id, not c["active"])
    flash(f"{c['code']} is now {'switched off' if c['active'] else 'active'}.", "ok")
    return redirect(url_for("admin.coupons"))
