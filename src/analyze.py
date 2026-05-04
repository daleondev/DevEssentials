"""Single CLI entrypoint: render all plot families from a samples/ root."""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import ensure_out
from .dataset import discover
from .plots import cpu, memory, rtt


FAMILIES = {
    "memory": memory.render_all,
    "cpu": cpu.render_all,
    "rtt": rtt.render_all,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Render benchmark analyzer plots from a samples/ tree.")
    p.add_argument("samples_root", nargs="?", default="samples",
                   help="Path to samples/ tree (default: ./samples).")
    p.add_argument("--out", default="output",
                   help="Output directory (default: ./output).")
    p.add_argument("--only", default=None,
                   help="Comma-separated subset of: " + ",".join(FAMILIES))
    args = p.parse_args(argv)

    selected = list(FAMILIES) if not args.only else [
        s.strip() for s in args.only.split(",") if s.strip()]
    unknown = [s for s in selected if s not in FAMILIES]
    if unknown:
        p.error(f"unknown family/families: {', '.join(unknown)}")

    ds = discover(args.samples_root)
    out = ensure_out(args.out)
    for name in selected:
        FAMILIES[name](ds, out)
    print(f"wrote {', '.join(selected)} to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
