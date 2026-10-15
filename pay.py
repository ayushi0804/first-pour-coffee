"""Payment pages: the pay screen, signature check, failure reports, and the Razorpay webhook."""
import json
from datetime import datetime

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import order_service as svc
import workflow as wf
from db import get_db
from payments import GatewayError, get_gateway

bp = Blueprint("pay", __name__)

OK_STATUSES = ("authorized", "captured")


def _order_or_404(number):
    order = svc.get_order(get_db(), number)
    if order is None:
        abort(404)
    return order


def _forget_cart_if_mine(number):
    """Once an order is paid, the cart that produced it is done with."""
    if session.get("pending_order") == number:
        session["cart"] = {}
        session.pop("coupon", None)
        session.pop("pending_order", None)


def _confirm_payment(order, payment_id, source):
    """
    Shared by the browser callback and the webhook. Marks the order paid, or, if the
    order was already cancelled (for example it expired), asks for a refund.
    Returns 'paid', 'already' or 'late'.
    """
    conn = get_db()
    outcome = svc.mark_paid(conn, order["id"], payment_id, source)
    if outcome == "late":
        svc.try_refund(conn, get_gateway(), order["order_number"], "system")
    return outcome


def _verify_and_finish(order, payment_id, signature, claimed_order_id=None):
    """Returns (ok, message, http_status)."""
    conn, gw = get_db(), get_gateway()
    gateway_order_id = order["gateway_order_id"]
    if not gateway_order_id:
        return False, "This order has no payment session.", 400

    # Always check against the order id we stored. The browser's copy is not trusted.
    if claimed_order_id and claimed_order_id != gateway_order_id:
        svc.log_event(conn, order["id"], "bad_payment", "Payment response named a different gateway order.", "gateway")
        return False, "That payment does not belong to this order.", 400

    if not gw.verify_payment_signature(gateway_order_id, payment_id, signature):
        svc.log_event(conn, order["id"], "bad_payment", "A payment response failed signature check.", "gateway")
        return False, "We could not verify that payment.", 400

    # Extra check where we can: ask the gateway what it holds for this payment id.
    try:
        details = gw.fetch_payment(payment_id)
    except GatewayError:
        details = None                      # the signature already proved it, so carry on
    if details and (details.get("order_id") != gateway_order_id
                    or details.get("amount") != order["total"]
                    or details.get("status") not in OK_STATUSES):
        svc.log_event(conn, order["id"], "bad_payment",
                      "Gateway record does not match the order (amount, order or status).", "gateway")
        return False, "The payment details did not match this order.", 400

    outcome = _confirm_payment(order, payment_id, "checkout")
    if outcome == "late":
        return False, ("Your payment arrived after this order had expired, so it was cancelled. "
                       "We've started a refund."), 409
    _forget_cart_if_mine(order["order_number"])
    return True, "Payment received.", 200


# ---------------------------------------------------------------- the pay page

@bp.route("/pay/<number>")
def pay_page(number):
    conn, gw = get_db(), get_gateway()
    svc.expire_stale_orders(conn)
    order = _order_or_404(number)
    if order["status"] != wf.PENDING:
        return redirect(url_for("order_confirmation", number=number))

    gateway_order_id = order["gateway_order_id"]
    if not gateway_order_id:                # the first attempt to reach the gateway failed
        try:
            created = gw.create_order(order["total"], number, {"order_number": number})
        except GatewayError as exc:
            flash(f"Payment service problem: {exc}", "error")
            return redirect(url_for("cart"))
        svc.set_gateway_order(conn, order["id"], gw.name, created["id"])
        gateway_order_id = created["id"]

    return render_template(
        "pay.html", o=order, items=svc.get_items(conn, order["id"]),
        cfg=gw.checkout_config(gateway_order_id, order["total"]),
        gateway=gw.name, can_cancel=session.get("pending_order") == number,
    )


@bp.post("/pay/<number>/verify")
def verify(number):
    data = request.get_json(silent=True) or {}
    ok, message, status = _verify_and_finish(
        _order_or_404(number),
        str(data.get("razorpay_payment_id", "")),
        str(data.get("razorpay_signature", "")),
        data.get("razorpay_order_id"),
    )
    body = {"ok": ok, "message": message}
    if ok:
        body["redirect"] = url_for("order_confirmation", number=number)
    return jsonify(body), status


@bp.post("/pay/<number>/failed")
def failed(number):
    """The browser tells us a payment attempt failed. We only log it; the order stays open for a retry."""
    order = _order_or_404(number)
    data = request.get_json(silent=True) or {}
    reason = str(data.get("description") or data.get("reason") or "Payment failed.")[:200]
    svc.record_failed_attempt(get_db(), order["id"], reason)
    return jsonify(ok=True)


@bp.post("/pay/<number>/cancel")
def cancel(number):
    order = _order_or_404(number)
    if session.get("pending_order") != number:
        abort(403)
    if order["status"] == wf.PENDING:
        svc.change_status(get_db(), number, wf.CANCELLED, "customer", note="Cancelled by the customer.")
        flash("Order cancelled. Your items are back in your cart.", "ok")
    session.pop("pending_order", None)
    return redirect(url_for("cart"))


@bp.post("/pay/<number>/mock")
def mock_pay(number):
    """Local payment simulator. It exists only when no Razorpay keys are configured."""
    gw = get_gateway()
    if gw.name != "mock":
        abort(404)
    order = _order_or_404(number)
    if order["status"] != wf.PENDING or not order["gateway_order_id"]:
        return redirect(url_for("order_confirmation", number=number))

    if request.form.get("outcome") == "success":
        pid, sig = gw.simulate_payment(order["gateway_order_id"], success=True)
        ok, message, _ = _verify_and_finish(order, pid, sig, order["gateway_order_id"])
        if not ok:
            flash(message, "error")
            return redirect(url_for("pay.pay_page", number=number))
        return redirect(url_for("order_confirmation", number=number))

    gw.simulate_payment(order["gateway_order_id"], success=False)
    svc.record_failed_attempt(get_db(), order["id"], "Simulated failure: the card was declined.")
    flash("The payment failed (simulated). You can try again.", "error")
    return redirect(url_for("pay.pay_page", number=number))


# ---------------------------------------------------------------- webhook

@bp.post("/webhooks/razorpay")
def webhook():
    """
    Razorpay calls this server-to-server, so the order still gets marked paid even if the
    customer closes the tab right after paying. It is signed with the webhook secret over
    the raw body, which is why we read the bytes before anything parses them.
    """
    gw, conn = get_gateway(), get_db()
    raw = request.get_data()
    if not gw.verify_webhook(raw, request.headers.get("X-Razorpay-Signature", "")):
        return jsonify(ok=False, message="bad signature"), 400

    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    if event_id and conn.execute("SELECT 1 FROM webhook_events WHERE event_id = ?", (event_id,)).fetchone():
        return jsonify(ok=True, message="duplicate ignored")

    try:
        payload = json.loads(raw.decode() or "{}")
    except ValueError:
        return jsonify(ok=False, message="bad json"), 400

    event = payload.get("event", "")
    payment = (payload.get("payload", {}).get("payment", {}) or {}).get("entity", {}) or {}
    order = svc.get_order_by_gateway_id(conn, payment.get("order_id"))

    if order is not None:
        if event in ("payment.captured", "order.paid"):
            if payment.get("amount") not in (None, order["total"]):
                svc.log_event(conn, order["id"], "bad_payment", "Webhook amount did not match the order.", "gateway")
            else:
                _confirm_payment(order, payment.get("id", ""), "webhook")
        elif event == "payment.failed":
            svc.record_failed_attempt(conn, order["id"], payment.get("error_description") or "Payment failed.")

    if event_id:
        conn.execute("INSERT OR IGNORE INTO webhook_events (event_id, received_at) VALUES (?, ?)",
                     (event_id, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    return jsonify(ok=True)
