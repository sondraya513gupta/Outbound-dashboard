from __future__ import annotations

import re
from urllib.parse import urlparse

from ddgs import DDGS
from ddgs.http_client import HttpClient

HttpClient._impersonates = ("chrome", "edge", "firefox", "safari")

SKIP_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "wikipedia.org",
    "wikidata.org",
    "crunchbase.com",
    "zoominfo.com",
    "yelp.com",
    "tripadvisor.com",
    "amazon.com",
    "play.google.com",
    "apps.apple.com",
    "w3schools.com",
    "educonnectin.com",
    "schools.org.in",
    "schoolspedia.in",
    "schoolsindia.net",
    "getschoolsinfo.com",
}

DIRECTORY_HINTS = (
    "directory",
    "list of",
    "search platform",
    "find & compare",
    "find and compare",
    "school search",
    "yellow pages",
)

COUNTRY_REGIONS = {
    "india": "in-en",
    "united states": "us-en",
    "usa": "us-en",
    "us": "us-en",
    "united kingdom": "uk-en",
    "uk": "uk-en",
    "britain": "uk-en",
    "canada": "ca-en",
    "australia": "au-en",
    "singapore": "sg-en",
    "uae": "ae-en",
    "united arab emirates": "ae-en",
    "germany": "de-en",
    "france": "fr-en",
}


def region_for(country: str) -> str:
    return COUNTRY_REGIONS.get(country.strip().lower(), "wt-wt")


def registrable_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_useful_result(url: str, title: str = "", snippet: str = "") -> bool:
    host = registrable_domain(url)
    if not host or "." not in host:
        return False
    if any(host == skip or host.endswith(f".{skip}") for skip in SKIP_DOMAINS):
        return False
    blob = f"{title} {snippet}".lower()
    return not any(hint in blob for hint in DIRECTORY_HINTS)


def search_web(query: str, country: str, max_results: int = 12) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        with DDGS() as client:
            for item in client.text(
                query,
                region=region_for(country),
                max_results=max_results,
                backend="auto",
            ):
                url = (item.get("href") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("body") or "").strip()
                if not url or not title or not is_useful_result(url, title, snippet):
                    continue
                domain = registrable_domain(url)
                if domain in seen:
                    continue
                seen.add(domain)
                rows.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "domain": domain,
                    }
                )
    except Exception:
        return rows
    return rows


def search_queries(product: str, country: str, industry: str) -> list[str]:
    industry = industry.strip()
    country = country.strip()
    queries = [
        f"{industry} official website {country}",
        f"{industry} group {country} official site",
        f"largest {industry} {country}",
        f"{industry} {country} contact email",
        f"{product.strip()[:50]} {industry} {country} official",
    ]
    lowered = f"{industry} {product}".lower()
    if any(word in lowered for word in ("school", "education", "edtech")):
        queries.append(f"international school {country} official website")
        queries.append(f"school trust {country} official website")
        if country.lower() == "india":
            queries.extend(
                [
                    "Delhi Public School Society official website",
                    "Kendriya Vidyalaya Sangathan official website",
                ]
            )
    if any(word in lowered for word in ("hospital", "health", "clinic")):
        queries.extend(
            [
                f"hospital group {country} official website",
                f"health system {country} official website",
            ]
        )
    if any(word in lowered for word in ("hr", "recruit", "hiring")):
        queries.extend(
            [
                f"companies {country} careers official website",
                f"employer {country} official site",
            ]
        )
    return queries


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
BAD_EMAIL_PARTS = (
    "example.com",
    "email.com",
    "domain.com",
    "sentry.io",
    "wixpress",
    "noreply",
    "no-reply",
    "privacy@",
    "legal@",
    ".png",
    ".jpg",
    ".svg",
)


def plausible_email(value: str | None) -> str | None:
    if not value:
        return None
    email = str(value).strip().lower()
    if email in {"null", "none", "n/a", ""}:
        return None
    if not EMAIL_RE.fullmatch(email):
        return None
    local, _, host = email.partition("@")
    if len(local) < 3 or len(host) < 5 or "." not in host:
        return None
    if any(part in email for part in BAD_EMAIL_PARTS):
        return None
    return email


def extract_emails(text: str, domain: str | None = None) -> list[str]:
    found: list[str] = []
    for match in EMAIL_RE.findall(text or ""):
        email = plausible_email(match.strip(".,;:()<>\"'"))
        if not email:
            continue
        if domain and not email.endswith(domain) and not email.endswith("." + domain):
            # Keep generic org emails even if subdomain differs; drop obvious third parties later
            pass
        found.append(email)
    # Prefer domain-matching addresses
    if domain:
        matching = [e for e in found if e.split("@")[-1].endswith(domain)]
        if matching:
            return list(dict.fromkeys(matching))
    return list(dict.fromkeys(found))


def find_contact_email(org_name: str, website: str, country: str) -> str | None:
    domain = registrable_domain(website)
    queries = [
        f'"{org_name}" contact email {country}',
        f"site:{domain} contact email",
        f"{org_name} admissions contact email" if "school" in org_name.lower() or "college" in org_name.lower() else f"{org_name} {domain} email",
    ]
    for query in queries:
        for row in search_web(query, country, max_results=6):
            emails = extract_emails(f"{row['title']} {row['snippet']}", domain)
            if emails:
                return emails[0]
    return None
