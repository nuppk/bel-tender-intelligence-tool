"""
extractor.py
------------
TOC-first PDF skimming + 20-parameter regex extraction.

Pipeline
    1. toc_page_filter()   -> PyMuPDF reads the PDF's internal table of contents
                              and picks the 50-150 pages that matter (no rendering).
    2. extract_text()      -> pdfplumber extracts text ONLY from those pages.
    3. extract_parameters()-> 60+ regex patterns pull the 20 procurement parameters.
"""
import io
import re
from datetime import datetime

try:
    import pymupdf as fitz          # new import name (PyMuPDF >= 1.24.3)
except ImportError:                 # pragma: no cover
    import fitz
import pdfplumber

MAX_PAGES = 150          # hard cap on pages that get text-extracted
FALLBACK_HEAD = 40       # no TOC -> first N pages ...
FALLBACK_TAIL = 20       # ... and last N pages

# Sections of a tender that carry the parameters we need
TOC_KEYWORDS = [
    "notice inviting", "nit", "invitation", "bid data", "bid details", "summary",
    "scope", "schedule of requirement", "delivery", "eligibility", "qualification",
    "special conditions", "scc", "general conditions", "gcc", "commercial",
    "payment", "emd", "earnest", "performance", "guarantee", "liquidated",
    "warranty", "nda", "non-disclosure", "pcip", "inspection", "consignee",
    "technical specification", "bid validity", "instructions to bidders",
]

# --------------------------------------------------------------------------- #
# 1. TOC scan
# --------------------------------------------------------------------------- #
def toc_page_filter(pdf_bytes):
    """Return (sorted 0-based page list, total_pages, used_toc: bool)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    toc = doc.get_toc(simple=True)          # [[level, title, page(1-based)], ...]
    doc.close()

    if total <= MAX_PAGES:                  # small tender: just read it all
        return list(range(total)), total, bool(toc)

    pages = set()
    if toc:
        for i, (level, title, start) in enumerate(toc):
            if not any(k in title.lower() for k in TOC_KEYWORDS):
                continue
            # section ends where the next entry of same-or-higher level begins
            end = total + 1
            for nxt_level, _, nxt_start in toc[i + 1:]:
                if nxt_level <= level:
                    end = nxt_start
                    break
            pages.update(range(max(start, 1) - 1, min(end - 1, total)))
        used_toc = bool(pages)
    else:
        used_toc = False

    if not pages:                           # fallback when TOC missing / useless
        pages.update(range(min(FALLBACK_HEAD, total)))
        pages.update(range(max(total - FALLBACK_TAIL, 0), total))

    pages.update(range(min(5, total)))      # cover page / NIT is always useful
    return sorted(pages)[:MAX_PAGES], total, used_toc


# --------------------------------------------------------------------------- #
# 2. Text extraction (selected pages only)
# --------------------------------------------------------------------------- #
def extract_text(pdf_bytes, page_numbers):
    chunks = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for n in page_numbers:
            page = pdf.pages[n]
            try:
                chunks.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
            finally:
                page.flush_cache()          # keep RAM flat on big files
    return "\n".join(chunks)


# --------------------------------------------------------------------------- #
# 3. The 20-parameter regex engine
# --------------------------------------------------------------------------- #
_I = re.IGNORECASE
_DATE = (r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+\d{4}"
         r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})")
_MONEY = r"((?:Rs\.?|INR|₹)\s*[\d,]+(?:\.\d+)?(?:\s*(?:lakhs?|lacs?|crores?|cr))?)"

PATTERNS = {
    "tender_number": [
        r"(?:tender|nit|rfq|enquiry|bid)\s*(?:no\.?|number|ref(?:erence)?\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{4,})",
        r"(?:ref\.?\s*no\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-_.]{4,})",
        r"\b(GEM/\d{4}/B/\d+)\b",
    ],
    "customer": [
        r"(?:customer|purchaser|buyer|issued by|issuing authority|organi[sz]ation name)\s*[:\-]\s*([^\n]{4,80})",
        r"(?:department|ministry)\s*(?:name)?\s*[:\-]\s*([^\n]{4,80})",
    ],
    "equipment": [
        r"(?:item|equipment|nomenclature|description of (?:goods|stores)|subject)\s*[:\-]\s*([^\n]{4,120})",
        r"(?:supply of|procurement of|purchase of)\s+([^\n.]{4,120})",
    ],
    "quantity": [
        r"(?:quantity|qty\.?|no\.? of units)\s*[:\-]?\s*(\d[\d,]*\s*(?:nos?\.?|units?|sets?|pcs?|lots?)?)",
        r"(\d[\d,]*)\s*(?:nos\.?|units|sets)\s+(?:of|required)",
    ],
    "scope": [
        r"scope of (?:work|supply)\s*[:\-]?\s*([^\n]{10,200})",
        r"(?:the scope|scope) (?:includes?|comprises?|covers?)\s*[:\-]?\s*([^\n]{10,200})",
    ],
    "bid_type": [
        r"((?:single|two|dual)[\s\-]*(?:bid|packet|cover)(?:\s*system)?)",
        r"(limited tender enquiry|open tender|global tender|single tender|rate contract|rfq|reverse auction)",
    ],
    "deadline": [
        rf"(?:bid|tender|offer)?\s*(?:end|closing|due|submission)\s*date(?:\s*(?:and|&)\s*time)?\s*[:\-]?\s*{_DATE}",
        rf"last\s*date\s*(?:of|for)\s*(?:bid\s*)?submission\s*[:\-]?\s*{_DATE}",
        rf"(?:bids?|offers?)\s*(?:must|should|shall)\s*(?:be\s*)?(?:submitted|received)\s*(?:on or )?(?:before|by)\s*{_DATE}",
        rf"closing\s*on\s*{_DATE}",
    ],
    "bid_opening": [
        rf"(?:bid|tender|technical)?\s*opening\s*date(?:\s*(?:and|&)\s*time)?\s*[:\-]?\s*{_DATE}",
        rf"bids?\s*(?:will|shall)\s*be\s*opened\s*on\s*{_DATE}",
    ],
    "emd": [
        rf"(?:emd|earnest money(?: deposit)?)\s*(?:amount)?\s*[:\-]?\s*{_MONEY}",
        r"(?:emd|earnest money(?: deposit)?)[^\n]{0,40}?(\d+(?:\.\d+)?\s*%)",
        r"(?:emd|earnest money)\s*[:\-]?\s*(exempt(?:ed)?|not applicable|nil|waived)",
    ],
    "estimated_value": [
        rf"(?:estimated|approx(?:imate)?|tender)\s*(?:value|cost)\s*[:\-]?\s*{_MONEY}",
        rf"(?:total\s*)?(?:bid\s*)?value\s*[:\-]\s*{_MONEY}",
    ],
    "nda": [
        r"(non[\s\-]*disclosure agreement|\bNDA\b)[^\n]{0,60}",
        r"(confidentiality (?:undertaking|agreement))[^\n]{0,60}",
    ],
    "pcip": [
        r"(pcip|pre[\s\-]*contract integrity pact|integrity pact)[^\n]{0,60}",
    ],
    "pbg": [
        r"(?:pbg|performance (?:bank )?guarantee|performance security)[^\n]{0,60}?(\d+(?:\.\d+)?\s*%)",
        rf"(?:pbg|performance (?:bank )?guarantee)[^\n]{{0,40}}?{_MONEY}",
        r"(?:pbg|performance (?:bank )?guarantee|performance security)\s*[:\-]?\s*(required|applicable|not applicable|nil)",
    ],
    "consignee": [
        r"consignee\s*(?:details|name|address)?\s*[:\-]\s*([^\n]{4,120})",
        r"(?:delivery|destination)\s*(?:location|address|point)\s*[:\-]\s*([^\n]{4,120})",
        r"deliver(?:ed|y)?\s*(?:at|to)\s*[:\-]?\s*([A-Z][^\n]{4,100})",
    ],
    "warranty": [
        r"warranty\s*(?:period)?\s*[:\-]?\s*(?:of\s*)?(\d+\s*(?:years?|yrs?|months?))",
        r"(\d+\s*(?:years?|yrs?|months?))\s*(?:comprehensive\s*)?warranty",
        r"guarantee period\s*[:\-]?\s*(\d+\s*(?:years?|months?))",
    ],
    "ld_percent": [
        r"(?:liquidated damages|\bLD\b)[^\n]{0,80}?(\d+(?:\.\d+)?\s*%)",
        r"(\d+(?:\.\d+)?\s*%)\s*(?:per\s*(?:week|month|day))[^\n]{0,60}(?:delay|late)",
        r"(?:penalty|delay)[^\n]{0,60}?(\d+(?:\.\d+)?\s*%)",
    ],
    "payment_terms": [
        r"payment\s*terms?\s*[:\-]\s*([^\n]{6,160})",
        r"(\d{1,3}\s*%\s*(?:advance|on delivery|against|on acceptance|after)[^\n]{0,120})",
        r"payment\s*(?:shall|will)\s*be\s*(?:made)?\s*([^\n]{6,160})",
    ],
    "delivery_period": [
        r"delivery\s*(?:period|schedule|time)\s*[:\-]?\s*(?:within\s*)?(\d+\s*(?:weeks?|months?|days?))",
        r"(?:to be )?(?:delivered|supplied|completed)\s*within\s*(\d+\s*(?:weeks?|months?|days?))",
        r"(\d+\s*(?:weeks?|months?|days?))\s*from\s*(?:the\s*)?date\s*of\s*(?:order|contract|po)",
    ],
    "bid_validity": [
        r"bid\s*validity\s*[:\-]?\s*(?:of\s*)?(\d+\s*(?:days?|months?))",
        r"(?:offer|bid)s?\s*(?:shall|should|must)\s*(?:remain\s*)?valid\s*(?:for)?\s*(\d+\s*(?:days?|months?))",
        r"validity\s*(?:of\s*offer)?\s*[:\-]?\s*(\d+\s*days)",
    ],
    "inspection": [
        r"((?:pre[\s\-]*dispatch|third[\s\-]*party|stage|final|customer)\s*inspection[^\n]{0,80})",
        r"(inspection\s*(?:by|through)\s*[^\n]{4,80})",
        r"(\bDGQA\b|\bDGAQA\b|\bCEMILAC\b|\bRCMA\b)[^\n]{0,40}",
    ],
}

PARAM_ORDER = list(PATTERNS.keys())          # exactly 20 keys
assert len(PARAM_ORDER) == 20

COMPILED = {k: [re.compile(p, _I) for p in v] for k, v in PATTERNS.items()}
NOT_FOUND = "Not Found"


def _clean(s):
    return re.sub(r"\s+", " ", str(s)).strip(" :-.,;")


def extract_parameters(text):
    """Run every pattern list until one hits. Returns {param: value}."""
    out = {}
    for key in PARAM_ORDER:
        value = NOT_FOUND
        for rx in COMPILED[key]:
            m = rx.search(text)
            if not m:
                continue
            groups = [g for g in m.groups() if g]
            value = _clean(groups[0] if groups else m.group(0))
            if value:
                break
        out[key] = value or NOT_FOUND
    return out


# --------------------------------------------------------------------------- #
# Helpers used by scorer.py
# --------------------------------------------------------------------------- #
_DATE_FORMATS = [
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y", "%d.%m.%y",
    "%d %B %Y", "%d %b %Y", "%d %B, %Y", "%d %b, %Y",
    "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
]


def parse_date(s):
    if not s or s == NOT_FOUND:
        return None
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s.strip(), flags=_I)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def days_left(deadline_str, today=None):
    d = parse_date(deadline_str)
    if d is None:
        return None
    today = today or datetime.now()
    return (d.date() - today.date()).days


def parse_money(s):
    """'Rs. 5,00,000' -> 500000.0 ; '2 lakhs' -> 200000 ; '1.5 crore' -> 15000000."""
    if not s or s == NOT_FOUND:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr)?", s, _I)
    if not m:
        return None
    try:
        val = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    if unit.startswith(("lakh", "lac")):
        val *= 1e5
    elif unit.startswith(("crore", "cr")):
        val *= 1e7
    return val


def parse_percent(s):
    if not s or s == NOT_FOUND:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
    return float(m.group(1)) if m else None


def parse_duration_days(s):
    if not s or s == NOT_FOUND:
        return None
    m = re.search(r"(\d+)\s*(day|week|month|year|yr)", s, _I)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * {"day": 1, "week": 7, "month": 30, "year": 365, "yr": 365}[unit]


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def process_pdf(pdf_bytes):
    pages, total, used_toc = toc_page_filter(pdf_bytes)
    text = extract_text(pdf_bytes, pages)
    params = extract_parameters(text)
    found = sum(1 for v in params.values() if v != NOT_FOUND)
    return {
        "params": params,
        "meta": {
            "total_pages": total,
            "pages_processed": len(pages),
            "used_toc": used_toc,
            "params_found": found,
        },
    }
