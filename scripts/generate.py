#!/usr/bin/env python3
"""
Trending AI Blog Generator
==========================
Daily pipeline:
1. Discover trending AI projects/repos from:
   - GitHub: recently created repos with rising stars (AI/ML tagged)
   - GitHub: high-star repos with recent activity
   - HackerNews: top stories mentioning AI/LLM/tools
2. Pick one trending topic per day (not already blogged)
3. Search YouTube for "how to install / setup / use [project]"
4. Fetch transcript + metadata from best matching video
5. Generate step-by-step HTML blog post
6. Update blog index page
7. Log everything for tracking
"""

import json
import os
import re
import subprocess
import sys
import html
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
POSTS_DIR   = BASE_DIR / "posts"
DATA_DIR    = BASE_DIR / "data"
LOG_FILE    = DATA_DIR / "log.jsonl"
STATE_FILE  = DATA_DIR / "state.json"
INDEX_FILE  = BASE_DIR / "index.html"
SITE_TITLE  = "AI Trend Daily"
SITE_DESC   = "Daily step-by-step guides for the hottest new AI tools and repos."
SITE_URL    = ""  # Set if you have a domain, e.g. "https://example.com"

# ── Config ──────────────────────────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # optional, raises rate limit
HN_TOPICS    = ["ai", "llm", "gpt", "agent", "model", "ml", "transformer",
                "genai", "rag", "open source", "github", "mcp", "claude",
                "anthropic", "openai", "diffusion", "stable", "langchain",
                "ollama", "huggingface", "copilot", "cursor", "vllm"]

# ── GitHub Trending ─────────────────────────────────────────────────

def github_headers():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AI-Trend-Blog"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def github_search(url):
    """Fetch a GitHub search API URL and return parsed JSON."""
    req = urllib.request.Request(url, headers=github_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  GitHub API error: {e}")
        return {"items": []}


def discover_github_trending():
    """Find trending AI repos: recently created + high stars, and high-star + recently pushed."""
    results = []

    # Query 1: Recently created AI repos (last 45 days) sorted by stars
    cutoff = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")
    q1 = f"topic:ai+created:>{cutoff}&sort=stars&order=desc&per_page=8"
    url1 = f"https://api.github.com/search/repositories?q={q1}"
    data1 = github_search(url1)
    for r in data1.get("items", []):
        results.append({
            "name": r["full_name"],
            "name_simple": r["name"],
            "url": r["html_url"],
            "stars": r["stargazers_count"],
            "description": r.get("description", "") or "",
            "language": r.get("language", "") or "",
            "created_at": r["created_at"][:10],
            "pushed_at": r.get("pushed_at", "")[:10],
            "topics": r.get("topics", []),
            "source": "github_new",
        })

    # Query 2: High-star AI repos recently pushed (active maintenance)
    q2 = f"topic:ai+stars:>5000+pushed:>{cutoff}&sort=stars&order=desc&per_page=8"
    url2 = f"https://api.github.com/search/repositories?q={q2}"
    data2 = github_search(url2)
    for r in data2.get("items", []):
        entry = {
            "name": r["full_name"],
            "name_simple": r["name"],
            "url": r["html_url"],
            "stars": r["stargazers_count"],
            "description": r.get("description", "") or "",
            "language": r.get("language", "") or "",
            "created_at": r["created_at"][:10],
            "pushed_at": r.get("pushed_at", "")[:10],
            "topics": r.get("topics", []),
            "source": "github_active",
        }
        # Dedupe by full_name
        if not any(e["name"] == entry["name"] for e in results):
            results.append(entry)

    # Query 3: LLM/agent-specific repos (broader topics)
    q3 = f"topic:llm+created:>{cutoff}&sort=stars&order=desc&per_page=5"
    url3 = f"https://api.github.com/search/repositories?q={q3}"
    data3 = github_search(url3)
    for r in data3.get("items", []):
        entry = {
            "name": r["full_name"],
            "name_simple": r["name"],
            "url": r["html_url"],
            "stars": r["stargazers_count"],
            "description": r.get("description", "") or "",
            "language": r.get("language", "") or "",
            "created_at": r["created_at"][:10],
            "pushed_at": r.get("pushed_at", "")[:10],
            "topics": r.get("topics", []),
            "source": "github_llm",
        }
        if not any(e["name"] == entry["name"] for e in results):
            results.append(entry)

    print(f"  GitHub: found {len(results)} trending repos")
    return results


# ── HackerNews Trending ─────────────────────────────────────────────

def discover_hackernews():
    """Fetch top HN stories and filter for AI/tool-related ones."""
    results = []
    try:
        # Get top story IDs
        req = urllib.request.Request(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers={"User-Agent": "AI-Trend-Blog"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            story_ids = json.loads(resp.read().decode("utf-8"))[:40]

        for sid in story_ids[:30]:
            try:
                sreq = urllib.request.Request(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    headers={"User-Agent": "AI-Trend-Blog"}
                )
                with urllib.request.urlopen(sreq, timeout=5) as sresp:
                    story = json.loads(sresp.read().decode("utf-8"))
                if not story:
                    continue
                title = story.get("title", "").lower()
                # Check if AI-related
                if not any(kw in title for kw in HN_TOPICS):
                    continue
                results.append({
                    "name": story.get("title", ""),
                    "name_simple": story.get("title", ""),
                    "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "stars": story.get("score", 0),  # Using HN score as "stars"
                    "description": story.get("title", ""),
                    "language": "",
                    "created_at": "",
                    "pushed_at": "",
                    "topics": ["hackernews"],
                    "source": "hackernews",
                    "hn_score": story.get("score", 0),
                    "hn_id": sid,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"  HN API error: {e}")

    print(f"  HackerNews: found {len(results)} AI-related stories")
    return results


# ── Topic Selection ──────────────────────────────────────────────────

def pick_topic(all_candidates, already_blogged):
    """
    Pick one topic to blog about today.
    Criteria:
      - Not already blogged
      - Prefer newer repos (GitHub new) with high star velocity
      - Also consider HN trending
      - Prefer topics that look "how-to-able" (have install/setup/usage)
    """
    # Filter out already blogged
    fresh = [c for c in all_candidates if c["name"] not in already_blogged]
    if not fresh:
        # Allow re-blogging if everything is done, but pick least recently done
        fresh = all_candidates
        if not fresh:
            return None

    # Score each candidate:
    #   - GitHub new repos: stars (higher = more trendy)
    #   - GitHub active repos: stars but slight penalty since less "new"
    #   - HN stories: HN score
    # Also boost if the description mentions "install", "setup", "use", "getting started"

    def score_candidate(c):
        score = 0
        if c["source"].startswith("github"):
            score = c.get("stars", 0)
            # New repos get a boost
            if c["source"] == "github_new":
                score = int(score * 1.3)
            # Boost if has install/setup/usage keywords in description
            desc = c.get("description", "").lower()
            if any(kw in desc for kw in ["install", "setup", "set up", "getting started", "quickstart", "usage"]):
                score = int(score * 1.2)
        elif c["source"] == "hackernews":
            score = c.get("hn_score", 0) * 500  # Scale up HN score to compete with star counts
        return score

    fresh.sort(key=score_candidate, reverse=True)
    return fresh[0] if fresh else None


# ── YouTube Search ──────────────────────────────────────────────────

def search_youtube(query, max_results=8):
    """Search YouTube via yt-dlp flat-playlist and return video metadata."""
    search_url = f"ytsearch{max_results}:{query}"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--print", "%(id)s|||%(title)s|||%(duration)s|||%(channel)s|||%(view_count)s|||%(upload_date)s",
                "--no-warning",
                search_url,
            ],
            capture_output=True, text=True, timeout=90
        )
    except Exception as e:
        print(f"  yt-dlp search error: {e}")
        return []

    videos = []
    if result.returncode != 0:
        print(f"  yt-dlp search error: {result.stderr[:300]}")
        return videos
    for line in result.stdout.strip().split("\n"):
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) < 6:
            continue
        vid_id, title, duration, channel, view_count, upload_date = parts
        try:
            dur = int(duration) if duration and duration != "NA" else 0
        except ValueError:
            dur = 0
        if dur < 60:
            continue
        videos.append({
            "id": vid_id,
            "title": title,
            "duration": dur,
            "channel": channel,
            "view_count": int(view_count) if view_count and view_count != "NA" else 0,
            "upload_date": upload_date if upload_date and upload_date != "NA" else "",
            "url": f"https://www.youtube.com/watch?v={vid_id}",
        })
    return videos


def find_best_video(topic, videos):
    """
    Pick the best video for a topic.
    Prefer:
      - Videos with "install", "setup", "tutorial", "how to", "guide" in title
      - Higher view count
      - Reasonable duration (2-20 min ideal)
    """
    if not videos:
        return None

    def score_video(v):
        score = v.get("view_count", 0)
        title_lower = v["title"].lower()

        # Boost for tutorial keywords in title
        for kw in ["install", "setup", "set up", "tutorial", "how to", "guide", "getting started", "step by step"]:
            if kw in title_lower:
                score = int(score * 1.5)
                break

        # Penalty for videos that are too long (>45 min) or too short (<2 min)
        dur = v.get("duration", 0)
        if dur > 2700:
            score = int(score * 0.7)
        if dur < 120:
            score = int(score * 0.5)

        # Boost for videos mentioning the topic name
        topic_lower = topic.lower()
        if topic_lower in title_lower:
            score = int(score * 1.3)

        return score

    videos.sort(key=score_video, reverse=True)
    return videos[0]


# ── Transcript Fetching ──────────────────────────────────────────────

def fetch_transcript(video_id, languages=None):
    """Fetch transcript via youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.fetch(video_id, languages=languages or ['en', 'en-US'])
        entries = []
        for entry in transcript_list.snippets:
            entries.append({
                "text": entry.text.strip(),
                "start": round(entry.start, 1),
                "duration": round(entry.duration, 2) if entry.duration else 0,
            })
        return entries
    except Exception:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.fetch(video_id)
            entries = []
            for entry in transcript_list.snippets:
                entries.append({
                    "text": entry.text.strip(),
                    "start": round(entry.start, 1),
                    "duration": round(entry.duration, 2) if entry.duration else 0,
                })
            return entries
        except Exception as e2:
            print(f"  Transcript fetch failed: {e2}")
            return []


def fetch_full_metadata(video_id):
    """Fetch full video metadata (description, tags, etc.) via yt-dlp."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--print", "%(id)s|||%(title)s|||%(description)s|||%(channel)s|||%(channel_url)s|||%(view_count)s|||%(like_count)s|||%(upload_date)s|||%(duration)s|||%(categories)s|||%(tags)s",
                "--no-warning",
                "--skip-download",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, timeout=90
        )
    except Exception as e:
        print(f"  yt-dlp metadata error: {e}")
        return {}

    if result.returncode != 0 or not result.stdout.strip():
        return {}
    parts = result.stdout.strip().split("|||")
    if len(parts) < 11:
        return {}
    return {
        "id": parts[0],
        "title": parts[1],
        "description": parts[2] if parts[2] != "NA" else "",
        "channel": parts[3] if parts[3] != "NA" else "",
        "channel_url": parts[4] if parts[4] != "NA" else "",
        "view_count": int(parts[5]) if parts[5] and parts[5] != "NA" else 0,
        "like_count": int(parts[6]) if parts[6] and parts[6] != "NA" else 0,
        "upload_date": parts[7] if parts[7] != "NA" else "",
        "duration": int(parts[8]) if parts[8] and parts[8] != "NA" else 0,
        "categories": parts[9] if parts[9] != "NA" else "",
        "tags": parts[10] if parts[10] != "NA" else "",
    }


# ── Transcript to Steps ──────────────────────────────────────────────

def transcript_to_steps(transcript_entries):
    """
    Convert raw transcript entries into a numbered list of step-like chunks.
    Groups transcript segments by natural pauses, then splits on step indicators.
    """
    if not transcript_entries:
        return []

    # Concatenate all text with timestamp markers
    segments = []
    current_text = []
    current_start = transcript_entries[0]["start"]
    last_start = current_start

    for entry in transcript_entries:
        if entry["start"] - last_start > 2.5 and current_text:
            segments.append({
                "start": current_start,
                "text": " ".join(current_text)
            })
            current_text = []
            current_start = entry["start"]
        current_text.append(entry["text"])
        last_start = entry["start"]

    if current_text:
        segments.append({
            "start": current_start,
            "text": " ".join(current_text)
        })

    full_text = " ".join(s["text"] for s in segments)

    # Try splitting on "step N" markers first
    step_markers = re.findall(r'step\s+\d+', full_text, re.IGNORECASE)
    if len(step_markers) >= 3:
        _pat = r'^Step\s*\d+:\s*'
        parts = re.split(r'step\s+\d+[.:\-–—\s]*', full_text, flags=re.IGNORECASE)
        steps = []
        for part in parts:
            part = part.strip()
            if len(part) > 10:
                step_text = re.sub(r'\s+', ' ', part)
                if len(step_text) > 350:
                    step_text = step_text[:350].rsplit(" ", 1)[0] + "..."
                steps.append(step_text)
        if len(steps) >= 3:
            return steps[:15]

    # Fallback: split into chunks based on action verbs / sentence boundaries
    action_patterns = [
        r'\b(?:go\s+to|click\s+on|open\s+up|install|download|run|type|create|navigate|select|choose|enter|press|add|set\s+up|configure|build|start|launch|execute|copy|paste|mkdir|cd\s+)\b',
    ]

    # Split on action-verb boundaries
    all_splits = [m.start() for m in re.finditer('|'.join(action_patterns), full_text, re.IGNORECASE)]
    if len(all_splits) >= 3:
        # Build chunks from split points
        split_points = [0] + all_splits + [len(full_text)]
        steps = []
        for i in range(len(split_points) - 1):
            chunk = full_text[split_points[i]:split_points[i+1]].strip()
            chunk = re.sub(r'\s+', ' ', chunk)
            if len(chunk) > 20:
                if len(chunk) > 350:
                    chunk = chunk[:350].rsplit(" ", 1)[0] + "..."
                steps.append(chunk)
            if len(steps) >= 15:
                break
        if len(steps) >= 3:
            return steps

    # Fallback 2: sentence-based chunking (3-4 sentences per step)
    sentences = re.split(r'(?<=[.!?])\s+', full_text)
    steps = []
    current_step_sentences = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        current_step_sentences.append(sentence)
        joined = " ".join(current_step_sentences)
        if len(current_step_sentences) >= 3 or len(joined) > 400:
            step_text = re.sub(r'\s+', ' ', joined).strip()
            if len(step_text) > 350:
                step_text = step_text[:350].rsplit(" ", 1)[0] + "..."
            steps.append(step_text)
            current_step_sentences = []

    if current_step_sentences:
        step_text = re.sub(r'\s+', ' ', " ".join(current_step_sentences)).strip()
        if len(step_text) > 350:
            step_text = step_text[:350].rsplit(" ", 1)[0] + "..."
        steps.append(step_text)

    # Fallback 3: use segments as steps
    if len(steps) < 3:
        steps = []
        for seg in segments:
            text = re.sub(r'\s+', ' ', seg["text"]).strip()
            if len(text) > 30:
                if len(text) > 350:
                    text = text[:350].rsplit(" ", 1)[0] + "..."
                steps.append(text)
            if len(steps) >= 7:
                break

    return steps[:15]


# ── Formatting ───────────────────────────────────────────────────────

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def format_date(date_str):
    if not date_str or len(date_str) != 8:
        return ""
    try:
        d = datetime.strptime(date_str, "%Y%m%d")
        return d.strftime("%B %d, %Y")
    except ValueError:
        return date_str


def format_count(count):
    if not count:
        return "0"
    return f"{count:,}"


def format_stars(stars):
    if stars >= 1000:
        return f"{stars/1000:.1f}k"
    return str(stars)


# ── HTML Generation ──────────────────────────────────────────────────

def generate_html_post(topic, video, meta, transcript, steps):
    """Generate an HTML blog post file."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_display = datetime.now().strftime("%B %d, %Y")

    title = html.escape(video["title"])
    channel = html.escape(video.get("channel", ""))
    topic_name = html.escape(topic["name"])
    topic_desc = html.escape(topic.get("description", "") or "")
    topic_url = topic.get("url", "")
    topic_stars = topic.get("stars", 0)
    topic_source = topic.get("source", "")

    # Build steps HTML
    steps_html = ""
    for step in steps:
        step_esc = html.escape(step)
        steps_html += f"""        <li>
          <div class="step-content">
            <p>{step_esc}</p>
          </div>
        </li>\n"""

    upload_date = format_date(meta.get("upload_date", "")) if meta else ""
    view_count = format_count(meta.get("view_count", video.get("view_count", 0))) if meta else format_count(video.get("view_count", 0))
    like_count = format_count(meta.get("like_count", 0)) if meta else "N/A"
    duration = format_duration(meta.get("duration", video.get("duration", 0))) if meta else format_duration(video.get("duration", 0))

    # Tags
    tags_str = meta.get("tags", "") if meta else ""
    tags_html = ""
    if tags_str and tags_str != "NA":
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()][:8]
        for tag in tag_list:
            tags_html += f'      <span class="tag">{html.escape(tag)}</span>\n'

    # GitHub/HN info section
    source_html = ""
    if topic_source.startswith("github"):
        source_label = "Repository"
        source_stars_label = f'{format_count(topic_stars)} stars'
    elif topic_source == "hackernews":
        source_label = "HackerNews Story"
        source_stars_label = f'HN Score: {topic.get("hn_score", 0)}'
    else:
        source_label = "Source"
        source_stars_label = ""

    source_html = f"""      <div class="topic-source">
        <h3>Trending Project</h3>
        <p><strong>{source_label}:</strong> <a href="{topic_url}" target="_blank" rel="noopener">{topic_name}</a></p>
        <p><strong>Stars/Score:</strong> {source_stars_label}</p>
        <p><strong>Description:</strong> {topic_desc}</p>
      </div>
"""

    post_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Step-by-Step Guide</title>
  <meta name="description" content="A step-by-step guide for {topic_name} based on the YouTube tutorial '{title}' by {channel}."/>
  <meta property="og:title" content="{title} — Step-by-Step Guide"/>
  <meta property="og:description" content="Step-by-step guide generated from {channel}'s YouTube tutorial."/>
  <meta property="og:type" content="article"/>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header class="site-header">
    <div class="container">
      <a href="../index.html" class="logo">{SITE_TITLE}</a>
      <nav>
        <a href="../index.html">Home</a>
      </nav>
    </div>
  </header>

  <article class="post">
    <div class="container">
      <div class="post-header">
        <span class="post-category">{topic_name}</span>
        <h1>{title}</h1>
        <div class="post-meta">
          <span class="post-date">{date_display}</span>
          <span class="sep">·</span>
          <span class="post-author">Based on video by {channel}</span>
          <span class="sep">·</span>
          <span class="post-duration">{duration}</span>
        </div>
      </div>

      <div class="post-intro">
        <p>This step-by-step guide was generated from the YouTube tutorial <a href="{video['url']}" target="_blank" rel="noopener">"{title}" by {channel}</a>. The video has {view_count} views and was published on {upload_date or 'YouTube'}.</p>
        <p class="trending-note">🔥 Trending now: <a href="{topic_url}" target="_blank" rel="noopener">{topic_name}</a> — {topic_desc[:120]}</p>
        <div class="video-embed">
          <iframe src="https://www.youtube.com/embed/{video['id']}" frameborder="0" allowfullscreen loading="lazy" class="video-frame"></iframe>
        </div>
      </div>

      <h2 class="steps-title">Step-by-Step Instructions</h2>
      <ol class="steps">
{steps_html}      </ol>

{source_html}
"""
    if tags_html:
        post_html += f"""
      <div class="post-tags">
        <h3>Tags</h3>
        <div class="tags">
{tags_html}        </div>
      </div>
"""
    post_html += f"""
      <div class="post-source">
        <h3>Source Video</h3>
        <p><strong>Channel:</strong> <a href="{meta.get('channel_url', '#')}" target="_blank" rel="noopener">{channel}</a></p>
        <p><strong>Views:</strong> {view_count}</p>
        <p><strong>Likes:</strong> {like_count}</p>
        <p><strong>Published:</strong> {upload_date or 'N/A'}</p>
        <p><strong>Watch on YouTube:</strong> <a href="{video['url']}" target="_blank" rel="noopener">{video['url']}</a></p>
      </div>

      <div class="post-disclaimer">
        <p>This guide was auto-generated from the video's transcript. Always refer to the <a href="{video['url']}" target="_blank" rel="noopener">original video</a> for the most accurate and up-to-date instructions.</p>
      </div>
    </div>
  </article>

  <footer class="site-footer">
    <div class="container">
      <p>&copy; {datetime.now().year} {SITE_TITLE}. Generated from YouTube tutorials.</p>
    </div>
  </footer>
</body>
</html>
"""
    return post_html, today_str


def generate_index_html(posts_info):
    """Generate/update the index.html listing all posts."""
    posts_html = ""
    for post in sorted(posts_info, key=lambda p: p["date"], reverse=True):
        post_file = post["file"]
        post_path = f"posts/{post_file}" if not post_file.startswith("posts/") else post_file
        posts_html += f"""      <article class="post-card">
        <span class="post-card-category">{html.escape(post['category'])}</span>
        <h2><a href="{post_path}">{html.escape(post['title'])}</a></h2>
        <div class="post-card-meta">
          <span>{post['date_display']}</span>
          <span class="sep">·</span>
          <span>{html.escape(post['channel'])}</span>
        </div>
        <p class="post-card-desc">{html.escape(post.get('description', '')[:150])}</p>
        <a href="{post_path}" class="read-more">Read the guide &rarr;</a>
      </article>
"""

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{SITE_TITLE} — {SITE_DESC}</title>
  <meta name="description" content="{SITE_DESC}"/>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="site-header">
    <div class="container">
      <a href="index.html" class="logo">{SITE_TITLE}</a>
      <nav>
        <a href="index.html">Home</a>
      </nav>
    </div>
  </header>

  <section class="hero">
    <div class="container">
      <h1>{SITE_TITLE}</h1>
      <p class="hero-desc">{SITE_DESC}</p>
      <p class="hero-sub">Every day, a new step-by-step guide for the hottest AI tools and repos trending on GitHub and HackerNews.</p>
    </div>
  </section>

  <main class="container">
    <h2 class="section-title">Latest Guides</h2>
    <div class="post-grid">
{posts_html}    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <p>&copy; {datetime.now().year} {SITE_TITLE}. Generated from YouTube tutorials.</p>
    </div>
  </footer>
</body>
</html>
"""
    return index_html


def generate_css():
    """Generate the blog stylesheet."""
    return """/* AI Trend Daily Blog - Stylesheet */
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface-hover: #222631;
  --text: #e4e4e7;
  --text-dim: #9ca3af;
  --accent: #6366f1;
  --accent-hover: #818cf8;
  --border: #2d3142;
  --radius: 12px;
  --max-width: 800px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
}

.container { max-width: var(--max-width); margin: 0 auto; padding: 0 24px; }

/* Header */
.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 16px 0;
  position: sticky;
  top: 0;
  z-index: 100;
}
.site-header .container { display: flex; justify-content: space-between; align-items: center; }
.logo { font-size: 1.3rem; font-weight: 700; color: var(--text); text-decoration: none; }
.site-header nav a { color: var(--text-dim); text-decoration: none; margin-left: 24px; transition: color 0.2s; }
.site-header nav a:hover { color: var(--accent-hover); }

/* Hero */
.hero { padding: 60px 0 40px; text-align: center; }
.hero h1 { font-size: 2.5rem; font-weight: 800; margin-bottom: 12px; }
.hero-desc { font-size: 1.2rem; color: var(--text-dim); margin-bottom: 8px; }
.hero-sub { font-size: 0.95rem; color: var(--text-dim); }

/* Post grid */
.section-title { font-size: 1.5rem; margin: 40px  0 24px; }
.post-grid { display: flex; flex-direction: column; gap: 24px; padding-bottom: 60px; }

.post-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  transition: border-color 0.2s, background 0.2s;
}
.post-card:hover { border-color: var(--accent); background: var(--surface-hover); }
.post-card-category {
  display: inline-block;
  background: rgba(99,102,241,0.15);
  color: var(--accent-hover);
  font-size: 0.8rem;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 20px;
  margin-bottom: 12px;
}
.post-card h2 { font-size: 1.25rem; margin-bottom: 8px; }
.post-card h2 a { color: var(--text); text-decoration: none; }
.post-card h2 a:hover { color: var(--accent-hover); }
.post-card-meta { font-size: 0.85rem; color: var(--text-dim); margin-bottom: 12px; }
.post-card-meta .sep { margin: 0 8px; }
.post-card-desc { color: var(--text-dim); font-size: 0.95rem; margin-bottom: 16px; }
.read-more { color: var(--accent-hover); text-decoration: none; font-weight: 600; font-size: 0.95rem; }
.read-more:hover { text-decoration: underline; }

/* Single post */
.post { padding: 40px 0 60px; }
.post-header { margin-bottom: 32px; }
.post-category {
  display: inline-block;
  background: rgba(99,102,241,0.15);
  color: var(--accent-hover);
  font-size: 0.85rem;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 20px;
  margin-bottom: 16px;
}
.post-header h1 { font-size: 2rem; line-height: 1.3; margin-bottom: 12px; }
.post-meta { font-size: 0.9rem; color: var(--text-dim); }
.post-meta .sep { margin: 0 8px; }

.post-intro { margin-bottom: 40px; }
.post-intro p { margin-bottom: 16px; color: var(--text-dim); }
.post-intro a { color: var(--accent-hover); text-decoration: none; }
.post-intro a:hover { text-decoration: underline; }

.trending-note {
  background: rgba(99,102,241,0.08);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 0.9rem;
}
.trending-note a { color: var(--accent-hover); }

.video-embed { margin: 24px 0; }
.video-frame { width: 100%; aspect-ratio: 16/9; border-radius: var(--radius); border: none; }

.steps-title { font-size: 1.5rem; margin-bottom: 24px; border-bottom: 1px solid var(--border); padding-bottom: 12px; }
.steps { list-style: none; counter-reset: step-counter; margin-bottom: 40px; }
.steps li {
  counter-increment: step-counter;
  position: relative;
  padding: 20px 20px 20px 64px;
  margin-bottom: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transition: border-color 0.2s;
}
.steps li:hover { border-color: var(--accent); }
.steps li::before {
  content: counter(step-counter);
  position: absolute;
  left: 20px;
  top: 20px;
  width: 32px;
  height: 32px;
  background: var(--accent);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1rem;
}
.step-content p { margin: 0; }

.topic-source, .post-source {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 24px;
}
.topic-source h3, .post-source h3 { font-size: 1.1rem; margin-bottom: 16px; }
.topic-source p, .post-source p { margin-bottom: 8px; color: var(--text-dim); font-size: 0.95rem; }
.topic-source strong, .post-source strong { color: var(--text); }
.topic-source a, .post-source a { color: var(--accent-hover); text-decoration: none; }
.topic-source a:hover, .post-source a:hover { text-decoration: underline; }

.post-tags { margin-bottom: 24px; }
.post-tags h3 { font-size: 1.1rem; margin-bottom: 12px; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; }
.tag {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-size: 0.85rem;
  padding: 4px 12px;
  border-radius: 20px;
}

.post-disclaimer {
  background: rgba(99,102,241,0.05);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  font-size: 0.85rem;
  color: var(--text-dim);
}
.post-disclaimer a { color: var(--accent-hover); text-decoration: none; }

/* Footer */
.site-footer { border-top: 1px solid var(--border); padding: 32px 0; }
.site-footer p { color: var(--text-dim); font-size: 0.85rem; text-align: center; }

/* Mobile */
@media (max-width: 600px) {
  .hero h1 { font-size: 1.8rem; }
  .post-header h1 { font-size: 1.4rem; }
  .steps li { padding-left: 56px; }
  .steps li::before { width: 28px; height: 28px; font-size: 0.85rem; }
}
"""


# ── Blog State ──────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"blogged_topics": [], "last_run": ""}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def log_entry(entry):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def scan_existing_posts():
    """Scan posts/ directory for existing post HTML files and extract metadata."""
    posts_info = []
    if not POSTS_DIR.exists():
        return posts_info

    for post_file in sorted(POSTS_DIR.glob("*.html"), reverse=True):
        content = post_file.read_text(encoding="utf-8")
        title_match = re.search(r'<title>(.*?)</title>', content)
        title = title_match.group(1).replace(" — Step-by-Step Guide", "") if title_match else post_file.stem

        cat_match = re.search(r'post-category">(.*?)</span>', content)
        category = cat_match.group(1) if cat_match else ""

        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', post_file.stem)
        date = date_match.group(1) if date_match else ""
        date_display = ""
        if date:
            try:
                d = datetime.strptime(date, "%Y-%m-%d")
                date_display = d.strftime("%B %d, %Y")
            except ValueError:
                pass

        ch_match = re.search(r'Based on video by (.*?)</span>', content)
        channel = ch_match.group(1) if ch_match else ""

        # Extract description from trending-note
        desc_match = re.search(r'trending-note[^>]*>.*?<a[^>]*>[^<]*</a>\s*&mdash;\s*(.*?)</p>', content, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""

        posts_info.append({
            "file": post_file.name,
            "title": title,
            "category": category,
            "date": date,
            "date_display": date_display or date,
            "channel": channel,
            "description": description,
        })
    return posts_info


def check_already_done_today():
    """Check if today's post was already generated."""
    if not LOG_FILE.exists():
        return False
    today_str = datetime.now().strftime("%Y-%m-%d")
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("date") == today_str and entry.get("status") == "success":
                return True
        except json.JSONDecodeError:
            continue
    return False


# ── Main Pipeline ───────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  AI Trend Daily Blog Generator")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Check if already done today
    if check_already_done_today():
        print("Today's post was already generated. Skipping.")
        return

    # 1. Discover trending topics
    print("--- Discovering trending AI topics ---")
    print("Fetching from GitHub...")
    github_topics = discover_github_trending()
    print("Fetching from HackerNews...")
    hn_topics = discover_hackernews()

    all_candidates = github_topics + hn_topics
    print(f"\nTotal candidates: {len(all_candidates)}")

    if not all_candidates:
        log_entry({"date": datetime.now().strftime("%Y-%m-%d"), "status": "error", "error": "no topics found"})
        print("ERROR: No trending topics found")
        return

    # 2. Load state and pick a topic
    state = load_state()
    already_blogged = set(state.get("blogged_topics", []))
    topic = pick_topic(all_candidates, already_blogged)

    if not topic:
        log_entry({"date": datetime.now().strftime("%Y-%m-%d"), "status": "error", "error": "no fresh topic"})
        print("ERROR: No fresh topic to blog about")
        return

    print(f"\n--- Selected topic: {topic['name']} ---")
    print(f"  Source: {topic['source']}")
    print(f"  Stars/Score: {topic.get('stars', 0)}")
    print(f"  Description: {topic.get('description', '')[:100]}")
    print()

    # 3. Search YouTube for tutorial videos
    # Build search query from project name
    search_query = f"how to install setup {topic['name_simple']}"
    print(f"Searching YouTube: \"{search_query}\"")
    videos = search_youtube(search_query, max_results=8)
    print(f"Found {len(videos)} videos")

    # If no results with install query, try broader search
    if not videos:
        search_query = f"{topic['name_simple']} tutorial setup"
        print(f"Trying broader search: \"{search_query}\"")
        videos = search_youtube(search_query, max_results=8)
        print(f"Found {len(videos)} videos")

    # Also try with the full repo name
    if not videos:
        search_query = f"{topic['name']} tutorial"
        print(f"Trying with full name: \"{search_query}\"")
        videos = search_youtube(search_query, max_results=8)
        print(f"Found {len(videos)} videos")

    if not videos:
        log_entry({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "error",
            "error": "no YouTube videos found",
            "topic": topic["name"],
        })
        print("ERROR: No YouTube videos found for this topic")
        return

    # 4. Pick best video
    selected_video = find_best_video(topic["name_simple"], videos)
    print(f"Selected: \"{selected_video['title']}\" by {selected_video['channel']} ({selected_video['view_count']:,} views)")

    # 5. Fetch transcript
    print("\nFetching transcript...")
    transcript = fetch_transcript(selected_video["id"])
    print(f"Got {len(transcript)} transcript entries")

    # If no transcript, try next best videos
    if not transcript:
        for v in videos:
            if v["id"] == selected_video["id"]:
                continue
            print(f"  Trying next video: {v['title']}")
            transcript = fetch_transcript(v["id"])
            if transcript:
                selected_video = v
                print(f"  Got {len(transcript)} entries from fallback")
                break

    # 6. Fetch full metadata
    print("\nFetching full video metadata...")
    meta = fetch_full_metadata(selected_video["id"])
    if meta:
        print(f"  Description: {len(meta.get('description', ''))} chars")
        print(f"  Likes: {meta.get('like_count', 'N/A')}")

    # 7. Generate steps from transcript
    print("\nGenerating step-by-step instructions...")
    steps = transcript_to_steps(transcript)
    print(f"Generated {len(steps)} steps")

    if not steps and transcript:
        full_text = " ".join(e["text"] for e in transcript[:20])
        steps = [full_text[:350]]
    elif not steps and not transcript:
        desc = meta.get("description", "") if meta else ""
        if desc:
            steps = [f"Watch the video for installation instructions: {desc[:350]}"]
        else:
            steps = ["Unable to extract steps. Please watch the embedded video for detailed instructions."]

    # 8. Generate HTML post
    print("\nGenerating HTML blog post...")
    post_html, date_str = generate_html_post(topic, selected_video, meta, transcript, steps)

    # Save post
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[^a-z0-9]+', '-', topic["name_simple"].lower()).strip('-')[:50]
    if not safe_name:
        safe_name = "trending-ai-tool"
    post_filename = f"{datetime.now().strftime('%Y-%m-%d')}-{safe_name}.html"
    post_path = POSTS_DIR / post_filename
    post_path.write_text(post_html, encoding="utf-8")
    print(f"Saved: {post_path}")

    # 9. Update state
    state["blogged_topics"].append(topic["name"])
    state["blogged_topics"] = state["blogged_topics"][-100:]
    state["last_run"] = datetime.now().isoformat()
    save_state(state)

    # 10. Update index.html
    print("\nUpdating index.html...")
    posts_info = scan_existing_posts()
    index_html = generate_index_html(posts_info)
    INDEX_FILE.write_text(index_html, encoding="utf-8")
    print(f"Updated: {INDEX_FILE}")

    # 11. Generate CSS if missing
    css_path = BASE_DIR / "style.css"
    if not css_path.exists():
        css_path.write_text(generate_css(), encoding="utf-8")
        print(f"Created: {css_path}")

    # 12. Log success
    log_entry({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic["name"],
        "topic_source": topic["source"],
        "topic_stars": topic.get("stars", 0),
        "video_id": selected_video["id"],
        "video_title": selected_video["title"],
        "channel": selected_video.get("channel", ""),
        "view_count": selected_video.get("view_count", 0),
        "transcript_entries": len(transcript),
        "steps_generated": len(steps),
        "post_file": post_filename,
        "status": "success"
    })

    print()
    print("=" * 60)
    print(f"  DONE! Post saved to posts/{post_filename}")
    print(f"  Blog index updated: {INDEX_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()