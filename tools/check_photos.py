"""Shows which products have a real photo and which are still using the drawing.

Run from the project root:  python tools/check_photos.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seed_data import PRODUCTS  # noqa: E402

folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "img", "products")
have = 0
for p in PRODUCTS:
    name = p[11]
    found = [e for e in ("jpg", "jpeg", "webp", "png") if os.path.exists(os.path.join(folder, f"{name}.{e}"))]
    print(("photo   " if found else "drawing ") + f"{name}.{found[0] if found else 'jpg'}")
    have += bool(found)
print(f"\n{have} of {len(PRODUCTS)} products use real photos")
