"""arXiv Radar — fetch new papers, score relevance with a cheap LLM, emit a digest.

Runs daily via GitHub Actions. Requires OPENAI_API_KEY in the environment.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.yaml"
SEEN_PATH = ROOT / "data" / "seen.json"
DIGEST_DIR = ROOT / "digests"

ARXIV_API = "https://export.arxiv.org/api/query"
OPENAI_API = "https://api.openai.com/v1/chat/completions"
ATOM = "{http://www.w3.org/2005/Atom}"

SEEN_CAP = 5000  # keep the seen-IDs file from growing forever


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen():
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    return []


def save_seen(seen):
    SEEN_PATH.parent.mkdir(exist_ok=True)
    SEEN_PATH.write_text(json.dumps(seen[-SEEN_CAP:], indent=0), encoding="utf-8")


def fetch_category(category, max_results):
    """Fetch the most recently submitted papers in one arXiv category."""
    params = urllib.parse.urlencode({
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    })
    req = urllib.request.Request(
        f"{ARXIV_API}?{params}",
        headers={"User-Agent": "arxiv-radar/1.0 (personal research digest)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        tree = ET.fromstring(resp.read())

    papers = []
    for entry in tree.iter(f"{ATOM}entry"):
        raw_id = entry.findtext(f"{ATOM}id", "")
        # http://arxiv.org/abs/2507.01234v1 -> 2507.01234
        arxiv_id = raw_id.rsplit("/", 1)[-1]
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        papers.append({
            "id": arxiv_id,
            "title": " ".join(entry.findtext(f"{ATOM}title", "").split()),
            "abstract": " ".join(entry.findtext(f"{ATOM}summary", "").split()),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "category": category,
            "published": entry.findtext(f"{ATOM}published", ""),
        })
    return papers


def call_llm(model, system, user_text, max_tokens=4096):
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_API,
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "content-type": "application/json",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(15 * (attempt + 1))
                continue
            raise


def parse_json_array(text):
    """Extract a JSON array from an LLM response, tolerating code fences."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array in response: {text[:200]}")
    return json.loads(match.group(0))


def score_batch(papers, config):
    system = (
        "You are a strict research-paper relevance filter. The user's interests:\n"
        f"{config['interests']}\n"
        "For each paper, rate relevance to these interests on a 1-10 scale and give a "
        "one-line reason. Be harsh — the user can only read a handful of papers a day:\n"
        "- 9-10: the paper's MAIN contribution is one of the listed interests; a must-read\n"
        "- 7-8: substantially about a listed interest, worth skimming\n"
        "- 4-6: touches an interest tangentially (e.g. generic LLM/agent work, "
        "adjacent domain, interest mentioned only as an application)\n"
        "- 1-3: unrelated\n"
        "Most papers in a daily feed should score 6 or below. Merely being about LLMs, "
        "agents, retrieval, or vision is NOT enough for a 7+.\n"
        "Respond with ONLY a JSON array, one object per paper, in the same order: "
        '[{"n": <paper number>, "score": <1-10>, "reason": "<one line>"}]'
    )
    lines = []
    for i, p in enumerate(papers, 1):
        lines.append(f"Paper {i}:\nTitle: {p['title']}\nAbstract: {p['abstract']}\n")
    text = call_llm(config["model"], system, "\n".join(lines))
    results = parse_json_array(text)

    scored = []
    by_n = {r["n"]: r for r in results if isinstance(r, dict) and "n" in r}
    for i, p in enumerate(papers, 1):
        r = by_n.get(i)
        if r is None:
            continue
        scored.append({**p, "score": int(r.get("score", 0)), "reason": str(r.get("reason", ""))})
    return scored


def write_digest(relevant, total_new, config):
    today = date.today().isoformat()
    path = DIGEST_DIR / f"{today}.md"
    lines = [
        f"# arXiv digest — {today}",
        "",
        f"Scanned **{total_new}** new papers in {', '.join(config['categories'])}; "
        f"**{len(relevant)}** scored ≥ {config['min_score']}.",
        "",
    ]
    for p in sorted(relevant, key=lambda x: -x["score"]):
        lines += [
            f"### [{p['title']}]({p['url']})",
            f"**Score {p['score']}/10** · `{p['category']}` · {p['id']}",
            "",
            f"> {p['reason']}",
            "",
            f"<details><summary>Abstract</summary>\n\n{p['abstract']}\n\n</details>",
            "",
        ]
    DIGEST_DIR.mkdir(exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    config = load_config()
    seen = load_seen()
    seen_set = set(seen)

    # 1. Fetch recent papers per category (arXiv asks for >=3s between requests)
    all_papers, ids = [], set()
    for cat in config["categories"]:
        for p in fetch_category(cat, config.get("max_results_per_category", 100)):
            if p["id"] not in ids:
                ids.add(p["id"])
                all_papers.append(p)
        time.sleep(3)

    new_papers = [p for p in all_papers if p["id"] not in seen_set]
    print(f"Fetched {len(all_papers)} papers, {len(new_papers)} new.")

    if not new_papers:
        print("Nothing new — no digest written.")
        return

    # 2. Score in batches with the cheap model
    batch_size = config.get("batch_size", 12)
    scored = []
    for i in range(0, len(new_papers), batch_size):
        batch = new_papers[i:i + batch_size]
        try:
            scored += score_batch(batch, config)
        except Exception as e:
            print(f"WARNING: batch {i // batch_size + 1} failed: {e}", file=sys.stderr)
        print(f"Scored {min(i + batch_size, len(new_papers))}/{len(new_papers)}")

    relevant = [p for p in scored if p["score"] >= config["min_score"]]

    # 3. Write digest and update the seen list
    path = write_digest(relevant, len(new_papers), config)
    save_seen(seen + [p["id"] for p in new_papers])
    print(f"Digest written: {path} ({len(relevant)} relevant papers)")

    # Expose for the workflow's issue-creation step
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"digest_path={path.relative_to(ROOT).as_posix()}\n")
            f.write(f"relevant_count={len(relevant)}\n")


if __name__ == "__main__":
    main()
