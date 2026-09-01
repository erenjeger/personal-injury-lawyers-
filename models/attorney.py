from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


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

    @property
    def is_publishable(self) -> bool:
        return bool(self.name.strip() and self.practice_area.strip() and self.phone.strip() and self.about.strip())
