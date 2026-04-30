"""Shared helpers for benchmark analyzers."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

LOG_PREFIX_RE = re.compile(r"^\d{7,}\|\d+\|\s?")
BUILD_PREFIX_RE = re.compile(r"^\[build\]\s?")

_UNIT_FACTORS = {
    "B": 1,
    "BYTES": 1,
    "KB": 1024,
    "KBYTES": 1024,
    "MB": 1024 * 1024,
    "MBYTES": 1024 * 1024,
    "GB": 1024 * 1024 * 1024,
    "GBYTES": 1024 * 1024 * 1024,
}


def strip_log_prefix(line: str) -> str:
    """Remove the ``NNNNNNN|NN| `` log prefix or ``[build] `` prefix if present."""
    line = LOG_PREFIX_RE.sub("", line)
    line = BUILD_PREFIX_RE.sub("", line)
    return line


def read_lines(path: str) -> list[str]:
    """Read a file (or '-' for stdin) and return prefix-stripped lines."""
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text()
    return [strip_log_prefix(ln).rstrip("\n") for ln in text.splitlines()]


def parse_bytes(value: str) -> float:
    """Parse '3.18 MBytes', '21.38 KBytes', '167', '64 MB' -> bytes (float)."""
    s = value.strip()
    m = re.match(r"^([\d.]+)\s*([A-Za-z]*)$", s)
    if not m:
        raise ValueError(f"cannot parse bytes value: {value!r}")
    num = float(m.group(1))
    unit = m.group(2).upper() or "B"
    if unit not in _UNIT_FACTORS:
        raise ValueError(f"unknown unit {unit!r} in {value!r}")
    return num * _UNIT_FACTORS[unit]


def parse_inputs_arg(items: Iterable[str]) -> list[tuple[str, str]]:
    """Turn ['path', 'name=path', ...] into [(label, path), ...]."""
    out: list[tuple[str, str]] = []
    for item in items:
        if "=" in item and not item.startswith("/") and not item.startswith("./"):
            label, _, path = item.partition("=")
            out.append((label, path))
        else:
            stem = "stdin" if item == "-" else Path(item).stem
            out.append((stem, item))
    return out


def make_argparser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "inputs",
        nargs="+",
        help="One or more excerpt files (use '-' for stdin, or 'label=path').",
    )
    p.add_argument(
        "--out",
        default="output",
        help="Output directory (default: ./output).",
    )
    p.add_argument(
        "--prefix",
        default=None,
        help="Filename prefix for generated artifacts (default: script-specific).",
    )
    return p


def ensure_out(out: str) -> Path:
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_table(df, out_dir: Path, name: str) -> tuple[Path, Path]:
    """Write a DataFrame as both Markdown and CSV; return (md_path, csv_path)."""
    from tabulate import tabulate

    md_path = out_dir / f"{name}.md"
    csv_path = out_dir / f"{name}.csv"
    md_path.write_text(tabulate(df, headers="keys", tablefmt="github", showindex=False) + "\n")
    df.to_csv(csv_path, index=False)
    return md_path, csv_path


def save_fig(fig, out_dir: Path, name: str) -> Path:
    path = out_dir / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    return path
