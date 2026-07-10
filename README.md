# arXiv Radar

Daily automated arXiv filter: a GitHub Actions cron job pulls new papers from
your chosen categories, a cheap LLM (GPT-4o-mini) scores each title+abstract
against your interests, and relevant papers land in a markdown digest committed
to `digests/` plus a GitHub issue you can read like an inbox.

## Setup

1. Create a GitHub repo (public repos get free Actions minutes) and push this code:

   ```
   git init
   git add .
   git commit -m "arxiv radar"
   gh repo create arxiv-radar --public --source . --push
   ```

2. Add your API key as a repo secret:

   ```
   gh secret set OPENAI_API_KEY
   ```

3. Create the issue label (one time):

   ```
   gh label create digest --color 1D76DB
   ```

4. Test it: go to **Actions → arXiv digest → Run workflow**, or run locally:

   ```
   pip install -r requirements.txt
   set OPENAI_API_KEY=sk-...   # PowerShell: $env:OPENAI_API_KEY="sk-..."
   python arxiv_radar.py
   ```

After that it runs itself daily at 06:30 UTC.

## Tuning

Everything lives in `config.yaml`:

- **categories** — arXiv category codes ([full list](https://arxiv.org/category_taxonomy))
- **interests** — plain-English description of what you care about; this is the
  prompt, so be specific
- **min_score** — raise to 8 if the digest is too noisy, lower to 6 if too quiet
- **model** — any cheap OpenAI model works (`gpt-4o-mini`, `gpt-4.1-mini`,
  `gpt-4.1-nano`); costs a few cents per day at ~300 papers/run

## How it avoids duplicates

`data/seen.json` (committed back by the workflow) records every paper ID already
scored, so each run only pays for genuinely new papers — no date-window math,
no weekend gaps.

## Cost

~200–400 new papers/day × ~350 tokens each through GPT-4o-mini ≈ **under $0.05/day**.
GitHub Actions is free for public repos.
