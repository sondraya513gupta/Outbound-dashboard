from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["Not Contacted", "Contacted"]


class CampaignInput(BaseModel):
    product_description: str = Field(min_length=8, max_length=800)
    country: str = Field(min_length=2, max_length=80)
    industry: str = Field(min_length=2, max_length=120)
    number_of_leads: int = Field(ge=1, le=25, default=10)


class Lead(BaseModel):
    id: str
    campaign_id: str
    organization_name: str
    website: str
    country: str
    industry: str
    contact_email: str | None = None
    description: str
    source_url: str
    email_subject: str = ""
    email_body: str = ""
    status: Status = "Not Contacted"


class Campaign(BaseModel):
    id: str
    product_description: str
    country: str
    industry: str
    requested: int
    created_at: str
    lead_ids: list[str] = Field(default_factory=list)


class Store(BaseModel):
    campaigns: list[Campaign] = Field(default_factory=list)
    leads: list[Lead] = Field(default_factory=list)


class ContactRequest(BaseModel):
    send_via_smtp: bool = False
