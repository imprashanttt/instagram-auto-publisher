import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

API_VERSION = os.getenv("IG_API_VERSION", "v26.0")
BASE_URL = f"https://graph.instagram.com/{API_VERSION}"
TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
USER_ID = os.getenv("IG_USER_ID", "")
QUEUE_PATH = Path("queue/posts.json")
TIMEOUT = 40


class InstagramAPIError(RuntimeError):
    pass


def require_credentials():
    if not TOKEN or not USER_ID:
        raise InstagramAPIError("Missing IG_ACCESS_TOKEN or IG_USER_ID environment secret.")


def api(method, path, *, params=None, data=None):
    require_credentials()
    url = f"{BASE_URL}/{path.lstrip('/')}"
    payload = dict(params or {})
    payload["access_token"] = TOKEN
    try:
        response = requests.request(method, url, params=payload, data=data, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise InstagramAPIError(f"Network error contacting Instagram API: {exc}") from exc
    try:
        result = response.json()
    except ValueError:
        result = {"raw_response": response.text[:500]}
    if not response.ok or "error" in result:
        # Do not include request params because they contain the token.
        err = result.get("error", result)
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        code = err.get("code", "") if isinstance(err, dict) else ""
        raise InstagramAPIError(f"Instagram API returned HTTP {response.status_code}, code={code}: {message}")
    return result


def validate_public_url(value):
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or not parsed.netloc or "REPLACE_WITH_PUBLIC" in value:
        raise InstagramAPIError("Each enabled post needs a real public HTTPS media_url.")
    return value


def load_queue():
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def save_queue(posts):
    QUEUE_PATH.write_text(json.dumps(posts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wait_for_container(container_id, attempts=18, interval=10):
    for _ in range(attempts):
        state = api("GET", container_id, params={"fields": "status_code,status"})
        code = state.get("status_code", "")
        if code == "FINISHED":
            return
        if code in {"ERROR", "EXPIRED"}:
            raise InstagramAPIError(f"Media container {container_id} ended with status {code}: {state.get('status', '')}")
        print(f"Container status: {code or 'PROCESSING'}")
        time.sleep(interval)
    raise InstagramAPIError(f"Container {container_id} did not finish processing in time; check Meta status before retrying.")


def publish_one(post):
    kind = post.get("type")
    media_url = validate_public_url(post.get("media_url", ""))
    caption = post.get("caption", "")
    if kind == "image":
        params = {"image_url": media_url, "caption": caption}
    elif kind == "reel":
        params = {"media_type": "REELS", "video_url": media_url, "caption": caption, "share_to_feed": "true"}
    else:
        raise InstagramAPIError(f"Unsupported post type {kind!r}; use 'image' or 'reel'.")
    container = api("POST", f"{USER_ID}/media", data=params)
    creation_id = container.get("id")
    if not creation_id:
        raise InstagramAPIError("Instagram did not return a media container ID.")
    print(f"Created media container for queue item {post.get('id')}.")
    # Images also need processing time; publishing too early gives error 9007.
    wait_for_container(creation_id, attempts=18, interval=5 if kind == "image" else 10)
    published = api("POST", f"{USER_ID}/media_publish", data={"creation_id": creation_id})
    media_id = published.get("id")
    if not media_id:
        raise InstagramAPIError("Publish response did not include a media ID.")
    post["status"] = "published"
    post["published_media_id"] = media_id
    post["published_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"Published queue item {post.get('id')} successfully. Media ID: {media_id}")


def publish_queue():
    posts = load_queue()
    candidates = [p for p in posts if p.get("enabled") is True and p.get("status", "pending") == "pending"]
    if not candidates:
        raise InstagramAPIError("No enabled pending queue item. Edit queue/posts.json and enable one item.")
    # Process one per run to avoid accidentally publishing a whole queue.
    post = candidates[0]
    print(f"Processing one queue item: {post.get('id')} ({post.get('type')}).")
    publish_one(post)
    save_queue(posts)


def account_media():
    return api("GET", f"{USER_ID}/media", params={
        "fields": "id,caption,media_type,permalink,timestamp",
        "limit": 25
    }).get("data", [])


def collect_insights():
    media = account_media()
    if not media:
        print("No media returned for this account.")
        return
    for item in media:
        media_id = item.get("id")
        print(json.dumps({
            "media_id": media_id,
            "caption": (item.get("caption") or "")[:100],
            "media_type": item.get("media_type"),
            "permalink": item.get("permalink"),
            "timestamp": item.get("timestamp"),
        }, ensure_ascii=False))
        # Metric availability differs by media type and Meta API changes.
        try:
            result = api("GET", f"{media_id}/insights", params={
                "metric": "reach,likes,comments,saved,shares"
            })
            print(json.dumps({"media_id": media_id, "insights": result.get("data", [])}, ensure_ascii=False))
        except InstagramAPIError as exc:
            print(f"Insights unavailable for media {media_id}: {exc}")


def monitor_comments():
    for item in account_media():
        media_id = item.get("id")
        try:
            result = api("GET", f"{media_id}/comments", params={
                "fields": "id,text,timestamp,username",
                "limit": 25
            })
        except InstagramAPIError as exc:
            print(f"Could not retrieve comments for media {media_id}: {exc}")
            continue
        for comment in result.get("data", []):
            # Do not print commenter data beyond what is needed for comment moderation.
            print(json.dumps({
                "media_id": media_id,
                "comment_id": comment.get("id"),
                "username": comment.get("username"),
                "text": comment.get("text"),
                "timestamp": comment.get("timestamp"),
                "permalink": item.get("permalink"),
            }, ensure_ascii=False))


def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "publish"
    try:
        if task == "publish":
            publish_queue()
        elif task == "insights":
            collect_insights()
        elif task == "comments":
            monitor_comments()
        elif task == "check":
            me = api("GET", "me", params={"fields": "user_id,username"})
            print(json.dumps(me, ensure_ascii=False))
        else:
            raise InstagramAPIError("Task must be one of: check, publish, insights, comments.")
    except (InstagramAPIError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
