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

    # 6. Yam Anthracnose (huge hastate leaf, dark sunken spots)
    img_yam = Image.new("RGB", (w, h), (25, 25, 25))
    draw_y = ImageDraw.Draw(img_yam)
    draw_y.polygon([(320, 30), (470, 250), (430, 460), (210, 460), (170, 250)], fill=(48, 150, 48))
    draw_y.line([(320, 40), (320, 450)], fill=(85, 190, 85), width=7)
    for sx, sy, sr in [(280, 200, 30), (360, 300, 36), (310, 370, 26), (340, 150, 24)]:
        draw_y.ellipse([sx - sr - 8, sy - sr - 8, sx + sr + 8, sy + sr + 8], fill=(235, 210, 40))
        draw_y.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(28, 14, 8))
    Image.fromarray(np.array(img_yam)).save(
        os.path.join(output_dir, "yam_anthracnose.jpg"), quality=95)

    # 7. Cowpea Aphids (trifoliate: 3 round leaflets, curled + mottled)
    img_cow = Image.new("RGB", (w, h), (25, 25, 25))
    draw_c = ImageDraw.Draw(img_cow)
    for cx, cy in [(250, 200), (390, 200), (320, 330)]:
        draw_c.ellipse([cx - 75, cy - 70, cx + 75, cy + 70], fill=(52, 158, 48))
    draw_c.line([(320, 400), (320, 260)], fill=(80, 190, 80), width=5)
    arr_c = np.array(img_cow).astype(np.float32)
    yg, xg = np.ogrid[:h, :w]
    mot = (np.sin(xg / 18.0) * np.cos(yg / 18.0) > 0.3) & (arr_c[:, :, 1] > 80)
    arr_c[mot, 0] = 230
    arr_c[mot, 1] = 215
    arr_c[mot, 2] = 40
    Image.fromarray(np.clip(arr_c, 0, 255).astype(np.uint8)).save(
        os.path.join(output_dir, "cowpea_aphids.jpg"), quality=95)

    # 8. Sorghum Anthracnose (broad draping blade, red-purple spots)
    img_sor = Image.new("RGB", (w, h), (25, 25, 25))
    draw_s = ImageDraw.Draw(img_sor)
    draw_s.polygon([(120, 470), (220, 470), (520, 60), (430, 30)], fill=(55, 155, 50))
    draw_s.line([(170, 470), (475, 45)], fill=(200, 210, 180), width=9)
    for sx, sy, sr in [(300, 300, 14), (380, 220, 18), (440, 140, 12)]:
        draw_s.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(140, 40, 60))
        draw_s.ellipse([sx - sr // 2, sy - sr // 2, sx + sr // 2, sy + sr // 2], fill=(200, 170, 90))
    Image.fromarray(np.array(img_sor)).save(
        os.path.join(output_dir, "sorghum_anthracnose.jpg"), quality=95)

    # 9. Rice Blast (narrow ribbon blade, diamond lesions)
    img_rice = Image.new("RGB", (w, h), (25, 25, 25))
    draw_r = ImageDraw.Draw(img_rice)
    draw_r.polygon([(270, 470), (310, 470), (380, 40), (340, 30)], fill=(60, 165, 55))
    draw_r.line([(290, 470), (360, 35)], fill=(120, 200, 110), width=3)
    for sx, sy in [(320, 350), (335, 250), (350, 150), (328, 300), (342, 200)]:
        draw_r.polygon([(sx - 14, sy), (sx, sy - 30), (sx + 14, sy), (sx, sy + 30)], fill=(150, 150, 150))
        draw_r.polygon([(sx - 14, sy), (sx, sy - 30), (sx + 14, sy), (sx, sy + 30)], outline=(110, 60, 30), width=4)
    Image.fromarray(np.array(img_rice)).save(
        os.path.join(output_dir, "rice_blast.jpg"), quality=95)

    # 10. Pepper Bacterial Spot (small glossy ovals, dark spots + halos)
    img_pep = Image.new("RGB", (w, h), (25, 25, 25))
    draw_p = ImageDraw.Draw(img_pep)
    for cx, cy in [(260, 220), (380, 260), (320, 350)]:
        draw_p.ellipse([cx - 55, cy - 45, cx + 55, cy + 45], fill=(40, 145, 45))
    for sx, sy, sr in [(250, 215, 10), (390, 265, 12), (315, 345, 9)]:
        draw_p.ellipse([sx - sr - 6, sy - sr - 6, sx + sr + 6, sy + sr + 6], fill=(235, 215, 40))
        draw_p.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(60, 40, 20))
    Image.fromarray(np.array(img_pep)).save(
        os.path.join(output_dir, "pepper_spot.jpg"), quality=95)

    # 11. Okra Yellow Vein Mosaic (coarse 5-lobed leaf, yellow vein netting)
    img_okra = Image.new("RGB", (w, h), (30, 28, 26))
    draw_o = ImageDraw.Draw(img_okra)
    center = (w // 2, h // 2 + 60)
    for angle in [-70, -35, 0, 35, 70]:
        rad = np.radians(angle)
        ex = int(center[0] + 175 * np.sin(rad))
        ey = int(center[1] - 175 * np.cos(rad))
        draw_o.line([center, (ex, ey)], fill=(58, 150, 48), width=60)
    arr_o = np.array(img_okra).astype(np.float32)
    vein = ((np.abs(np.sin(xg / 9.0)) < 0.25) | (np.abs(np.cos(yg / 9.0)) < 0.25)) & (arr_o[:, :, 1] > 80)
    arr_o[vein, 0] = 240
    arr_o[vein, 1] = 225
    arr_o[vein, 2] = 30
    Image.fromarray(np.clip(arr_o, 0, 255).astype(np.uint8)).save(
        os.path.join(output_dir, "okra_mosaic.jpg"), quality=95)

    # 12. Groundnut Rosette (4 small oval leaflets, stunted + mottled)
    img_gnut = Image.new("RGB", (w, h), (25, 25, 25))
    draw_g = ImageDraw.Draw(img_gnut)
    for cx, cy in [(270, 210), (370, 210), (270, 320), (370, 320)]:
        draw_g.ellipse([cx - 48, cy - 38, cx + 48, cy + 38], fill=(55, 155, 50))
    arr_g = np.array(img_gnut).astype(np.float32)
    motg = (np.sin(xg / 16.0) * np.cos(yg / 16.0) > 0.2) & (arr_g[:, :, 1] > 80)
    arr_g[motg, 0] = 225
    arr_g[motg, 1] = 210
    arr_g[motg, 2] = 45
    Image.fromarray(np.clip(arr_g, 0, 255).astype(np.uint8)).save(
        os.path.join(output_dir, "groundnut_rosette.jpg"), quality=95)

    # 13. Sweet Potato Virus (heart-shaped lobed leaf, feathery yellow mosaic)
    img_sp = Image.new("RGB", (w, h), (25, 25, 25))
    draw_sp = ImageDraw.Draw(img_sp)
    draw_sp.polygon([(320, 120), (440, 220), (400, 380), (240, 380), (200, 220)], fill=(52, 155, 50))
    draw_sp.line([(320, 130), (320, 370)], fill=(90, 195, 90), width=5)
    arr_sp = np.array(img_sp).astype(np.float32)
    feather = (np.abs(np.sin((xg + yg) / 12.0)) < 0.3) & (arr_sp[:, :, 1] > 80)
    arr_sp[feather, 0] = 235
    arr_sp[feather, 1] = 220
    arr_sp[feather, 2] = 35
    Image.fromarray(np.clip(arr_sp, 0, 255).astype(np.uint8)).save(
        os.path.join(output_dir, "sweetpotato_virus.jpg"), quality=95)


if __name__ == "__main__":
    create_sample_dataset()
