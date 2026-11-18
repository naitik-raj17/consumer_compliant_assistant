import logging
import re
from datetime import date

import numpy as np
import requests

import config
import db
import kb
from classifier import FORUM_NAMES, FORUM_SECTION, forum_heading, format_inr
from pdf import _HEAD_RE, _KEYMAP

log = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z]{4,}")
JURISDICTION_SECTIONS = set(FORUM_SECTION.values())          # {"34", "47", "58"}
CORE_SECTIONS = ["2(11)", "2(47)"]                            # deficiency, unfair trade practice
PROCEDURAL_SECTIONS = {"35", "69"}                            # kept out of LLM context; handled by fixed text
EXTRA_K = max(1, config.TOP_K - 2)                            # similarity picks on top of pinned sections
LIMITATION_GROUND = "The complaint is filed within the period of two years prescribed by Section 69 of the Act."
_LIMITATION_RE = re.compile(r"\blimitation\b|time[- ]barred|time[- ]limit|\btwo[- ]years?\b|\b2 years?\b|\bdelay\b.*\bcondon", re.I)
_SECTION_CITE = re.compile(r"Section\s+(\d+(?:\(\d+\))?)", re.I)
_MARKER = re.compile(r"\[\d+\]\s*(\([^)]*\.(?:txt|pdf)\)\s*)?|\([\w\-]+\.(?:txt|pdf)\)\s*", re.I)


def ollama_up() -> bool:
    try:
        return requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=config.PING_TIMEOUT).ok
    except requests.RequestException:
        return False


def _keyword_rank(query: str, rows: list[dict], k: int) -> list[dict]:
    q = set(_WORD.findall(query.lower()))
    scored = [(len(q & set(_WORD.findall(r["text"].lower()))), -i, r) for i, r in enumerate(rows)]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [r for _, _, r in scored[:k]]


def retrieve(query: str, k: int = config.TOP_K, rows: list[dict] | None = None) -> list[dict]:
    """Cosine top-k over kb_chunks; keyword overlap if embeddings/Ollama are unavailable."""
    rows = db.all_chunks() if rows is None else rows
    if not rows:
        return []
    embedded = [r for r in rows if r["embedding"]]
    if embedded:
        try:
            q = kb.embed([query], prefix=kb.QUERY_PREFIX)[0]
            same = [r for r in embedded if len(r["embedding"]) == q.nbytes]
            if same:
                m = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in same])
                scores = m @ q
                order = np.argsort(-scores)[:k]
                return [dict(same[i], score=float(scores[i])) for i in order]
        except kb.OllamaError as e:
            log.info("Vector search unavailable, using keyword ranking: %s", e)
    return _keyword_rank(query, rows, k)


def _section_of(chunk: dict) -> str | None:
    m = re.match(r"\s*Section\s+(\d+(?:\(\d+\))?)\s*\(", chunk["text"])
    return m.group(1) if m else None


def context_chunks(case: dict) -> list[dict]:
    """Pinned: the forum's jurisdiction section + 2(11) + 2(47). Then top similarity matches,
    never including another forum's jurisdiction section."""
    rows = db.all_chunks()
    own = FORUM_SECTION.get(case["forum"], "34")
    pinned_ids = {own, *CORE_SECTIONS}
    pinned = [r for r in rows if _section_of(r) in pinned_ids]
    pinned.sort(key=lambda r: [own, *CORE_SECTIONS].index(_section_of(r)))
    pool = [r for r in rows if r not in pinned
            and _section_of(r) not in JURISDICTION_SECTIONS | PROCEDURAL_SECTIONS]
    extra = retrieve(case["text"], k=EXTRA_K, rows=pool) if pool else []
    return pinned + extra


def fill(body: str, values: dict) -> str:
    for key, val in values.items():
        body = body.replace("{" + key + "}", str(val))
    return body


def _first_sentence(text: str, limit: int = 300) -> str:
    m = re.match(r"(.+?[.;])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "..."


def jurisdiction_ground(case: dict) -> str:
    loc = ", ".join(p for p in (case.get("district"), case["state"]) if p)
    return (f"This Commission has pecuniary jurisdiction under Section {FORUM_SECTION.get(case['forum'], '34')} "
            f"of the Act as the value of goods/services paid as consideration is Rs. {format_inr(case['value'])}, "
            f"and territorial jurisdiction as the cause of action arose at {loc}.")


def fallback_grounds(case: dict, chunks: list[dict]) -> str:
    lines = ["The acts and omissions of the Opposite Party amount to deficiency in service under "
             "Section 2(11) and/or an unfair trade practice under Section 2(47) of the Consumer "
             "Protection Act, 2019, violating the Complainant's rights under Section 2(9)."]
    own = FORUM_SECTION.get(case["forum"], "34")
    for c in chunks:
        if _section_of(c) != own:
            lines.append(f"Reliance is placed on {_first_sentence(c['text'])}")
    lines.append(jurisdiction_ground(case))
    lines.append(LIMITATION_GROUND)
    return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))


def template_values(case: dict, user: dict) -> dict:
    return {
        "complainant": user["name"],
        "opposite_party": case.get("opposite_party") or "the Opposite Party",
        "facts": case["text"],
        "value": format_inr(case["value"]),
        "state": case["state"],
        "district": case.get("district") or case["state"],
        "forum": FORUM_NAMES.get(case["forum"], case["forum"]),
        "category": case["category"],
        "date": date.today().strftime("%d-%m-%Y"),
    }


def build_prompt(case: dict, user: dict, template_body: str, chunks: list[dict]) -> str:
    vals = template_values(case, user)
    own = FORUM_SECTION.get(case["forum"], "34")
    others = ", ".join(sorted(JURISDICTION_SECTIONS - {own}))
    # Starting grounds without pasted definitions; the law text is in LEGAL CONTEXT only.
    skeleton = fill(template_body, {**vals, "grounds": fallback_grounds(case, [])})
    context = "\n".join(f"- {c['text']}" for c in chunks) or "(none)"
    return f"""You are a legal drafting assistant for Indian consumer complaints under the Consumer Protection Act, 2019.
Draft the body of a consumer complaint to be filed before the {forum_heading(case['forum'], case['state'], case.get('district', ''))}.

Rules:
- Use ONLY the facts given. Do not invent names, dates, amounts or documents.
- Refer to the parties only as "the Complainant" and "the Opposite Party"; never use he, she, his or her.
- Formal, plain English. No markdown, no asterisks.
- Output exactly these four headings, each on its own line, in this order:
FACTS OF THE CASE:
GROUNDS:
RELIEF SOUGHT:
VERIFICATION:
- GROUNDS must be 4 to 6 numbered points in your own words that apply the law to these facts.
  Do not restate or quote the definitions; say how the facts meet them.
  Explain why the facts amount to deficiency in service (Section 2(11)) and/or unfair trade practice (Section 2(47)).
- For jurisdiction cite ONLY Section {own}. Never mention Sections {others}.
- Do not copy the legal context word for word and do not write markers like [1] or file names.

CASE FACTS:
Complainant: {vals['complainant']}
Opposite Party: {vals['opposite_party']}
Category: {vals['category']}
Value of goods/services: Rs. {vals['value']}
Place: {vals['district']}, {vals['state']}
Forum: {vals['forum']} (jurisdiction under Section {own})
Narrative: {case['text']}

LEGAL CONTEXT:
{context}

TEMPLATE TO FOLLOW (keep its structure; rewrite GROUNDS to apply the law to the facts):
{skeleton}
"""


def call_llm(prompt: str) -> str:
    r = requests.post(f"{config.OLLAMA_URL}/api/generate",
                      json={"model": config.LLM_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.2, "num_ctx": 4096}},
                      timeout=config.LLM_TIMEOUT)
    if not r.ok:
        raise kb.OllamaError(f"Generation failed ({r.status_code}): {r.text[:200]}")
    text = r.json().get("response", "")
    return re.sub(r"[*#`]+", "", text).strip()


_PRONOUNS = [(re.compile(r"\b(?:she|he)\b"), "the Complainant"), (re.compile(r"\b(?:She|He)\b"), "The Complainant"),
             (re.compile(r"\b(?:her|his)\b"), "the Complainant's"), (re.compile(r"\b(?:Her|His)\b"), "The Complainant's"),
             (re.compile(r"\bhim\b"), "the Complainant"), (re.compile(r"\bherself|himself\b"), "the Complainant")]


def _neutral(line: str) -> str:
    """The small model ignores the no-pronoun rule; refer to the Complainant neutrally in grounds."""
    for pat, rep in _PRONOUNS:
        line = pat.sub(rep, line)
    return line.replace("the Complainant's's", "the Complainant's")


def sanitize_draft(draft: str, case: dict, fallback_verification: str = "") -> str:
    """Strip copied context markers, drop grounds citing another forum's jurisdiction section,
    guarantee a correct jurisdiction ground, renumber grounds, and restore a missing verification."""
    own = FORUM_SECTION.get(case["forum"], "34")
    wrong = JURISDICTION_SECTIONS - {own}
    out, grounds, section = [], [], None

    def flush_grounds():
        kept = [g for g in grounds if g.strip()]
        if not any(own in _SECTION_CITE.findall(g) for g in kept):
            kept.append(jurisdiction_ground(case))
        kept.append(LIMITATION_GROUND)
        for i, g in enumerate(kept, 1):
            out.append(f"{i}. {re.sub(r'^\s*(?:\d+[.)]\s*)?(?:[-•–]\s*)?', '', g).strip()}")
        out.append("")

    for line in draft.splitlines():
        m = _HEAD_RE.match(line)
        if m:
            if section == "grounds":
                flush_grounds()
            section = _KEYMAP[m.group(1)[0].upper()]
            out.append(line.strip())
            if m.group(2):
                (grounds if section == "grounds" else out).append(m.group(2))
            continue
        if section == "grounds":
            line = _neutral(_MARKER.sub("", line))
            if set(_SECTION_CITE.findall(line)) & wrong:
                log.info("Dropped ground citing wrong jurisdiction: %s", line[:120])
                continue
            if "69" in _SECTION_CITE.findall(line) or _LIMITATION_RE.search(line):
                log.info("Dropped LLM limitation ground (replaced by fixed text): %s", line[:120])
                continue
            grounds.append(line)
        else:
            out.append(line)
    if section == "grounds":
        flush_grounds()
    text = "\n".join(out).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if "VERIFICATION" not in text.upper() and fallback_verification:
        text += "\n\n" + fallback_verification
    return text


def fallback_draft(case: dict, user: dict, template_body: str, chunks: list[dict]) -> str:
    return fill(template_body, {**template_values(case, user), "grounds": fallback_grounds(case, chunks)})


def _verification_block(filled_template: str) -> str:
    idx = filled_template.upper().rfind("VERIFICATION")
    return filled_template[idx:].strip() if idx >= 0 else ""


def generate_draft(case: dict, user: dict) -> dict:
    """Returns {draft, used_llm, sources, note}. Never raises for Ollama problems."""
    tpl = db.get_template_for_category(case["category"])
    body = tpl["body"] if tpl else "FACTS OF THE CASE:\n{facts}\n\nGROUNDS:\n{grounds}\n\nRELIEF SOUGHT:\n\nVERIFICATION:\n"
    chunks = context_chunks(case)
    sources = [c["source"] for c in chunks]
    fallback = fallback_draft(case, user, body, chunks)
    note = ""
    if ollama_up():
        try:
            draft = call_llm(build_prompt(case, user, body, chunks))
            if len(draft) > 200 and "GROUNDS" in draft.upper():
                draft = sanitize_draft(draft, case, _verification_block(fallback))
                return {"draft": draft, "used_llm": True, "sources": sources, "note": "Drafted with local LLM."}
            note = "LLM output was incomplete; used template instead."
        except (requests.RequestException, kb.OllamaError, ValueError) as e:
            log.warning("LLM drafting failed: %s", e)
            note = f"LLM failed ({e}); used template instead."
    else:
        note = "Ollama is not reachable; draft filled from template."
    return {"draft": fallback, "used_llm": False, "sources": sources, "note": note}
