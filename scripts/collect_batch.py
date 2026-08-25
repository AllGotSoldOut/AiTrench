#!/usr/bin/env python3
"""
Batch trend collector: gathers MANY trending repos (not just one) and
writes one draft JSON per repo into data/queue/ for parallel writing.
Usage: python scripts/collect_batch.py [--limit N]
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from collect import (
    discover_github_trending, discover_trendshift, discover_ossinsight,
    enrich_repo, looks_ai, search_youtube_recent, find_best_video,
    fetch_transcript, grab_video_frames, grab_readme_images, repo_intel,
    STATE_FILE, DATA_DIR, VIDEO_MAX_AGE_DAYS,
)

QUEUE_DIR = DATA_DIR / "queue"


def main():
    limit = 25
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    done = set(state.get("done", []))

    raw = (discover_github_trending() + discover_trendshift()
           + discover_ossinsight())
    uniq, seen = [], set()
    for c in raw:
        k = c["name"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    print(f"Unique candidates: {len(uniq)}")

    # enrich all, rank AI-looking ones first
    enriched = []
    for c in uniq:
        if c["name"].lower() in done:
            continue
        e = enrich_repo(dict(c))
        if e:
            ai = looks_ai((e["description"] or "") + " " + " ".join(e["topics"]))
            score = min(e["stars"], 50000) / 50
            if ai:
                score += 1000
            if e.get("source") == "github_trending":
                score += 200
            elif e.get("source") == "trendshift":
                score += 150
            if e.get("created_at", "") >= (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d"):
                score += 100
            e["_score"] = score
            enriched.append(e)
    enriched.sort(key=lambda x: x["_score"], reverse=True)
    print(f"Enriched: {len(enriched)}; taking top {limit}")

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0
    for topic in enriched[:limit]:
        slug_base = re.sub(r"[^a-z0-9]+", "-", topic["name"].split("/")[-1].lower()).strip("-")
        slug = f"{today}-{slug_base}"
        qfile = QUEUE_DIR / f"{slug}.json"
        if qfile.exists():
            continue
        readme_images, readme_text = [], ""
        try:
            readme_images, readme_text = grab_readme_images(
                topic["name"], slug, topic.get("default_branch", "main"))
        except Exception as e:
            print(f"  readme error {topic['name']}: {e}")

        videos = []
        try:
            videos = search_youtube_recent(topic["name"])
        except Exception as e:
            print(f"  yt error {topic['name']}: {e}")
        video = find_best_video(topic["name"], videos) if videos else None

        draft = {
            "date": today,
            "slug": slug,
            "topic": topic,
            "mode": "docs",
            "readme_excerpt": (readme_text or "")[:6000],
            "readme_images": readme_images,
            "screenshots": [],
        }
        if video:
            transcript = fetch_transcript(video["id"])
            frames = grab_video_frames(video["url"], slug, video["duration"]) if transcript else []
            draft.update({
                "mode": "video",
                "video": video,
                "transcript_segments": transcript[:400],
                "screenshots": frames or [],
            })
        try:
            draft["intel"] = repo_intel(topic["name"])
        except Exception:
            draft["intel"] = {"latest_release": None, "recent_commits": [], "hot_issues": []}

        # tags: repo name, owner org, key topics
        tags = [topic["name"].split("/")[-1], topic["name"].split("/")[0]]
        tags += [t for t in topic.get("topics", [])][:6]
        draft["tags"] = sorted(set(tags))

        qfile.write_text(json.dumps(draft, indent=2))
        count += 1
        print(f"Queued: {slug} ({draft['mode']})")

    print(f"Queued {count} drafts in {QUEUE_DIR}")


if __name__ == "__main__":
    main()
