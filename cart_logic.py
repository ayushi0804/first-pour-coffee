"""
Everything about money, coupons and checkout validation lives here, away from
Flask, so it can be tested on its own.

All amounts are integers in paise (100 paise = 1 rupee).
"""
import re
import secrets

SHIPPING_FEE = 9900            # ₹99
FREE_SHIPPING_FROM = 150000    # free when the order is ₹1,500 or more (after discount)
MAX_PER_LINE = 10

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
]


# ------------------------------------------------------------------ coupons

def coupon_discount(coupon, subtotal):
    """
    How much a coupon takes off a subtotal (paise). coupon is a dict with
    kind ('percent' or 'flat'), value, max_discount and min_subtotal.
    Whether the coupon is still valid (dates, usage) is decided in coupons.py.
    """
    if not coupon or subtotal < coupon.get("min_subtotal", 0):
        return 0
    if coupon["kind"] == "percent":
        discount = subtotal * coupon["value"] // 100
        if coupon.get("max_discount"):
            discount = min(discount, coupon["max_discount"])
    else:
        discount = coupon["value"]
    return max(0, min(discount, subtotal))


# ------------------------------------------------------------------ totals

def calc_totals(lines, coupon=None):
    """
    lines: list of dicts with unit_price, qty, tax_rate (percent).
    Tax is worked out per line on the price *after* that line's share of the
    discount, then added on top of the price (prices in the shop are ex-GST).
    """
    for l in lines:
        l["line_total"] = l["unit_price"] * l["qty"]
    subtotal = sum(l["line_total"] for l in lines)

    discount = coupon_discount(coupon, subtotal)

    # split the discount across lines in proportion to their value; give any
    # leftover paise out one at a time so the shares add up exactly
    shares = [discount * l["line_total"] // subtotal if subtotal else 0 for l in lines]
    leftover = discount - sum(shares)
    i = 0
    while leftover > 0 and lines:
        if shares[i % len(lines)] < lines[i % len(lines)]["line_total"]:
            shares[i % len(lines)] += 1
            leftover -= 1
        i += 1

    by_rate = {}
    tax = 0
    for l, share in zip(lines, shares):
        taxable = l["line_total"] - share
        line_tax = (taxable * l["tax_rate"] + 50) // 100      # round half up to the paise
        l["discount"], l["tax"] = share, line_tax
        by_rate[l["tax_rate"]] = by_rate.get(l["tax_rate"], 0) + line_tax
        tax += line_tax

    after_discount = subtotal - discount
    if subtotal == 0 or after_discount >= FREE_SHIPPING_FROM:
        shipping = 0
    else:
        shipping = SHIPPING_FEE

    return {
        "lines": lines,
        "item_count": sum(l["qty"] for l in lines),
        "subtotal": subtotal,
        "discount": discount,
        "coupon_code": coupon["code"] if discount else None,
        "coupon_note": "",
        "shipping": shipping,
        "tax": tax,
        "tax_lines": sorted(by_rate.items()),
        "total": after_discount + shipping + tax,
        "free_shipping_gap": max(0, FREE_SHIPPING_FROM - after_discount) if subtotal else 0,
        "free_shipping_progress": min(100, after_discount * 100 // FREE_SHIPPING_FROM) if subtotal else 0,
    }


# ------------------------------------------------------------------ checkout form

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")
PIN_RE = re.compile(r"^[1-9]\d{5}$")


def validate_checkout(form):
    """Returns (clean_values, errors). errors maps field name -> message."""
    get = lambda k: (form.get(k) or "").strip()
    clean = {
        "full_name": get("full_name"),
        "email": get("email").lower(),
        "phone": re.sub(r"[\s-]", "", get("phone")),
        "address1": get("address1"),
        "address2": get("address2"),
        "city": get("city"),
        "state": get("state"),
        "pincode": get("pincode"),
    }
    if clean["phone"].startswith("+91"):
        clean["phone"] = clean["phone"][3:]

    errors = {}
    if len(clean["full_name"]) < 2:
        errors["full_name"] = "Enter your full name."
    if not EMAIL_RE.match(clean["email"]):
        errors["email"] = "Enter a valid email address."
    if not PHONE_RE.match(clean["phone"]):
        errors["phone"] = "Enter a 10-digit mobile number."
    if len(clean["address1"]) < 5:
        errors["address1"] = "Enter your street address."
    if len(clean["city"]) < 2:
        errors["city"] = "Enter your city."
    if clean["state"] not in STATES:
        errors["state"] = "Choose your state."
    if not PIN_RE.match(clean["pincode"]):
        errors["pincode"] = "Enter a 6-digit PIN code."
    return clean, errors


def new_order_number():
    # no 0/O/1/I so it is easy to read out over the phone
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "FP-" + "".join(secrets.choice(alphabet) for _ in range(8))
