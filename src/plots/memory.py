"""Memory-footprint plots: binary, heap peak, stack peak.

All visible labels are centralized in the constants near the top so they can
be tweaked without touching the renderers.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from ..common import save_fig, save_table
from ..dataset import Dataset, DeviceData


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

REGION = "OCTO_SPI_FLASH"
RELEVANT_THREAD = {
    "bioreactor": "OPC/UA Client Thread",
    "processingstation": "OPC/UA Server Thread",
}
BUILD_ORDER = ["main", "no_module", "with_module"]
SCENARIO_ORDER = ["no_module", "with_module"]

# User-tweakable display labels.
SCENARIO_LABEL = {
    "no_module": "no module",
    "with_module": "with module",
}
BUILD_LABEL = {
    "main": "main",
    "no_module": "no module",
    "with_module": "with module",
}
TITLE_BINARY = f"binary size - {REGION}"
TITLE_HEAP = "peak heap usage - Bioreactor"
TITLE_STACK = "peak stack usage - Bioreactor (OPC/UA Client Thread)"
YLABEL_BINARY = "flash [KB]"
YLABEL_HEAP = "usage [KB]"
YLABEL_STACK = "usage [bytes]"
LABEL_AVAILABLE = "available"
LABEL_USED = "used"
NA_TEXT = "n/a"
COLOR_USED = "#1f77b4"
COLOR_AVAILABLE = "#dddddd"
COLOR_AVAILABLE_EDGE = "#888888"
COLOR_NA = "#888"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _is_nan(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


def _plain_int(ax, axis: str = "y") -> None:
    """Disable scientific/offset on linear axes."""
    fmt = mticker.FuncFormatter(lambda v, _pos: f"{int(round(v)):d}")
    if axis in ("y", "both"):
        ax.yaxis.set_major_formatter(fmt)
    if axis in ("x", "both"):
        ax.xaxis.set_major_formatter(fmt)


# --------------------------------------------------------------------------- #
# binary size
# --------------------------------------------------------------------------- #

def plot_binary(ds: Dataset, out_dir: Path) -> None:
    rows = []
    for variant in BUILD_ORDER:
        if variant not in ds.builds:
            continue
        r = ds.builds[variant].regions.get(REGION)
        if not r:
            continue
        rows.append({
            "variant": variant,
            "used_KB": r["used_B"] / 1024,
            "total_KB": r["total_B"] / 1024,
            "pct": r["pct"],
        })
    if not rows:
        print("memory_binary: no build_*.txt found, skipping")
        return
    df = pd.DataFrame(rows)
    if (df["variant"] == "main").any():
        baseline_kb = float(df.loc[df["variant"] == "main", "used_KB"].iloc[0])
        baseline_pct = float(df.loc[df["variant"] == "main", "pct"].iloc[0])
    else:
        baseline_kb = float(df["used_KB"].iloc[0])
        baseline_pct = float(df["pct"].iloc[0])
    df["delta_vs_main_KB"] = df["used_KB"] - baseline_kb
    df["delta_pct"] = df["pct"] - baseline_pct

    save_table(df, out_dir, "memory_binary")

    total_kb = float(df["total_KB"].iloc[0])
    total_mb = total_kb / 1024
    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(len(df))
    ax.bar(x, [total_kb] * len(df), color=COLOR_AVAILABLE,
           edgecolor=COLOR_AVAILABLE_EDGE,
           label=f"{LABEL_AVAILABLE} ({total_mb:.0f} MB)")
    bars = ax.bar(x, df["used_KB"], color=COLOR_USED, label=LABEL_USED)
    for bar, row in zip(bars, df.itertuples()):
        delta_str = (f"  ({row.delta_vs_main_KB:+.0f} KB)"
                     if row.variant != "main" else "")
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{row.used_KB:.0f} KB\n{row.pct:.2f}%{delta_str}",
                ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([BUILD_LABEL.get(v, v) for v in df["variant"]])
    ax.set_ylabel(YLABEL_BINARY)
    ax.set_title(f"{TITLE_BINARY} ({total_mb:.0f} MB available)")
    ax.set_ylim(0, total_kb * 1.08)
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    _plain_int(ax)
    save_fig(fig, out_dir, "memory_binary")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# heap peak (bioreactor only, no_module vs with_module)
# --------------------------------------------------------------------------- #

def _heap_peak(dev: DeviceData) -> tuple[float | None, str | None]:
    best = None
    best_src = None
    for ms, iv in dev.intervals.items():
        for kind, run in iv.runs.items():
            v = run.sections.get("Heap usage", {}).get("max")
            if v is None:
                continue
            if best is None or v > best:
                best = v
                best_src = f"{ms}ms/{kind}.txt"
    return best, best_src


def plot_heap(ds: Dataset, out_dir: Path) -> None:
    rows = []
    for sc in SCENARIO_ORDER:
        dev = ds.device(sc, "bioreactor")
        if dev is None:
            continue
        peak, src = _heap_peak(dev)
        rows.append({
            "scenario": sc,
            "device": "bioreactor",
            "peak_KB": (peak / 1024) if peak is not None else None,
            "peak_MB": (peak / 1024 / 1024) if peak is not None else None,
            "source": src,
        })
    if not rows:
        print("memory_heap: no bioreactor scenarios found, skipping")
        return
    df = pd.DataFrame(rows)
    save_table(df, out_dir, "memory_heap")

    fig, ax = plt.subplots(figsize=(6, 5))
    x = np.arange(len(df))
    values = [0 if _is_nan(v) else v for v in df["peak_KB"]]
    bars = ax.bar(x, values, color=COLOR_USED)
    nonzero = [v for v in values if v > 0]
    headroom = max(nonzero) * 0.20 if nonzero else 1
    for bar, row in zip(bars, df.itertuples()):
        if _is_nan(row.peak_KB):
            ax.text(bar.get_x() + bar.get_width() / 2, headroom,
                    NA_TEXT, ha="center", va="center",
                    fontsize=14, color=COLOR_NA, fontweight="bold")
            continue
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{row.peak_MB:.2f} MB", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABEL.get(s, s) for s in df["scenario"]])
    ax.set_ylabel(YLABEL_HEAP)
    ax.set_title(TITLE_HEAP)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    cur = ax.get_ylim()[1]
    ax.set_ylim(0, cur * 1.10 if cur > 0 else 1)
    _plain_int(ax)
    save_fig(fig, out_dir, "memory_heap")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# stack peak (bioreactor only)
# --------------------------------------------------------------------------- #

def _stack_peak(dev: DeviceData) -> tuple[float | None, str | None]:
    thread = RELEVANT_THREAD.get(dev.device)
    if thread is None:
        return None, None
    candidates: list[tuple[float, str]] = []
    if dev.idle.stack is not None:
        row = dev.idle.stack[dev.idle.stack["Name"] == thread]
        if not row.empty:
            candidates.append((float(row["Peak_B"].iloc[0]), "idle/stack.txt"))
    for ms, iv in dev.intervals.items():
        for kind, run in iv.runs.items():
            v = run.sections.get("Stack usage", {}).get("max")
            if v is None:
                continue
            candidates.append((float(v), f"{ms}ms/{kind}.txt"))
    if not candidates:
        return None, None
    best = max(candidates, key=lambda t: t[0])
    return best[0], best[1]


def plot_stack(ds: Dataset, out_dir: Path) -> None:
    rows = []
    for sc in SCENARIO_ORDER:
        dev = ds.device(sc, "bioreactor")
        if dev is None:
            continue
        peak, src = _stack_peak(dev)
        rows.append({
            "scenario": sc,
            "device": "bioreactor",
            "thread": RELEVANT_THREAD["bioreactor"],
            "peak_B": peak,
            "source": src,
        })
    if not rows:
        print("memory_stack: no bioreactor scenarios found, skipping")
        return
    df = pd.DataFrame(rows)
    save_table(df, out_dir, "memory_stack")

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(df))
    values = [0 if _is_nan(v) else v for v in df["peak_B"]]
    bars = ax.bar(x, values, color=COLOR_USED)
    nonzero = [v for v in values if v > 0]
    headroom = max(nonzero) * 0.20 if nonzero else 1
    for bar, row in zip(bars, df.itertuples()):
        v = row.peak_B
        if _is_nan(v):
            ax.text(bar.get_x() + bar.get_width() / 2, headroom,
                    NA_TEXT, ha="center", va="center",
                    fontsize=14, color=COLOR_NA, fontweight="bold")
            continue
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.0f} B", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABEL.get(s, s) for s in df["scenario"]])
    ax.set_ylabel(YLABEL_STACK)
    ax.set_title(TITLE_STACK)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    cur = ax.get_ylim()[1]
    ax.set_ylim(0, cur * 1.10 if cur > 0 else 1)
    _plain_int(ax)
    save_fig(fig, out_dir, "memory_stack")
    plt.close(fig)


def render_all(ds: Dataset, out_dir: Path) -> None:
    plot_binary(ds, out_dir)
    plot_heap(ds, out_dir)
    plot_stack(ds, out_dir)
