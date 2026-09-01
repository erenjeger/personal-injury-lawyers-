from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Attorney(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attorney_id: str
    name: str
    practice_area: str
    firm: str
    city: str
    state: str
    licensed_states: str = ""
    education: str = ""
    affiliations: str = ""
    badges: str = ""
    photo: str = ""
    years_experience: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    phone: str
    languages: str = ""
    about: str
    callout_text: str = ""
    status: str = "publish"
    menu_order: int = Field(ge=1)
    source_url: str = ""
    photo_url: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("status")
    @classmethod
    def status_is_publish(cls, value: str) -> str:
        return "publish" if not value else value

    @property
    def is_publishable(self) -> bool:
        return all(bool(getattr(self, k, "").strip()) for k in ("name", "practice_area", "phone", "about"))
