"""CPU-load ladder plots: peak load vs cycle time.

All visible labels are centralized in the constants below so they can be
tweaked without touching the renderer.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from ..common import save_fig, save_table
from ..dataset import Dataset


# --------------------------------------------------------------------------- #
# User-tweakable labels
# --------------------------------------------------------------------------- #

DEVICE_LABEL = {
    "bioreactor": "Bioreactor",
    "processingstation": "ProcessingStation",
}
SCENARIO_LABEL = {
    "no_module": "no module",
    "with_module": "with module",
}
WORKLOAD_TITLE = {
    "write_os": "Write Operating Schemes",
    "outputs": "Monitor Outputs",
}
VARIANT_TITLE = {
    "bioreactor": "Bioreactor",
    "processingstation": "ProcessingStation",
    "with_module": "with module"
}

X_LABEL = "cycle time [ms]"
Y_LABEL = "CPU load [%]"
COLOR_BIO_NO = "#1f77b4"
COLOR_BIO_WITH = "#ff7f0e"
COLOR_PS_WITH = "#2ca02c"


# (scenario, device, color)
_LINE_BIO_NO = ("no_module", "bioreactor", COLOR_BIO_NO)
_LINE_BIO_WITH = ("with_module", "bioreactor", COLOR_BIO_WITH)
_LINE_PS_WITH = ("with_module", "processingstation", COLOR_PS_WITH)

VARIANTS = {
    # workload kind -> {variant_name: [lines]}
    "write_os": {
        "all": [_LINE_BIO_NO, _LINE_BIO_WITH, _LINE_PS_WITH],
    },
    "outputs": {
        "all": [_LINE_BIO_WITH, _LINE_PS_WITH],
    },
}

# When False, lines whose scenario is "no_module" are dropped from every chart.
# Flip to True to include them again.
INCLUDE_NO_MODULE = False

# Idle baseline styling
IDLE_LABEL_FMT = "{label} Idle"
IDLE_LINESTYLE = ":"
IDLE_LINEWIDTH = 1.2
IDLE_ALPHA = 0.6


# --------------------------------------------------------------------------- #

def _line_label(scenario: str, device: str, scenarios_in_chart: set[str]) -> str:
    """``"<device>"`` if only one scenario is present, else ``"<scenario> / <device>"``."""
    dev = DEVICE_LABEL.get(device, device)
    if len(scenarios_in_chart) <= 1:
        return dev
    return f"{SCENARIO_LABEL.get(scenario, scenario)} / {dev}"


def _collect(ds: Dataset, kind: str, scenario: str, device: str
             ) -> list[tuple[int, float]]:
    dev = ds.device(scenario, device)
    if dev is None:
        return []
    out: list[tuple[int, float]] = []
    for ms, iv in sorted(dev.intervals.items()):
        run = iv.runs.get(kind)
        if not run:
            continue
        v = run.sections.get("CPU Load", {}).get("max")
        if v is None:
            continue
        out.append((ms, float(v)))
    return out


def _render(kind: str, variant: str, lines, ds: Dataset, out_dir: Path) -> None:
    collected = []
    table_rows: list[dict] = []
    for scenario, device, color in lines:
        pts = _collect(ds, kind, scenario, device)
        if not pts:
            continue
        collected.append((scenario, device, color, pts))
        for ms, v in pts:
            table_rows.append({
                "scenario": scenario,
                "device": device,
                "cycle_time_ms": ms,
                "peak_cpu_pct": v,
            })
    if not collected:
        print(f"cpu_{kind}__{variant}: no data, skipping")
        return
    df = pd.DataFrame(table_rows)
    save_table(df, out_dir, f"cpu_{kind}__{variant}")

    scenarios_in_chart = {sc for sc, _, _, _ in collected}

    fig, ax = plt.subplots(figsize=(8, 5))
    for scenario, device, color, pts in collected:
        xs = [ms for ms, _ in pts]
        ys = [v for _, v in pts]
        label = _line_label(scenario, device, scenarios_in_chart)
        ax.plot(xs, ys, marker="o", color=color, label=label, linewidth=2)

    # Place value labels without overlap: at each x, sort by y and stack
    # bottom-most below the marker, top-most above, middles offset sideways.
    per_x: dict[float, list[tuple[float, str, int]]] = {}
    for idx, (_s, _d, color, pts) in enumerate(collected):
        for x, y in pts:
            per_x.setdefault(x, []).append((y, color, idx))
    for x, items in per_x.items():
        items.sort(key=lambda t: t[0])
        n = len(items)
        for rank, (y, color, _idx) in enumerate(items):
            if n == 1:
                dx, dy, ha, va = 0, 7, "center", "bottom"
            elif rank == 0:
                dx, dy, ha, va = 0, -8, "center", "top"
            elif rank == n - 1:
                dx, dy, ha, va = 0, 7, "center", "bottom"
            else:
                # middle entries: offset to the right, alternating up/down
                dx, dy = 8, (5 if rank % 2 else -5)
                ha, va = "left", "center"
            ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                        xytext=(dx, dy), ha=ha, va=va,
                        fontsize=8, color=color)

    # Idle baselines (one per scenario/device line, peak of idle samples)
    seen_idle: set[tuple[str, str]] = set()
    for scenario, device, color, _pts in collected:
        if (scenario, device) in seen_idle:
            continue
        seen_idle.add((scenario, device))
        dev = ds.device(scenario, device)
        if dev is None or not dev.idle.cpu_samples:
            continue
        idle_peak = max(dev.idle.cpu_samples)
        ax.axhline(idle_peak, color=color, linestyle=IDLE_LINESTYLE,
                   linewidth=IDLE_LINEWIDTH, alpha=IDLE_ALPHA,
                   label=IDLE_LABEL_FMT.format(
                       label=_line_label(scenario, device, scenarios_in_chart),
                       value=idle_peak))
    ax.set_xscale("log")
    ax.invert_xaxis()
    # Pin major ticks to actual cycle-time samples so the dotted gridlines
    # only appear at meaningful values instead of at every log decade.
    all_xs = sorted({x for _s, _d, _c, pts in collected for x, _ in pts})
    ax.set_xticks(all_xs)
    fmt = mticker.FuncFormatter(lambda v, _pos: f"{int(round(v)):d}")
    ax.xaxis.set_major_formatter(fmt)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlabel(X_LABEL)
    ax.set_ylabel(Y_LABEL)
    ax.set_title(f"CPU load - {WORKLOAD_TITLE.get(kind, kind)}")
    ax.grid(True, which="major", linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="best", fontsize=9)
    cur = ax.get_ylim()[1]
    ax.set_ylim(0, max(cur * 1.10, 100))
    save_fig(fig, out_dir, f"cpu_{kind}__{variant}")
    plt.close(fig)


def render_all(ds: Dataset, out_dir: Path) -> None:
    for kind, variants in VARIANTS.items():
        for variant, lines in variants.items():
            if not INCLUDE_NO_MODULE:
                lines = [ln for ln in lines if ln[0] != "no_module"]
            _render(kind, variant, lines, ds, out_dir)
