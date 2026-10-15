"""Catalog data. Prices are in rupees here and converted to paise on insert."""

# slug, name, GST percent
CATEGORIES = [
    ("brewing-gear", "Brewing gear", 18),
    ("beans", "Beans", 5),
    ("mugs-and-accessories", "Mugs & accessories", 12),
]

# slug, name, category, price, compare_at, summary, description, specs, stock, rating, rating_count, image, added_on
PRODUCTS = [
    # ---- brewing gear ----
    ("ceramic-dripper-02", "Ceramic Pour-Over Dripper", "brewing-gear", 1450, None,
     "Size 02, brews one to four cups.",
     "A cone dripper with spiral ribs that keep the paper off the wall, so water moves through the bed evenly instead of "
     "racing down the sides. The glaze is thick and holds heat, which matters more than people think on a cold morning.\n"
     "Sits on most mugs and carafes. Hand wash, or top rack if you are in a hurry.",
     [("Material", "Glazed ceramic"), ("Size", "02 (1-4 cups)"), ("Filter", "No. 02 cone"), ("Weight", "420 g")],
     24, 4.7, 212, "ceramic-dripper", "2026-03-04"),

    ("gooseneck-kettle-800", "Gooseneck Kettle, 800 ml", "brewing-gear", 3900, 4600,
     "Fine spout for slow, steady pouring.",
     "The long curved spout gives you control over where the water lands and how fast it comes out. That is most of the "
     "difference between a flat cup and a good one.\n"
     "Stainless steel body with a stay-cool handle and a built-in thermometer slot in the lid. Works on gas, induction "
     "and electric hobs.",
     [("Capacity", "800 ml"), ("Material", "304 stainless steel"), ("Hob", "Gas, induction, electric"), ("Handle", "Stay-cool")],
     11, 4.6, 148, "gooseneck-kettle", "2026-02-11"),

    ("hand-grinder-steel", "Hand Grinder, Steel Burrs", "brewing-gear", 5200, None,
     "Consistent grind from espresso to French press.",
     "Conical steel burrs and a thumb-adjustable dial with clear click stops. It grinds 20 g in about a minute without "
     "making you regret it, and it packs down small enough for a backpack.\n"
     "The aluminium body has a slightly rough finish so it does not slip out of wet hands.",
     [("Burrs", "Conical, stainless steel"), ("Capacity", "25 g"), ("Body", "Anodised aluminium"), ("Weight", "610 g")],
     8, 4.8, 305, "hand-grinder", "2026-01-20"),

    ("glass-french-press-600", "Glass French Press, 600 ml", "brewing-gear", 1799, None,
     "Borosilicate glass, fits in a kitchen drawer.",
     "The classic. Heat-resistant borosilicate glass in a steel frame, with a mesh plunger that keeps most of the grounds "
     "where they belong. Makes about two big mugs.\n"
     "The glass can be replaced separately if you ever crack it, so the frame does not go to waste.",
     [("Capacity", "600 ml"), ("Glass", "Borosilicate"), ("Frame", "Stainless steel"), ("Dishwasher safe", "Yes")],
     30, 4.4, 97, "glass-press", "2025-11-02"),

    ("brew-scale-timer", "Digital Brew Scale with Timer", "brewing-gear", 2450, 2950,
     "0.1 g resolution, built-in brew timer.",
     "Weighing your coffee and water is the cheapest way to make your results repeatable. This scale reads to 0.1 g, "
     "has a flow-rate readout, and a timer that starts as soon as you pour.\n"
     "The silicone mat is splash-proof and comes off for cleaning. USB-C charging, about 40 hours per charge.",
     [("Capacity", "2 kg"), ("Resolution", "0.1 g"), ("Battery", "USB-C, ~40 h"), ("Size", "14 x 14 x 2.5 cm")],
     0, 4.5, 183, "brew-scale", "2025-12-15"),

    ("travel-press-brewer", "Travel Press Brewer", "brewing-gear", 2950, None,
     "Light, tough and quick to clean.",
     "Pressure-brews a smooth single cup in about a minute and cleans up by popping the puck into the bin. It lives in "
     "our office drawer and in more than one hiking bag.\n"
     "Comes with 100 paper filters and a stirrer.",
     [("Makes", "1 cup (up to 240 ml)"), ("Body", "BPA-free copolyester"), ("Includes", "100 filters, stirrer"), ("Weight", "180 g")],
     17, 4.6, 264, "travel-press", "2026-05-09"),

    # ---- beans ----
    ("guji-natural-250", "Ethiopia Guji Natural, 250 g", "beans", 720, None,
     "Blueberry jam and jasmine. Light roast.",
     "Dried in the cherry on raised beds in the Guji zone, which is where all that fruit comes from. Bright and sweet, "
     "with a floral finish that shows up best as a pour-over.\n"
     "Roasted to order every Tuesday and shipped within two days.",
     [("Origin", "Guji, Ethiopia"), ("Process", "Natural"), ("Roast", "Light"), ("Notes", "Blueberry, jasmine, honey")],
     40, 4.9, 176, "guji-natural", "2026-06-02"),

    ("chikmagalur-washed-250", "Chikmagalur Estate Washed, 250 g", "beans", 520, None,
     "Chocolate, toasted almond. Medium roast.",
     "Grown under shade in the hills of Karnataka and washed at the estate. A balanced, easy cup that holds up to milk "
     "and does not fall apart as it cools.\n"
     "Our most reliable all-rounder, good for moka pots, filter and espresso.",
     [("Origin", "Chikmagalur, Karnataka"), ("Process", "Washed"), ("Roast", "Medium"), ("Notes", "Chocolate, almond, caramel")],
     65, 4.5, 241, "chikmagalur", "2025-10-18"),

    ("araku-honey-250", "Araku Valley Honey, 250 g", "beans", 590, 650,
     "Stone fruit and brown sugar. Medium-light roast.",
     "Honey processing leaves some of the fruit on the bean while it dries, so the cup comes out round and sweet without "
     "being sticky. Grown by smallholder farmers in the Eastern Ghats.\n"
     "A good first step if you are moving away from dark roasts.",
     [("Origin", "Araku Valley, Andhra Pradesh"), ("Process", "Honey"), ("Roast", "Medium-light"), ("Notes", "Peach, brown sugar")],
     33, 4.6, 119, "araku-honey", "2026-04-14"),

    ("huila-washed-250", "Colombia Huila Washed, 250 g", "beans", 680, None,
     "Red apple, cane sugar. Medium roast.",
     "Clean and juicy, with the sort of acidity that tastes like a crisp apple rather than a lemon. A very forgiving "
     "bean if your grind is not perfect yet.\n"
     "Single farm lot from the Huila region, roasted a touch darker than our Ethiopian.",
     [("Origin", "Huila, Colombia"), ("Process", "Washed"), ("Roast", "Medium"), ("Notes", "Red apple, cane sugar, cocoa")],
     3, 4.7, 88, "huila-washed", "2026-07-21"),

    ("monsooned-malabar-250", "Monsooned Malabar, 250 g", "beans", 450, None,
     "Low acidity, heavy body. Dark roast.",
     "An old Indian style: beans are left out to the monsoon winds for a few months until they swell and turn pale gold. "
     "The result is low acid, earthy and thick, very good in a French press or with milk.\n"
     "Not for everyone, but the people who like it really like it.",
     [("Origin", "Malabar Coast, Kerala"), ("Process", "Monsooned"), ("Roast", "Dark"), ("Notes", "Cedar, dark chocolate, spice")],
     52, 4.3, 134, "monsooned-malabar", "2025-09-05"),

    # ---- mugs & accessories ----
    ("stoneware-mug-300", "Stoneware Mug, 300 ml", "mugs-and-accessories", 750, None,
     "Hand-glazed in dusty rose.",
     "Thrown and glazed by a small pottery studio, so no two have exactly the same drips on the base. Thick walls hold "
     "the heat and the handle fits two fingers comfortably.\n"
     "Microwave and dishwasher safe.",
     [("Capacity", "300 ml"), ("Material", "Stoneware"), ("Finish", "Satin glaze"), ("Microwave safe", "Yes")],
     46, 4.6, 72, "stoneware-mug", "2026-03-27"),

    ("double-wall-glass-cups", "Double-Wall Glass Cups, set of 2", "mugs-and-accessories", 990, 1190,
     "Looks like it floats. Stays cool to hold.",
     "Two layers of borosilicate glass with an air gap between them, so the coffee stays hot and your fingers stay "
     "comfortable. Good for lattes, cortados and tea.\n"
     "Sold as a pair, packed in a recycled-paper box.",
     [("Capacity", "2 x 250 ml"), ("Glass", "Double-wall borosilicate"), ("Pieces", "2"), ("Dishwasher safe", "Yes")],
     28, 4.5, 156, "double-wall-cups", "2025-12-01"),

    ("insulated-tumbler-350", "Insulated Travel Tumbler, 350 ml", "mugs-and-accessories", 1650, None,
     "Hot for 6 hours, leak-proof lid.",
     "Vacuum-insulated steel that keeps coffee hot for about six hours (and cold for twelve). The lid slides shut, "
     "so it can ride in a bag without drama.\n"
     "Fits most car cup holders.",
     [("Capacity", "350 ml"), ("Material", "18/8 stainless steel"), ("Hot", "6 hours"), ("Cold", "12 hours")],
     21, 4.4, 109, "travel-tumbler", "2026-02-25"),

    ("cone-filter-papers-02", "Cone Filter Papers No. 02, 100 pcs", "mugs-and-accessories", 399, None,
     "Oxygen-bleached, no papery aftertaste.",
     "Fits our ceramic dripper and most other 02 cone drippers. Thin enough to let the oils through, strong enough "
     "not to tear when you rinse them.\n"
     "A pack lasts a bit over three months at one cup a day.",
     [("Size", "02 cone"), ("Count", "100 sheets"), ("Bleaching", "Oxygen"), ("Fits", "Most 02 drippers")],
     120, 4.7, 331, "filter-papers", "2025-08-12"),

    ("airtight-bean-canister", "Airtight Bean Canister, 500 ml", "mugs-and-accessories", 1250, None,
     "Holds about 250 g of beans.",
     "Beans go stale faster than most people expect. This jar has a silicone-sealed lid and a one-way valve for the "
     "carbon dioxide that fresh beans give off, which keeps them tasting good for weeks.\n"
     "Wipe clean, do not soak the lid.",
     [("Capacity", "500 ml"), ("Lid", "Silicone seal, one-way valve"), ("Holds", "~250 g beans"), ("Height", "17 cm")],
     14, 4.5, 64, "bean-canister", "2026-01-08"),
]


# code, kind, value (percent or rupees), cap (rupees), minimum order (rupees),
# starts (days from today), expires (days from today), max uses, once per customer, shown in cart, description
COUPONS = [
    ("WELCOME10", "percent", 10, 500, 0, None, None, None, 1, 1, "10% off, up to ₹500. One use per customer."),
    ("FLAT100", "flat", 100, None, 999, None, None, None, 0, 1, "₹100 off orders over ₹999."),
    ("FIRSTPOUR20", "percent", 20, 1000, 2000, None, 90, 50, 1, 1, "20% off orders over ₹2,000, up to ₹1,000. First 50 uses."),
    ("SUMMER25", "percent", 25, 750, 0, None, -10, None, 0, 0, "Summer sale (ended)."),
]
