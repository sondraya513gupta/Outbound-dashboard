from config import AGENCY_NAME, AGENCY_ROLE, AGENCY_SENDER, OPENROUTER_EMAIL_MODEL
from services.openrouter import chat, parse_json_object

SYSTEM = f"""You write cold emails for {AGENCY_NAME}, a marketing agency that does outbound for SaaS startups.
Write like a sharp human, not a newsletter.

Rules:
- One email per lead. Reference that organization by name and one specific fact from its description or website.
- Connect the product to a problem that organization would actually have. Do not invent awards, user counts, or case studies.
- 90 to 140 words. Short paragraphs. No emojis. No "I hope this email finds you well". No "touching base".
- Subject: 6 to 10 words, concrete, not clickbait.
- End with one clear ask: reply with a 15-minute slot this week, or say it is not relevant.
- Sign as {AGENCY_SENDER}, {AGENCY_ROLE} at {AGENCY_NAME}.
- Return JSON only."""


async def write_emails(
    product: str,
    country: str,
    industry: str,
    leads: list[dict],
) -> list[dict]:
    if not leads:
        return leads

    roster = "\n".join(
        (
            f"{i}. {lead['organization_name']} | {lead.get('website', '')} | "
            f"{lead.get('description', '')}"
        )
        for i, lead in enumerate(leads, start=1)
    )
    user = f"""SaaS product: {product}
Buyer industry: {industry}
Buyer country: {country}

Leads:
{roster}

Return one email per lead, same order, using the lead index:
{{
  "emails": [
    {{
      "index": 1,
      "organization_name": "",
      "subject": "",
      "body": "plain text email including greeting, body, CTA, and signature"
    }}
  ]
}}"""

    try:
        text = await chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
            model=OPENROUTER_EMAIL_MODEL,
            json_mode=True,
            temperature=0.55,
            timeout=90,
        )
        items = [
            item
            for item in (parse_json_object(text).get("emails") or [])
            if isinstance(item, dict)
        ]
        for index, lead in enumerate(leads, start=1):
            item = _match_email(items, lead, index)
            if item and item.get("subject") and item.get("body"):
                lead["email_subject"] = str(item["subject"]).strip()
                lead["email_body"] = str(item["body"]).strip()
            else:
                lead.update(_fallback_email(product, lead))
        return leads
    except Exception:
        for lead in leads:
            lead.update(_fallback_email(product, lead))
        return leads


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _match_email(items: list[dict], lead: dict, index: int) -> dict | None:
    by_index = next((item for item in items if item.get("index") == index), None)
    if by_index:
        return by_index
    target = _norm(lead["organization_name"])
    for item in items:
        name = _norm(str(item.get("organization_name") or ""))
        if name and (name == target or name in target or target in name):
            return item
    if index - 1 < len(items):
        return items[index - 1]
    return None


def _fallback_email(product: str, lead: dict) -> dict[str, str]:
    name = lead["organization_name"]
    subject = f"{name}: a faster way to handle this"
    body = (
        f"Hello {name} team,\n\n"
        f"I work with {AGENCY_NAME} and we are introducing {product} "
        f"to {lead.get('industry', 'organizations')} in {lead.get('country', 'your market')}.\n\n"
        f"{lead.get('description') or name} looks like a fit because this kind of team "
        f"usually spends too much time on the process this product automates.\n\n"
        f"Would you have 15 minutes this week for a short walkthrough, or is this not relevant?\n\n"
        f"{AGENCY_SENDER}\n{AGENCY_ROLE}, {AGENCY_NAME}"
    )
    return {"email_subject": subject, "email_body": body}
