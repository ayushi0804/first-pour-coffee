DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS webhook_events;
DROP TABLE IF EXISTS order_events;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
    id         INTEGER PRIMARY KEY,
    slug       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    tax_rate   INTEGER NOT NULL DEFAULT 18 CHECK (tax_rate BETWEEN 0 AND 100)  -- GST percent
);

-- prices are stored in paise so we never do money maths with floats
CREATE TABLE products (
    id           INTEGER PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    category_id  INTEGER NOT NULL REFERENCES categories(id),
    price        INTEGER NOT NULL CHECK (price > 0),
    compare_at   INTEGER,                        -- old price, only set when on sale
    summary      TEXT NOT NULL,                  -- one line, shown on the cards
    description  TEXT NOT NULL,
    specs        TEXT NOT NULL DEFAULT '[]',     -- JSON list of [label, value]
    stock        INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    rating       REAL NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    image        TEXT NOT NULL,
    added_on     TEXT NOT NULL                   -- YYYY-MM-DD, used for "newest"
);

CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_price    ON products(price);

-- Orders. Prices and names are copied into order_items on purpose, so an old
-- order still shows what the customer really paid after the catalog changes.
CREATE TABLE orders (
    id               INTEGER PRIMARY KEY,
    order_number     TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL,
    full_name        TEXT NOT NULL,
    email            TEXT NOT NULL,
    phone            TEXT NOT NULL,
    address1         TEXT NOT NULL,
    address2         TEXT NOT NULL DEFAULT '',
    city             TEXT NOT NULL,
    state            TEXT NOT NULL,
    pincode          TEXT NOT NULL,
    coupon_code      TEXT,
    subtotal         INTEGER NOT NULL,
    discount         INTEGER NOT NULL DEFAULT 0,
    shipping         INTEGER NOT NULL DEFAULT 0,
    tax              INTEGER NOT NULL,
    total            INTEGER NOT NULL,

    -- workflow: pending -> paid -> shipped -> delivered (or cancelled)
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled')),
    expires_at       TEXT,                 -- unpaid orders give their stock back after this
    paid_at          TEXT,
    shipped_at       TEXT,
    delivered_at     TEXT,
    cancelled_at     TEXT,
    cancel_reason    TEXT,
    carrier          TEXT,
    tracking_number  TEXT,

    -- payment gateway (Razorpay test mode, or the local mock)
    gateway          TEXT,
    gateway_order_id TEXT UNIQUE,
    payment_id       TEXT,
    payment_attempts INTEGER NOT NULL DEFAULT 0,
    refund_status    TEXT NOT NULL DEFAULT 'none'
                     CHECK (refund_status IN ('none', 'pending', 'refunded', 'failed')),
    refund_id        TEXT
);

CREATE INDEX idx_orders_status  ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);

CREATE TABLE order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    name       TEXT NOT NULL,
    image      TEXT NOT NULL,
    unit_price INTEGER NOT NULL,
    qty        INTEGER NOT NULL CHECK (qty > 0),
    tax_rate   INTEGER NOT NULL,
    line_total INTEGER NOT NULL
);

CREATE INDEX idx_order_items_order ON order_items(order_id);

-- a log of everything that happened to an order (status changes, payment attempts, refunds)
CREATE TABLE order_events (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    note        TEXT NOT NULL DEFAULT '',
    actor       TEXT NOT NULL DEFAULT 'system'     -- customer, admin, gateway or system
);

CREATE INDEX idx_order_events_order ON order_events(order_id);

-- webhook ids we have already handled (Razorpay can send the same event more than once)
CREATE TABLE webhook_events (
    event_id    TEXT PRIMARY KEY,
    received_at TEXT NOT NULL
);

-- Coupons. value is a percent (1-100) for kind='percent', or paise for kind='flat'.
CREATE TABLE coupons (
    id                INTEGER PRIMARY KEY,
    code              TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind              TEXT NOT NULL CHECK (kind IN ('percent', 'flat')),
    value             INTEGER NOT NULL CHECK (value > 0),
    max_discount      INTEGER,                          -- cap in paise (percent coupons)
    min_subtotal      INTEGER NOT NULL DEFAULT 0,       -- paise
    starts_on         TEXT,                             -- YYYY-MM-DD, inclusive
    expires_on        TEXT,                             -- YYYY-MM-DD, inclusive
    max_uses          INTEGER,                          -- NULL means unlimited
    used_count        INTEGER NOT NULL DEFAULT 0,
    once_per_customer INTEGER NOT NULL DEFAULT 0,
    active            INTEGER NOT NULL DEFAULT 1,
    public            INTEGER NOT NULL DEFAULT 0,       -- listed as a hint in the cart
    description       TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL
);

-- every change to a product's stock, so the numbers can always be explained
CREATE TABLE stock_movements (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    delta       INTEGER NOT NULL,
    stock_after INTEGER NOT NULL,
    kind        TEXT NOT NULL,         -- order, cancel, restock, adjustment
    reason      TEXT NOT NULL DEFAULT '',
    order_id    INTEGER REFERENCES orders(id),
    actor       TEXT NOT NULL DEFAULT 'system',
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_stock_movements_product ON stock_movements(product_id, id);
