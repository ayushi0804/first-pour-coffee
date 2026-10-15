# Using real Razorpay test mode

The store works without any keys (it uses a local payment simulator). To use the real Razorpay Checkout window in **test mode**:

## 1. Get test keys (free, no real money)

1. Sign up at razorpay.com and open the Dashboard.
2. Switch the dashboard to **Test Mode** (toggle at the top).
3. Go to **Account & Settings → API Keys → Generate Test Key**. (Menu names can move around a little, so search the dashboard for "API keys" if you don't see it.)
4. Copy the **Key Id** (starts with `rzp_test_`) and the **Key Secret**. The secret is shown once.

## 2. Put them in `.env`

```bash
cp .env.example .env
```

Edit `.env`:

```
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_PASSWORD=pick-something-long
SECRET_KEY=any-long-random-string
```

The app refuses to start if the key id is not a `rzp_test_` key. Never commit `.env` (it is in `.gitignore`).

Restart the app. The pay page now shows a **Pay with Razorpay** button instead of the simulator.

## 3. Pay with the published test details

| Method | What to enter | Result |
|---|---|---|
| Card | `4111 1111 1111 1111`, any future expiry, any CVV | success |
| UPI | `success@razorpay` | success |
| UPI | `failure@razorpay` | failure |
| Net banking / wallet | choose any bank, then press **Success** or **Failure** on the mock page | as chosen |

(From Razorpay's test-mode documentation. If something has changed, check their "Test Integration" page.)

## 4. Optional: webhook (so an order is paid even if the tab is closed)

Razorpay needs a public address to call, so tunnel your local server:

```bash
ngrok http 5000
```

In the Dashboard (Test Mode) add a webhook:

- URL: `https://<your-ngrok-address>/webhooks/razorpay`
- Secret: any long random string. Put the same value in `.env` as `RAZORPAY_WEBHOOK_SECRET`
- Events: `payment.captured`, `order.paid`, `payment.failed`

Restart the app after changing `.env`. Pay, then close the tab before the redirect: the order should still turn to **Paid** and the event log will say "(webhook)".

## 5. If payments stay "authorized"

Refunds only work on captured payments. If your test payments show as *authorized* in the dashboard, set payment capture to automatic in the dashboard's payment settings.

## How the security works

- The server creates the Razorpay order with the amount **from the database**, never from the browser.
- After payment, Checkout returns `razorpay_payment_id` and `razorpay_signature`. The server recomputes `HMAC_SHA256(key_secret, order_id|payment_id)` using the order id **it stored**, and compares in constant time.
- It also asks Razorpay for the payment and checks the amount, order and status.
- Webhooks are verified separately: `HMAC_SHA256(webhook_secret, raw_body)` against the `X-Razorpay-Signature` header. The `X-Razorpay-Event-Id` header is stored so repeated deliveries are ignored.
- Only the public key id reaches the browser.
