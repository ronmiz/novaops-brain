"""Read the corpus and turn it into chunks with metadata. Pure Python — no AWS.

Permission metadata (spec section 12):
  * handbook/ carries `audience: all`, manager_playbook/ carries `audience: manager`.
  * The other five collections carry NO audience: absent means "unrestricted", not "deny".
  * Fail closed WITHIN the restricted collection: anything under manager_playbook/ is
    `manager` even if its front matter were missing or wrong.

Chunking: a document of <= 300 words is ONE chunk (all 70 operational documents);
longer ones (handbook, manager playbook) are split by markdown section (`## ...`), and
a long section is windowed with overlap. See docs/adr/0003-chunking-by-measurement.md.
"""
import re
from pathlib import Path

RESTRICTED_COLLECTIONS = {"manager_playbook"}
WHOLE_DOCUMENT = "(whole document)"
MAX_WORDS = 300
OVERLAP_WORDS = 50
_DATE = re.compile(
    r"^(?:last_updated|last updated|effective date|date)\s*:\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.MULTILINE,
)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a '---'-fenced `key: value` header from the body (Lesson 7's parser)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, parts[2].lstrip("\n")


def audience_for(collection: str, meta: dict) -> str:
    if collection in RESTRICTED_COLLECTIONS or meta.get("audience") == "manager":
        return "manager"
    return "all"


def doc_date(meta: dict, body: str) -> str | None:
    """The document's own date, so 'newer overrides older' can be reasoned about."""
    if meta.get("last_updated"):
        return meta["last_updated"]
    match = _DATE.search(body[:1500])
    return match.group(1) if match else None


def split_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (title, [(section_name, section_text), ...]). Text before the first
    `## ` heading (key: value header lines in contracts, offer letters...) is 'Header'."""
    title, sections, name, lines = "", [], "Header", []
    for line in body.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((name, "\n".join(lines).strip()))
            name, lines = line[3:].strip(), []
        else:
            lines.append(line)
    sections.append((name, "\n".join(lines).strip()))
    return title, [(n, t) for n, t in sections if t]


def window(text: str) -> list[str]:
    words = text.split()
    if len(words) <= MAX_WORDS:
        return [text]
    out, start = [], 0
    while start < len(words):
        out.append(" ".join(words[start:start + MAX_WORDS]))
        if start + MAX_WORDS >= len(words):
            break
        start += MAX_WORDS - OVERLAP_WORDS
    return out


def people_in(body: str, people: dict[str, str]) -> list[str]:
    """Employee ids of everyone the document names in full (#35). Documents name people,
    almost never their ids, so the id is attached here, from the employee table."""
    return sorted({emp_id for name, emp_id in people.items() if name in body})


def load_chunks(docs_dir: Path, people: dict[str, str] | None = None) -> list[dict]:
    """One record per chunk. `source` is `documents/<collection>/<file>.md` — the same
    form GOLDEN-DATASETS.json uses, so citations compare 1:1 with the expectations.
    `people` (full name -> employee id) tags every chunk of a document with the ids of
    the people it names — a document about Maya Cohen is about E001 in every chunk."""
    chunks = []
    for path in sorted(docs_dir.glob("*/*.md")):
        collection = path.parent.name
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title, sections = split_sections(body)
        base = {
            "source": f"documents/{collection}/{path.name}",
            "collection": collection,
            "title": title or path.stem,
            "audience": audience_for(collection, meta),
            "doc_date": doc_date(meta, body),
            "people": people_in(body, people or {}),
        }
        # Short documents stay WHOLE. Measured (evals/retrieval_eval.py): splitting a
        # 120-word KB article into 5 sections left "MFA" only in the title, so the
        # reranker scored the right article 0.4 and cut it. All 70 operational docs are
        # <= MAX_WORDS; only the handbook and manager playbook are split by section.
        if len(body.split()) <= MAX_WORDS:
            chunks.append({**base, "section": WHOLE_DOCUMENT, "text": body.strip()})
            continue
        for section, text in sections:
            for piece in window(text):
                chunks.append({**base, "section": section, "text": piece})
    return chunks


def embedding_text(chunk: dict) -> str:
    """What gets embedded: the chunk plus its title/section, so a short section like
    'Escalation' still knows which document it belongs to."""
    return f"{chunk['title']} — {chunk['section']}\n{chunk['text']}"
