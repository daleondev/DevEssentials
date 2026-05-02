"""Analyze build memory-region tables; focus on OCTO_SPI_FLASH (binary size)."""
from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import (
    ensure_out,
    make_argparser,
    parse_bytes,
    parse_inputs_arg,
    read_lines,
    save_fig,
    save_table,
)

REGION = "OCTO_SPI_FLASH"
ROW_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+):\s+([\d.]+\s*[A-Za-z]+)\s+([\d.]+\s*[A-Za-z]+)\s+([\d.]+)%"
)


def parse_region(lines: list[str], region: str) -> dict[str, float] | None:
    for ln in lines:
        m = ROW_RE.match(ln)
        if not m or m.group(1) != region:
            continue
        return {
            "used_B": parse_bytes(m.group(2)),
            "total_B": parse_bytes(m.group(3)),
            "pct": float(m.group(4)),
        }
    return None


def main(argv: list[str] | None = None) -> int:
    parser = make_argparser(__doc__ or "")
    parser.add_argument("--baseline", help="Label to use as delta baseline (default: first input).")
    args = parser.parse_args(argv)
    out_dir = ensure_out(args.out)
    prefix = args.prefix or "build_flash"

    rows = []
    for label, path in parse_inputs_arg(args.inputs):
        info = parse_region(read_lines(path), REGION)
        if info is None:
            print(f"warning: {REGION} not found in {label} ({path})")
            continue
        rows.append({"Source": label, **info})

    if not rows:
        print(f"error: no {REGION} entries found")
        return 1

    df = pd.DataFrame(rows)
    df["used_KB"] = (df["used_B"] / 1024).round(2)
    df["total_KB"] = (df["total_B"] / 1024).round(2)
    df["free_KB"] = ((df["total_B"] - df["used_B"]) / 1024).round(2)
    df["used_%_of_total"] = (df["used_B"] / df["total_B"] * 100).round(2)

    baseline = args.baseline or df["Source"].iloc[0]
    if baseline not in df["Source"].values:
        print(f"error: baseline {baseline!r} not in inputs")
        return 1
    base_used = df.loc[df["Source"] == baseline, "used_B"].iloc[0]
    total_B = df["total_B"].iloc[0]
    df["delta_B"] = (df["used_B"] - base_used).astype(int)
    df["delta_KB"] = (df["delta_B"] / 1024).round(2)
    df["delta_%_of_total"] = ((df["used_B"] - base_used) / total_B * 100).round(2)

    save_table(df, out_dir, prefix)
    _render(df, out_dir, prefix, baseline, total_B)

    # Additional default view: drop 'feature' so main vs experimental stands alone.
    if "feature" in df["Source"].values and len(df) > 2:
        df_me = df[df["Source"] != "feature"].reset_index(drop=True)
        base_used_me = df_me.loc[df_me["Source"] == baseline, "used_B"]
        if not base_used_me.empty:
            base_me = base_used_me.iloc[0]
            df_me = df_me.copy()
            df_me["delta_B"] = (df_me["used_B"] - base_me).astype(int)
            df_me["delta_KB"] = (df_me["delta_B"] / 1024).round(2)
            df_me["delta_%_of_total"] = ((df_me["used_B"] - base_me) / total_B * 100).round(2)
            save_table(df_me, out_dir, f"{prefix}_main_vs_experimental")
            _render(df_me, out_dir, f"{prefix}_main_vs_experimental",
                    baseline, total_B, title="binary size")

    print(f"wrote {prefix}.md/.csv/.png to {out_dir}")
    return 0


def _render(df: pd.DataFrame, out_dir, prefix: str, baseline: str, total_B: float,
            title: str | None = None) -> None:
    total_kb = total_B / 1024
    fig, ax = plt.subplots(figsize=(max(6, 1.5 * len(df)), 4.8))
    x = np.arange(len(df))
    ax.bar(x, [total_kb] * len(df), color="#dddddd",
           edgecolor="#888888", label=f"available ({total_kb:.0f} KB)")
    bars = ax.bar(x, df["used_KB"], color="#1f77b4", label="used")
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", " ") for s in df["Source"]])
    ax.set_ylabel("flash (KB)")
    ax.set_title(title or f"{REGION} — binary size (baseline: {baseline})")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.legend(loc="upper right")
    for bar, used_kb, pct, dpct in zip(
        bars, df["used_KB"], df["used_%_of_total"], df["delta_%_of_total"]
    ):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height(),
            f"{used_kb:.0f} KB\n{pct:.2f}%  ({dpct:+.2f}%)",
            ha="center", va="bottom", fontsize=9,
        )
    ax.set_ylim(0, total_kb * 1.10)
    save_fig(fig, out_dir, prefix)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
