from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import DATA_DIR
from models import CampaignInput, ContactRequest
from services import storage
from services.email_gen import write_emails
from services.lead_gen import discover_leads
from services.outreach import send_smtp, smtp_ready

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Upthrust Outbound Desk")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "smtp": smtp_ready()}


@app.get("/api/campaigns")
def campaigns() -> dict:
    store = storage.load_store()
    return {"campaigns": [item.model_dump() for item in store.campaigns]}


@app.get("/api/leads")
def leads(campaign_id: str | None = Query(default=None)) -> dict:
    rows = storage.list_leads(campaign_id)
    return {
        "leads": [
            {**lead.model_dump(), "mailto": storage.mailto_link(lead)} for lead in rows
        ]
    }


@app.post("/api/campaigns/run")
async def run_campaign(payload: CampaignInput) -> StreamingResponse:
    async def events():
        def emit(step: str, detail: str, extra: dict | None = None) -> str:
            body = {"step": step, "detail": detail, **(extra or {})}
            return f"data: {json.dumps(body)}\n\n"

        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def progress(step: str, detail: str) -> None:
            queue.put_nowait((step, detail))

        try:
            yield emit("input", "Campaign received")
            task = asyncio.create_task(
                discover_leads(
                    payload.product_description,
                    payload.country,
                    payload.industry,
                    payload.number_of_leads,
                    progress=progress,
                )
            )
            while not task.done():
                try:
                    step, detail = await asyncio.wait_for(queue.get(), timeout=0.25)
                    yield emit(step, detail)
                except asyncio.TimeoutError:
                    continue
            while not queue.empty():
                step, detail = queue.get_nowait()
                yield emit(step, detail)

            raw = task.result()
            if not raw:
                yield emit(
                    "error",
                    "No real organizations found. Try a broader industry or another country.",
                )
                return

            yield emit("emails", f"Writing outreach for {len(raw)} leads")
            raw = await write_emails(
                payload.product_description,
                payload.country,
                payload.industry,
                raw,
            )

            yield emit("storage", "Saving Excel and CSV")
            campaign, leads = storage.add_campaign(payload, raw)
            yield emit(
                "done",
                f"Ready: {len(leads)} leads in the sheet",
                {
                    "campaign": campaign.model_dump(),
                    "leads": [
                        {**lead.model_dump(), "mailto": storage.mailto_link(lead)}
                        for lead in leads
                    ],
                },
            )
        except Exception as exc:
            yield emit("error", str(exc))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/leads/{lead_id}/contact")
def contact_lead(lead_id: str, payload: ContactRequest) -> dict:
    lead = storage.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if payload.send_via_smtp:
        try:
            send_smtp(lead)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = storage.mark_contacted(lead_id)
    assert updated
    return {
        "lead": {**updated.model_dump(), "mailto": storage.mailto_link(updated)},
        "sent_via_smtp": payload.send_via_smtp,
    }


@app.get("/api/export/{kind}")
def export_file(kind: str) -> FileResponse:
    if kind not in {"csv", "xlsx"}:
        raise HTTPException(status_code=404, detail="Use csv or xlsx")
    paths = storage.export_paths()
    path = paths[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail="No leads exported yet")
    media = (
        "text/csv"
        if kind == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/api/files")
def files() -> dict:
    return {
        "csv": "/api/export/csv",
        "xlsx": "/api/export/xlsx",
        "folder": str(DATA_DIR),
        "smtp": smtp_ready(),
    }
