"""Autopilot: render next post from content/bank.json, publish it, write weekly report.
Tasks: render-test | post | report
"""
import json, os, subprocess, sys, time, shutil, tempfile
from datetime import datetime, timezone
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont
import instagram_automation as ia

BANK = Path("content/bank.json")
STATE = Path("content/state.json")
MEDIA = Path("media")
REPORTS = Path("reports")
HANDLE = "@ft.prashu"
BG, FG, ACCENT, DIM = (11, 15, 20), (235, 240, 245), (0, 255, 156), (120, 135, 150)
FD = "/usr/share/fonts/truetype/dejavu/"

def font(size, bold=True, mono=False):
    name = ("DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf") if mono else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    try:
        return ImageFont.truetype(FD + name, size)
    except OSError:
        return ImageFont.load_default()

def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines

def frame(w, h):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 10], fill=ACCENT)
    d.text((70, h - 110), HANDLE, font=font(38), fill=ACCENT)
    d.text((w - 70, h - 108), "cybersecurity", font=font(32, False), fill=DIM, anchor="ra")
    return img, d

def draw_block(d, text, fnt, x, y, max_w, fill, gap=14):
    for line in wrap(d, text, fnt, max_w):
        d.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + gap
    return y

def make_image(item, path):
    w, h = 1080, 1350
    img, d = frame(w, h)
    y = draw_block(d, item["title"], font(76), 70, 110, w - 140, FG, 16) + 30
    d.rectangle([70, y, 270, y + 8], fill=ACCENT); y += 60
    fs = 50 if len(item["points"]) <= 4 else 46
    for i, p in enumerate(item["points"], 1):
        d.text((70, y), f"{i:02d}", font=font(fs, mono=True), fill=ACCENT)
        y = draw_block(d, p, font(fs, False), 170, y, w - 240, FG, 12) + 56
    img.convert("RGB").save(path, "JPEG", quality=92)

def make_reel(item, path):
    w, h = 1080, 1920
    tmp = Path(tempfile.mkdtemp())
    slides = [("title", item["title"])] + [("pt", p) for p in item["points"]]
    for i, (kind, text) in enumerate(slides, 1):
        img, d = frame(w, h)
        if kind == "title":
            y = draw_block(d, text, font(96), 80, 650, w - 160, FG, 20) + 30
            d.rectangle([80, y, 330, y + 10], fill=ACCENT)
        else:
            d.text((80, 520), f"{i-1:02d}/{len(item['points']):02d}", font=font(54, mono=True), fill=ACCENT)
            draw_block(d, text, font(66), 80, 640, w - 160, FG, 20)
        img.save(tmp / f"s{i:02d}.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "1/3", "-i", str(tmp / "s%02d.png"),
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(path)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)

def render(item):
    MEDIA.mkdir(exist_ok=True)
    ext = "jpg" if item["type"] == "image" else "mp4"
    path = MEDIA / f"{item['id']}.{ext}"
    (make_image if item["type"] == "image" else make_reel)(item, path)
    return path

def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"done": []}

def sh(*cmd):
    subprocess.run(cmd, check=True)

def raw_url(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path.as_posix()}"

def wait_for_url(url, tries=12):
    for _ in range(tries):
        r = requests.head(url, timeout=20, allow_redirects=True)
        if r.status_code == 200:
            return
        time.sleep(5)
    raise ia.InstagramAPIError(f"Media URL not reachable yet: {url}")

def post():
    bank, state = json.loads(BANK.read_text()), load_state()
    todo = [b for b in bank if b["id"] not in state["done"]]
    if not todo:
        raise ia.InstagramAPIError("Content bank is empty. Ask Claude for a new batch and add it to content/bank.json.")
    item = todo[0]
    path = render(item)
    sh("git", "add", str(path)); sh("git", "commit", "-m", f"Add media {item['id']}"); sh("git", "push")
    url = raw_url(path); wait_for_url(url)
    entry = {"id": item["id"], "type": item["type"], "media_url": url,
             "caption": item["caption"] + "\n\n" + item["tags"]}
    ia.publish_one(entry)
    state["done"].append(item["id"])
    state.setdefault("log", []).append({"id": item["id"], "media_id": entry["published_media_id"], "at": entry["published_at_utc"]})
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    sh("git", "add", str(STATE)); sh("git", "commit", "-m", f"Published {item['id']}"); sh("git", "push")
    print(f"{len(todo)-1} posts left in the bank.")

def report():
    REPORTS.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# Instagram report {now}", ""]
    try:
        me = ia.api("GET", "me", params={"fields": "username,followers_count,follows_count,media_count"})
        lines += [f"- Account: {me.get('username')}", f"- Followers: {me.get('followers_count')}",
                  f"- Following: {me.get('follows_count')}", f"- Media count: {me.get('media_count')}", ""]
    except ia.InstagramAPIError as e:
        lines += [f"- Account stats unavailable: {e}", ""]
    lines += ["| media_id | type | date | reach | likes | comments | saved | shares | views | link |", "|---|---|---|---|---|---|---|---|---|---|"]
    for m in ia.account_media():
        vals = {}
        for metrics in ("reach,likes,comments,saved,shares,views", "reach,likes,comments,saved,shares"):
            try:
                res = ia.api("GET", f"{m['id']}/insights", params={"metric": metrics})
                vals = {x["name"]: (x.get("values") or [{}])[0].get("value", "") for x in res.get("data", [])}
                break
            except ia.InstagramAPIError:
                continue
        g = lambda k: vals.get(k, "-")
        lines.append(f"| {m['id']} | {m.get('media_type')} | {(m.get('timestamp') or '')[:10]} | {g('reach')} | {g('likes')} | {g('comments')} | {g('saved')} | {g('shares')} | {g('views')} | {m.get('permalink')} |")
    text = "\n".join(lines) + "\n"
    (REPORTS / "latest.md").write_text(text); (REPORTS / f"{now}.md").write_text(text)
    sh("git", "add", "reports"); sh("git", "commit", "-m", f"Weekly report {now}")
    sh("git", "push")

def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "post"
    try:
        if task == "render-test":
            for it in json.loads(BANK.read_text()): print(render(it))
        elif task == "post": post()
        elif task == "report": report()
        else: raise ia.InstagramAPIError("Task must be render-test, post or report.")
    except (ia.InstagramAPIError, subprocess.CalledProcessError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
