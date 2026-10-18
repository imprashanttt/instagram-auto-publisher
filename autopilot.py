"""Autopilot for @ft.prashu: render next post from content/bank.json, publish it, weekly report.
Tasks: render-test | post | report
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests
import instagram_automation as ia
import render

BANK, STATE = Path("content/bank.json"), Path("content/state.json")
MEDIA, REPORTS = Path("media"), Path("reports")

def sh(*cmd):
    subprocess.run(cmd, check=True)

def commit_push(paths, message, remove=()):
    for r in remove:
        subprocess.run(["git", "rm", "-q", "--ignore-unmatch", str(r)], check=False)
    if paths:
        sh("git", "add", *[str(p) for p in paths])
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("Nothing new to commit."); return
    sh("git", "commit", "-m", message)
    sh("git", "pull", "--rebase", "--autostash")
    sh("git", "push")

def raw_url(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{Path(path).as_posix()}"

def wait_for_url(url, tries=14):
    for _ in range(tries):
        try:
            if requests.head(url, timeout=20, allow_redirects=True).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise ia.InstagramAPIError(f"Media URL not reachable yet: {url}")

def full_caption(item):
    return item["caption"].strip() + "\n\n" + item["tags"]

def publish_carousel(item, urls):
    child_ids = []
    for u in urls:
        r = ia.api("POST", f"{ia.USER_ID}/media", data={"image_url": u, "is_carousel_item": "true"})
        child_ids.append(r["id"])
    for cid in child_ids:
        ia.wait_for_container(cid, attempts=18, interval=5)
    parent = ia.api("POST", f"{ia.USER_ID}/media", data={"media_type": "CAROUSEL", "children": ",".join(child_ids), "caption": full_caption(item)})
    ia.wait_for_container(parent["id"], attempts=18, interval=5)
    pub = ia.api("POST", f"{ia.USER_ID}/media_publish", data={"creation_id": parent["id"]})
    return pub["id"]

def post():
    bank = json.loads(BANK.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {"done": []}
    todo = [b for b in bank if b["id"] not in state["done"]]
    if not todo:
        raise ia.InstagramAPIError("Content bank is empty. Ask Claude for a new batch.")
    item = todo[0]
    MEDIA.mkdir(exist_ok=True)
    if item["type"] == "carousel":
        files = render.render_carousel(item, MEDIA)
    else:
        files = [render.render_reel(item, MEDIA / f"{item['id']}.mp4")]
    commit_push(files, f"Add media {item['id']}")
    urls = [raw_url(f) for f in files]
    for u in urls: wait_for_url(u)
    if item["type"] == "carousel":
        media_id = publish_carousel(item, urls)
    else:
        entry = {"id": item["id"], "type": "reel", "media_url": urls[0], "caption": full_caption(item)}
        ia.publish_one(entry); media_id = entry["published_media_id"]
    state["done"].append(item["id"])
    state.setdefault("log", []).append({"id": item["id"], "type": item["type"], "media_id": media_id,
                                        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    commit_push([STATE], f"Published {item['id']}", remove=files)
    print(f"Published {item['id']}. {len(todo)-1} posts left in the bank.")

def score(v):
    n = lambda k: v.get(k) if isinstance(v.get(k), (int, float)) else 0
    return n("saved") * 4 + n("shares") * 4 + n("comments") * 3 + n("likes")

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
    rows, comments = [], []
    for m in ia.account_media():
        vals = {}
        for metrics in ("reach,likes,comments,saved,shares,views", "reach,likes,comments,saved,shares"):
            try:
                res = ia.api("GET", f"{m['id']}/insights", params={"metric": metrics})
                vals = {x["name"]: (x.get("values") or [{}])[0].get("value", "") for x in res.get("data", [])}
                break
            except ia.InstagramAPIError:
                continue
        rows.append((score(vals), m, vals))
        try:
            for c in ia.api("GET", f"{m['id']}/comments", params={"fields": "id,text,username,timestamp", "limit": 10}).get("data", []):
                comments.append((c.get("timestamp", ""), m.get("permalink"), c.get("username"), c.get("text")))
        except ia.InstagramAPIError:
            pass
    rows.sort(key=lambda r: r[0], reverse=True)
    lines += ["## Posts ranked by engagement score (saves x4, shares x4, comments x3, likes x1)", "",
              "| score | caption start | type | date | reach | likes | comments | saved | shares | views | link |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for sc, m, v in rows:
        g = lambda k: v.get(k, "-")
        cap = (m.get("caption") or "").split("\n")[0][:50].replace("|", "/")
        lines.append(f"| {sc} | {cap} | {m.get('media_type')} | {(m.get('timestamp') or '')[:10]} | {g('reach')} | {g('likes')} | {g('comments')} | {g('saved')} | {g('shares')} | {g('views')} | {m.get('permalink')} |")
    lines += ["", "## Recent comments", ""]
    for ts, link, user, text in sorted(comments, reverse=True)[:30]:
        lines.append(f"- {ts[:10]} @{user}: {(text or '').replace(chr(10), ' ')[:200]} ({link})")
    text = "\n".join(lines) + "\n"
    (REPORTS / "latest.md").write_text(text); (REPORTS / f"{now}.md").write_text(text)
    commit_push([REPORTS], f"Weekly report {now}")

def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "post"
    try:
        if task == "render-test":
            for it in json.loads(BANK.read_text())[:3]:
                print(render.render_carousel(it, "/tmp/rt") if it["type"] == "carousel" else render.render_reel(it, f"/tmp/rt/{it['id']}.mp4"))
        elif task == "post": post()
        elif task == "report": report()
        else: raise ia.InstagramAPIError("Task must be render-test, post or report.")
    except (ia.InstagramAPIError, subprocess.CalledProcessError, OSError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
