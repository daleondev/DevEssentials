"""Parser for the 'Benchmark Write OS' / 'Benchmark Monitor Outputs' stat blocks."""
from __future__ import annotations

import re

from .common import parse_bytes

_SECTION_RE = re.compile(r"^-+\s*([A-Za-z0-9 /]+?)\s*-+$")
_KV_RE = re.compile(r"^\s*([A-Za-z0-9_ ]+?):\s*(.+?)\s*$")
RTT_KEYS = ("min", "max", "mean", "stddev", "p50", "p90", "p99", "p999")


def parse_blocks(lines: list[str]) -> dict[str, dict[str, float]]:
    """Return ``{section_name: {field: numeric_value}}``."""
    blocks: dict[str, dict[str, float]] = {}
    current: str | None = None
    for raw in lines:
        ln = raw.strip()
        if not ln:
            continue
        m_sec = _SECTION_RE.match(ln)
        if m_sec:
            name = m_sec.group(1).strip()
            if name and set(name) != {"="}:
                current = name
                blocks.setdefault(current, {})
            else:
                current = None
            continue
        if ln.startswith("=") or ln.startswith("-"):
            continue
        if current is None:
            continue
        m_kv = _KV_RE.match(ln)
        if not m_kv:
            continue
        key = m_kv.group(1).strip().lower()
        value = m_kv.group(2).strip()
        key = (
            key.replace("num samples", "n")
            .replace("min load", "min").replace("max load", "max").replace("mean load", "mean")
            .replace("min usage", "min").replace("max usage", "max").replace("mean usage", "mean")
        )
        try:
            if value.endswith("%"):
                num = float(value.rstrip("%").strip())
            elif value.endswith("ms"):
                num = float(value[:-2].strip())
            elif "Bytes" in value or value.endswith("B"):
                num = parse_bytes(value)
            else:
                num = float(value.split()[0])
        except ValueError:
            continue
        blocks[current][key] = num
    return blocks
