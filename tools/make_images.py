"""
Draws the product illustrations as SVG files into static/img/products.

I don't have a photo shoot budget, so every product gets a flat illustration
instead. If you'd rather use real photos, drop them in static/img/products and
change the `image` column in seed_data.py - nothing else needs to change.

Run from the project root:  python tools/make_images.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "products"
INK = "#17231F"


def wrap(bg, body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600">'
        f'<rect width="600" height="600" fill="{bg}"/>'
        '<ellipse cx="300" cy="506" rx="170" ry="14" fill="#000" opacity=".10"/>'
        f"{body}</svg>"
    )


def dripper(c1, c2):
    ridges = "".join(
        f'<line x1="{x1}" y1="240" x2="{x2}" y2="465" stroke="{c2}" stroke-width="5" opacity=".55"/>'
        for x1, x2 in [(205, 270), (255, 285), (300, 300), (345, 315), (395, 330)]
    )
    return (
        f'<rect x="205" y="470" width="190" height="32" rx="10" fill="{c2}"/>'
        f'<path d="M455 262 C525 262 525 345 450 352" fill="none" stroke="{c1}" stroke-width="22" stroke-linecap="round"/>'
        f'<polygon points="150,232 450,232 350,472 250,472" fill="{c1}"/>'
        f"{ridges}"
        f'<rect x="138" y="214" width="324" height="26" rx="13" fill="{c1}"/>'
        f'<rect x="150" y="219" width="300" height="6" rx="3" fill="#fff" opacity=".35"/>'
    )


def kettle(c1, c2):
    return (
        f'<path d="M190 312 C95 300 95 450 182 455" fill="none" stroke="{c2}" stroke-width="22" stroke-linecap="round"/>'
        f'<path d="M405 360 C480 360 478 285 512 232" fill="none" stroke="{c1}" stroke-width="20" stroke-linecap="round"/>'
        f'<path d="M168 502 L188 306 Q190 274 222 274 L378 274 Q410 274 412 306 L432 502 Z" fill="{c1}"/>'
        f'<path d="M205 300 L190 480" stroke="#fff" stroke-width="10" opacity=".25" stroke-linecap="round"/>'
        f'<rect x="222" y="256" width="156" height="22" rx="10" fill="{c2}"/>'
        f'<circle cx="300" cy="244" r="16" fill="{c2}"/>'
        f'<rect x="168" y="420" width="264" height="14" fill="{c2}" opacity=".9"/>'
    )


def grinder(c1, c2):
    return (
        f'<rect x="218" y="418" width="164" height="84" rx="12" fill="{c2}"/>'
        f'<rect x="232" y="246" width="136" height="180" rx="14" fill="{c1}"/>'
        f'<rect x="232" y="330" width="136" height="12" fill="{c2}"/>'
        f'<rect x="244" y="220" width="112" height="34" rx="8" fill="{c2}"/>'
        f'<rect x="291" y="186" width="18" height="40" fill="{c2}"/>'
        f'<rect x="291" y="172" width="150" height="18" rx="9" fill="{c1}"/>'
        f'<rect x="428" y="126" width="20" height="66" rx="10" fill="{c2}"/>'
        f'<rect x="248" y="262" width="12" height="56" rx="6" fill="#fff" opacity=".22"/>'
    )


def french_press(c1, c2):
    return (
        f'<path d="M395 276 C478 276 478 448 395 448" fill="none" stroke="{c1}" stroke-width="22" stroke-linecap="round"/>'
        f'<rect x="206" y="244" width="190" height="248" rx="12" fill="#fff" opacity=".6" stroke="{c1}" stroke-opacity=".25" stroke-width="3"/>'
        f'<rect x="209" y="340" width="184" height="149" rx="9" fill="{c2}" opacity=".85"/>'
        f'<rect x="291" y="164" width="18" height="86" fill="{c1}"/>'
        f'<circle cx="300" cy="156" r="22" fill="{c1}"/>'
        f'<rect x="194" y="228" width="214" height="20" rx="9" fill="{c1}"/>'
        f'<rect x="194" y="484" width="214" height="22" rx="9" fill="{c1}"/>'
        f'<rect x="224" y="262" width="10" height="64" rx="5" fill="#fff" opacity=".8"/>'
    )


def scale(c1, c2):
    return (
        f'<rect x="120" y="396" width="360" height="104" rx="26" fill="{c1}"/>'
        f'<rect x="146" y="378" width="308" height="30" rx="12" fill="{c2}"/>'
        f'<rect x="228" y="432" width="144" height="40" rx="7" fill="#0e1714"/>'
        '<text x="300" y="462" text-anchor="middle" font-family="DejaVu Sans Mono, monospace" font-size="26" fill="#9ef0c0">28.4 g</text>'
        f'<circle cx="178" cy="452" r="11" fill="{c2}"/><circle cx="422" cy="452" r="11" fill="{c2}"/>'
        '<rect x="250" y="306" width="100" height="74" rx="10" fill="#fff"/>'
        '<path d="M350 322 C384 322 384 362 348 362" fill="none" stroke="#fff" stroke-width="12"/>'
        '<ellipse cx="300" cy="308" rx="50" ry="8" fill="#5b3a29"/>'
    )


def press(c1, c2):
    grips = "".join(
        f'<rect x="{x}" y="338" width="6" height="90" rx="3" fill="#fff" opacity=".3"/>'
        for x in range(255, 350, 18)
    )
    return (
        f'<rect x="236" y="196" width="128" height="254" rx="10" fill="{c1}"/>'
        f'<rect x="252" y="120" width="96" height="86" rx="10" fill="{c2}"/>'
        f'<rect x="276" y="100" width="48" height="26" rx="8" fill="{c2}"/>'
        f"{grips}"
        f'<rect x="222" y="440" width="156" height="26" rx="10" fill="{c2}"/>'
        f'<rect x="196" y="466" width="208" height="36" rx="12" fill="#fff"/>'
        f'<rect x="204" y="470" width="192" height="10" rx="5" fill="#5b3a29"/>'
    )


def bag(c1, c2, lines):
    big, small = lines
    size = 30 if len(big) <= 7 else 22
    return (
        f'<path d="M188 172 L412 172 L434 502 L166 502 Z" fill="{c1}"/>'
        f'<rect x="182" y="144" width="236" height="40" rx="4" fill="{c2}"/>'
        f'<line x1="196" y1="164" x2="404" y2="164" stroke="#fff" stroke-width="3" stroke-dasharray="7 7" opacity=".5"/>'
        f'<circle cx="300" cy="222" r="11" fill="{c2}"/>'
        '<rect x="212" y="268" width="176" height="182" rx="6" fill="#f6f4ee"/>'
        f'<text x="300" y="298" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" letter-spacing="3" fill="{c1}">FIRST POUR</text>'
        f'<text x="300" y="352" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-weight="700" font-size="{size}" fill="{INK}">{big}</text>'
        f'<text x="300" y="380" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="14" fill="{INK}" opacity=".7">{small}</text>'
        f'<line x1="240" y1="400" x2="360" y2="400" stroke="{c1}" stroke-width="2"/>'
        f'<text x="300" y="430" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="{INK}" opacity=".7">250 g</text>'
    )


def mug(c1, c2):
    steam = "".join(
        f'<path d="M{x} 200 C{x-14} 178 {x+14} 160 {x} 136" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".75"/>'
        for x in (258, 300, 342)
    )
    return (
        f'<path d="M398 306 C484 300 484 428 394 436" fill="none" stroke="{c1}" stroke-width="26" stroke-linecap="round"/>'
        f'<path d="M200 262 L200 440 Q200 492 252 492 L348 492 Q400 492 400 440 L400 262 Z" fill="{c1}"/>'
        f'<ellipse cx="300" cy="262" rx="100" ry="19" fill="{c2}"/>'
        f'<ellipse cx="300" cy="264" rx="88" ry="13" fill="#4a2e20"/>'
        f'<path d="M222 320 L222 430" stroke="#fff" stroke-width="10" opacity=".22" stroke-linecap="round"/>'
        f"{steam}"
    )


def glass_pair(c1, c2):
    def cup(x, top, w, h, coffee):
        inset = w * 0.12
        return (
            f'<path d="M{x} {top} L{x+w} {top} L{x+w-inset} {top+h} Q{x+w-inset-4} {top+h+10} {x+w-inset-16} {top+h+10} L{x+inset+16} {top+h+10} Q{x+inset+4} {top+h+10} {x+inset} {top+h} Z" fill="#fff" fill-opacity=".55" stroke="{c1}" stroke-opacity=".5" stroke-width="3"/>'
            f'<path d="M{x+7} {top+coffee} L{x+w-7} {top+coffee} L{x+w-inset-6} {top+h} L{x+inset+6} {top+h} Z" fill="{c2}" opacity=".9"/>'
        )
    return cup(110, 280, 170, 200, 60) + cup(310, 240, 170, 240, 80)


def tumbler(c1, c2):
    return (
        f'<path d="M222 202 L378 202 L362 488 Q360 504 344 504 L256 504 Q240 504 238 488 Z" fill="{c1}"/>'
        f'<polygon points="231,330 369,330 367,362 233,362" fill="{c2}"/>'
        f'<rect x="212" y="170" width="176" height="38" rx="13" fill="{c2}"/>'
        f'<rect x="326" y="184" width="36" height="9" rx="4" fill="#0e1714"/>'
        f'<path d="M252 232 L260 480" stroke="#fff" stroke-width="9" opacity=".22" stroke-linecap="round"/>'
    )


def filters(c1, c2):
    cones = "".join(
        f'<polygon points="{x},338 {x+70},338 {x+45},{y}" fill="#fbfaf6" stroke="#cfcbbd" stroke-width="2"/>'
        for x, y in [(212, 214), (246, 190), (280, 220)]
    )
    return (
        f"{cones}"
        f'<rect x="186" y="330" width="228" height="172" rx="8" fill="{c1}"/>'
        f'<rect x="186" y="330" width="228" height="26" rx="6" fill="{c2}"/>'
        '<rect x="226" y="390" width="148" height="76" rx="4" fill="#f6f4ee"/>'
        f'<text x="300" y="422" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-weight="700" font-size="19" fill="{INK}">No. 02 cone</text>'
        f'<text x="300" y="446" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="{INK}" opacity=".7">100 sheets</text>'
    )


def canister(c1, c2):
    beans = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="17" ry="11" transform="rotate({r} {x} {y})" fill="#5b3a29"/>'
        f'<path d="M{x-10} {y} Q{x} {y-4} {x+10} {y}" transform="rotate({r} {x} {y})" stroke="#2f1d14" stroke-width="2" fill="none"/>'
        for x, y, r in [(236, 478, 20), (270, 484, -15), (306, 480, 10), (342, 484, -25), (372, 476, 18),
                        (250, 452, -10), (290, 456, 25), (326, 454, -8), (358, 450, 15),
                        (264, 428, 12), (306, 430, -20), (346, 426, 8), (286, 404, -12), (328, 402, 22)]
    )
    return (
        f'<rect x="204" y="248" width="192" height="254" rx="28" fill="#fff" fill-opacity=".5" stroke="{c1}" stroke-opacity=".5" stroke-width="3"/>'
        f"{beans}"
        f'<rect x="248" y="322" width="104" height="70" rx="6" fill="#f6f4ee"/>'
        f'<text x="300" y="354" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-weight="700" font-size="17" fill="{INK}">BEANS</text>'
        f'<text x="300" y="374" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="{INK}" opacity=".7">airtight</text>'
        f'<rect x="212" y="202" width="176" height="52" rx="14" fill="{c1}"/>'
        f'<rect x="276" y="184" width="48" height="24" rx="10" fill="{c2}"/>'
    )


# file name -> (background, drawing)
IMAGES = {
    "ceramic-dripper":   ("#dfe8f5", dripper("#f4f1ea", "#2a44f5")),
    "gooseneck-kettle":  ("#e8e3f0", kettle("#2c3a36", "#8b94a0")),
    "hand-grinder":      ("#f2e6d8", grinder("#b9743f", "#2c3a36")),
    "glass-press":       ("#dcebe4", french_press("#2c3a36", "#6b4630")),
    "brew-scale":        ("#f3e2dd", scale("#2c3a36", "#c9ced2")),
    "travel-press":      ("#e3ecd9", press("#3e6b52", "#2c3a36")),
    "guji-natural":      ("#f4dede", bag("#b8342f", "#7c1f1c", ("Guji", "Ethiopia · natural"))),
    "chikmagalur":       ("#dde9de", bag("#2f6b4a", "#1f4a32", ("Chikmagalur", "Karnataka · washed"))),
    "araku-honey":       ("#f6ead2", bag("#c98a1b", "#8a5c0a", ("Araku", "Andhra · honey"))),
    "huila-washed":      ("#dde3f4", bag("#2a44f5", "#1d2fb0", ("Huila", "Colombia · washed"))),
    "monsooned-malabar": ("#e9e1d6", bag("#6b5a47", "#473a2b", ("Malabar", "Monsooned · dark"))),
    "stoneware-mug":     ("#f3e0e7", mug("#d9a5b3", "#8c5566")),
    "double-wall-cups":  ("#e1ecf3", glass_pair("#2c3a36", "#6b4630")),
    "travel-tumbler":    ("#dfe6dc", tumbler("#e8ece6", "#2a44f5")),
    "filter-papers":     ("#f2ecd9", filters("#d4c7a1", "#b59f5c")),
    "bean-canister":     ("#e6e2ef", canister("#2c3a36", "#8b94a0")),
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (bg, body) in IMAGES.items():
        (OUT / f"{name}.svg").write_text(wrap(bg, body), encoding="utf-8")
    print(f"wrote {len(IMAGES)} images to {OUT}")
