#!/usr/bin/env python3
"""
Cross-post the latest AI Trend Daily HTML post to WordPress.com.
Usage:
    python post_to_wp.py            # posts newest post not yet posted
    python post_to_wp.py --dry-run  # show what would be posted
Credentials come from env vars or C:/Users/allgo/blog-youtube/data/wp_config.json:
    WP_USER, WP_APP_PASSWORD, WP_SITE
"""
import base64
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POSTS_DIR = BASE_DIR / "posts"
STATE_FILE = DATA_DIR / "wp_state.json"

WP_SITE = "trenchwithai.wordpress.com"


def load_config():
    cfg = {}
    cfg_file = DATA_DIR / "wp_config.json"
    if cfg_file.exists():
        cfg.update(json.loads(cfg_file.read_text(encoding="utf-8")))
    import os
    cfg.setdefault("user", os.environ.get("WP_USER", ""))
    cfg.setdefault("password", os.environ.get("WP_APP_PASSWORD", ""))
    cfg.setdefault("site", os.environ.get("WP_SITE", WP_SITE))
    return cfg


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"posted": []}


def html_to_blocks(post_html):
    """Extract <article> content from the static post and convert to Gutenberg blocks."""
    m = re.search(r"<article[^>]*>(.*?)</article>", post_html, re.S)
    content = m.group(1) if m else post_html

    # Strip nav/header chrome inside article
    content = re.sub(r"<header.*?</header>", "", content, flags=re.S)
    # Convert wrapper divs to nothing (keep inner content) - remove container/post-header wrappers
    content = re.sub(r'<div class="container">', "<!-- wp:group -->", content)

    # YouTube iframe -> embed block
    def iframe_to_embed(mm):
        vid = mm.group(1)
        return f'<!-- wp:embed {{"url":"https://www.youtube.com/watch?v={vid}","type":"video","providerNameSlug":"youtube","responsive":true,"align":"center"}} -->\n<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube wp-embed-aspect-16-9 wp-has-aspect-ratio"><div class="wp-block-embed__wrapper">\nhttps://www.youtube.com/watch?v={vid}\n</div></figure>\n<!-- /wp:embed -->'
    content = re.sub(r'<iframe src="https://www\.youtube\.com/embed/([\w-]+)"[^>]*></iframe>', iframe_to_embed, content)

    # Links opening in new tab: keep but add rel noopener already present
    return content.strip()


def extract_title(post_html):
    m = re.search(r"<h1>(.*?)</h1>", post_html, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "AI Trend Daily"


def extract_tags(post_html):
    return [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r'<span class="tag">(.*?)</span>', post_html, re.S)]


def newest_unposted_post(state):
    files = sorted(POSTS_DIR.glob("*.html"))
    posted = set(state["posted"])
    for f in reversed(files):  # newest first (date-prefixed names)
        if f.name in posted:
            continue
        return f
    return None


def publish(cfg, title, content_html, tags):
    url = f"https://public-api.wordpress.com/rest/v1.1/sites/{cfg['site']}/posts/new"
    auth = base64.b64encode(f"{cfg['user']}:{cfg['password']}".encode()).decode()
    payload = {
        "title": title,
        "content": content_html,
        "status": "publish",
        "terms": {"post_tag": tags} if tags else {},
    }
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "AI-Trend-Daily/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"ERROR {e.code}: {body[:500]}")
        return None


import urllib.parse  # noqa: E402


def main():
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    state = load_state()

    if not dry and (not cfg["user"] or not cfg["password"]):
        print("Missing WP_USER / WP_APP_PASSWORD. Put them in data/wp_config.json:")
        print('{"user": "your-wp-username", "password": "xxxx xxxx xxxx xxxx xxxx xxxx"}')
        sys.exit(1)

    post_file = newest_unposted_post(state)
    if not post_file:
        print("Nothing new to post.")
        return

    print(f"Posting: {post_file.name}")
    post_html = post_file.read_text(encoding="utf-8")
    title = extract_title(post_html)
    content = html_to_blocks(post_html)
    tags = extract_tags(post_html)[:8]

    if dry:
        print(f"Title: {title}")
        print(f"Tags: {tags}")
        print(f"Content length: {len(content)} chars")
        print(content[:800])
        return

    result = publish(cfg, title, content, tags)
    if result:
        print(f"Published: {result.get('URL', '?')}")
        state["posted"].append(post_file.name)
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
