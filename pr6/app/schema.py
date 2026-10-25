import json
from pydantic import BaseModel, Field, ValidationError


class AnswerSchema(BaseModel):
    """Схема очікуваної відповіді від мовної моделі."""

    answer: str = Field(description="Текст відповіді клієнту українською мовою.")
    found: bool = Field(
        description="True, якщо відповідь вдалося знайти в наданих документах, інакше False."
    )
    sources: list[int] = Field(
        description="Список номерів джерел [ref], на які спирається відповідь. Порожній, якщо found=False."
    )


def output_schema() -> dict:
    """Повернути JSON Schema відповіді моделі."""
    return AnswerSchema.model_json_schema()


def validate(raw: str) -> dict:
    """Перевірити сиру відповідь моделі й повернути словник."""
    clean_raw = raw.strip()
    if clean_raw.startswith("```json"):
        clean_raw = clean_raw[7:-3].strip()
    elif clean_raw.startswith("```"):
        clean_raw = clean_raw[3:-3].strip()

    try:
        data = json.loads(clean_raw)
        validated = AnswerSchema(**data)
        return validated.model_dump()
    except json.JSONDecodeError as e:
        raise ValueError(f"Відповідь не є валідним JSON: {e}")
    except ValidationError as e:
        raise ValueError(f"Відповідь не відповідає схемі: {e}")