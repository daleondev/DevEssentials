"""Compare idle baseline (threads/mallinfo/cpuload) against a workload stat block.

Plots are simple grouped bars:
- CPU: idle max vs workload max
- Heap: idle uordblks vs workload max
- Stack: per source, the workload thread is identified (Server vs Client) and
  shown next to the matching idle OPC/UA thread peak.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import ensure_out, read_lines, save_fig, save_table
from .idle import IdleBundle
from .workload import RTT_KEYS, parse_blocks

# Per-source mapping: which idle OPC/UA thread the workload's stack belongs to.
WORKLOAD_THREAD = {
    "bioreactor": "OPC/UA Client Thread",
    "processingstation": "OPC/UA Server Thread",
}
DEFAULT_WORKLOAD_THREAD = "OPC/UA Server Thread"


@dataclass
class SourceData:
    label: str
    idle: IdleBundle
    workload: dict[str, dict[str, float]]


def load_source(label: str, root: Path, workload_file: str) -> SourceData:
    idle = IdleBundle(root)
    blocks = parse_blocks(read_lines(str(root / workload_file)))
    return SourceData(label=label, idle=idle, workload=blocks)


def opcua_peak(idle: IdleBundle, name: str) -> float | None:
    row = idle.opcua[idle.opcua["Name"] == name]
    if row.empty:
        return None
    return float(row["Peak"].iloc[0])


def opcua_current(idle: IdleBundle, name: str) -> float | None:
    row = idle.opcua[idle.opcua["Name"] == name]
    if row.empty:
        return None
    return float(row["Current"].iloc[0])


def workload_thread_for(label: str) -> str:
    return WORKLOAD_THREAD.get(label, DEFAULT_WORKLOAD_THREAD)


def build_summary(sources: list[SourceData], workload_label: str) -> pd.DataFrame:
    rows = []
    for s in sources:
        cpu = s.workload.get("CPU Load", {})
        stack = s.workload.get("Stack usage", {})
        heap = s.workload.get("Heap usage", {})
        idle_cpu_max = (s.idle.cpuload["percent"].max()
                        if not s.idle.cpuload.empty else None)
        wl_thread = workload_thread_for(s.label)
        rows.append({
            "Source": s.label,
            "idle_cpu_max_%": idle_cpu_max,
            f"{workload_label}_cpu_max_%": cpu.get("max"),
            "idle_heap_uordblks_B": s.idle.mallinfo.get("uordblks"),
            f"{workload_label}_heap_max_B": heap.get("max"),
            "workload_thread": wl_thread,
            "idle_workload_thread_peak_B": opcua_peak(s.idle, wl_thread),
            "idle_workload_thread_current_B": opcua_current(s.idle, wl_thread),
            f"{workload_label}_stack_max_B": stack.get("max"),
        })
    return pd.DataFrame(rows)


def _grouped_bars(ax, sources: list[SourceData],
                  series: list[tuple[str, list[float]]],
                  ylabel: str, title: str, value_fmt: str = "{:.0f}") -> None:
    labels = [s.label for s in sources]
    x = np.arange(len(labels))
    n = len(series)
    w = 0.8 / max(n, 1)
    for i, (name, values) in enumerate(series):
        offset = (i - (n - 1) / 2) * w
        bars = ax.bar(x + offset, values, w, label=name)
        for bar, v in zip(bars, values):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    value_fmt.format(v), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9)


def plot_cpu(sources, workload_label, title):
    idle_max = [s.idle.cpuload["percent"].max() if not s.idle.cpuload.empty else 0
                for s in sources]
    work_max = [s.workload.get("CPU Load", {}).get("max") or 0 for s in sources]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(sources) + 3), 4.5))
    _grouped_bars(ax, sources,
                  [("idle max", idle_max), ("operation max", work_max)],
                  "CPU load %", title, value_fmt="{:.1f}%")
    ax.set_ylim(0, max(idle_max + work_max) * 1.18)
    return fig


def plot_heap(sources, workload_label, title):
    idle_kb = [(s.idle.mallinfo.get("uordblks") or 0) / 1024 for s in sources]
    work_kb = [(s.workload.get("Heap usage", {}).get("max") or 0) / 1024 for s in sources]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(sources) + 3), 4.5))
    _grouped_bars(ax, sources,
                  [("idle baseline", idle_kb), ("operation max", work_kb)],
                  "heap (KB)", title, value_fmt="{:.0f}")
    ax.set_ylim(0, max(idle_kb + work_kb) * 1.18)
    return fig


def plot_stack(sources, workload_label, title):
    """Per source: idle peak + idle current of the matching OPC/UA thread vs workload max."""
    labels = [f"{s.label}\n({workload_thread_for(s.label)})" for s in sources]
    idle_peak = [opcua_peak(s.idle, workload_thread_for(s.label)) or 0 for s in sources]
    idle_curr = [opcua_current(s.idle, workload_thread_for(s.label)) or 0 for s in sources]
    work_max = [s.workload.get("Stack usage", {}).get("max") or 0 for s in sources]

    x = np.arange(len(sources))
    w = 0.27
    fig, ax = plt.subplots(figsize=(max(7, 2.0 * len(sources) + 3), 4.8))
    series = (
        (ax.bar(x - w, idle_peak, w, label="idle peak"), idle_peak),
        (ax.bar(x,     idle_curr, w, label="idle current"), idle_curr),
        (ax.bar(x + w, work_max,  w, label="operation max"), work_max),
    )
    for bars, values in series:
        for bar, v in zip(bars, values):
            if not v:
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("stack (bytes)")
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9)
    ymax = max(idle_peak + idle_curr + work_max) or 1
    ax.set_ylim(0, ymax * 1.18)
    return fig


def plot_rtt(sources, out_dir: Path, prefix: str) -> None:
    rows = []
    for s in sources:
        for sec in ("Single Write RTT", "OS Write RTT"):
            data = s.workload.get(sec)
            if not data or data.get("n", 0) < 2:
                continue
            for k in RTT_KEYS:
                if k in data:
                    rows.append({"Source": s.label, "Metric": sec,
                                 "Stat": k, "Value_ms": data[k]})
    if not rows:
        return
    df = pd.DataFrame(rows)
    save_table(df, out_dir, f"{prefix}_rtt")
    metrics = sorted(df["Metric"].unique())
    fig, axes = plt.subplots(1, len(metrics), figsize=(5 * len(metrics), 4.5),
                             squeeze=False)
    for ax, metric in zip(axes[0], metrics):
        sub = df[df["Metric"] == metric]
        pivot = sub.pivot(index="Stat", columns="Source", values="Value_ms").reindex(RTT_KEYS)
        pivot.plot(kind="bar", ax=ax, logy=True)
        ax.set_title(metric)
        ax.set_ylabel("ms (log)")
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=0)
        ax.grid(axis="y", which="both", linestyle=":", alpha=0.5)
    fig.suptitle("Write OS — RTT distribution")
    save_fig(fig, out_dir, f"{prefix}_rtt")
    plt.close(fig)


def run(workload_file: str, workload_label: str, default_prefix: str,
        argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+",
                        help="Source directories (each contains threads.txt, "
                             "mallinfo.txt, cpuload.txt, and the workload file). "
                             "Use 'label=path' to override the directory-name label.")
    parser.add_argument("--out", default="output", help="Output directory.")
    parser.add_argument("--prefix", default=default_prefix,
                        help=f"Filename prefix (default: {default_prefix}).")
    args = parser.parse_args(argv)
    out_dir = ensure_out(args.out)

    sources: list[SourceData] = []
    for item in args.sources:
        if "=" in item and not item.startswith("/") and not item.startswith("."):
            label, _, path = item.partition("=")
        else:
            path = item
            label = Path(path).name
        sources.append(load_source(label, Path(path), workload_file))

    summary = build_summary(sources, workload_label)
    save_table(summary, out_dir, f"{args.prefix}_summary")

    for fig_factory, name in (
        (plot_cpu, f"{args.prefix}_cpu"),
        (plot_heap, f"{args.prefix}_heap"),
        (plot_stack, f"{args.prefix}_stack"),
    ):
        fig = fig_factory(sources, workload_label, f"Idle vs {workload_label}")
        save_fig(fig, out_dir, name)
        plt.close(fig)

    plot_rtt(sources, out_dir, args.prefix)
    print(f"wrote {args.prefix}_* to {out_dir}")
    return 0
