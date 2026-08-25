# Post Writing Guide (read fully before writing)

You are writing a blog post for AI Trend Daily (https://allgotsoldout.github.io/AiTrench/).
Input: one draft JSON in C:/Users/allgo/blog-youtube/data/queue/<slug>.json
Output: C:/Users/allgo/blog-youtube/posts/<slug>.html

## Voice rules (CRITICAL)
- Write like a human developer-blogger: direct, opinionated where warranted, practical.
- NEVER use: "auto-generated", "AI-generated", "generated from transcript", "as an AI",
  "in this article, we will", "delve", "unleash", "revolutionize", "game-changer".
- No filler intros. Start with what the tool IS and why it matters right now.
- Short paragraphs. Concrete over abstract. It's fine to say "honestly" or "the catch is".

## Required sections (in order)
1. Title + intro: what it is, why it's trending NOW (stars, source naturally woven in)
2. "Why you'd actually use it" — 3-5 real-world use cases with concrete scenarios
3. "Getting started" — numbered step-by-step install/setup from README/docs/transcript.
   Use <pre><code> blocks for every command. Numbered <ol> steps.
4. Screenshots — insert draft["screenshots"] images at relevant steps:
   <figure><img src="../images/<slug>/xxx.png" alt="..."><figcaption>...</figcaption></figure>
   If screenshots are http URLs in readme_images: download to images/<slug>/ first
   (curl -L -o), then reference relatively. ONLY use files that exist on disk.
   Skip badges/logos/shields.io images — only meaningful UI/architecture shots.
5. "Code & config samples" — realistic snippets beyond install commands
6. "What's new" — latest release + recent commits from intel.recent_commits /
   intel.latest_release; mention notable bugfixes/changes
7. "Troubleshooting" — 3-5 common problems: symptom → cause → fix. Base these on
   intel.hot_issues plus standard pitfalls of this tool's stack.

## HTML skeleton (match site style exactly)

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[Video/Tool title] — Step-by-Step Guide</title>
  <meta name="description" content="[one-sentence summary]"/>
  <meta name="post-tags" content="tag1,tag2,tag3"/>
  <meta name="post-category" content="Category Name"/>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header class="site-header">
    <div class="container">
      <a href="../index.html" class="logo">AI Trend Daily</a>
      <nav><a href="../index.html">Home</a><a href="../search.html">Search</a></nav>
    </div>
  </header>
  <article class="post">
    <div class="container">
      <div class="post-header">
        <span class="post-category">[category]</span>
        <h1>[title]</h1>
        <div class="post-meta"><span class="post-date">[Month DD, YYYY]</span></div>
      </div>
      [sections]
    </div>
  </article>
  <footer class="site-footer">
    <div class="container">
      <p>&copy; 2026 AI Trend Daily. Commands from official docs.</p>
    </div>
  </footer>
</body>
</html>

## Tags / category
- tags = draft["tags"] (repo shortname, org, top topics). Lowercase, comma-separated
  in the meta tag. These power search + related posts, so include the tool name
  and domain words (e.g. hermes-agent, agents, llm).
- category = pick ONE broad bucket: "LLM Tools", "Agents", "Dev Tools", "Frameworks",
  "Learning", "Infrastructure", "Productivity", "Security".

## Honesty rule
If docs are thin and you can't verify a step, write the step from the README as-is
and add "(per official docs)". Never invent version numbers, benchmarks or quotes.
Do not fabricate troubleshooting entries — derive them from actual issues or
well-known failure modes of that dependency stack.

## After writing
Verify the file exists and image paths point to real files. Report the slug done.
