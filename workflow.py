"""The order status workflow, kept in one place so the rules are easy to read and test."""

PENDING = "pending"
PAID = "paid"
SHIPPED = "shipped"
DELIVERED = "delivered"
CANCELLED = "cancelled"

STATUSES = [PENDING, PAID, SHIPPED, DELIVERED, CANCELLED]

LABELS = {
    PENDING: "Pending payment",
    PAID: "Paid",
    SHIPPED: "Shipped",
    DELIVERED: "Delivered",
    CANCELLED: "Cancelled",
}

# what each status is allowed to turn into
TRANSITIONS = {
    PENDING: {PAID, CANCELLED},
    PAID: {SHIPPED, CANCELLED},
    SHIPPED: {DELIVERED},
    DELIVERED: set(),
    CANCELLED: set(),
}

# "paid" can only come from the payment gateway, never from the admin form
ADMIN_CAN_SET = {SHIPPED, DELIVERED, CANCELLED}


def can_transition(current, new):
    return new in TRANSITIONS.get(current, set())


def admin_next_steps(current):
    """Statuses the admin screen should offer buttons for, in a sensible order."""
    order = [SHIPPED, DELIVERED, CANCELLED]
    return [s for s in order if s in TRANSITIONS.get(current, set()) and s in ADMIN_CAN_SET]


# the four steps shown on the customer's progress tracker
TRACKER = [PENDING, PAID, SHIPPED, DELIVERED]


def tracker_index(status):
    """How far along the tracker an order is (0-based). Cancelled has no position."""
    return TRACKER.index(status) if status in TRACKER else -1
