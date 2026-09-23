"""Turn page text into a stable form and find the passages that changed."""
import difflib
import hashlib
import re
import unicodedata

# Lines that change often without changing meaning (dates, "last updated" stamps, copyright years).
_NOISE = [
    re.compile(r"^(last\s+(updated|modified|revised)|effective\s+(date|as of)|updated)\b.{0,60}$", re.I),
    re.compile(r"^(©|\(c\)|copyright)\s*\d{4}.*$", re.I),
    re.compile(r"^[\W\d_]*$"),  # lines with no letters at all
]
MIN_LINE_CHARS = 3
MIN_MEANINGFUL_CHANGE_CHARS = 40  # smaller edits (typo fixes) are saved silently


def normalize(text: str) -> str:
    """Plain, stable text: no control characters, single spaces, one line per paragraph."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) >= MIN_LINE_CHARS:
            lines.append(line)
    return "\n".join(lines)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_noise(line: str) -> bool:
    return any(p.match(line) for p in _NOISE)


def changed_passages(old: str, new: str) -> tuple[list[str], list[str]]:
    """Return (removed_lines, added_lines), ignoring noise-only lines."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    removed, added = [], []
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(l for l in old_lines[i1:i2] if not _is_noise(l))
        if tag in ("replace", "insert"):
            added.extend(l for l in new_lines[j1:j2] if not _is_noise(l))
    return removed, added


def is_meaningful(removed: list[str], added: list[str]) -> bool:
    """True if the edit is bigger than a typo fix. Compares words, not positions."""
    old_words = " ".join(removed).split()
    new_words = " ".join(added).split()
    sm = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    changed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            changed += len(" ".join(old_words[i1:i2])) + len(" ".join(new_words[j1:j2]))
    return changed >= MIN_MEANINGFUL_CHANGE_CHARS


def clip(lines: list[str], limit: int) -> str:
    """Join lines, cutting cleanly at the limit."""
    out = "\n".join(lines)
    return out if len(out) <= limit else out[: limit - 1].rsplit(" ", 1)[0] + "…"
