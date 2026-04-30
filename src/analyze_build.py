"""Analyze build memory-region tables; focus on OCTO_SPI_FLASH (binary size)."""
from __future__ import annotations

import re

import matplotlib.pyplot as plt
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

    baseline = args.baseline or df["Source"].iloc[0]
    if baseline not in df["Source"].values:
        print(f"error: baseline {baseline!r} not in inputs")
        return 1
    base_used = df.loc[df["Source"] == baseline, "used_B"].iloc[0]
    df["delta_B"] = (df["used_B"] - base_used).astype(int)
    df["delta_KB"] = (df["delta_B"] / 1024).round(2)
    df["delta_%"] = ((df["used_B"] - base_used) / base_used * 100).round(2)

    save_table(df, out_dir, prefix)

    fig, ax = plt.subplots(figsize=(max(6, 1.5 * len(df)), 4.5))
    bars = ax.bar(df["Source"], df["used_KB"])
    ax.set_ylabel("used (KB)")
    ax.set_title(f"{REGION} — binary size (baseline: {baseline})")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    for bar, used_kb, dpct in zip(bars, df["used_KB"], df["delta_%"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height(),
            f"{used_kb:.0f} KB\n({dpct:+.2f}%)",
            ha="center", va="bottom", fontsize=9,
        )
    ax.set_ylim(0, df["used_KB"].max() * 1.18)
    save_fig(fig, out_dir, prefix)
    plt.close(fig)
    print(f"wrote {prefix}.md/.csv/.png to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
