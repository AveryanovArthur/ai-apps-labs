import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.01")
VAT_RATE = Decimal("0.20")
INVOICE = "рахунок"


@dataclass
class Issue:
    field: str
    rule: str
    message: str
    severity: str = "error"


def load_reference() -> tuple[dict, list[dict]]:
    company = json.loads((REFERENCE_DIR / "company.json").read_text(encoding="utf-8"))
    suppliers = json.loads((REFERENCE_DIR / "suppliers.json").read_text(encoding="utf-8"))
    return company, suppliers


@lru_cache(maxsize=1)
def _reference() -> tuple[dict, list[dict]]:
    return load_reference()


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _compact(text: str) -> str:
    return re.sub(r"[\s«»\"'`ʼ’‘„“”]", "", text.lower())


def _mask(iban: str) -> str:
    return f"{iban[:4]}…{iban[-4:]}" if len(iban) > 8 else iban


def _get(document: dict, path: str):
    value = document
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _severity(path: str) -> str:
    return "warning" if path.endswith((".name", ".unit")) else "error"


def iban_checksum_ok(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def edrpou_ok(code: str) -> bool:
    digits = [int(c) for c in code]
    number = int(code)
    weights = [7, 1, 2, 3, 4, 5, 6] if 30000000 <= number < 60000000 else [1, 2, 3, 4, 5, 6, 7]
    remainder = sum(d * w for d, w in zip(digits[:7], weights)) % 11
    if remainder == 10:
        shifted = [w + 2 for w in weights]
        remainder = sum(d * w for d, w in zip(digits[:7], shifted)) % 11
        if remainder == 10:
            remainder = 0
    return remainder == digits[7]


def rnokpp_ok(code: str) -> bool:
    weights = [-1, 5, 7, 9, 4, 6, 10, 5, 7]
    total = sum(int(c) * w for c, w in zip(code[:9], weights))
    return (total % 11) % 10 == int(code[9])


def _code_issue(path: str, code: str) -> Issue | None:
    if re.fullmatch(r"\d{8}", code):
        if not edrpou_ok(code):
            return Issue(path, "code_checksum", f"Код ЄДРПОУ {code} не проходить перевірку контрольного розряду.")
    elif re.fullmatch(r"\d{10}", code):
        if not rnokpp_ok(code):
            return Issue(path, "code_checksum", f"Код РНОКПП {code} не проходить перевірку контрольного розряду.")
    else:
        return Issue(path, "code_format", f"Код «{code}» має бути 8 цифр (ЄДРПОУ) або 10 цифр (РНОКПП).")
    return None


def _required(document: dict, skip: set[str]) -> list[Issue]:
    issues = []

    def need(path: str, value) -> None:
        if path in skip:
            return
        if value is None or value == "" or value == []:
            issues.append(Issue(
                path, "missing_required",
                f"Обовʼязкове поле «{path}» відсутнє або не прочитано.",
                _severity(path),
            ))

    for path in (
        "document_type", "number", "date",
        "supplier.name", "supplier.code", "supplier.iban",
        "buyer.name", "buyer.code",
        "total_without_vat", "vat", "total", "items",
    ):
        need(path, _get(document, path))
    for index, item in enumerate(document.get("items") or []):
        for key in ("name", "unit", "quantity", "price", "amount"):
            need(f"items.{index}.{key}", item.get(key))
    return issues


def _unreadable(document: dict) -> list[Issue]:
    return [
        Issue(
            path, "unreadable",
            f"Поле «{path}» є в документі, але модель не змогла його прочитати.",
            _severity(path),
        )
        for path in document.get("unreadable_fields") or []
    ]


def _unparsed(document: dict) -> list[Issue]:
    return [
        Issue(path, "unparsed", f"Значення «{raw}» у полі «{path}» не вдалося розпізнати.", _severity(path))
        for path, raw in (document.get("unparsed") or {}).items()
    ]


def _supplier(document: dict, suppliers: list[dict]) -> tuple[list[Issue], dict | None]:
    supplier = document.get("supplier") or {}
    code, iban, name = supplier.get("code"), supplier.get("iban"), supplier.get("name")
    issues = []

    if code:
        problem = _code_issue("supplier.code", code)
        if problem:
            issues.append(problem)

    if iban:
        if not re.fullmatch(r"UA\d{27}", iban):
            issues.append(Issue(
                "supplier.iban", "iban_format",
                f"IBAN {_mask(iban)} має бути «UA» і 27 цифр, разом 29 символів.",
            ))
        elif not iban_checksum_ok(iban):
            issues.append(Issue(
                "supplier.iban", "iban_checksum",
                f"IBAN {_mask(iban)} не проходить контрольне число (mod 97).",
            ))

    entry = next((s for s in suppliers if s["code"] == code), None) if code else None
    if code and entry is None:
        issues.append(Issue("supplier.code", "supplier_registry", f"Постачальника з кодом {code} немає в довіднику."))
    if entry:
        if iban and iban != entry["iban"]:
            diff = [str(i + 1) for i, (a, b) in enumerate(zip(iban, entry["iban"])) if a != b]
            if len(iban) == len(entry["iban"]) and diff:
                where = f"відрізняються символи на позиціях {', '.join(diff)}"
            else:
                where = "довжина або склад відрізняються"
            issues.append(Issue(
                "supplier.iban", "iban_registry",
                f"IBAN {_mask(iban)} не збігається з IBAN постачальника в довіднику ({_mask(entry['iban'])}): {where}.",
            ))
        if name and _compact(name) != _compact(entry["name"]):
            issues.append(Issue(
                "supplier.name", "supplier_registry",
                f"Назва «{name}» відрізняється від назви в довіднику «{entry['name']}».",
                "warning",
            ))
    return issues, entry


def _buyer(document: dict, company: dict) -> list[Issue]:
    buyer = document.get("buyer") or {}
    code, name = buyer.get("code"), buyer.get("name")
    issues = []
    if code:
        problem = _code_issue("buyer.code", code)
        if problem:
            issues.append(problem)
        if code != company["code"]:
            issues.append(Issue(
                "buyer.code", "buyer",
                f"Рахунок виставлено покупцеві з кодом {code}, а має бути «{company['name']}» ({company['code']}).",
            ))
        elif name and _compact(name) != _compact(company["name"]):
            issues.append(Issue(
                "buyer.name", "buyer",
                f"Назва покупця «{name}» відрізняється від «{company['name']}».",
                "warning",
            ))
    return issues


def _arithmetic(document: dict, entry: dict | None) -> list[Issue]:
    issues = []
    items = document.get("items") or []

    amounts = []
    for index, item in enumerate(items):
        quantity, price, amount = _dec(item.get("quantity")), _dec(item.get("price")), _dec(item.get("amount"))
        amounts.append(amount)
        if quantity is None or price is None or amount is None:
            continue
        expected = (quantity * price).quantize(CENT, ROUND_HALF_UP)
        if abs(expected - amount) > TOLERANCE:
            issues.append(Issue(
                f"items.{index}.amount", "arithmetic_line",
                f"Кількість {quantity} × ціна {price} = {expected}, а в рядку надруковано {amount}.",
            ))

    base = _dec(document.get("total_without_vat"))
    vat = _dec(document.get("vat"))
    total = _dec(document.get("total"))

    if base is not None and items and all(a is not None for a in amounts):
        summed = sum(amounts, Decimal("0"))
        if abs(summed - base) > TOLERANCE:
            issues.append(Issue(
                "total_without_vat", "arithmetic_sum",
                f"Сума рядків {summed}, а «разом без ПДВ» надруковано {base}.",
            ))

    if base is not None and vat is not None:
        expected_vat = (base * VAT_RATE).quantize(CENT, ROUND_HALF_UP)
        if entry is None:
            allowed = [expected_vat, Decimal("0")]
        elif entry.get("vat_payer"):
            allowed = [expected_vat]
        else:
            allowed = [Decimal("0")]
        if not any(abs(vat - a) <= TOLERANCE for a in allowed):
            issues.append(Issue(
                "vat", "arithmetic_vat",
                f"ПДВ має бути {' або '.join(str(a) for a in allowed)}, а надруковано {vat}.",
            ))

    if base is not None and vat is not None and total is not None:
        if abs(base + vat - total) > TOLERANCE:
            issues.append(Issue(
                "total", "arithmetic_total",
                f"Разом без ПДВ {base} + ПДВ {vat} = {base + vat}, а «до сплати» надруковано {total}.",
            ))
    return issues


def _dates(document: dict) -> list[Issue]:
    issues = []
    issued = None
    if document.get("date"):
        issued = date.fromisoformat(document["date"])
        if issued > date.today():
            issues.append(Issue("date", "date", f"Дата рахунку {issued.isoformat()} у майбутньому."))
    if issued and document.get("valid_until"):
        until = date.fromisoformat(document["valid_until"])
        if until < issued:
            issues.append(Issue(
                "valid_until", "date",
                f"Строк дії {until.isoformat()} раніше за дату рахунку {issued.isoformat()}.",
            ))
    return issues


def check(document: dict) -> list[Issue]:
    company, suppliers = _reference()

    doc_type = document.get("document_type")
    if doc_type and doc_type != INVOICE:
        return [Issue(
            "document_type", "document_type",
            f"Це не рахунок на оплату, а «{doc_type}»: такий документ не передається в реєстр платежів.",
        )]

    skip = set(document.get("unreadable_fields") or []) | set((document.get("unparsed") or {}).keys())

    supplier_issues, entry = _supplier(document, suppliers)

    issues = []
    issues += _required(document, skip)
    issues += _unreadable(document)
    issues += _unparsed(document)
    issues += supplier_issues
    issues += _buyer(document, company)
    issues += _arithmetic(document, entry)
    issues += _dates(document)
    return issues