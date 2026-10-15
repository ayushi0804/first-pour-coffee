"""
Coupon rules that need the database: is the code real, active, in date, under its
usage limit, and (for one-per-customer codes) not already used by this email.

The maths of how much a coupon takes off lives in cart_logic.coupon_discount.
"""
from datetime import date


def _money(paise):
    rupees = paise / 100
    return f"₹{rupees:,.0f}" if rupees == int(rupees) else f"₹{rupees:,.2f}"


def find(conn, code):
    row = conn.execute("SELECT * FROM coupons WHERE code = ?", ((code or "").strip(),)).fetchone()
    return dict(row) if row else None


def describe(c):
    """A short sentence about what the coupon does, shown to shoppers and in the admin list."""
    if c["kind"] == "percent":
        text = f"{c['value']}% off"
        if c["max_discount"]:
            text += f", up to {_money(c['max_discount'])}"
    else:
        text = f"{_money(c['value'])} off"
    if c["min_subtotal"]:
        text += f" orders over {_money(c['min_subtotal'])}"
    return text


def check(conn, code, subtotal, email=None, today=None):
    """Returns (coupon_dict, "") if it can be used on this cart, or (None, reason)."""
    code = (code or "").strip()
    if not code:
        return None, ""
    c = find(conn, code)
    if c is None:
        return None, "That code isn't valid."
    today = (today or date.today()).isoformat()

    if not c["active"]:
        return None, "That coupon is switched off."
    if c["starts_on"] and today < c["starts_on"]:
        return None, f"That coupon starts on {c['starts_on']}."
    if c["expires_on"] and today > c["expires_on"]:
        return None, "That coupon has expired."
    if c["max_uses"] is not None and c["used_count"] >= c["max_uses"]:
        return None, "That coupon has been fully redeemed."
    if subtotal < c["min_subtotal"]:
        return None, f"Spend at least {_money(c['min_subtotal'])} to use {c['code']}."
    if c["once_per_customer"] and email and used_by(conn, c["code"], email):
        return None, "You've already used that coupon."
    return c, ""


def used_by(conn, code, email):
    """Has this email got a live (not cancelled) order that used the coupon?"""
    row = conn.execute(
        "SELECT 1 FROM orders WHERE coupon_code = ? AND lower(email) = lower(?) AND status != 'cancelled' LIMIT 1",
        (code, email.strip())).fetchone()
    return row is not None


def public_hints(conn, today=None):
    """Active, in-date coupons marked public, for the 'try one of these' list in the cart."""
    today = (today or date.today()).isoformat()
    rows = conn.execute(
        "SELECT * FROM coupons WHERE active = 1 AND public = 1 "
        "AND (starts_on IS NULL OR starts_on <= ?) AND (expires_on IS NULL OR expires_on >= ?) "
        "AND (max_uses IS NULL OR used_count < max_uses) ORDER BY id", (today, today)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- admin helpers

def validate_new(form, conn):
    """Checks the admin 'new coupon' form. Returns (values_ready_for_insert, errors)."""
    import re
    get = lambda k: (form.get(k) or "").strip()
    errors, v = {}, {}

    code = get("code").upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,20}", code):
        errors["code"] = "Use 3 to 20 letters, numbers, - or _."
    elif find(conn, code):
        errors["code"] = "That code already exists."
    v["code"] = code

    kind = get("kind")
    if kind not in ("percent", "flat"):
        errors["kind"] = "Choose percentage or flat."
    v["kind"] = kind

    def number(field, label, minimum=0, maximum=None, allow_blank=False):
        raw = get(field)
        if raw == "":
            if allow_blank:
                return None
            errors[field] = f"Enter {label}."
            return None
        try:
            n = float(raw)
        except ValueError:
            errors[field] = f"{label.capitalize()} must be a number."
            return None
        if n < minimum or (maximum is not None and n > maximum):
            errors[field] = f"{label.capitalize()} is out of range."
            return None
        return n

    value = number("value", "a value", minimum=0.01, maximum=100 if kind == "percent" else 1_000_000)
    if value is not None:
        v["value"] = int(round(value)) if kind == "percent" else int(round(value * 100))
        if kind == "percent" and value != int(value):
            errors["value"] = "Percentages must be whole numbers."
    cap = number("max_discount", "a cap", minimum=1, allow_blank=True)
    v["max_discount"] = int(round(cap * 100)) if cap is not None and kind == "percent" else None
    minimum = number("min_subtotal", "a minimum", minimum=0, allow_blank=True)
    v["min_subtotal"] = int(round(minimum * 100)) if minimum else 0
    uses = number("max_uses", "a use limit", minimum=1, allow_blank=True)
    v["max_uses"] = int(uses) if uses is not None else None

    for field in ("starts_on", "expires_on"):
        raw = get(field)
        if raw:
            try:
                date.fromisoformat(raw)
            except ValueError:
                errors[field] = "Use the date picker (YYYY-MM-DD)."
        v[field] = raw or None
    if v["starts_on"] and v["expires_on"] and "starts_on" not in errors and "expires_on" not in errors \
            and v["expires_on"] < v["starts_on"]:
        errors["expires_on"] = "The end date is before the start date."

    v["once_per_customer"] = 1 if form.get("once_per_customer") else 0
    v["public"] = 1 if form.get("public") else 0
    v["description"] = get("description")[:120]
    return v, errors
