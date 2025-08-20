from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List
import urllib.parse

import httpx

# Ensure a headless-friendly backend for matplotlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Guard BeautifulSoup import (bs4)
try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except Exception:
    BeautifulSoup = None  # type: ignore
    _HAS_BS4 = False


# --------- Memory ----------------------------------------------------------------

@dataclass
class Memory:
    workflows: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def create(self, workflow_id: str, question: str) -> None:
        self.workflows[workflow_id] = {
            "question": question,
            "steps": [],
            "artifacts": {},
            "started_at": time.time(),
        }

    def add_step(self, workflow_id: str, name: str, result: Any) -> None:
        wf = self.workflows[workflow_id]
        wf["steps"].append({"name": name, "timestamp": time.time()})
        wf["artifacts"][name] = result

    def get(self, workflow_id: str) -> Dict[str, Any]:
        return self.workflows[workflow_id]


memory = Memory()


# --------- Core Tools ------------------------------------------------------------

async def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    if not _HAS_BS4:
        raise RuntimeError("beautifulsoup4 is required for web_search/web_scrape. Please `pip install beautifulsoup4`.")
    # naive DuckDuckGo HTML scraping
    url = f"https://duckduckgo.com/html/?q={query}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    candidates = soup.select("a.result__a") or soup.select("a[data-testid='result-title-a']") or soup.select("a")
    for a in candidates:
        if len(out) >= max_results:
            break
        href = a.get("href") or ""
        if not href:
            continue
        resolved = ""
        if "uddg=" in href:
            # DuckDuckGo redirect links contain the real URL in the 'uddg' query param
            try:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if "uddg" in qs and qs["uddg"]:
                    resolved = urllib.parse.unquote(qs["uddg"][0])
            except Exception:
                resolved = ""
        elif href.startswith("http"):
            resolved = href
        if not resolved or not resolved.startswith("http"):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        title = a.get_text(strip=True) or resolved
        out.append({"title": title, "url": resolved})
    return out


async def web_scrape(url: str, max_chars: int = 4000) -> Dict[str, Any]:
    if not _HAS_BS4:
        raise RuntimeError("beautifulsoup4 is required for web_search/web_scrape. Please `pip install beautifulsoup4`.")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.get_text(strip=True) if getattr(soup, "title", None) else ""
    text = soup.get_text(" ", strip=True)
    text = text[:max_chars]
    return {"title": title, "text": text, "length": len(text)}


def summarize_text(text: str, max_chars: int = 600) -> str:
    text = text.strip()
    return text[: max_chars - 3] + "..." if len(text) > max_chars else text


def make_chart(items: List[Dict[str, Any]]) -> str:
    # items: [{"name": str, "value": number}]
    names = [x["name"] for x in items]
    values = [x["value"] for x in items]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(names, values, color="#4e79a7")
    ax.set_ylabel("Value")
    ax.set_title("Funding Chart")
    fig.tight_layout()
    bio = io.BytesIO()
    fig.savefig(bio, format="png")
    plt.close(fig)
    return base64.b64encode(bio.getvalue()).decode("utf-8")


def build_pdf(markdown_text: str) -> bytes:
    # Lazy-import reportlab to avoid hard import error if missing
    try:
        from reportlab.pdfgen import canvas  # type: ignore
        from reportlab.lib.pagesizes import letter  # type: ignore
    except Exception as e:
        raise RuntimeError("reportlab is required for PDF output. Please `pip install reportlab`.") from e

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    y = height - 72
    for line in markdown_text.splitlines():
        c.drawString(72, y, line[:95])
        y -= 14
        if y < 72:
            c.showPage()
            y = height - 72
    c.showPage()
    c.save()
    return buf.getvalue()


# --------- Planner / Executor ----------------------------------------------------

async def plan_research(question: str) -> Dict[str, Any]:
    # simple linear plan
    return {
        "question": question,
        "steps": [
            {"name": "search", "tool": "web_search"},
            {"name": "scrape", "tool": "web_scrape"},
            {"name": "summarize", "tool": "summarize_text"},
            {"name": "chart", "tool": "make_chart"},
        ],
    }


async def execute_research(workflow_id: str, question: str) -> Dict[str, Any]:
    memory.create(workflow_id, question)
    # 1) search
    results = await web_search(question, max_results=5)
    memory.add_step(workflow_id, "search", results)
    top = results[:3]
    # 2) scrape
    scraped: List[Dict[str, Any]] = []
    for r in top:
        try:
            scraped.append({"url": r["url"], **(await web_scrape(r["url"]))})
        except Exception:
            continue
    memory.add_step(workflow_id, "scrape", scraped)
    # 3) summarize
    combined = "\n\n".join([f"# {s.get('title','')}\n{s.get('text','')}" for s in scraped])
    summary = summarize_text(combined, 1200)
    memory.add_step(workflow_id, "summary", summary)
    # 4) chart (fake numbers for demo)
    chart_png_b64 = make_chart(
        [{"name": f"Co{i+1}", "value": (i+1) * 10} for i in range(min(5, len(scraped) or 5))]
    )
    memory.add_step(workflow_id, "chart", chart_png_b64)
    return memory.get(workflow_id)


def build_report(workflow_id: str, format: str = "markdown") -> Dict[str, Any]:
    wf = memory.get(workflow_id)
    summary = wf["artifacts"].get("summary", "")
    # Prefer scraped page titles/links; fall back to search results if scraping failed
    scraped_items: List[Dict[str, Any]] = wf["artifacts"].get("scrape", []) or []
    searched_items: List[Dict[str, Any]] = wf["artifacts"].get("search", []) or []
    sources: List[tuple[str, str]] = []
    if scraped_items:
        for s in scraped_items:
            url = s.get("url")
            if not url:
                continue
            title = s.get("title") or url
            sources.append((title, url))
    elif searched_items:
        for s in searched_items:
            url = s.get("url")
            if not url:
                continue
            title = s.get("title") or url
            sources.append((title, url))
    chart_b64 = wf["artifacts"].get("chart")
    md = [
        f"# Research Report\n",
        f"**Question:** {wf['question']}\n",
        "## Executive Summary\n",
        summary + "\n",
        "## Sources\n",
    ]
    for title, url in sources:
        md.append(f"- [{title}]({url})")
    if chart_b64:
        md.append("\n## Chart (PNG base64)\n")
        md.append("(embedded as data; render on client)")
    markdown_text = "\n".join(md)
    if format == "pdf":
        pdf_bytes = build_pdf(markdown_text)
        return {"format": "pdf", "content_b64": base64.b64encode(pdf_bytes).decode("utf-8")}
    return {"format": "markdown", "content": markdown_text, "chart_png_b64": chart_b64}
