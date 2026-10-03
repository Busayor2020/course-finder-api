"""Pure cleaning functions: text in, clean value out. No database, no pandas.

Each function returns None when it cannot make sense of its input, and the
pipeline turns that None into a rejection reason. Keeping them pure makes every
messy case a one-line unit test.
"""

import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

COUNTRY_ALIASES = {
    "uk": "UK",
    "united kingdom": "UK",
    "great britain": "UK",
    "england": "UK",
    "scotland": "UK",
    "wales": "UK",
    "northern ireland": "UK",
    "ca": "CA",
    "canada": "CA",
}

LEVEL_ALIASES = {
    "foundation": "Foundation",
    "foundation year": "Foundation",
    "undergraduate": "Undergraduate",
    "bachelor": "Undergraduate",
    "bachelors": "Undergraduate",
    "ba": "Undergraduate",
    "bsc": "Undergraduate",
    "beng": "Undergraduate",
    "llb": "Undergraduate",
    "masters": "Masters",
    "master's": "Masters",
    "ma": "Masters",
    "msc": "Masters",
    "mba": "Masters",
    "meng": "Masters",
    "llm": "Masters",
    "mph": "Masters",
    "phd": "PhD",
    "doctorate": "PhD",
}

STUDY_MODE_ALIASES = {
    "": "full_time",  # most courses are full time, so a blank means full time
    "full time": "full_time",
    "full-time": "full_time",
    "ft": "full_time",
    "part time": "part_time",
    "part-time": "part_time",
    "pt": "part_time",
}

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip

# The fields that describe a course. If any of them changes, the hash changes
# and the pipeline updates the row. The lookup key (university, slug, level)
# is deliberately not here: a different key is a different course.
HASH_FIELDS = (
    "title",
    "subject_area",
    "duration_months",
    "study_mode",
    "intakes",
    "tuition_fee_international",
    "currency",
    "ielts_min",
    "source_url",
)


def _key(value: str) -> str:
    """Lowercase and collapse whitespace, for looking a value up in an alias table."""
    return " ".join(value.lower().split())


def normalize_country(value: str) -> str | None:
    return COUNTRY_ALIASES.get(_key(value))


def normalize_level(value: str) -> str | None:
    # "BSc (Hons)" and "BSc" are the same level.
    return LEVEL_ALIASES.get(_key(value.replace("(Hons)", "").replace("(hons)", "")))


def normalize_study_mode(value: str) -> str | None:
    return STUDY_MODE_ALIASES.get(_key(value))


def parse_fee(value: str, country: str | None) -> tuple[Decimal | None, str | None]:
    """Turn "£18,500", "CAD 32,000" or "$29,450" into (amount, currency).

    The currency comes from a symbol or code in the text if there is one,
    otherwise from the university's country. "$" means CAD: it is the only
    dollar currency this service covers.
    """
    text = value.upper()
    if "£" in text or "GBP" in text:
        currency = "GBP"
    elif "$" in text or "CAD" in text:
        currency = "CAD"
    else:
        currency = {"UK": "GBP", "CA": "CAD"}.get(country)

    number = re.sub(r"[^\d.\-]", "", text)  # drop symbols, codes and thousands separators
    try:
        amount = Decimal(number).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None, currency
    return amount, currency


def parse_ielts(value: str) -> Decimal | None:
    if not re.fullmatch(r"\d+(\.\d+)?", value):  # rejects "abc", "NaN", "Infinity"
        return None
    return Decimal(value).quantize(Decimal("0.1"))


def parse_duration_months(value: str) -> int | None:
    """Turn "12", "12 months" or "1 year" into a number of months."""
    match = re.fullmatch(r"(\d+)\s*(months?|years?)?", _key(value))
    if not match:
        return None
    number, unit = int(match.group(1)), match.group(2) or "months"
    return number * 12 if unit.startswith("year") else number


def parse_intakes(value: str) -> list[str] | None:
    """Turn "Sept; Jan" or "september, january" into ["January", "September"].

    Months come back in calendar order with duplicates removed, so the same
    intakes always produce the same list (and therefore the same hash).
    Returns None if any part is not a recognisable month.
    """
    parts = [part for part in re.split(r"[,;/|]", value) if part.strip()]
    found = set()
    for part in parts:
        prefix = _key(part)[:3]
        month = next((m for m in MONTHS if m.lower().startswith(prefix)), None)
        if len(prefix) < 3 or month is None:
            return None
        found.add(month)
    return [month for month in MONTHS if month in found]


def slugify(value: str) -> str:
    """ "Université de Montréal" -> "universite-de-montreal", "King's" -> "kings"."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_text = ascii_text.replace("'", "")
    ascii_text = ascii_text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def row_hash(row: dict) -> str:
    """SHA-256 of a course's normalised business fields.

    The fields are serialised as sorted-key JSON, so the hash only depends on
    the values, never on dict order. Decimals are written as strings with a
    fixed number of decimal places, so 18500 and 18500.00 hash the same.
    """
    fields = {name: row[name] for name in HASH_FIELDS}
    payload = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
