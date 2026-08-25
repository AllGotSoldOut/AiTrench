#!/usr/bin/env python3
"""
Trend Collector
===============
Collects everything needed for one daily blog post into data/draft.json:
  1. Trending repos from github.com/trending, trendshift.io, ossinsight.io
  2. Picks best candidate not already blogged
  3. Finds a YouTube how-to video uploaded within last 30 days
     (if none: mode="docs", guide written from README/docs instead)
  4. Downloads transcript + screenshot frames from the video,
     falls back to README images
  5. Gathers repo intel: description, README, latest release, recent
     commits, most-commented open issues (for troubleshooting section)

Output: data/draft.json  (the daily agent turns this into the final post)
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
POSTS_DIR  = BASE_DIR / "posts"
DATA_DIR   = BASE_DIR / "data"
IMAGES_DIR = BASE_DIR / "images"
DRAFT_FILE = DATA_DIR / "draft.json"
STATE_FILE = DATA_DIR / "state.json"

VIDEO_MAX_AGE_DAYS = 30
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Trend-Blog"}


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def http_json(url, timeout=20):
    return json.loads(http_get(url, timeout))


# ── 1. Trend discovery ────────────────────────────────────────────────

AI_HINTS = ["ai", "llm", "gpt", "agent", "ml", "machine-learning", "rag",
            "diffusion", "stable-diffusion", "transformer", "genai",
            "voice", "vision", "chatbot", "embedding", "mcp"]


def looks_ai(text):
    t = text.lower()
    return any(h in t for h in AI_HINTS)


def discover_github_trending():
    """Scrape github.com/trending HTML (daily)."""
    results = []
    try:
        page = http_get("https://github.com/trending?since=daily")
        # Repo entries carry a /stargazers link
        slugs = re.findall(r'href="/([^"/]+/[^"/]+)/stargazers', page)
        seen = set()
        for s in slugs:
            s = s.strip("/")
            if "/" not in s or s in seen or any(x in s.lower() for x in [".github", "topics", "trending", "collections"]):
                continue
            seen.add(s)
            results.append({"name": s, "source": "github_trending"})
        print(f"  github.com/trending: {len(results)} repos")
    except Exception as e:
        print(f"  github trending error: {e}")
    return results


def discover_trendshift():
    """Scrape trendshift.io front page."""
    results = []
    try:
        page = http_get("https://trendshift.io/")
        slugs = set(re.findall(r'href="https://github\.com/([^"/]+/[^"/?#]+)"', page))
        for s in slugs:
            s = s.strip("/")
            if "/" in s:
                results.append({"name": s, "source": "trendshift"})
        print(f"  trendshift.io: {len(results)} repos")
    except Exception as e:
        print(f"  trendshift error: {e}")
    return results


def discover_ossinsight():
    """Ossinsight trending AI repos via their public API."""
    results = []
    urls = [
        "https://api.ossinsight.io/v1/trends/repos/?period=past_7_days&language=&limit=15",
    ]
    for u in urls:
        try:
            data = http_json(u)
            rows = data.get("data", {}).get("rows", [])
            for row in rows:
                name = row.get("full_name") or row.get("repo_name") or ""
                if name and "/" in name:
                    results.append({"name": name, "source": "ossinsight"})
            print(f"  ossinsight: {len(results)} repos")
            break
        except Exception as e:
            print(f"  ossinsight error ({u}): {e}")
    return results


def enrich_repo(entry):
    """Fill in stars/description/language/topics via GitHub API."""
    try:
        r = http_json(f"https://api.github.com/repos/{entry['name']}")
        entry.update({
            "url": r["html_url"],
            "stars": r["stargazers_count"],
            "description": r.get("description") or "",
            "language": r.get("language") or "",
            "topics": r.get("topics", []),
            "homepage": r.get("homepage") or "",
            "pushed_at": (r.get("pushed_at") or "")[:10],
            "created_at": (r.get("created_at") or "")[:10],
            "default_branch": r.get("default_branch", "main"),
        })
        return entry
    except Exception as e:
        print(f"  enrich failed for {entry['name']}: {e}")
        return None


def already_blogged(state):
    return set(state.get("done", []))


def pick_topic(candidates, done):
    """Prefer AI-looking repos, higher stars, sources we trust."""
    scored = []
    for c in candidates:
        if c["name"].lower() in done:
            continue
        enriched = enrich_repo(c)
        if not enriched:
            continue
        score = 0
        desc_topics = (enriched["description"] + " " + " ".join(enriched["topics"])).lower()
        if looks_ai(desc_topics):
            score += 1000
        elif not looks_ai(enriched["name"]):
            score -= 300  # hard-ish penalty for clearly non-AI repos
        score += min(enriched["stars"], 50000) / 50
        if enriched["source"] == "github_trending":
            score += 200       # on GH trending today = hottest signal
        elif enriched["source"] == "trendshift":
            score += 150
        if enriched["created_at"] >= (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d"):
            score += 100       # fresh projects preferred
        scored.append((score, enriched))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored]


# ── 2. YouTube ────────────────────────────────────────────────────────

def search_youtube_recent(topic_name, max_results=10):
    """Search YouTube, return only videos uploaded within VIDEO_MAX_AGE_DAYS."""
    query = f"{topic_name.split('/')[-1]} install setup tutorial"
    search_url = f"ytsearchdate{max_results}:{query}"  # sorted by recency
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print",
             "%(id)s|||%(title)s|||%(duration)s|||%(channel)s|||%(view_count)s|||%(upload_date)s",
             "--no-warning", search_url],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:
        print(f"  yt-dlp search error: {e}")
        return []

    cutoff = datetime.utcnow() - timedelta(days=VIDEO_MAX_AGE_DAYS)
    videos = []
    for line in result.stdout.strip().split("\n"):
        if "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) < 6:
            continue
        vid_id, title, duration, channel, views, up = parts
        try:
            dur = int(duration) if duration.isdigit() else 0
        except ValueError:
            dur = 0
        if dur < 90:
            continue
        # upload_date filter (YYYYMMDD); skip if missing or too old
        if not re.match(r"^\d{8}$", up or ""):
            continue
        try:
            dt = datetime.strptime(up, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff.replace(tzinfo=timezone.utc):
            continue
        videos.append({
            "id": vid_id,
            "title": title,
            "duration": dur,
            "channel": channel,
            "view_count": int(views) if views.isdigit() else 0,
            "upload_date": up,
            "url": f"https://www.youtube.com/watch?v={vid_id}",
        })
    return videos


def find_best_video(topic_name, videos):
    if not videos:
        return None
    kw = ["install", "setup", "set up", "tutorial", "how to", "guide",
          "getting started", "step by step", "beginner"]
    key = topic_name.split("/")[-1].lower()

    def score(v):
        s = v["view_count"] + 1
        tl = v["title"].lower()
        for k in kw:
            if k in tl:
                s *= 2
                break
        if key in tl:
            s *= 1.5
        if 120 <= v["duration"] <= 1500:
            s *= 1.2
        return s

    videos.sort(key=score, reverse=True)
    return videos[0]


def fetch_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        tl = api.fetch(video_id, languages=["en", "en-US"])
        return [{"text": e.text.strip(), "start": round(e.start, 1)}
                for e in tl.snippets]
    except Exception as e:
        print(f"  transcript error: {e}")
        return []


def grab_video_frames(video_url, slug, duration, n=6):
    """
    Download video at low res and save n evenly-spaced frames as PNGs.
    Returns list of relative image paths.
    """
    out_dir = IMAGES_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["yt-dlp", "-f", "best[height<=480]/best", "-o", str(out_dir / "video.%(ext)s"),
             "--no-warning", "-q", video_url],
            capture_output=True, timeout=600,
        )
        video_file = next(out_dir.glob("video.*"), None)
        if not video_file:
            return []
        paths = []
        step = max(duration // (n + 1), 10)
        for i in range(n):
            ts = step * (i + 1)
            if ts >= duration:
                break
            img = out_dir / f"step{i+1}.png"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", str(video_file),
                 "-frames:v", "1", "-q:v", "3", str(img)],
                capture_output=True, timeout=60,
            )
            if img.exists():
                paths.append(f"../images/{slug}/{img.name}")
        video_file.unlink(missing_ok=True)  # don't bloat repo
        print(f"  grabbed {len(paths)} video frames")
        return paths
    except Exception as e:
        print(f"  frame grab error: {e}")
        return []


def grab_readme_images(repo, slug, default_branch):
    """Extract image URLs from the README as fallback visuals."""
    raw = f"https://raw.githubusercontent.com/{repo}/{default_branch}/README.md"
    try:
        text = http_get(raw)
    except Exception:
        try:
            raw = f"https://raw.githubusercontent.com/{repo}/{default_branch}/readme.md"
            text = http_get(raw)
        except Exception:
            return [], ""
    imgs = re.findall(r'!\[[^\]]*\]\((https?://[^)\s]+\.(?:png|jpg|jpeg|gif|webp))\)', text, re.I)
    imgs += [m for m in re.findall(r'<img[^>]+src="(https?://[^"]+)"', text, re.I)]
    seen, unique = set(), []
    for i in imgs:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    return unique[:6], text


# ── 3. Repo intel ─────────────────────────────────────────────────────

def repo_intel(repo):
    intel = {}
    # Latest release
    try:
        rel = http_json(f"https://api.github.com/repos/{repo}/releases/latest")
        intel["latest_release"] = {
            "tag": rel.get("tag_name", ""),
            "date": (rel.get("published_at") or "")[:10],
            "notes": (rel.get("body") or "")[:800],
        }
    except Exception:
        intel["latest_release"] = None
    # Recent commits
    try:
        commits = http_json(f"https://api.github.com/repos/{repo}/commits?per_page=8")
        intel["recent_commits"] = [
            {"message": (c["commit"]["message"].split("\n")[0])[:110],
             "date": c["commit"]["author"]["date"][:10]}
            for c in commits
        ]
    except Exception:
        intel["recent_commits"] = []
    # Most-commented open issues (bug reports -> troubleshooting material)
    try:
        issues = http_json(
            f"https://api.github.com/repos/{repo}/issues?state=open&sort=comments&direction=desc&per_page=6")
        intel["hot_issues"] = [
            {"title": i["title"][:120], "comments": i["comments"],
             "url": i["html_url"], "labels": [l["name"] for l in i.get("labels", [])][:4]}
            for i in issues if "pull_request" not in i
        ]
    except Exception:
        intel["hot_issues"] = []
    return intel


# ── Main ──────────────────────────────────────────────────────────────

def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    done = already_blogged(state)

    candidates = (discover_github_trending()
                  + discover_trendshift()
                  + discover_ossinsight())
    # dedupe
    uniq, seen = [], set()
    for c in candidates:
        if c["name"].lower() not in seen:
            seen.add(c["name"].lower())
            uniq.append(c)
    print(f"Total unique candidates: {len(uniq)}")

    ranked = pick_topic(uniq, done)
    if not ranked:
        print("No new topics available.")
        sys.exit(1)

    topic = ranked[0]
    slug_base = topic["name"].split("/")[-1].lower()
    today = datetime.now().strftime("%Y-%m-%d")
    slug = f"{today}-{re.sub(r'[^a-z0-9]+', '-', slug_base).strip('-')}"
    print(f"Picked: {topic['name']} ({topic['source']}, {topic['stars']} stars)")

    # Video hunt
    videos = search_youtube_recent(topic["name"])
    video = find_best_video(topic["name"], videos)
    draft = {"date": today, "slug": slug, "topic": topic, "mode": "docs"}

    readme_images, readme_text = grab_readme_images(
        topic["name"], slug, topic.get("default_branch", "main"))
    draft["readme_excerpt"] = readme_text[:6000]
    draft["readme_images"] = readme_images

    if video:
        print(f"Video: {video['title']} ({video['upload_date']})")
        transcript = fetch_transcript(video["id"])
        frames = grab_video_frames(video["url"], slug, video["duration"]) if transcript else []
        draft.update({
            "mode": "video",
            "video": video,
            "transcript_segments": transcript[:400],
            "screenshots": frames or readme_images,
        })
    else:
        print("No tutorial <30 days old — writing from official docs.")
        draft["mode"] = "docs"
        draft["screenshots"] = readme_images

    draft["intel"] = repo_intel(topic["name"])

    DRAFT_FILE.write_text(json.dumps(draft, indent=2))
    print(f"Draft saved: {DRAFT_FILE}")


if __name__ == "__main__":
    main()
