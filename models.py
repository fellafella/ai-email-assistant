"""Modèles de données Pydantic pour l'assistant d'e-mails."""
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    RECRUITMENT = "Recruitment"
    MEETING = "Meeting"
    FINANCE = "Finance"
    GENERAL = "General"


class Priority(str, Enum):
    HIGH = "High"
    NORMAL = "Normal"


class EmailInput(BaseModel):
    """E-mail à analyser (validé avant tout traitement)."""

    sender: str | None = None
    subject: str = ""
    body: str = Field(min_length=1)

    @field_validator("subject", "body")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("Le corps de l'e-mail ne peut pas être vide.")
        return value


class EmailAnalysis(BaseModel):
    """Résultat de l'analyse, garanti conforme par Pydantic."""

    category: Category
    priority: Priority
    category_keywords: list[str] = Field(default_factory=list)
    priority_keywords: list[str] = Field(default_factory=list)