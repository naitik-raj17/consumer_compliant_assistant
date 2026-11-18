import re

import config

KEYWORDS: dict[str, list[str]] = {
    "ecommerce": ["amazon", "flipkart", "myntra", "meesho", "snapdeal", "ajio", "nykaa", "online",
                  "order", "ordered", "delivery", "delivered", "e-commerce", "ecommerce", "website",
                  "seller", "courier", "replacement", "cash on delivery", "cod", "parcel", "package"],
    "banking": ["bank", "loan", "credit card", "debit card", "atm", "upi", "emi", "cheque", "insurance",
                "policy", "nbfc", "transaction", "kyc", "neft", "imps", "rtgs", "account debited",
                "unauthorised", "unauthorized", "interest rate", "fixed deposit", "premium"],
    "real_estate": ["builder", "flat", "apartment", "possession", "rera", "plot", "property",
                    "construction", "developer", "villa", "booking amount", "allotment", "housing",
                    "sale deed", "carpet area"],
    "medical": ["hospital", "doctor", "surgery", "treatment", "medical", "negligence", "clinic",
                "patient", "medicine", "diagnosis", "nursing home", "operation", "icu", "pathology",
                "dentist", "surgeon"],
    "telecom": ["mobile network", "sim", "network", "broadband", "recharge", "jio", "airtel",
                "vodafone", "bsnl", "internet", "telecom", "data pack", "postpaid", "prepaid",
                "call drop", "fibre", "fiber", "wifi", "dth"],
}

_PATTERNS = {cat: [re.compile(r"\b" + re.escape(k) + r"\b", re.I) for k in kws]
             for cat, kws in KEYWORDS.items()}

FORUM_NAMES = {
    "District": "District Consumer Disputes Redressal Commission",
    "State": "State Consumer Disputes Redressal Commission",
    "National": "National Consumer Disputes Redressal Commission",
}
FORUM_SECTION = {"District": "34", "State": "47", "National": "58"}


def classify_category(text: str) -> str:
    scores = {cat: sum(len(p.findall(text or "")) for p in pats) for cat, pats in _PATTERNS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def pick_forum(value: float) -> str:
    if value <= config.DISTRICT_LIMIT:
        return "District"
    if value <= config.STATE_LIMIT:
        return "State"
    return "National"


def classify(text: str, value: float) -> tuple[str, str]:
    return classify_category(text), pick_forum(value)


def forum_heading(forum: str, state: str = "", district: str = "") -> str:
    name = FORUM_NAMES.get(forum, forum)
    if forum == "District":
        loc = ", ".join(p for p in (district, state) if p)
        return f"{name}, {loc}" if loc else name
    if forum == "State":
        return f"{name}, {state}" if state else name
    return f"{name}, New Delhi"


def format_inr(value: float) -> str:
    """Indian digit grouping: 12,34,567.00"""
    neg = value < 0
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{'-' if neg else ''}{whole}.{frac}"
