"""Generates realistic sample leaf pathology images for testing and demoing."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def create_sample_dataset(output_dir: str = "sample_data"):
    os.makedirs(output_dir, exist_ok=True)
    w, h = 640, 480

    # 1. Cassava Mosaic Leaf (Yellow mottled chlorosis + green base)
    img_cassava = Image.new("RGB", (w, h), (30, 28, 26))  # dark neutral background
    draw = ImageDraw.Draw(img_cassava)
    # 5-lobed cassava leaf outline
    center = (w // 2, h // 2 + 50)
    for angle in [-65, -32, 0, 32, 65]:
        rad = np.radians(angle)
        ex = int(center[0] + 195 * np.sin(rad))
        ey = int(center[1] - 195 * np.cos(rad))
        draw.line([center, (ex, ey)], fill=(55, 155, 45), width=75)

    arr = np.array(img_cassava).astype(np.float32)
    # Add mottled yellow mosaic spots on 40% of the leaf
    y_grid, x_grid = np.ogrid[:h, :w]
    mosaic_pattern = (np.sin(x_grid / 14.0) * np.cos(y_grid / 14.0) > 0.1)
    leaf_zone = (arr[:, :, 1] > 80)
    # Bright chlorotic yellow (R=240, G=225, B=30)
    arr[mosaic_pattern & leaf_zone, 0] = 240
    arr[mosaic_pattern & leaf_zone, 1] = 225
    arr[mosaic_pattern & leaf_zone, 2] = 30
    cassava_img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    cassava_img.save(os.path.join(output_dir, "cassava_mosaic.jpg"), quality=95)

    # 2. Maize Leaf with Fall Armyworm (Elongated green blade with chewed holes)
    img_maize = Image.new("RGB", (w, h), (25, 25, 25))
    draw_m = ImageDraw.Draw(img_maize)
    # Long maize blade
    draw_m.polygon([(80, 460), (140, 460), (560, 40), (500, 20)], fill=(50, 160, 45))
    # Midrib
    draw_m.line([(110, 460), (530, 30)], fill=(90, 200, 80), width=6)
    # Chewed holes & necrotic edges
    holes = [(260, 290, 24), (340, 210, 28), (420, 130, 20), (370, 175, 16)]
    for hx, hy, hr in holes:
        draw_m.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(25, 25, 25))  # hole through to background
        draw_m.ellipse([hx - hr - 3, hy - hr - 3, hx + hr + 3, hy + hr + 3], outline=(160, 80, 25), width=3) # necrotic margin
    img_maize.save(os.path.join(output_dir, "maize_fall_armyworm.jpg"), quality=95)

    # 3. Tomato Early Blight (Dark brown target spots with yellow halos)
    img_tomato = Image.new("RGB", (w, h), (28, 28, 28))
    draw_t = ImageDraw.Draw(img_tomato)
    # Tomato leaflet
    draw_t.ellipse([160, 100, 480, 400], fill=(55, 150, 45))
    # Target-board lesions
    spots = [(270, 220, 26), (370, 280, 32), (320, 320, 20)]
    for sx, sy, sr in spots:
        draw_t.ellipse([sx - sr - 10, sy - sr - 10, sx + sr + 10, sy + sr + 10], fill=(235, 210, 35)) # Yellow halo
        draw_t.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(130, 65, 25)) # Necrotic brown
        draw_t.ellipse([sx - sr // 2, sy - sr // 2, sx + sr // 2, sy + sr // 2], fill=(60, 30, 15)) # Dark center
    tomato_img = img_tomato.filter(ImageFilter.GaussianBlur(0.8))
    tomato_img.save(os.path.join(output_dir, "tomato_early_blight.jpg"), quality=95)

    # 4. Healthy Leaf (Vibrant uniform green)
    img_healthy = Image.new("RGB", (w, h), (25, 25, 25))
    draw_h = ImageDraw.Draw(img_healthy)
    draw_h.ellipse([150, 80, 490, 420], fill=(45, 165, 50))
    draw_h.line([(320, 420), (320, 90)], fill=(90, 205, 95), width=8) # Main vein
    for vy in range(150, 390, 35):
        draw_h.line([(320, vy), (210, vy - 25)], fill=(75, 185, 80), width=3)
        draw_h.line([(320, vy), (430, vy - 25)], fill=(75, 185, 80), width=3)
    healthy_img = img_healthy.filter(ImageFilter.GaussianBlur(0.6))
    healthy_img.save(os.path.join(output_dir, "healthy_leaf.jpg"), quality=95)

    # 5. Non-leaf image (concrete grey texture)
    img_nonleaf = Image.new("RGB", (w, h), (145, 142, 140))
    img_nonleaf.save(os.path.join(output_dir, "non_leaf_sample.jpg"), quality=90)


if __name__ == "__main__":
    create_sample_dataset()
