"""Parsers for the idle-section excerpts (threads, mallinfo, cpuload)."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .common import parse_bytes, read_lines

# --- Threads --------------------------------------------------------------
OPCUA_THREADS = ("OPC/UA Server Thread", "OPC/UA Client Thread")
_THREAD_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)%\s*\|"
    r"\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
)


def parse_threads(lines: list[str]) -> pd.DataFrame:
    rows = []
    for ln in lines:
        m = _THREAD_ROW_RE.match(ln)
        if not m:
            continue
        rows.append(
            {
                "Prio": int(m.group(1)),
                "Name": m.group(2).strip(),
                "Peak%": float(m.group(3)),
                "Current": int(m.group(4)),
                "Peak": int(m.group(5)),
                "Total": int(m.group(6)),
            }
        )
    return pd.DataFrame(rows)


def opcua_threads(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["Name"].isin(OPCUA_THREADS)].reset_index(drop=True)


# --- mallinfo -------------------------------------------------------------
_MALLINFO_KEYS = {
    "Total non-mmapped bytes (arena)": "arena",
    "Total allocated space (uordblks)": "uordblks",
    "Total free space (fordblks)": "fordblks",
    "Topmost releasable block (keepcost)": "keepcost",
    "SBRK Total Size": "sbrk_total",
    "SBRK Remaining Size": "sbrk_free",
    "SBRK Percentage Free": "sbrk_pct_free",
}
_KV_RE = re.compile(r"^([^:]+):\s+(.+)$")


def parse_mallinfo(lines: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ln in lines:
        m = _KV_RE.match(ln.strip())
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        if key not in _MALLINFO_KEYS:
            continue
        col = _MALLINFO_KEYS[key]
        if value.endswith("%"):
            out[col] = float(value.rstrip("%").strip())
        else:
            out[col] = parse_bytes(value)
    return out


# --- CPU-Load timeseries --------------------------------------------------
_CPU_ROW_RE = re.compile(r"^\|\s*(\d{2}:\d{2}:\d{2})\s*\|\s*([\d.]+)%")
_CPU_AVG_RE = re.compile(r"Moving Average\s*\(([^)]+)\):\s*([\d.]+)%")


def parse_cpuload(lines: list[str]) -> tuple[pd.DataFrame, float | None]:
    rows = []
    avg: float | None = None
    for ln in lines:
        m = _CPU_ROW_RE.match(ln.strip())
        if m:
            rows.append({"time": m.group(1), "percent": float(m.group(2))})
            continue
        a = _CPU_AVG_RE.search(ln)
        if a:
            avg = float(a.group(2))
    return pd.DataFrame(rows), avg


# --- Bundle loader --------------------------------------------------------
class IdleBundle:
    """Loads ``threads.txt``, ``mallinfo.txt``, ``cpuload.txt`` from a dir."""

    def __init__(self, root: Path):
        self.root = root
        self.threads = parse_threads(read_lines(str(_pick(root, "stack.txt", "threads.txt"))))
        self.opcua = opcua_threads(self.threads)
        self.mallinfo = parse_mallinfo(read_lines(str(_pick(root, "heap.txt", "mallinfo.txt"))))
        self.cpuload, self.cpuload_avg = parse_cpuload(
            read_lines(str(root / "cpuload.txt"))
        )


def _pick(root: Path, *candidates: str) -> Path:
    for name in candidates:
        p = root / name
        if p.exists():
            return p
    return root / candidates[0]
