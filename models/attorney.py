from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Attorney(BaseModel):
    """Validated attorney record.

    The first 20 fields are the exact spreadsheet contract from the supplied
    attorney-data-example.xlsx template. Internal provenance/quality fields
    are kept after those columns and are never exported.
    """

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

    # Internal fields: intentionally excluded from the spreadsheet contract.
    source_url: str = ""
    photo_url: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("status")
    @classmethod
    def status_is_publish(cls, value: str) -> str:
        return "publish" if not value else value

    @property
    def is_publishable(self) -> bool:
        return all(
            bool(getattr(self, key, "").strip())
            for key in ("name", "practice_area", "phone", "about")
        )
