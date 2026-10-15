"""
Everything that changes an order lives here. It takes a plain sqlite connection
(no Flask), so the rules can be tested without a web server.

Stock is taken (reserved) when the order is created, and given back if the order
is cancelled or the customer never pays. Every change writes a row to order_events.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta

import coupons as coupon_rules
import workflow as wf
from cart_logic import new_order_number
from payments import GatewayError

HOLD_MINUTES = 30        # how long an unpaid order keeps its stock
LOW_STOCK = 5            # at or below this (but above zero) a product counts as low


class OrderError(Exception):
    pass


def _now():
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE takes the write lock up front, so two checkouts can't both take the last item."""
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def add_event(conn, order_id, kind, note="", actor="system", from_status=None, to_status=None, now=None):
    conn.execute(
        "INSERT INTO order_events (order_id, created_at, kind, from_status, to_status, note, actor) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (order_id, now or _now(), kind, from_status, to_status, note, actor),
    )


def log_event(conn, order_id, kind, note="", actor="system"):
    """add_event inside its own transaction, for places that only need to write a log line."""
    with transaction(conn):
        add_event(conn, order_id, kind, note, actor)


# ---------------------------------------------------------------- reading

def get_order(conn, number):
    return conn.execute("SELECT * FROM orders WHERE order_number = ?", (number,)).fetchone()


def get_order_by_gateway_id(conn, gateway_order_id):
    if not gateway_order_id:
        return None
    return conn.execute("SELECT * FROM orders WHERE gateway_order_id = ?", (gateway_order_id,)).fetchone()


def get_items(conn, order_id):
    return conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()


def get_events(conn, order_id):
    return conn.execute(
        "SELECT * FROM order_events WHERE order_id = ? ORDER BY id", (order_id,)
    ).fetchall()


# ---------------------------------------------------------------- creating

def _move_stock(conn, product_id, delta, kind, reason="", order_id=None, actor="system", now=None):
    """Changes a product's stock and writes the movement. Returns False if it would go below zero."""
    changed = conn.execute(
        "UPDATE products SET stock = stock + ? WHERE id = ? AND stock + ? >= 0",
        (delta, product_id, delta)).rowcount
    if changed != 1:
        return False
    after = conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()["stock"]
    conn.execute(
        "INSERT INTO stock_movements (product_id, delta, stock_after, kind, reason, order_id, actor, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (product_id, delta, after, kind, reason, order_id, actor, now or _now()))
    return True


def create_pending_order(conn, lines, totals, info, now=None):
    """
    Saves a new order as 'pending', takes the stock and counts the coupon use, all in one
    transaction. Raises OrderError if stock, a price or the coupon changed since the cart was read.
    """
    created = now or datetime.now()
    stamp = created.isoformat(timespec="seconds")
    number = new_order_number()
    code = totals["coupon_code"]
    with transaction(conn):
        if code:
            # count the use with a guarded UPDATE so two shoppers can't both take the last one
            used = conn.execute(
                "UPDATE coupons SET used_count = used_count + 1 WHERE code = ? AND active = 1 "
                "AND (max_uses IS NULL OR used_count < max_uses)", (code,)).rowcount
            if used != 1:
                raise OrderError(f"Coupon {code} is no longer available. Please review your cart.")
            once = conn.execute("SELECT once_per_customer FROM coupons WHERE code = ?", (code,)).fetchone()
            if once and once["once_per_customer"] and coupon_rules.used_by(conn, code, info["email"]):
                raise OrderError(f"You've already used coupon {code}.")

        cur = conn.execute(
            """INSERT INTO orders (order_number, created_at, full_name, email, phone, address1,
                   address2, city, state, pincode, coupon_code, subtotal, discount, shipping,
                   tax, total, status, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (number, stamp, info["full_name"], info["email"],
             info["phone"], info["address1"], info["address2"], info["city"], info["state"],
             info["pincode"], code, totals["subtotal"], totals["discount"],
             totals["shipping"], totals["tax"], totals["total"],
             (created + timedelta(minutes=HOLD_MINUTES)).isoformat(timespec="seconds")),
        )
        order_id = cur.lastrowid
        for l in lines:
            row = conn.execute("SELECT price FROM products WHERE id = ?", (l["product_id"],)).fetchone()
            if row is None or row["price"] != l["unit_price"]:
                raise OrderError("A price changed while you were checking out. Please review your cart.")
            if not _move_stock(conn, l["product_id"], -l["qty"], "order", f"Order {number}",
                               order_id, "customer", stamp):
                raise OrderError(f"{l['name']} no longer has enough stock. Please review your cart.")
            conn.execute(
                """INSERT INTO order_items (order_id, product_id, name, image, unit_price, qty, tax_rate, line_total)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_id, l["product_id"], l["name"], l["image"], l["unit_price"],
                 l["qty"], l["tax_rate"], l["line_total"]))
        add_event(conn, order_id, "created", "Order placed, waiting for payment.", "customer",
                  to_status=wf.PENDING, now=stamp)
    return number


def set_gateway_order(conn, order_id, gateway_name, gateway_order_id):
    with transaction(conn):
        conn.execute("UPDATE orders SET gateway = ?, gateway_order_id = ? WHERE id = ?",
                     (gateway_name, gateway_order_id, order_id))
        add_event(conn, order_id, "gateway_order", f"Payment session created ({gateway_order_id}).", "system")


# ---------------------------------------------------------------- payment results

def mark_paid(conn, order_id, payment_id, source="checkout", now=None):
    """
    Called when the gateway confirms a payment (from the browser or from a webhook).
    Safe to call twice for the same payment. Returns:
      'paid'     this call moved the order from pending to paid
      'already'  the order was already paid with this payment
      'late'     the order had been cancelled; the money must be refunded
    """
    now = now or _now()
    actor = "gateway"
    with transaction(conn):
        o = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if o["status"] == wf.PENDING:
            conn.execute(
                "UPDATE orders SET status = 'paid', payment_id = ?, paid_at = ?, "
                "payment_attempts = payment_attempts + 1, expires_at = NULL WHERE id = ?",
                (payment_id, now, order_id))
            add_event(conn, order_id, "payment", f"Payment {payment_id} received ({source}).", actor,
                      wf.PENDING, wf.PAID, now)
            return "paid"

        if o["status"] == wf.CANCELLED:
            if o["payment_id"] == payment_id:
                return "already"
            conn.execute("UPDATE orders SET payment_id = ?, refund_status = 'pending' WHERE id = ?",
                         (payment_id, order_id))
            add_event(conn, order_id, "late_payment",
                      f"Payment {payment_id} arrived after the order was cancelled. It needs a refund.",
                      actor, now=now)
            return "late"

        # already paid / shipped / delivered
        if o["payment_id"] != payment_id:
            add_event(conn, order_id, "duplicate_payment",
                      f"A second payment {payment_id} was received. Check the gateway dashboard.",
                      actor, now=now)
        return "already"


def record_failed_attempt(conn, order_id, description, now=None):
    with transaction(conn):
        o = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if o["status"] != wf.PENDING:
            return
        conn.execute("UPDATE orders SET payment_attempts = payment_attempts + 1 WHERE id = ?", (order_id,))
        add_event(conn, order_id, "payment_failed", description or "Payment failed.", "gateway", now=now)


# ---------------------------------------------------------------- status changes

def _restock(conn, order_id, number, now):
    for it in get_items(conn, order_id):
        if it["product_id"] is not None:
            _move_stock(conn, it["product_id"], it["qty"], "cancel", f"Order {number} cancelled",
                        order_id, "system", now)


def change_status(conn, number, new_status, actor, note="", carrier="", tracking="", now=None):
    """
    The single door for status changes. Checks the workflow rules, then updates the
    order, restocks on cancel, and logs the change, all in one transaction.
    Returns the new status. Raises OrderError with a readable message if not allowed.
    """
    now = now or _now()
    with transaction(conn):
        o = get_order(conn, number)
        if o is None:
            raise OrderError("Order not found.")
        current = o["status"]
        if not wf.can_transition(current, new_status):
            raise OrderError(f"An order that is {wf.LABELS[current].lower()} can't be changed to "
                             f"{wf.LABELS[new_status].lower()}.")

        if new_status == wf.PAID:
            raise OrderError("Orders become paid only when the payment gateway confirms the payment.")

        if new_status == wf.SHIPPED:
            conn.execute("UPDATE orders SET status = 'shipped', shipped_at = ?, carrier = ?, tracking_number = ? "
                         "WHERE id = ?", (now, carrier.strip()[:40] or None, tracking.strip()[:60] or None, o["id"]))
            detail = " ".join(x for x in (carrier.strip(), tracking.strip()) if x)
            add_event(conn, o["id"], "status", f"Marked as shipped. {detail}".strip(), actor, current, new_status, now)

        elif new_status == wf.DELIVERED:
            conn.execute("UPDATE orders SET status = 'delivered', delivered_at = ? WHERE id = ?", (now, o["id"]))
            add_event(conn, o["id"], "status", "Marked as delivered.", actor, current, new_status, now)

        elif new_status == wf.CANCELLED:
            refund = "pending" if current == wf.PAID else "none"
            conn.execute("UPDATE orders SET status = 'cancelled', cancelled_at = ?, cancel_reason = ?, "
                         "refund_status = ?, expires_at = NULL WHERE id = ?",
                         (now, note.strip()[:200] or None, refund, o["id"]))
            _restock(conn, o["id"], number, now)
            if o["coupon_code"]:  # Restore the coupon usage count.
                conn.execute("UPDATE coupons SET used_count = MAX(used_count - 1, 0) WHERE code = ?",
                             (o["coupon_code"],))
            text = "Cancelled." + (f" Reason: {note.strip()}" if note.strip() else "")
            if refund == "pending":
                text += " A refund is due."
            add_event(conn, o["id"], "status", text, actor, current, new_status, now)
    return new_status


def try_refund(conn, gateway, number, actor="system", now=None):
    """Asks the gateway to refund a cancelled, paid order. Records the outcome either way."""
    o = get_order(conn, number)
    if o is None or o["refund_status"] not in ("pending", "failed") or not o["payment_id"]:
        return False
    try:
        result = gateway.refund(o["payment_id"], o["total"], notes={"order_number": number})
    except GatewayError as exc:
        with transaction(conn):
            conn.execute("UPDATE orders SET refund_status = 'failed' WHERE id = ?", (o["id"],))
            add_event(conn, o["id"], "refund_failed", f"Refund failed: {exc}", actor, now=now)
        return False
    with transaction(conn):
        conn.execute("UPDATE orders SET refund_status = 'refunded', refund_id = ? WHERE id = ?",
                     (result.get("id"), o["id"]))
        add_event(conn, o["id"], "refund", f"Refunded {o['total'] / 100:,.2f} ({result.get('id')}).", actor, now=now)
    return True


def expire_stale_orders(conn, now=None):
    """Cancels unpaid orders whose hold time ran out, which also gives their stock back."""
    now = now or _now()
    rows = conn.execute("SELECT order_number FROM orders WHERE status = 'pending' AND expires_at IS NOT NULL "
                        "AND expires_at < ?", (now,)).fetchall()
    count = 0
    for r in rows:
        try:
            change_status(conn, r["order_number"], wf.CANCELLED, "system",
                          note="Payment was not completed in time.", now=now)
            count += 1
        except OrderError:
            pass          # it was paid or cancelled a moment ago, nothing to do
    return count


# ---------------------------------------------------------------- admin queries

def _like(term):
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_orders(conn, status="", q="", page=1, per_page=15):
    where, params = [], []
    if status in wf.STATUSES:
        where.append("status = ?")
        params.append(status)
    for term in q.split():
        where.append("(order_number LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\')")
        params += [_like(term)] * 3
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute("SELECT COUNT(*) FROM orders" + clause, params).fetchone()[0]
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    rows = conn.execute(
        "SELECT * FROM orders" + clause + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page]).fetchall()
    return rows, total, page, pages


def status_counts(conn):
    counts = {s: 0 for s in wf.STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status"):
        counts[r["status"]] = r["n"]
    return counts


def dashboard_stats(conn, today=None):
    today = today or datetime.now().date().isoformat()
    counts = status_counts(conn)
    revenue = conn.execute(
        "SELECT COALESCE(SUM(total), 0) FROM orders WHERE status IN ('paid', 'shipped', 'delivered')").fetchone()[0]
    today_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
    refunds_due = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE refund_status IN ('pending', 'failed')").fetchone()[0]
    low = conn.execute("SELECT COUNT(*) FROM products WHERE stock BETWEEN 1 AND ?", (LOW_STOCK,)).fetchone()[0]
    out = conn.execute("SELECT COUNT(*) FROM products WHERE stock = 0").fetchone()[0]
    return {"counts": counts, "revenue": revenue, "today": today_orders,
            "to_ship": counts[wf.PAID], "refunds_due": refunds_due, "low_stock": low, "out_of_stock": out}


# ---------------------------------------------------------------- inventory (admin)

def list_inventory(conn, show="", q=""):
    where, params = [], []
    if show == "low":
        where.append("p.stock BETWEEN 1 AND ?")
        params.append(LOW_STOCK)
    elif show == "out":
        where.append("p.stock = 0")
    for term in q.split():
        where.append("(p.name LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')")
        params += [_like(term)] * 2
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return conn.execute(
        "SELECT p.*, c.name AS category_name FROM products p JOIN categories c ON c.id = p.category_id"
        + clause + " ORDER BY p.stock ASC, p.name COLLATE NOCASE", params).fetchall()


def stock_movements(conn, product_id, limit=100):
    return conn.execute(
        "SELECT m.*, o.order_number FROM stock_movements m LEFT JOIN orders o ON o.id = m.order_id "
        "WHERE m.product_id = ? ORDER BY m.id DESC LIMIT ?", (product_id, limit)).fetchall()


def adjust_stock(conn, product_id, delta, reason, actor="admin", now=None):
    """Manual correction or restock. Returns the new stock level; raises OrderError if it would go negative."""
    if delta == 0:
        raise OrderError("Enter a change other than zero.")
    kind = "restock" if delta > 0 else "adjustment"
    with transaction(conn):
        if not _move_stock(conn, product_id, delta, kind, reason.strip()[:120], None, actor, now):
            raise OrderError("Stock can't go below zero.")
        return conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()["stock"]


# ---------------------------------------------------------------- coupons (admin)

def list_coupons(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM coupons ORDER BY active DESC, id DESC")]


def create_coupon(conn, v, now=None):
    with transaction(conn):
        conn.execute(
            """INSERT INTO coupons (code, kind, value, max_discount, min_subtotal, starts_on, expires_on,
                   max_uses, once_per_customer, public, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (v["code"], v["kind"], v["value"], v["max_discount"], v["min_subtotal"], v["starts_on"],
             v["expires_on"], v["max_uses"], v["once_per_customer"], v["public"], v["description"], now or _now()))


def set_coupon_active(conn, coupon_id, active):
    with transaction(conn):
        conn.execute("UPDATE coupons SET active = ? WHERE id = ?", (1 if active else 0, coupon_id))
