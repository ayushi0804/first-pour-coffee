"""
Takes the README screenshots into docs/screenshots/.

Needs Playwright (pip install playwright && playwright install chromium) and a running store
that has demo data:

    python run.py --demo            # in one terminal
    python tools/screenshots.py     # in another   (reads ADMIN_PASSWORD from .env)

It places and pays one order through the local payment simulator, so run it against a demo database.
"""
import asyncio
import os
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")


def admin_password():
    if os.environ.get("ADMIN_PASSWORD"):
        return os.environ["ADMIN_PASSWORD"]
    env = ROOT / ".env"
    if env.exists():
        m = re.search(r"(?m)^ADMIN_PASSWORD=(.*)$", env.read_text())
        if m:
            return m.group(1).strip()
    sys.exit("Set ADMIN_PASSWORD (or create .env) so the admin screens can be captured.")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        page = await ctx.new_page()

        async def shot(name, full=False):
            await page.wait_for_timeout(250)
            await page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
            print("saved", name)

        # --- storefront
        await page.goto(BASE + "/")
        await shot("01-shop")
        await page.goto(BASE + "/?category=brewing-gear&sort=price-asc")
        await shot("02-filters-out-of-stock")
        await page.goto(BASE + "/product/gooseneck-kettle-800")
        await shot("03-product")

        # --- cart with a coupon
        await page.goto(BASE + "/")
        await page.click(".card-add button >> nth=0")
        await page.wait_for_timeout(500)
        await page.goto(BASE + "/product/hand-grinder-steel")
        await page.click(".buy button")
        await page.wait_for_timeout(500)
        await page.goto(BASE + "/cart")
        await page.fill("#code", "WELCOME10")
        await page.click(".coupon .btn")
        await page.wait_for_load_state()
        await shot("04-cart-coupon")

        # --- checkout and payment
        await page.goto(BASE + "/checkout")
        for field, value in dict(full_name="Asha Rawat", email="asha.screens@example.com", phone="9876543210",
                                 address1="12 Rajpur Road", city="Dehradun", pincode="248001").items():
            await page.fill("#" + field, value)
        await page.select_option("#state", "Uttarakhand")
        await shot("05-checkout")
        await page.click("#checkout-form button[type=submit]")
        await page.wait_for_load_state()
        await shot("06-payment")
        await page.click("button[value=success]")
        await page.wait_for_load_state()
        number = page.url.rsplit("/", 1)[1]

        # --- admin: ship that order, then show the customer's tracker
        admin = await ctx.new_page()
        await admin.goto(BASE + "/admin/login")
        await admin.fill("#username", "admin")
        await admin.fill("#password", admin_password())
        await admin.click(".checkout button[type=submit]")
        await admin.wait_for_load_state()
        await admin.goto(f"{BASE}/admin/orders/{number}")
        await admin.select_option("#carrier", "Delhivery")
        await admin.fill("#tracking", "DL4821907")
        await admin.click("text=Mark as shipped")
        await admin.wait_for_load_state()
        await page.goto(f"{BASE}/order/{number}")
        await shot("07-order-tracker", full=True)

        async def admin_shot(name, url, full=False):
            await admin.goto(BASE + url)
            await admin.wait_for_timeout(250)
            await admin.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
            print("saved", name)

        await admin_shot("08-admin-orders", "/admin/orders")
        await admin_shot("09-admin-order", f"/admin/orders/{number}", full=True)
        await admin_shot("10-admin-inventory", "/admin/inventory")
        await admin_shot("11-admin-coupons", "/admin/coupons")
        await browser.close()


asyncio.run(main())
