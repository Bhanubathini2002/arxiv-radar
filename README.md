# 📡 arXiv Radar

**Your personal AI research assistant — reads hundreds of arXiv papers every day, hands you only the ones that matter.**

arXiv publishes **300–500 new AI papers every single day**. Nobody can read that. This bot can.

Every morning, arXiv Radar pulls the newest papers in your chosen categories, has a cheap LLM read every title and abstract, scores each paper against *your* research interests, and delivers a short ranked digest as a GitHub issue — like a personalized research newspaper, built overnight while you sleep.

- ⚙️ **Zero infrastructure** — runs entirely on free GitHub Actions; no servers, laptop can be off
- 💸 **Nearly free** — GPT-4o-mini scores ~300 papers for under $0.05/day
- 🧠 **Personalized** — you describe your interests in plain English; the LLM does the judging
- 📥 **Zero effort** — digests arrive automatically as GitHub issues at 7:30 AM every day

---

## How it works

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  arXiv API   │ ──▶ │  Dedupe filter    │ ──▶ │  GPT-4o-mini scores  │ ──▶ │  Ranked digest    │
│  ~300 new    │     │  skip papers      │     │  each title+abstract │     │  GitHub issue +   │
│  papers/day  │     │  already scored   │     │  1–10 vs interests   │     │  markdown archive │
└─────────────┘     └──────────────────┘     └─────────────────────┘     └──────────────────┘
        ▲                                                                          │
        └────────────────── GitHub Actions cron · daily · free ◀──────────────────┘
```

1. **Fetch** — a scheduled GitHub Actions job queries the [arXiv API](https://info.arxiv.org/help/api/) for the newest papers in your categories
2. **Dedupe** — paper IDs already scored are skipped (tracked in `data/seen.json`, committed back by the bot), so every paper is paid for exactly once — no date math, no weekend gaps
3. **Score** — papers go to GPT-4o-mini in batches of 12 with a strict rubric: *"9–10 = the paper's main contribution is one of your interests; most papers should score 6 or below"*
4. **Deliver** — everything scoring ≥ 8 lands in a ranked digest: committed to [`digests/`](digests/) and opened as a GitHub issue you read like an inbox

## Sample output

> ### [DynaKRAG: A Unified Framework for Learnable Evidence Control in Multi-Hop RAG](https://arxiv.org/abs/2607.06507)
> **Score 10/10** · `cs.IR`
>
> > Directly addresses RAG with a focus on evidence control and multi-hop retrieval strategies.
>
> <em>▸ Abstract folded underneath — one click to expand</em>

A real day looks like: **296 papers scanned → 38 surfaced → the top 10 are genuinely must-reads.**

---

## Setup (5 minutes)

**Prerequisites:** a GitHub account, the [`gh` CLI](https://cli.github.com/), and an [OpenAI API key](https://platform.openai.com/api-keys).

```bash
# 1. Get the code (fork/clone this repo, or copy the three files)
git clone https://github.com/Bhanubathini2002/arxiv-radar && cd arxiv-radar

# 2. Store your OpenAI key as an encrypted repo secret
gh secret set OPENAI_API_KEY

# 3. Create the label used for digest issues
gh label create digest --color 1D76DB

# 4. Fire a test run (or wait for the daily schedule)
gh workflow run "arXiv digest"
```

That's it. Check the **Issues** tab a few minutes later for your first digest.

### Run locally (optional)

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # PowerShell: $env:OPENAI_API_KEY="sk-..."
python arxiv_radar.py
```

---

## Make it yours

All personalization lives in one file — [`config.yaml`](config.yaml):

```yaml
categories:          # WHERE to look — arXiv sections
  - cs.CL            # NLP & language models
  - cs.IR            # information retrieval
  - cs.CV            # computer vision

interests: |         # WHAT to look for — plain English, this IS the prompt
  I am building a production RAG chat application...
  - RAG architectures: chunking, reranking, multi-hop retrieval
  - RAG evaluation: faithfulness metrics, hallucination detection
  - Guardrails: prompt injection defense, jailbreak detection

min_score: 8         # raise to 9 for must-reads only, lower to 7 for more volume
model: gpt-4o-mini   # any cheap model works (gpt-4.1-mini, gpt-4.1-nano, ...)
```

| Knob | Effect |
|---|---|
| `categories` | Which arXiv sections to scan — [full taxonomy](https://arxiv.org/category_taxonomy) |
| `interests` | Plain-English description of what you care about. Be specific — it's the LLM's rubric |
| `min_score` | Digest cutoff. `9` ≈ 5–10 papers/day, `8` ≈ 10–20, `7` = firehose |
| `model` | Any OpenAI chat model; cheaper = fine, the task is easy |
| cron in [`digest.yml`](.github/workflows/digest.yml) | Delivery time (UTC) — currently 12:30 UTC = 7:30 AM US Central |

Edit, commit, push — the next run picks it up. No redeploy, because there's nothing deployed.

---

## Cost & design notes

- **LLM cost:** ~300 papers/day × ~350 tokens through GPT-4o-mini ≈ **$0.50–1.50/month**
- **Compute cost:** $0 — GitHub Actions is free for public repositories
- **Dependencies:** Python standard library + `pyyaml`. No LangChain, no frameworks — the whole pipeline is [one ~200-line script](arxiv_radar.py)
- **Polite to arXiv:** requests are spaced 3+ seconds apart per their [API guidelines](https://info.arxiv.org/help/api/tou.html)
- **Resilient:** automatic retry with backoff on rate limits; a failed scoring batch is logged and skipped, never fatal

## Project structure

```
arxiv-radar/
├── arxiv_radar.py                 # the entire pipeline: fetch → dedupe → score → digest
├── config.yaml                    # your categories, interests, and thresholds
├── .github/workflows/digest.yml   # daily cron + commit + issue creation
├── data/seen.json                 # paper IDs already scored (bot-maintained)
└── digests/                       # daily markdown digests (bot-maintained archive)
```

---

## License

MIT — take it, fork it, point it at your own research interests.
