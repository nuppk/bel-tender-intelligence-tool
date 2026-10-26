"""
scorer.py
---------
MCDA priority score (0-100). Every axis is scored 0-100 where HIGHER = MORE FAVOURABLE
(i.e. lower risk / lower effort), so the final score maps onto the status labels:

    Priority = Financial*0.30 + Time*0.25 + Technical*0.20 + Compliance*0.15 + Logistics*0.10
"""
from extractor import (NOT_FOUND, days_left, parse_money, parse_percent,
                       parse_duration_days)

WEIGHTS = {
    "Financial Risk": 0.30,
    "Time Urgency": 0.25,
    "Technical Complexity": 0.20,
    "Compliance Burden": 0.15,
    "Logistics Effort": 0.10,
}

HIGH_TECH_WORDS = ["radar", "electronic warfare", "ew ", "avionics", "sonar", "missile",
                   "communication", "jammer", "fire control", "transponder", "satcom",
                   "simulator", "encrypt", "phased array", "seeker"]


def _clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _has(v):
    return v is not None and v != NOT_FOUND


def _is_negative(v):
    return str(v).lower().startswith(("not applicable", "nil", "exempt", "waived", "no "))


def financial_score(p):
    risk = 20                                           # baseline
    pbg = parse_percent(p.get("pbg"))
    if pbg is not None:
        risk += 40 if pbg >= 10 else 28 if pbg >= 5 else 15
    elif _has(p.get("pbg")) and not _is_negative(p["pbg"]):
        risk += 25
    emd = p.get("emd")
    if _has(emd) and not _is_negative(emd):
        amt = parse_money(emd)
        pct = parse_percent(emd)
        if amt is not None:
            risk += 25 if amt >= 1e6 else 15 if amt >= 1e5 else 8
        elif pct is not None:
            risk += 20 if pct >= 3 else 10
        else:
            risk += 10
    ld = parse_percent(p.get("ld_percent"))
    if ld is not None:
        risk += 20 if ld >= 10 else 12 if ld >= 5 else 6
    pay = str(p.get("payment_terms", "")).lower()
    if _has(p.get("payment_terms")) and "advance" not in pay:
        risk += 8                                       # payment only after delivery
    return _clamp(100 - risk)


def time_score(p):
    d = days_left(p.get("deadline"))
    if d is None:
        return 50, None
    if d < 0:
        return 0, d
    for limit, score in ((3, 5), (7, 15), (14, 40), (30, 65), (60, 85)):
        if d <= limit:
            return score, d
    return 95, d


def technical_score(p):
    risk = 25
    blob = " ".join(str(p.get(k, "")) for k in ("equipment", "scope")).lower()
    hits = sum(1 for w in HIGH_TECH_WORDS if w in blob)
    risk += min(hits * 15, 45)
    scope = p.get("scope")
    if _has(scope):
        risk += 10 if len(scope) > 100 else 5
    qty = parse_money(p.get("quantity"))                # reuses number parser
    if qty is not None:
        risk += 15 if qty >= 50 else 8 if qty >= 10 else 3
    wr = parse_duration_days(p.get("warranty"))
    if wr is not None:
        risk += 10 if wr >= 730 else 5
    if _has(p.get("bid_type")) and p["bid_type"].lower().startswith(("two", "dual")):
        risk += 8
    return _clamp(100 - risk)


def compliance_score(p):
    risk = 10
    for key, pts in (("nda", 25), ("pcip", 25), ("inspection", 25)):
        if _has(p.get(key)) and not _is_negative(p[key]):
            risk += pts
    if _has(p.get("bid_validity")):
        days = parse_duration_days(p["bid_validity"])
        risk += 10 if days and days >= 120 else 5
    return _clamp(100 - risk)


def logistics_score(p):
    risk = 15
    dd = parse_duration_days(p.get("delivery_period"))
    if dd is not None:
        risk += 40 if dd <= 60 else 25 if dd <= 120 else 10
    cons = p.get("consignee")
    if _has(cons):
        risk += 20 if (cons.count(",") >= 3 or " and " in cons.lower()) else 8
    if _has(p.get("inspection")):
        risk += 10
    return _clamp(100 - risk)


def status_label(score, days):
    if days is not None and days < 7:
        return "CRITICAL" if days >= 0 else "CRITICAL (Expired)"
    if score >= 75:
        return "Favourable"
    if score >= 55:
        return "Moderate"
    if score >= 35:
        return "Caution"
    return "High Risk"


def urgency_flag(days):
    if days is None:
        return ""
    if days < 0:
        return "EXPIRED"
    if days < 3:
        return "CRITICAL"
    if days < 7:
        return "URGENT"
    return ""


def score_tender(params):
    t_score, days = time_score(params)
    axes = {
        "Financial Risk": financial_score(params),
        "Time Urgency": t_score,
        "Technical Complexity": technical_score(params),
        "Compliance Burden": compliance_score(params),
        "Logistics Effort": logistics_score(params),
    }
    total = round(sum(axes[k] * WEIGHTS[k] for k in axes), 1)
    return {
        "priority_score": total,
        "axes": axes,
        "days_left": days,
        "status": status_label(total, days),
        "flag": urgency_flag(days),
    }
