# Outbound Desk

Internal Upthrust tool for SaaS outbound. One campaign brief becomes a sheet of real organizations, a personalized email for each, and a way to start outreach.

```
Campaign Input → Lead Generation → Personalized Emails → Excel / CSV → Outreach
```

## Run it

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Use Python 3.13 (or 3.11/3.12). Default `python` on this machine is 3.14, which cannot install the current Pydantic wheel.

Open [http://localhost:8000](http://localhost:8000). The OpenRouter key lives in `.env`.

## What it does

1. **Campaign input** — product, country, industry, number of leads.
2. **Lead generation** — DuckDuckGo search for live organizations in that market, then OpenRouter to keep only relevant buyers. Websites are checked. Public emails are kept only when they appear in search snippets. No invented contacts.
3. **Emails** — one subject, body, and call to action per organization, written against that lead’s description.
4. **Storage** — every run writes `data/leads.xlsx` and `data/leads.csv`. Same columns the brief asked for, including `Not Contacted` / `Contacted`.
5. **Outreach** — **Start outreach** opens the local mail client with the draft (`mailto:`) and marks the row Contacted. Optional SMTP send if `SMTP_*` is set in `.env`.

## Why this approach

Lead quality is the hard part. The model does not invent a school list. It ranks organizations that already showed up in web search, then writes the email. That keeps names, sites, and source URLs checkable during a demo.
