"""Pure parsers for benchmark sample files.

Each function takes a path, returns a plain dict / DataFrame, and does no I/O
beyond ``read_lines``. Callers handle aggregation and plotting.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .common import parse_bytes, read_lines


# --------------------------------------------------------------------------- #
# build_*.txt
# --------------------------------------------------------------------------- #

_BUILD_ROW_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+):\s+([\d.]+\s*[KMG]?B(?:ytes)?)\s+"
    r"([\d.]+\s*[KMG]?B(?:ytes)?)\s+([\d.]+)%\s*$"
)


def parse_build(path: str) -> dict[str, dict[str, float]]:
    """Return ``{region: {used_B, total_B, pct}}`` from a build_*.txt file."""
    out: dict[str, dict[str, float]] = {}
    for line in read_lines(path):
        m = _BUILD_ROW_RE.match(line)
        if not m:
            continue
        region, used, total, pct = m.groups()
        out[region] = {
            "used_B": parse_bytes(used),
            "total_B": parse_bytes(total),
            "pct": float(pct),
        }
    return out


# --------------------------------------------------------------------------- #
# cpuload_*.txt
# --------------------------------------------------------------------------- #

_CPULOAD_ROW_RE = re.compile(
    r"^\|\s*\d{2}:\d{2}:\d{2}\s*\|\s*([\d.]+)%\s*\|"
)


def parse_cpuload_log(path: str) -> list[float]:
    """Return the list of CPU-load percent samples from a cpuload_*.txt file."""
    out: list[float] = []
    for line in read_lines(path):
        m = _CPULOAD_ROW_RE.match(line.strip())
        if m:
            out.append(float(m.group(1)))
    return out


# --------------------------------------------------------------------------- #
# heap.txt
# --------------------------------------------------------------------------- #

_HEAP_FIELDS = {
    "Total non-mmapped bytes (arena)": "arena",
    "# of free chunks (ordblks)": "ordblks",
    "# of free fastbin blocks (smblks)": "smblks",
    "# of mapped regions (hblks)": "hblks",
    "Bytes in mapped regions (hblkhd)": "hblkhd",
    "Max. total allocated space (usmblks)": "usmblks",
    "Free bytes held in fastbins (fsmblks)": "fsmblks",
    "Total allocated space (uordblks)": "uordblks",
    "Total free space (fordblks)": "fordblks",
    "Topmost releasable block (keepcost)": "keepcost",
    "SBRK Total Size": "sbrk_total",
    "SBRK Remaining Size": "sbrk_remaining",
}


def parse_heap(path: str) -> dict[str, float]:
    """Return ``{field_key: bytes_or_count}`` from a heap.txt file.

    Counts (ordblks, smblks, hblks) are returned as ints in float form.
    """
    out: dict[str, float] = {}
    for line in read_lines(path):
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        key = _HEAP_FIELDS.get(label.strip())
        if not key:
            continue
        v = value.strip()
        if v.isdigit():
            out[key] = float(int(v))
        else:
            try:
                out[key] = parse_bytes(v)
            except ValueError:
                continue
    return out


# --------------------------------------------------------------------------- #
# stack.txt
# --------------------------------------------------------------------------- #

_STACK_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([\d.]+)%\s*\|\s*"
    r"(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
)


def parse_stack(path: str) -> pd.DataFrame:
    """Return a DataFrame with thread stack usage rows.

    Columns: ``Prio``, ``Name``, ``PeakPct``, ``Current_B``, ``Peak_B``, ``Total_B``.
    """
    rows: list[dict[str, Any]] = []
    for line in read_lines(path):
        m = _STACK_ROW_RE.match(line.strip())
        if not m:
            continue
        prio, name, pct, current, peak, total = m.groups()
        rows.append({
            "Prio": int(prio),
            "Name": name.strip(),
            "PeakPct": float(pct),
            "Current_B": int(current),
            "Peak_B": int(peak),
            "Total_B": int(total),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# write_os.txt / outputs.txt / outputs_interval.txt
# --------------------------------------------------------------------------- #

_SECTION_RE = re.compile(r"^-+\s*(.+?)\s*-+$")
_NUM_RE = re.compile(r"^([\d.]+|-)\s*(.*)$")

_BLOCK_SECTIONS = {"CPU Load", "Stack usage", "Heap usage"}
_BLOCK_FIELDS = {
    "num samples": "n",
    "min load": "min",
    "max load": "max",
    "mean load": "mean",
    "min usage": "min",
    "max usage": "max",
    "mean usage": "mean",
}


def _parse_value(raw: str) -> float | None:
    raw = raw.strip()
    if raw == "-" or raw == "":
        return None
    try:
        return parse_bytes(raw)
    except ValueError:
        # try plain percent / number with trailing unit like '%'
        m = _NUM_RE.match(raw)
        if not m:
            return None
        val = m.group(1)
        if val == "-":
            return None
        try:
            return float(val)
        except ValueError:
            return None


def parse_workload_block(path: str) -> dict[str, dict[str, float | None]]:
    """Parse write_os.txt / outputs.txt / outputs_interval.txt.

    Returns ``{section: {n, min, max, mean}}`` for sections
    ``CPU Load`` (% units), ``Stack usage`` (bytes), ``Heap usage`` (bytes).
    Missing values (``-`` / ``0 samples``) are returned as ``None`` (except
    ``n`` which stays as the parsed int).
    """
    sections: dict[str, dict[str, float | None]] = {}
    current: str | None = None
    for line in read_lines(path):
        line = line.strip()
        if not line:
            continue
        m = _SECTION_RE.match(line)
        if m:
            label = m.group(1).strip()
            if label in _BLOCK_SECTIONS:
                current = label
                sections[current] = {"n": None, "min": None, "max": None, "mean": None}
            else:
                current = None
            continue
        if current is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        key = _BLOCK_FIELDS.get(label.strip())
        if not key:
            continue
        if key == "n":
            try:
                sections[current][key] = int(value.strip())
            except ValueError:
                sections[current][key] = None
        else:
            sections[current][key] = _parse_value(value)
    return sections


# --------------------------------------------------------------------------- #
# rtt.txt
# --------------------------------------------------------------------------- #

_RTT_SECTIONS = {"Single Write RTT", "OS Write RTT"}
_RTT_FIELDS = {"num samples", "min", "max", "mean", "stddev",
               "p50", "p90", "p99", "p999"}


def parse_rtt(path: str) -> dict[str, dict[str, float | None]]:
    """Parse rtt.txt -> ``{section: {n, min, max, mean, stddev, p50, p90, p99, p999}}``.

    All time values are returned in milliseconds (the source file's native unit).
    """
    sections: dict[str, dict[str, float | None]] = {}
    current: str | None = None
    for line in read_lines(path):
        line = line.strip()
        if not line:
            continue
        m = _SECTION_RE.match(line)
        if m:
            label = m.group(1).strip()
            if label in _RTT_SECTIONS:
                current = label
                sections[current] = {}
            else:
                current = None
            continue
        if current is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = label.strip()
        if label not in _RTT_FIELDS:
            continue
        key = "n" if label == "num samples" else label
        v = value.strip().split()[0] if value.strip() else ""
        if key == "n":
            try:
                sections[current][key] = int(v)
            except ValueError:
                sections[current][key] = None
        else:
            try:
                sections[current][key] = float(v)
            except ValueError:
                sections[current][key] = None
    return sections


# --------------------------------------------------------------------------- #
# tiny convenience
# --------------------------------------------------------------------------- #

def first_existing(*paths: str | Path) -> Path | None:
    for p in paths:
        pth = Path(p)
        if pth.is_file():
            return pth
    return None
