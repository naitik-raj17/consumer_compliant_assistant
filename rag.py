import logging
import re
from datetime import date

import numpy as np
import requests

import config
import db
import kb
from classifier import FORUM_NAMES, FORUM_SECTION, forum_heading, format_inr

log = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z]{4,}")


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


def retrieve(query: str, k: int = config.TOP_K) -> list[dict]:
    rows = db.all_chunks()
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


def fill(body: str, values: dict) -> str:
    for key, val in values.items():
        body = body.replace("{" + key + "}", str(val))
    return body


def _first_sentence(text: str, limit: int = 300) -> str:
    m = re.match(r"(.+?[.;])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "..."


def fallback_grounds(case: dict, chunks: list[dict]) -> str:
    forum = case["forum"]
    loc = ", ".join(p for p in (case.get("district"), case["state"]) if p)
    lines = ["The acts and omissions of the Opposite Party amount to deficiency in service under "
             "Section 2(11) and/or an unfair trade practice under Section 2(47) of the Consumer "
             "Protection Act, 2019, violating the Complainant's rights under Section 2(9)."]
    for c in chunks:
        lines.append(f"Reliance is placed on {_first_sentence(c['text'])}")
    lines.append(f"This Commission has pecuniary jurisdiction under Section {FORUM_SECTION.get(forum, '34')} "
                 f"as the value of goods/services paid as consideration is Rs. {format_inr(case['value'])}, "
                 f"and territorial jurisdiction as the cause of action arose at {loc}.")
    lines.append("The complaint is filed within the period of two years prescribed by Section 69 of the Act.")
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
    skeleton = fill(template_body, {**vals, "grounds": "[Write numbered legal grounds citing the sections below]"})
    context = "\n".join(f"[{i}] ({c['source']}) {c['text']}" for i, c in enumerate(chunks, 1)) or "(none)"
    return f"""You are a legal drafting assistant for Indian consumer complaints under the Consumer Protection Act, 2019.
Draft the body of a consumer complaint to be filed before the {forum_heading(case['forum'], case['state'], case.get('district', ''))}.

Rules:
- Use ONLY the facts given. Do not invent names, dates, amounts or documents.
- Formal, plain English. No markdown, no asterisks.
- Output exactly these four headings, each on its own line, in this order:
FACTS OF THE CASE:
GROUNDS:
RELIEF SOUGHT:
VERIFICATION:
- In GROUNDS, cite the relevant sections from the legal context and state why this forum has jurisdiction.

CASE FACTS:
Complainant: {vals['complainant']}
Opposite Party: {vals['opposite_party']}
Category: {vals['category']}
Value of goods/services: Rs. {vals['value']}
Place: {vals['district']}, {vals['state']}
Forum: {vals['forum']} (Section {FORUM_SECTION.get(case['forum'], '34')})
Narrative: {case['text']}

LEGAL CONTEXT:
{context}

TEMPLATE TO FOLLOW (keep its structure, improve the wording, fill the grounds):
{skeleton}
"""


def call_llm(prompt: str) -> str:
    r = requests.post(f"{config.OLLAMA_URL}/api/generate",
                      json={"model": config.LLM_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.3, "num_ctx": 4096}},
                      timeout=config.LLM_TIMEOUT)
    if not r.ok:
        raise kb.OllamaError(f"Generation failed ({r.status_code}): {r.text[:200]}")
    text = r.json().get("response", "")
    return re.sub(r"[*#`]+", "", text).strip()


def fallback_draft(case: dict, user: dict, template_body: str, chunks: list[dict]) -> str:
    return fill(template_body, {**template_values(case, user), "grounds": fallback_grounds(case, chunks)})


def generate_draft(case: dict, user: dict) -> dict:
    """Returns {draft, used_llm, sources, note}. Never raises for Ollama problems."""
    tpl = db.get_template_for_category(case["category"])
    body = tpl["body"] if tpl else "FACTS OF THE CASE:\n{facts}\n\nGROUNDS:\n{grounds}\n\nRELIEF SOUGHT:\n\nVERIFICATION:\n"
    chunks = retrieve(case["text"])
    sources = [c["source"] for c in chunks]
    note = ""
    if ollama_up():
        try:
            draft = call_llm(build_prompt(case, user, body, chunks))
            if len(draft) > 200 and "GROUNDS" in draft.upper():
                return {"draft": draft, "used_llm": True, "sources": sources, "note": "Drafted with local LLM."}
            note = "LLM output was incomplete; used template instead."
        except (requests.RequestException, kb.OllamaError, ValueError) as e:
            log.warning("LLM drafting failed: %s", e)
            note = f"LLM failed ({e}); used template instead."
    else:
        note = "Ollama is not reachable; draft filled from template."
    return {"draft": fallback_draft(case, user, body, chunks), "used_llm": False, "sources": sources, "note": note}
