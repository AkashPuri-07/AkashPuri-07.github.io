"""Post-process AI-generated images: overlay branded text on og:image, and build favicon set."""
from PIL import Image, ImageDraw, ImageFont

PUB = "/app/frontend/public"
INK = (20, 19, 15)
INK_2 = (74, 71, 64)
GOLD = (143, 116, 67)   # #8f7443 – gold_deep

# -------------- OG IMAGE (1200x630) --------------
og_bg = Image.open(f"{PUB}/og-image.png").convert("RGB")
# Center-crop to 1200x630 aspect ratio and resize
target_w, target_h = 1200, 630
src_w, src_h = og_bg.size
target_ratio = target_w / target_h
src_ratio = src_w / src_h
if src_ratio > target_ratio:
    # source wider — crop width
    new_w = int(src_h * target_ratio)
    left = (src_w - new_w) // 2
    og_bg = og_bg.crop((left, 0, left + new_w, src_h))
else:
    new_h = int(src_w / target_ratio)
    top = (src_h - new_h) // 2
    og_bg = og_bg.crop((0, top, src_w, top + new_h))
og_bg = og_bg.resize((target_w, target_h), Image.LANCZOS)

draw = ImageDraw.Draw(og_bg)
f_title = ImageFont.truetype("/tmp/fonts/Fraunces-VF.ttf", 120)
f_title.set_variation_by_axes([30, 0, 144, 500])  # SOFT, WONK, opsz, wght
f_sub = ImageFont.truetype("/tmp/fonts/Fraunces-Italic-VF.ttf", 44)
f_sub.set_variation_by_axes([100, 0, 144, 500])
f_tag = ImageFont.truetype("/tmp/fonts/Inter-VF.ttf", 22)
f_tag.set_variation_by_axes([32, 600])
f_brand = ImageFont.truetype("/tmp/fonts/Inter-VF.ttf", 20)
f_brand.set_variation_by_axes([14, 600])

pad_x, pad_top = 80, 180
# Small brand tag at top
draw.text((pad_x, pad_top - 100), "PORTFOLIO — 2025", font=f_brand, fill=GOLD, spacing=4)
# Title
draw.text((pad_x, pad_top), "Akash Puri", font=f_title, fill=INK)
# Italic gold subtitle
draw.text((pad_x, pad_top + 165), "Programmatic & Display Advertising", font=f_sub, fill=GOLD)
# Small tagline
draw.text((pad_x, pad_top + 240), "TURNING ATTENTION INTO RESULTS.", font=f_tag, fill=INK_2, spacing=4)

og_bg.save(f"{PUB}/og-image.png", "PNG", optimize=True)
og_bg.save(f"{PUB}/og-image.jpg", "JPEG", quality=88, optimize=True)
print(f"OG image saved: 1200x630")

# -------------- FAVICON (multiple sizes + .ico) --------------
fav_src = Image.open(f"{PUB}/favicon-source.png").convert("RGBA")
# Center-crop to square (already square-ish, but ensure tight)
sw, sh = fav_src.size
side = min(sw, sh)
left = (sw - side) // 2
top = (sh - side) // 2
fav_src = fav_src.crop((left, top, left + side, top + side))

# Sizes
sizes = [16, 32, 48, 64, 180, 192, 256, 512]
imgs = {}
for s in sizes:
    imgs[s] = fav_src.resize((s, s), Image.LANCZOS)
imgs[512].save(f"{PUB}/favicon-512.png", "PNG", optimize=True)
imgs[192].save(f"{PUB}/favicon-192.png", "PNG", optimize=True)
imgs[180].save(f"{PUB}/apple-touch-icon.png", "PNG", optimize=True)
imgs[32].save(f"{PUB}/favicon-32.png", "PNG", optimize=True)

# Multi-size .ico
imgs[64].save(f"{PUB}/favicon.ico", format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print("Favicon set saved.")
