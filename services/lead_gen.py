from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx

from services.openrouter import chat, parse_json_object
from services.search import (
    find_contact_email,
    plausible_email,
    registrable_domain,
    search_queries,
    search_web,
)

Progress = Callable[[str, str], None]

EXTRACT_SYSTEM = """You are a B2B lead researcher at a marketing agency.
You only return real organizations that appear in the supplied search results.
Never invent a company, website, email, or source URL.
Pick organizations that would BUY the product, not vendors that compete with it.
Skip directories, news listicles, job boards, marketplaces, and other SaaS tools.
Prefer operators: school groups, hospitals, employers, government departments, or companies in the named industry.
Prefer official organization websites over listicles.
Return JSON only."""


async def discover_leads(
    product: str,
    country: str,
    industry: str,
    count: int,
    progress: Callable[[str, str], Any] | None = None,
) -> list[dict[str, Any]]:
    def note(step: str, detail: str) -> None:
        if progress:
            progress(step, detail)

    note("search", f"Searching the live web for {industry} in {country}")
    raw: list[dict[str, str]] = []
    seen_domains: set[str] = set()
    for query in search_queries(product, country, industry):
        for row in search_web(query, country, max_results=10):
            if row["domain"] in seen_domains:
                continue
            seen_domains.add(row["domain"])
            raw.append(row)
        if len(raw) >= count * 4:
            break

    note("search", f"Found {len(raw)} candidate pages")

    leads = await _extract_from_results(product, country, industry, count, raw)
    if len(leads) < count:
        note("search", "Asking OpenRouter to search the web for more organizations")
        extra = await _web_model_leads(product, country, industry, count)
        leads = _merge(leads, extra, country, industry)

    leads = await _verify_and_enrich(leads, country, count, note)
    return leads[:count]


async def _extract_from_results(
    product: str,
    country: str,
    industry: str,
    count: int,
    results: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not results:
        return []

    numbered = "\n".join(
        f"{i}. {r['title']} | {r['url']} | {r['snippet']}"
        for i, r in enumerate(results, start=1)
    )
    user = f"""Product being sold: {product}
Target country: {country}
Target industry: {industry}
Need up to {count} buyer organizations.

Search results:
{numbered}

Pick organizations in {country} that could reasonably buy this product.
Do not pick software vendors, LMS tools, or consultancies that sell a similar product.
Each lead must use a website and source_url that appear in the search results.
contact_email must be null unless an email is literally present in a snippet.

Return:
{{
  "leads": [
    {{
      "organization_name": "",
      "website": "https://...",
      "contact_email": null,
      "description": "1-2 factual sentences",
      "source_url": "https://..."
    }}
  ]
}}"""
    try:
        text = await chat(
            [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ],
            json_mode=True,
            temperature=0.1,
        )
        data = parse_json_object(text)
        return _normalize(data.get("leads") or [], country, industry)
    except Exception:
        return _heuristic_leads(results, country, industry, count)


async def _web_model_leads(
    product: str,
    country: str,
    industry: str,
    count: int,
) -> list[dict[str, Any]]:
    user = f"""Find {count} real {industry} organizations in {country} that could buy this SaaS product: {product}.

Use web search. Official websites only. No invented names or URLs.
contact_email only if you actually found a public email.

Return JSON:
{{
  "leads": [
    {{
      "organization_name": "",
      "website": "https://...",
      "contact_email": null,
      "description": "",
      "source_url": "https://..."
    }}
  ]
}}"""
    try:
        text = await chat(
            [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ],
            json_mode=True,
            use_web=True,
            temperature=0.1,
            timeout=120,
        )
        data = parse_json_object(text)
        return _normalize(data.get("leads") or [], country, industry)
    except Exception:
        return []


def _heuristic_leads(
    results: list[dict[str, str]],
    country: str,
    industry: str,
    count: int,
) -> list[dict[str, Any]]:
    leads = []
    for row in results[: count * 2]:
        name = row["title"].split(" - ")[0].split(" | ")[0].strip()
        if len(name) < 3:
            continue
        leads.append(
            {
                "organization_name": name[:80],
                "website": f"https://{row['domain']}",
                "country": country,
                "industry": industry,
                "contact_email": None,
                "description": row["snippet"][:280],
                "source_url": row["url"],
            }
        )
    return leads


def _normalize(raw: list[Any], country: str, industry: str) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("organization_name") or "").strip()
        website = str(item.get("website") or "").strip()
        source = str(item.get("source_url") or website).strip()
        if not name or not website:
            continue
        if not website.startswith("http"):
            website = "https://" + website
        domain = registrable_domain(website)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        email = plausible_email(item.get("contact_email"))
        leads.append(
            {
                "organization_name": name,
                "website": website,
                "country": str(item.get("country") or country),
                "industry": str(item.get("industry") or industry),
                "contact_email": email,
                "description": str(item.get("description") or "").strip()[:400],
                "source_url": source if source.startswith("http") else website,
            }
        )
    return leads


def _merge(
    primary: list[dict[str, Any]],
    extra: list[dict[str, Any]],
    country: str,
    industry: str,
) -> list[dict[str, Any]]:
    return _normalize(primary + extra, country, industry)


async def _site_looks_live(url: str) -> bool:
    headers = {"User-Agent": "UpthrustLeadDesk/1.0"}
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=8.0, headers=headers
        ) as client:
            response = await client.head(url)
            if response.status_code >= 400:
                response = await client.get(url)
            return response.status_code < 500
    except Exception:
        return True


async def _verify_and_enrich(
    leads: list[dict[str, Any]],
    country: str,
    count: int,
    note: Callable[[str, str], None],
) -> list[dict[str, Any]]:
    candidates = leads[: max(count * 2, count)]
    note("verify", f"Checking {len(candidates)} websites")
    live_flags = await asyncio.gather(
        *[_site_looks_live(lead["website"]) for lead in candidates]
    )
    checked: list[dict[str, Any]] = []
    for lead, live in zip(candidates, live_flags):
        if not live:
            continue
        if not lead.get("description"):
            lead["description"] = (
                f"{lead['organization_name']} is a {lead['industry']} organization in {country}."
            )
        checked.append(lead)
        if len(checked) >= count:
            break

    missing = [lead for lead in checked if not lead.get("contact_email")][:6]
    if missing:
        note("verify", f"Looking up public emails for {len(missing)} organizations")

        async def lookup(lead: dict[str, Any]) -> None:
            try:
                lead["contact_email"] = await asyncio.to_thread(
                    find_contact_email,
                    lead["organization_name"],
                    lead["website"],
                    country,
                )
            except Exception:
                lead["contact_email"] = None

        await asyncio.gather(*[lookup(lead) for lead in missing])
    return checked
