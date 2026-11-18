import re

from pydantic import BaseModel, Field, ValidationError, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str
    password: str = Field(min_length=6, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        return str(v or "").strip()

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        v = str(v or "").strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("enter a valid email address")
        return v


class ComplaintIn(BaseModel):
    text: str
    value: float = Field(gt=0)
    state: str
    district: str = ""
    opposite_party: str = ""

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, v):
        v = str(v or "").strip()
        if len(v) < 50:
            raise ValueError(f"must be at least 50 characters (currently {len(v)})")
        return v

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, v):
        if isinstance(v, str):
            v = v.replace(",", "").replace("₹", "").replace("Rs.", "").strip()
            if not v:
                raise ValueError("is required")
        return v

    @field_validator("state", mode="before")
    @classmethod
    def _state(cls, v):
        v = str(v or "").strip()
        if not v:
            raise ValueError("is required")
        return v

    @field_validator("district", "opposite_party", mode="before")
    @classmethod
    def _strip(cls, v):
        return str(v or "").strip()


def friendly(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        field = ".".join(str(p) for p in e.get("loc", ())) or "input"
        msg = e.get("msg", "invalid").removeprefix("Value error, ")
        lines.append(f"{field.replace('_', ' ').capitalize()}: {msg}")
    return "\n".join(lines)
