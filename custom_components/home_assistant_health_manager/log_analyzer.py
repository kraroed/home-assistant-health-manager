import re
from collections import Counter

LEVEL_RE = re.compile(r"\b(CRITICAL|FATAL|ERROR|WARNING|WARN)\b", re.I)
TIMESTAMP_PREFIX = re.compile(r"^\s*\S+\s+\S+\s+")


def analyze_log(log_text):
    if not log_text:
        return {
            "available": False,
            "line_count": 0,
            "level_counts": {},
            "top_messages": [],
        }

    counts = Counter()
    messages = Counter()
    for line in log_text.splitlines():
        match = LEVEL_RE.search(line)
        if not match:
            continue
        level = match.group(1).upper()
        counts["WARNING" if level == "WARN" else level] += 1
        normalized = TIMESTAMP_PREFIX.sub("", line)
        normalized = LEVEL_RE.sub("<LEVEL>", normalized, count=1)
        messages[normalized[:240]] += 1

    return {
        "available": True,
        "line_count": len(log_text.splitlines()),
        "level_counts": dict(counts),
        "top_messages": [
            {"message": message, "count": count}
            for message, count in messages.most_common(20)
        ],
    }
