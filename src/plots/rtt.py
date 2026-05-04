"""RTT percentile-ladder plot.

User-tweakable labels are centralized at the top.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from ..common import save_fig, save_table
from ..dataset import Dataset


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

LADDER = ["p50", "p90", "p99", "p999", "max"]
METRICS = ["Single Write RTT", "OS Write RTT"]

METRIC_TITLE = {
    "Single Write RTT": "Write Single Value RTT",
    "OS Write RTT": "Write Operating Scheme RTT",
}
SUPTITLE = ""
XLABEL = "percentile"
YLABEL = "latency [ms]"
MEAN_LABEL_FMT = "mean: {value:.2f} ms"
COLOR_BAR = "#1f77b4"
COLOR_MEAN = "#d62728"


# --------------------------------------------------------------------------- #

def _find_rtt(ds: Dataset):
    for dev in ds.all_devices():
        if dev.rtt is not None:
            return dev
    return None


def render_all(ds: Dataset, out_dir: Path) -> None:
    dev = _find_rtt(ds)
    if dev is None:
        print("rtt: no rtt.txt found, skipping")
        return
    sections = dev.rtt.sections

    rows = []
    for metric in METRICS:
        data = sections.get(metric, {})
        for stat in ["n", "min", "max", "mean", "stddev", "p50", "p90", "p99", "p999"]:
            if data.get(stat) is None:
                continue
            rows.append({"metric": metric, "stat": stat, "value": data[stat]})
    df = pd.DataFrame(rows)
    save_table(df, out_dir, "rtt")

    metrics_present = [m for m in METRICS if m in sections and sections[m].get("n")]
    if not metrics_present:
        print("rtt: no metric had samples, skipping plot")
        return

    fig, axes = plt.subplots(1, len(metrics_present),
                             figsize=(6 * len(metrics_present), 5),
                             squeeze=False)
    plain = mticker.FuncFormatter(lambda v, _pos: f"{int(round(v)):d}")
    for ax, metric in zip(axes[0], metrics_present):
        data = sections[metric]
        x = np.arange(len(LADDER))
        values = [data.get(k) for k in LADDER]
        bar_vals = [0 if v is None else v for v in values]
        bars = ax.bar(x, bar_vals, 0.6, color=COLOR_BAR)
        for bar, v in zip(bars, values):
            if v is None:
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{v:.1f}", ha="center", va="bottom", fontsize=8)
        mean = data.get("mean")
        if mean is not None:
            ax.axhline(mean, linestyle="--", color=COLOR_MEAN,
                       linewidth=1.2, alpha=0.8)
            ax.text(0.02, 0.97, MEAN_LABEL_FMT.format(value=mean),
                    transform=ax.transAxes, color=COLOR_MEAN, fontsize=9,
                    va="top", ha="left",
                    bbox=dict(boxstyle="round,pad=0.3",
                              facecolor="white", edgecolor=COLOR_MEAN,
                              alpha=0.9))
        n = data.get("n")
        title = METRIC_TITLE.get(metric, metric)
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(LADDER)
        ax.set_xlabel(XLABEL)
        ax.set_ylabel(YLABEL)
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        ax.set_axisbelow(True)
        ax.yaxis.set_major_formatter(plain)
        cur = ax.get_ylim()[1]
        ax.set_ylim(0, cur * 1.10 if cur > 0 else 1)

    fig.suptitle(SUPTITLE) if SUPTITLE else None
    save_fig(fig, out_dir, "rtt")
    plt.close(fig)
