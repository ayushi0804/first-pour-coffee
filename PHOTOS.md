# Getting real product photos

Free sites with photos you can use: **Unsplash**, **Pexels**, **Pixabay**. Check the licence on each photo and note the photographer in your README.

Save each photo into `static/img/products/` using the exact file name below (`.jpg`, `.webp` or `.png` all work). Square or near-square photos look best, around 800 x 800 px. Keep each file under about 200 KB so the page loads fast.

| Save as | Search for |
|---|---|
| ceramic-dripper | ceramic coffee dripper, pour over |
| gooseneck-kettle | gooseneck kettle |
| hand-grinder | manual coffee grinder |
| glass-press | french press |
| brew-scale | coffee scale |
| travel-press | aeropress, travel coffee brewer |
| guji-natural | coffee bag, specialty coffee |
| chikmagalur | coffee beans bag |
| araku-honey | coffee beans, light roast |
| huila-washed | coffee bag packaging |
| monsooned-malabar | dark roast coffee beans |
| stoneware-mug | ceramic mug, handmade mug |
| double-wall-cups | double wall glass cup coffee |
| travel-tumbler | insulated tumbler, travel mug |
| filter-papers | coffee filter papers |
| bean-canister | coffee canister, airtight jar |

For the four coffee bags, any bag of coffee works. Then check what you have:

```
python tools/check_photos.py
```

Products without a photo keep showing the drawing, so you can add them a few at a time.
