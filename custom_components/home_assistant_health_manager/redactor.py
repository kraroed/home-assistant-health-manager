import re
from collections import Counter

PATTERNS = [
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("assignment_secret", re.compile(r"""(?i)\b(password|passwd|token|api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token)\b(\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;]+)""")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("mac_address", re.compile(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b", re.I)),
    ("ipv4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    ("ipv6", re.compile(r"(?<![\\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\\w:])", re.I)),
    ("url_credentials", re.compile(r"(https?://)[^/\s:@]+:[^@\s/]+@", re.I)),
    ("coordinates", re.compile(r"(?<!\d)-?(?:[0-8]?\d(?:\.\d{3,})|90(?:\.0+)?),\s*-?(?:1[0-7]\d(?:\.\d{3,})|[1-9]?\d(?:\.\d{3,})|180(?:\.0+)?)")),
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)),
    ("entity_id", re.compile(r"\b[a-z][a-z0-9_]*\.[a-z0-9_]+\b", re.I)),
    ("home_path", re.compile(r"(?i)(/home/|/Users/)[^/\s]+")),
    ("windows_user_path", re.compile(r"(?i)([A-Z]:\\Users\\)[^\\\s]+")),
    ("long_token", re.compile(r"\b(?=[A-F0-9_-]{32,}\b)(?=.*[A-F])(?=.*\d)[A-F0-9_-]{32,}\b", re.I)),
]


def redact_text(value):
    counts = Counter()
    text = value
    for category, pattern in PATTERNS:
        def replace(match, category=category):
            counts[category] += 1
            if category == "assignment_secret":
                return f"{match.group(1)}{match.group(2)}<REDACTED>"
            if category == "url_credentials":
                return f"{match.group(1)}<REDACTED>@"
            if category == "home_path":
                return f"{match.group(1)}<REDACTED>"
            if category == "windows_user_path":
                return f"{match.group(1)}<REDACTED>"
            return f"<REDACTED:{category}>"
        text = pattern.sub(replace, text)
    return text, dict(counts)


def redact_object(value):
    totals = Counter()

    def walk(item):
        if isinstance(item, str):
            cleaned, counts = redact_text(item)
            totals.update(counts)
            return cleaned
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, dict):
            return {str(key): walk(child) for key, child in item.items()}
        return item

    return walk(value), dict(totals)
