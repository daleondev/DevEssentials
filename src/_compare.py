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
DEVICE_DISPLAY = {
    "bioreactor": "Bioreactor",
    "processingstation": "ProcessingStation",
}
DEFAULT_WORKLOAD_THREAD = "OPC/UA Server Thread"


@dataclass
class SourceData:
    label: str
    root: Path
    idle: IdleBundle
    workload: dict[str, dict[str, float]]


def load_source(label: str, root: Path, workload_file: str) -> SourceData:
    idle = IdleBundle(root)
    blocks = parse_blocks(read_lines(str(root / workload_file)))
    return SourceData(label=label, root=root, idle=idle, workload=blocks)


def device_for(source: "SourceData") -> str:
    """Resolve the device key (used for thread mapping) from the source path.

    Walks the source's directory leaf upward until it matches a known device key;
    falls back to the source label.
    """
    parts = list(source.root.parts)[::-1]
    for part in parts:
        if part.lower() in WORKLOAD_THREAD:
            return part.lower()
    return source.label.lower()


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


def workload_thread_for(source: "SourceData") -> str:
    return WORKLOAD_THREAD.get(device_for(source), DEFAULT_WORKLOAD_THREAD)


def build_summary(sources: list[SourceData], workload_label: str) -> pd.DataFrame:
    rows = []
    for s in sources:
        cpu = s.workload.get("CPU Load", {})
        stack = s.workload.get("Stack usage", {})
        heap = s.workload.get("Heap usage", {})
        idle_cpu_max = (s.idle.cpuload["percent"].max()
                        if not s.idle.cpuload.empty else None)
        wl_thread = workload_thread_for(s)
        rows.append({
            "Source": s.label,
            "idle_cpu_max_%": idle_cpu_max,
            f"{workload_label}_cpu_max_%": cpu.get("max"),
            "idle_heap_uordblks_B": s.idle.mallinfo.get("uordblks"),
            f"{workload_label}_heap_max_B": heap.get("max"),
            "workload_thread": wl_thread,
            "idle_server_peak_B": opcua_peak(s.idle, "OPC/UA Server Thread"),
            "idle_client_peak_B": opcua_peak(s.idle, "OPC/UA Client Thread"),
            "idle_workload_thread_current_B": opcua_current(s.idle, wl_thread),
            f"{workload_label}_stack_max_B": stack.get("max"),
        })
    return pd.DataFrame(rows)


def _layout(sources: list[SourceData], gap: float = 0.7
            ) -> tuple[list[float], list[tuple[str, float]]]:
    """Compute x positions per source and (group_label, group_center) tuples.

    Sources sharing the same `device_for` value are placed at consecutive
    integers; an extra `gap` is inserted between groups. Only groups with more
    than one source are returned (singletons get no subgroup label).
    """
    positions: list[float] = []
    raw_groups: list[tuple[str, int, int]] = []  # (key, start_idx, end_idx)
    cur_group: str | None = None
    cur_start: int = 0
    x = 0.0
    for i, s in enumerate(sources):
        g = device_for(s)
        if cur_group is None:
            cur_group = g
            cur_start = i
        elif g != cur_group:
            raw_groups.append((cur_group, cur_start, i - 1))
            cur_group = g
            cur_start = i
            x += gap
        positions.append(x)
        x += 1.0
    if cur_group is not None and positions:
        raw_groups.append((cur_group, cur_start, len(positions) - 1))
    # Emit a subgroup row when at least one group has >1 source, OR when at
    # least one source's label is just the device name (and would otherwise be
    # hidden as duplicative). Always include all groups so devices appear at
    # the same level.
    needs_groups = (
        any(end > start for _, start, end in raw_groups)
        or any(s.label.lower() == device_for(s) for s in sources)
    )
    if not needs_groups:
        return positions, []
    groups = [
        (DEVICE_DISPLAY.get(key, key), (positions[start] + positions[end]) / 2)
        for key, start, end in raw_groups
    ]
    return positions, groups


def _add_group_axis(ax, groups: list[tuple[str, float]]) -> None:
    if not groups:
        return
    sec = ax.secondary_xaxis(-0.14)
    sec.set_xticks([c for _, c in groups])
    sec.set_xticklabels([g for g, _ in groups], fontsize=10, fontweight="bold")
    sec.tick_params(length=0)
    for spine in sec.spines.values():
        spine.set_visible(False)


def _source_label(s: "SourceData") -> str:
    """Per-source xtick label; hide if it just duplicates the device name."""
    if s.label.lower() == device_for(s):
        return ""
    return s.label.replace("_", " ")


def _grouped_bars(ax, sources: list[SourceData],
                  series: list[tuple[str, list[float]]],
                  ylabel: str, title: str, value_fmt: str = "{:.0f}") -> None:
    labels = [_source_label(s) for s in sources]
    x, groups = _layout(sources)
    x_arr = np.array(x)
    n = len(series)
    w = 0.8 / max(n, 1)
    for i, (name, values) in enumerate(series):
        offset = (i - (n - 1) / 2) * w
        bars = ax.bar(x_arr + offset, values, w, label=name)
        for bar, v in zip(bars, values):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    value_fmt.format(v), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x_arr)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9)
    _add_group_axis(ax, groups)


def plot_cpu(sources, workload_label, title):
    idle_max = [s.idle.cpuload["percent"].max() if not s.idle.cpuload.empty else 0
                for s in sources]
    work_max = [s.workload.get("CPU Load", {}).get("max") or 0 for s in sources]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(sources) + 3), 4.5))
    _grouped_bars(ax, sources,
                  [("idle peak", idle_max), ("operation peak", work_max)],
                  "CPU load %", "cpu-load", value_fmt="{:.1f}%")
    ax.set_ylim(0, max(idle_max + work_max) * 1.18)
    return fig


def plot_heap(sources, workload_label, title):
    idle_kb = [(s.idle.mallinfo.get("uordblks") or 0) / 1024 for s in sources]
    work_kb = [(s.workload.get("Heap usage", {}).get("max") or 0) / 1024 for s in sources]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(sources) + 3), 4.5))
    _grouped_bars(ax, sources,
                  [("idle baseline", idle_kb), ("operation peak", work_kb)],
                  "heap (KB)", "heap", value_fmt="{:.0f}")
    ax.set_ylim(0, max(idle_kb + work_kb) * 1.18)
    return fig


def plot_stack_matched(sources, workload_label, title):
    """Per source: idle peak + idle current of the matching OPC/UA thread vs workload peak.

    Missing values are rendered as a 0-height bar with an explicit 'n/a' label.
    """
    labels = [f"{_source_label(s)}\n({workload_thread_for(s)})" for s in sources]
    idle_peak = [opcua_peak(s.idle, workload_thread_for(s)) for s in sources]
    idle_curr = [opcua_current(s.idle, workload_thread_for(s)) for s in sources]
    work_max = [s.workload.get("Stack usage", {}).get("max") for s in sources]
    return _stack_fig(sources, labels, [
        ("idle peak", idle_peak),
        ("idle current", idle_curr),
        ("operation peak", work_max),
    ], "stack")


def plot_stack_both_opcua(sources, workload_label, title):
    """Per source: Server peak, Client peak, workload op peak."""
    labels = [_source_label(s) for s in sources]
    server = [opcua_peak(s.idle, "OPC/UA Server Thread") for s in sources]
    client = [opcua_peak(s.idle, "OPC/UA Client Thread") for s in sources]
    work_max = [s.workload.get("Stack usage", {}).get("max") for s in sources]
    return _stack_fig(sources, labels, [
        ("Server idle peak", server),
        ("Client idle peak", client),
        ("operation peak", work_max),
    ], "stack")


def _stack_fig(sources, labels, series, title):
    x, groups = _layout(sources)
    x_arr = np.array(x)
    n = len(labels)
    w = 0.27
    fig, ax = plt.subplots(figsize=(max(7, 2.0 * n + 3), 4.8))
    for i, (name, values) in enumerate(series):
        offset = (i - (len(series) - 1) / 2) * w
        bars = ax.bar(x_arr + offset, [v or 0 for v in values], w, label=name)
        for bar, v in zip(bars, values):
            if v is None:
                ax.text(bar.get_x() + bar.get_width() / 2, 0,
                        "n/a", ha="center", va="bottom", fontsize=8, color="#888")
            else:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x_arr)
    ax.set_xticklabels(labels)
    ax.set_ylabel("stack (bytes)")
    ax.set_title(title)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9)
    flat = [v for _, vs in series for v in vs if v]
    ax.set_ylim(0, (max(flat) if flat else 1) * 1.18)
    _add_group_axis(ax, groups)
    return fig


STACK_PLOTS = {
    "matched": plot_stack_matched,
    "both_opcua": plot_stack_both_opcua,
}


def _alltime_stack(s: SourceData) -> float | None:
    candidates = [
        opcua_peak(s.idle, workload_thread_for(s)),
        s.workload.get("Stack usage", {}).get("max"),
    ]
    vals = [v for v in candidates if v is not None]
    return max(vals) if vals else None


def _alltime_heap(s: SourceData) -> float | None:
    candidates = [
        s.idle.mallinfo.get("uordblks"),
        s.workload.get("Heap usage", {}).get("max"),
    ]
    vals = [v for v in candidates if v is not None]
    return max(vals) if vals else None


def plot_alltime_peak(sources, kind: str, ylabel: str, value_fn,
                      value_fmt: str = "{:.0f}"):
    """One bar per bioreactor source showing all-time peak across idle and operation."""
    bio = [s for s in sources if device_for(s) == "bioreactor"]
    if len(bio) < 2:
        return None
    labels = [s.label.replace("_", " ") for s in bio]
    values = [value_fn(s) for s in bio]
    x = np.arange(len(bio))
    fig, ax = plt.subplots(figsize=(max(5, 1.4 * len(bio) + 2), 4.5))
    bars = ax.bar(x, [v or 0 for v in values], 0.6)
    for bar, v in zip(bars, values):
        if v is None:
            ax.text(bar.get_x() + bar.get_width() / 2, 0,
                    "n/a", ha="center", va="bottom", fontsize=9, color="#888")
        else:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    value_fmt.format(v), ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(kind)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    flat = [v for v in values if v]
    ax.set_ylim(0, (max(flat) if flat else 1) * 1.18)
    return fig


def plot_rtt(sources, out_dir: Path, prefix: str) -> None:
    rows = []
    excluded = []
    for s in sources:
        has_any = False
        for sec in ("Single Write RTT", "OS Write RTT"):
            data = s.workload.get(sec)
            if not data or data.get("n", 0) < 2:
                continue
            has_any = True
            for k in RTT_KEYS:
                if k in data:
                    rows.append({"Source": s.label, "Metric": sec,
                                 "Stat": k, "Value_ms": data[k]})
        if not has_any:
            excluded.append(s.label)
    if not rows:
        if excluded:
            print(f"rtt: skipped (no source has n>=2): {', '.join(excluded)}")
        return
    if excluded:
        print(f"rtt: excluded (no n>=2): {', '.join(excluded)}")
    df = pd.DataFrame(rows)
    save_table(df, out_dir, f"{prefix}_rtt")

    # Focus chart: percentile ladder (p50..max), drop min/stddev as noise.
    # Mean rendered as a dashed reference line so typical-vs-tail is obvious.
    ladder = ["p50", "p90", "p99", "p999", "max"]
    metric_order = ["Single Write RTT", "OS Write RTT"]
    metrics = [m for m in metric_order if m in df["Metric"].unique()]
    sources_in_plot = list(dict.fromkeys(df["Source"]))
    palette = plt.get_cmap("tab10").colors

    fig, axes = plt.subplots(1, len(metrics), figsize=(6 * len(metrics), 5),
                             squeeze=False)
    for ax, metric in zip(axes[0], metrics):
        sub = df[df["Metric"] == metric]
        pivot = sub.pivot(index="Stat", columns="Source", values="Value_ms")
        pivot = pivot.reindex(ladder).reindex(columns=sources_in_plot)
        x = np.arange(len(ladder))
        n_src = len(sources_in_plot)
        w = 0.8 / max(n_src, 1)
        for i, src in enumerate(sources_in_plot):
            offset = (i - (n_src - 1) / 2) * w
            values = pivot[src].to_numpy()
            color = palette[i % len(palette)]
            bars = ax.bar(x + offset, values, w, label=src.replace("_", " "), color=color)
            for bar, v in zip(bars, values):
                if np.isnan(v):
                    continue
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{v:.0f}", ha="center", va="bottom", fontsize=8)
            mean_v = sub[(sub["Source"] == src) & (sub["Stat"] == "mean")]["Value_ms"]
            if not mean_v.empty:
                m = float(mean_v.iloc[0])
                ax.axhline(m, color=color, linestyle="--", linewidth=1, alpha=0.7)
                ax.text(-0.45, m, f"mean {m:.1f} ms ",
                        color=color, fontsize=8, va="bottom", ha="left")

        n_total = next((int(s.workload.get(metric, {}).get("n", 0))
                        for s in sources if s.label in sources_in_plot), 0)
        ax.set_title(f"{metric}  (n={n_total})" if n_total else metric)
        ax.set_xticks(x)
        ax.set_xticklabels(ladder)
        ax.set_xlabel("percentile")
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        ax.ticklabel_format(axis="y", style="plain")
        ax.set_axisbelow(True)
        # add 12% headroom so the bar value labels never collide with the title
        cur_max = ax.get_ylim()[1]
        ax.set_ylim(0, cur_max * 1.08)
        if n_src > 1:
            ax.legend(fontsize=9)

    axes[0][0].set_ylabel("latency (ms)")
    for ax in axes[0]:
        ax.set_ylabel("latency (ms)")
    fig.suptitle("Communication")
    save_fig(fig, out_dir, f"{prefix}_rtt")
    plt.close(fig)


def run(workload_file: str, workload_label: str, default_prefix: str,
        argv: list[str] | None = None, stack_mode: str = "matched") -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+",
                        help="Source directories (each contains stack.txt, "
                             "heap.txt, cpuload.txt, and the workload file). "
                             "Use 'label=path' to override the directory-name label.")
    parser.add_argument("--out", default="output", help="Output directory.")
    parser.add_argument("--prefix", default=default_prefix,
                        help=f"Filename prefix (default: {default_prefix}).")
    args = parser.parse_args(argv)
    out_dir = ensure_out(args.out)

    sources: list[SourceData] = []
    for item in args.sources:
        if "=" in item:
            label, _, path = item.partition("=")
        else:
            path = item
            label = Path(path).name
        sources.append(load_source(label, Path(path), workload_file))

    summary = build_summary(sources, workload_label)
    save_table(summary, out_dir, f"{args.prefix}_summary")

    plot_stack = STACK_PLOTS[stack_mode]
    for fig_factory, name in (
        (plot_cpu, f"{args.prefix}_cpu"),
        (plot_heap, f"{args.prefix}_heap"),
        (plot_stack, f"{args.prefix}_stack"),
    ):
        fig = fig_factory(sources, workload_label, "")
        save_fig(fig, out_dir, name)
        plt.close(fig)

    plot_rtt(sources, out_dir, args.prefix)
    for kind, ylabel, fn, name, fmt in (
        ("stack", "stack (bytes)", _alltime_stack,
         f"{args.prefix}_stack_alltime", "{:.0f}"),
        ("heap", "heap (KB)",
         lambda s: ((_alltime_heap(s) or 0) / 1024
                    if _alltime_heap(s) is not None else None),
         f"{args.prefix}_heap_alltime", "{:.0f}"),
    ):
        fig = plot_alltime_peak(sources, kind, ylabel, fn, value_fmt=fmt)
        if fig is None:
            continue
        save_fig(fig, out_dir, name)
        plt.close(fig)
    print(f"wrote {args.prefix}_* to {out_dir}")
    return 0
