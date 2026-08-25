#!/usr/bin/env python3
"""
Rebuild index.html + search.html from posts/ metadata.
Each post carries tags in a <meta name="post-tags"> tag and category
in <meta name="post-category">. Search is client-side over search-data.js.
"""
import json
import re
import html
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
POSTS = BASE / "posts"


def post_meta(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    def meta(name, default=""):
        m = re.search(rf'<meta name="{name}" content="([^"]*)"', text)
        return html.unescape(m.group(1)) if m else default
    m = re.search(r"<title>([^<]+)</title>", text)
    title = html.unescape(m.group(1)).split("—")[0].strip() if m else path.stem
    # derive date from filename
    dm = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    date = dm.group(1) if dm else ""
    return {
        "file": f"posts/{path.name}",
        "title": title,
        "tags": [t for t in meta("post-tags").split(",") if t],
        "category": meta("post-category", "Guide"),
        "description": meta("description")[:160],
        "date": date,
    }


def main():
    metas = sorted((post_meta(p) for p in POSTS.glob("*.html")),
                   key=lambda m: m["date"], reverse=True)

    # search-data.js (client-side index)
    data_js = "window.POSTS = " + json.dumps(metas, indent=1) + ";"
    (BASE / "search-data.js").write_text(data_js, encoding="utf-8")

    # tag counts
    counts = {}
    for m in metas:
        for t in m["tags"]:
            counts[t.lower()] = counts.get(t.lower(), 0) + 1
    top_tags = sorted(counts.items(), key=lambda x: -x[1])[:24]

    cards = ""
    for m in metas:
        tags_html = "".join(
            f'<a class="tag" href="search.html?q={html.escape(t)}">{html.escape(t)}</a> '
            for t in m["tags"][:5])
        date_disp = datetime.strptime(m["date"], "%Y-%m-%d").strftime("%b %d, %Y") if m["date"] else ""
        cards += f'''      <article class="post-card" data-tags="{' '.join(t.lower() for t in m['tags'])}">
        <span class="post-card-category">{html.escape(m['category'])}</span>
        <h2><a href="{m['file']}">{html.escape(m['title'])}</a></h2>
        <p class="card-desc">{html.escape(m['description'] or '')}</p>
        <div class="card-meta"><span class="post-date">{date_disp}</span></div>
        <div class="card-tags">{tags_html}</div>
      </article>
'''

    tag_chips = "".join(
        f'<a class="tagchip" href="search.html?q={html.escape(t)}">{html.escape(t)} <span>{n}</span></a>'
        for t, n in top_tags)

    index = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Trend Daily — Step-by-step guides for trending AI tools</title>
  <meta name="description" content="Fresh step-by-step guides for the hottest trending AI repos and tools.">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="site-header">
    <div class="container header-inner">
      <a href="index.html" class="logo">AI Trend Daily</a>
      <form class="searchbar" action="search.html" method="get">
        <input type="search" name="q" placeholder="Search guides, tools, tags…" aria-label="Search">
        <button type="submit">Search</button>
      </form>
      <nav><a href="index.html">Home</a><a href="search.html">Browse tags</a></nav>
    </div>
  </header>

  <main class="container">
    <section class="hero">
      <h1>Guides for what's trending in AI — today.</h1>
      <p>Step-by-step install &amp; setup walkthroughs, use cases, code samples and troubleshooting, updated daily from the trending repos everyone's talking about.</p>
      <div class="tagcloud">{tag_chips}</div>
    </section>

    <h2 class="section-title">Latest guides</h2>
    <section class="post-grid">
{cards}    </section>
  </main>

  <footer class="site-footer">
    <div class="container">
      <p>&copy; {datetime.now().year} AI Trend Daily. Commands from official docs.</p>
    </div>
  </footer>
</body>
</html>
'''
    (BASE / "index.html").write_text(index, encoding="utf-8")

    search_page = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Search — AI Trend Daily</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="site-header">
    <div class="container header-inner">
      <a href="index.html" class="logo">AI Trend Daily</a>
      <form class="searchbar" action="search.html" method="get">
        <input type="search" id="q" name="q" placeholder="Search guides, tools, tags…" autofocus>
        <button type="submit">Search</button>
      </form>
      <nav><a href="index.html">Home</a></nav>
    </div>
  </header>
  <main class="container">
    <div id="taglist" class="tagcloud"></div>
    <h2 class="section-title" id="results-title">All guides</h2>
    <section class="post-grid" id="results"></section>
    <p id="noresults" hidden>No guides found — try another term.</p>
  </main>
  <script src="search-data.js"></script>
  <script>
    function card(p){
      var tags=(p.tags||[]).slice(0,6).map(function(t){
        return '<a class="tag" href="search.html?q='+encodeURIComponent(t)+'">'+t+'</a>';}).join(' ');
      return '<article class="post-card"><span class="post-card-category">'+(p.category||'')+
        '</span><h2><a href="'+p.file+'">'+p.title+'</a></h2><p class="card-desc">'+
        (p.description||'')+'</p><div class="card-meta">'+p.date+'</div><div class="card-tags">'+
        tags+'</div></article>';
    }
    function render(){
      var q=(new URLSearchParams(location.search).get('q')||'').trim().toLowerCase();
      var box=document.getElementById('results');
      var list=window.POSTS||[];
      if(q){ list=list.filter(function(p){
        return (p.title+' '+p.description+' '+(p.tags||[]).join(' ')+' '+p.category).toLowerCase().indexOf(q)>=0;});}
      document.getElementById('results-title').textContent =
        q ? ('Results for "'+q+'" ('+list.length+')') : ('All guides ('+list.length+')');
      box.innerHTML=list.map(card).join('');
      document.getElementById('noresults').hidden = list.length>0;
      document.getElementById('q').value=q;
      // popular tag cloud
      var counts={};(window.POSTS||[]).forEach(function(p){(p.tags||[]).forEach(function(t){
        counts[t.toLowerCase()]=(counts[t.toLowerCase()]||0)+1;});});
      var top=Object.keys(counts).sort(function(a,b){return counts[b]-counts[a];}).slice(0,24);
      document.getElementById('taglist').innerHTML=top.map(function(t){
        return '<a class="tagchip" href="?q='+encodeURIComponent(t)+'">'+t+' <span>'+counts[t]+'</span></a>';}).join('');
    }
    render();
  </script>
</body>
</html>
'''
    (BASE / "search.html").write_text(search_page, encoding="utf-8")
    print(f"Index rebuilt: {len(metas)} posts")


if __name__ == "__main__":
    main()
