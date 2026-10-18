"""High-quality slide renderer: carousels (1080x1350) and Reels (1080x1920)."""
import shutil, subprocess, tempfile
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).parent / "assets" / "fonts"
W = 1080
HANDLE = "@ft.prashu"
BG1, BG2 = (5, 8, 15), (11, 19, 36)
ACC, ACC2 = (0, 255, 156), (56, 189, 248)
WHITE, SOFT, DIM = (244, 247, 251), (190, 202, 218), (104, 120, 142)
PANEL, PANEL_LINE = (13, 22, 38), (28, 52, 64)

@lru_cache(maxsize=256)
def F(kind, size, wght):
    name, axes = {"head": ("SpaceGrotesk.ttf", lambda s, w: [w]),
                  "body": ("Inter.ttf", lambda s, w: [min(32, max(14, s)), w]),
                  "mono": ("JetBrainsMono.ttf", lambda s, w: [w])}[kind]
    f = ImageFont.truetype(str(FONTS / name), size)
    f.set_variation_by_axes(axes(size, wght))
    return f

def background(w, h, seed=0):
    img = Image.new("RGB", (w, h), BG1)
    top, bot = Image.new("RGB", (1, 2)), None
    grad = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), BG2), img, grad)
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx, cy = (w - 120, 170) if seed % 2 == 0 else (120, h - 260)
    g.ellipse([cx - 380, cy - 380, cx + 380, cy + 380], fill=(0, 120, 80))
    g.ellipse([w // 2 - 300 + (seed % 3) * 90, h // 2 - 100, w // 2 + 300, h // 2 + 500], fill=(10, 50, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    img = Image.blend(img, Image.composite(glow, img, Image.new("L", (w, h), 255)), 0.55)
    d = ImageDraw.Draw(img)
    for x in range(54, w, 54):
        for y in range(54, h, 54):
            d.point((x, y), fill=(34, 48, 68))
    return img

def words_with_style(text):
    out, parts = [], text.split("*")
    for i, seg in enumerate(parts):
        for wd in seg.split():
            out.append((wd, i % 2 == 1))
    return out

def layout(d, text, font, max_w):
    lines, cur, cw = [], [], 0
    space = d.textlength(" ", font=font)
    for wd, acc in words_with_style(text):
        wl = d.textlength(wd, font=font)
        if cur and cw + space + wl > max_w:
            lines.append(cur); cur, cw = [], 0
        cw += (space if cur else 0) + wl
        cur.append((wd, acc))
    if cur: lines.append(cur)
    return lines

def fit(d, text, kind, wght, max_w, max_h, start, minimum, gap=1.14):
    size = start
    while size >= minimum:
        f = F(kind, size, wght)
        lines = layout(d, text, f, max_w)
        if len(lines) * size * gap <= max_h:
            return f, lines, int(size * gap)
        size -= 4
    f = F(kind, minimum, wght)
    return f, layout(d, text, f, max_w), int(minimum * gap)

def draw_lines(d, lines, f, x, y, lh, color, acc=ACC):
    space = d.textlength(" ", font=f)
    for ln in lines:
        cx = x
        for wd, a in ln:
            d.text((cx, y), wd, font=f, fill=acc if a else color)
            cx += d.textlength(wd, font=f) + space
        y += lh
    return y

def chip(d, x, y, text, color=ACC):
    f = F("mono", 28, 700)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([x, y, x + tw + 44, y + 54], radius=27, outline=color, width=2, fill=(8, 28, 28))
    d.text((x + 22, y + 11), text, font=f, fill=color)

def chrome(d, w, h, i, n, last=False, reel=False):
    seg = (w - 160 - (n - 1) * 8) / n
    for k in range(n):
        x0 = 80 + k * (seg + 8)
        d.rounded_rectangle([x0, 70, x0 + seg, 78], radius=4, fill=ACC if k <= i else (36, 50, 70))
    d.text((80, h - 112), HANDLE, font=F("head", 40, 700), fill=ACC)
    if not last:
        label = "WATCH TO THE END" if reel and i == 0 else ("SWIPE  >>" if not reel else "")
        if label:
            d.text((w - 80, h - 106), label, font=F("mono", 30, 700), fill=DIM, anchor="ra")

def cover(item, w, h, n, reel=False):
    img = background(w, h, 0); d = ImageDraw.Draw(img)
    chrome(d, w, h, 0, n, reel=reel)
    chip(d, 80, 130, "CYBERSECURITY")
    top, bottom = 250, h - 360
    f, lines, lh = fit(d, item["hook"], "head", 700, w - 160, bottom - top - 190, 132, 66, 1.08)
    block = len(lines) * lh
    y0 = top + max(0, (bottom - top - 190 - block) // 2)
    y = draw_lines(d, lines, f, 80, y0, lh, WHITE)
    d.rounded_rectangle([80, y + 24, 260, y + 32], radius=4, fill=ACC)
    if item.get("sub"):
        fs, ls, lhs = fit(d, item["sub"], "body", 500, w - 180, 180, 46, 34, 1.3)
        draw_lines(d, ls, fs, 80, y + 70, lhs, SOFT)
    return img

def content(item, s, idx, total, n, w, h, reel=False):
    img = background(w, h, idx); d = ImageDraw.Draw(img)
    chrome(d, w, h, idx, n, reel=reel)
    top, bottom = (230, h - 200) if not reel else (330, h - 260)
    blocks = []
    num = f"{idx:02d}"
    fh, lh_, hl = fit(d, s["h"], "head", 700, w - 160, 360, 92, 56, 1.1)
    body_lines = None
    if s.get("b"):
        fb, body_lines, bl = fit(d, s["b"], "body", 400, w - 170, 480, 58, 38, 1.36)
    code_lines = s.get("code", "").split("\n") if s.get("code") else []
    fc = F("mono", 38 if max((len(c) for c in code_lines), default=0) <= 30 else 32, 600)
    total_h = 90 + len(lh_) * hl + 40
    if body_lines: total_h += len(body_lines) * bl + 40
    if code_lines: total_h += len(code_lines) * 58 + 70
    y = top + max(0, (bottom - top - total_h) // 2)
    d.text((80, y), num, font=F("mono", 64, 800), fill=ACC)
    d.text((80 + d.textlength(num, font=F("mono", 64, 800)) + 24, y + 30), "/" + f"{total:02d}", font=F("mono", 30, 600), fill=DIM)
    y += 100
    y = draw_lines(d, lh_, fh, 80, y, hl, WHITE) + 26
    if body_lines:
        y = draw_lines(d, body_lines, fb, 80, y, bl, SOFT) + 30
    if code_lines:
        bh = len(code_lines) * 58 + 44
        d.rounded_rectangle([80, y, w - 80, y + bh], radius=22, fill=PANEL, outline=PANEL_LINE, width=2)
        cy = y + 22
        for c in code_lines:
            d.text((112, cy), "$ " if not c.startswith(("#", " ")) and s.get("prompt", True) else "", font=fc, fill=DIM)
            off = d.textlength("$ ", font=fc) if (not c.startswith(("#", " ")) and s.get("prompt", True)) else 0
            d.text((112 + off, cy), c, font=fc, fill=ACC)
            cy += 58
    return img

def outro(item, n, w, h, reel=False):
    img = background(w, h, 1); d = ImageDraw.Draw(img)
    chrome(d, w, h, n - 1, n, last=True, reel=reel)
    top, bottom = (230, h - 220) if not reel else (380, h - 300)
    y = top + (bottom - top - 760) // 2
    d.text((80, y), "Found this useful?", font=F("head", 84, 700), fill=WHITE)
    y += 150
    rows = [("SAVE", "so you can find it later"), ("SEND", "to a friend who needs this"), ("FOLLOW", HANDLE + " for daily cyber tips")]
    for a, b in rows:
        d.rounded_rectangle([80, y, w - 80, y + 118], radius=26, fill=PANEL, outline=PANEL_LINE, width=2)
        d.text((116, y + 30), a, font=F("mono", 40, 800), fill=ACC)
        d.text((116 + 250, y + 36), b, font=F("body", 34, 500), fill=SOFT)
        y += 142
    q = item.get("q")
    if q:
        y += 20
        d.text((80, y), "COMMENT BELOW", font=F("mono", 28, 700), fill=ACC2)
        fq, lq, hq = fit(d, q, "head", 700, w - 160, 200, 56, 40, 1.12)
        draw_lines(d, lq, fq, 80, y + 50, hq, WHITE)
    return img

def scenes(item, w, h, reel=False):
    body = item["slides"]
    n = len(body) + 2
    out = [cover(item, w, h, n, reel)]
    for i, s in enumerate(body, 1):
        out.append(content(item, s, i, len(body), n, w, h, reel))
    out.append(outro(item, n, w, h, reel))
    return out

def render_carousel(item, outdir):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, img in enumerate(scenes(item, W, 1350), 1):
        p = outdir / f"{item['id']}-{i:02d}.jpg"
        img.convert("RGB").save(p, "JPEG", quality=93, optimize=True)
        paths.append(p)
    return paths

def render_reel(item, path):
    tmp = Path(tempfile.mkdtemp())
    imgs = scenes(item, W, 1920, reel=True)
    dur, fade = 3.4, 0.45
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for i, img in enumerate(imgs):
        img.save(tmp / f"s{i:02d}.png")
        cmd += ["-loop", "1", "-t", str(dur + fade), "-framerate", "30", "-i", str(tmp / f"s{i:02d}.png")]
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    n = len(imgs)
    filt, last = [], "[0:v]"
    for i in range(1, n):
        off = round(i * (dur - 0.0), 2) - fade * 0 
        out = f"[x{i}]"
        filt.append(f"{last}[{i}:v]xfade=transition=slideleft:duration={fade}:offset={round(i * dur - fade, 2)}{out}")
        last = out
    total = round(n * dur, 2)
    filt.append(f"{last}fps=30,format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[v]", "-map", f"{n}:a", "-t", str(total),
            "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(path)]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return Path(path)
