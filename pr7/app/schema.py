import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, ValidationError

Scalar = str | int | float | None

MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}

TEMPLATE = """{
  "document_type": "рахунок | видаткова накладна | інший",
  "number": "номер документа",
  "date": "дата документа",
  "valid_until": "строк дії або null",
  "supplier": {"name": "назва", "code": "ЄДРПОУ або РНОКПП", "iban": "IBAN"},
  "buyer": {"name": "назва", "code": "код"},
  "items": [
    {"name": "найменування", "unit": "одиниця", "quantity": "кількість", "price": "ціна", "amount": "сума"}
  ],
  "total_without_vat": "разом без ПДВ",
  "vat": "ПДВ",
  "total": "усього до сплати",
  "unreadable_fields": []
}"""


class SchemaError(Exception):
    pass


class RawSupplier(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Scalar = None
    code: Scalar = None
    iban: Scalar = None


class RawBuyer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Scalar = None
    code: Scalar = None


class RawItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Scalar = None
    unit: Scalar = None
    quantity: Scalar = None
    price: Scalar = None
    amount: Scalar = None


class RawDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document_type: Scalar = None
    number: Scalar = None
    date: Scalar = None
    valid_until: Scalar = None
    supplier: RawSupplier
    buyer: RawBuyer
    items: list[RawItem]
    total_without_vat: Scalar = None
    vat: Scalar = None
    total: Scalar = None
    unreadable_fields: list[str] = []


def output_schema() -> dict:
    return RawDocument.model_json_schema()


def _parse_number(text: str) -> Decimal | None:
    cleaned = text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    cleaned = re.sub(r"(?i)грн\.?|uah|₴|\s", "", cleaned).replace("−", "-")
    if not re.fullmatch(r"-?[\d.,]+", cleaned) or not re.search(r"\d", cleaned):
        return None
    if "," in cleaned and "." in cleaned:
        sep = max(cleaned.rfind(","), cleaned.rfind("."))
        cleaned = re.sub(r"[.,]", "", cleaned[:sep]) + "." + cleaned[sep + 1:]
    elif "," in cleaned or "." in cleaned:
        char = "," if "," in cleaned else "."
        parts = cleaned.split(char)
        head = parts[0].lstrip("-")
        if len(parts) > 2 or (len(parts[1]) == 3 and head not in ("0", "")):
            cleaned = "".join(parts)
        else:
            cleaned = parts[0] + "." + parts[1]
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _money(text: str) -> str | None:
    value = _parse_number(text)
    if value is None:
        return None
    if -value.as_tuple().exponent <= 2:
        return format(value.quantize(Decimal("0.01")), "f")
    return format(value.normalize(), "f")


def _quantity(text: str) -> str | None:
    value = _parse_number(text)
    if value is None:
        return None
    return format(value.normalize(), "f")

def _vat(text: str) -> str | None:
    if re.search(r"(?i)без\s*пдв|не\s*є\s*платник|не\s*обклада", text) or text.strip() in {"-", "—", "–"}:
        return "0.00"
    return _money(text)

def _date(text: str) -> str | None:
    low = text.strip().lower()
    year = month = day = None
    found = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", low)
    if found:
        year, month, day = (int(x) for x in found.groups())
    else:
        found = re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})", low)
        if found:
            day, month, year = (int(x) for x in found.groups())
        else:
            found = re.search(r"(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})", low)
            if found and found.group(2) in MONTHS:
                day, month, year = int(found.group(1)), MONTHS[found.group(2)], int(found.group(3))
    if year is None:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _doc_type(text: str) -> str:
    low = text.lower()
    if "накладн" in low:
        return "видаткова накладна"
    if "рахун" in low:
        return "рахунок"
    return "інший"


def _iban(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def _code(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _plain(text: str) -> str:
    return text


def _load(raw: str):
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    try:
        payload = json.loads(text, parse_float=str)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise SchemaError("відповідь не є JSON")
        try:
            payload = json.loads(text[start:end + 1], parse_float=str)
        except ValueError:
            raise SchemaError("відповідь не є коректним JSON")
    if not isinstance(payload, dict):
        raise SchemaError("JSON має бути обʼєктом")
    return payload


def _describe(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:3]:
        where = ".".join(str(x) for x in error["loc"]) or "відповідь"
        parts.append(f"{where}: {error['msg']}")
    return "; ".join(parts)


def validate(raw: str) -> dict:
    payload = _load(raw)
    try:
        parsed = RawDocument.model_validate(payload)
    except ValidationError as exc:
        raise SchemaError(_describe(exc)) from exc

    unparsed: dict[str, str] = {}

    def field(path: str, value: Scalar, parser) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        result = parser(text)
        if result is None:
            unparsed[path] = text
        return result

    items = []
    for index, item in enumerate(parsed.items):
        base = f"items.{index}"
        items.append({
            "name": field(f"{base}.name", item.name, _plain),
            "unit": field(f"{base}.unit", item.unit, _plain),
            "quantity": field(f"{base}.quantity", item.quantity, _quantity),
            "price": field(f"{base}.price", item.price, _money),
            "amount": field(f"{base}.amount", item.amount, _money),
        })

    return {
        "document_type": field("document_type", parsed.document_type, _doc_type),
        "number": field("number", parsed.number, _plain),
        "date": field("date", parsed.date, _date),
        "valid_until": field("valid_until", parsed.valid_until, _date),
        "supplier": {
            "name": field("supplier.name", parsed.supplier.name, _plain),
            "code": field("supplier.code", parsed.supplier.code, _code),
            "iban": field("supplier.iban", parsed.supplier.iban, _iban),
        },
        "buyer": {
            "name": field("buyer.name", parsed.buyer.name, _plain),
            "code": field("buyer.code", parsed.buyer.code, _code),
        },
        "items": items,
        "total_without_vat": field("total_without_vat", parsed.total_without_vat, _money),
        "vat": field("vat", parsed.vat, _vat),
        "total": field("total", parsed.total, _money),
        "unreadable_fields": [p.strip() for p in parsed.unreadable_fields if p.strip()],
        "unparsed": unparsed,
    }

