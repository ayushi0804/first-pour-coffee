# Final screen recording script (about 4 minutes)

Start from a fresh database with sample orders: `python run.py --reset --demo`. Sign in to `/admin` in a second window first.

1. **Shop (30 s):** scroll the catalog, click a category, search "ethiopia", set a price preset, sort by price. Open the **Digital Brew Scale** to show **Out of stock** (disabled button).
2. **Cart (40 s):** add two items, use +/-, try `SUMMER25` (expired message), then `WELCOME10`. Point at GST, shipping and the discount.
3. **Checkout (30 s):** submit with a wrong PIN (error), fix it, press *Continue to payment*.
4. **Payment (40 s):** show the TEST MODE banner. Pay with the failing option first (order stays pending), then the successful one (card `4111 1111 1111 1111`).
5. **Order page (20 s):** show the tracker on **Paid**.
6. **Inventory (40 s):** in admin, open the product you bought. Show the stock history line "Order FP-..." and the lower stock. Restock something with a reason. Show the Low / Out of stock filters.
7. **Workflow (40 s):** open the order, ship it (carrier + tracking), refresh the customer page to show **Shipped**, mark delivered. Show the event log.
8. **Coupons (30 s):** open Coupons, create a new one (e.g. `MONSOON15`, 15%, cap ₹400, one use per customer), then apply it in the store.
9. **Close (10 s):** cancel a paid demo order to show the refund and the stock coming back, then say where the README and tests are.
