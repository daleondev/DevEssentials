"""Idle baseline vs 'Benchmark Monitor Outputs' workload (CPU/Heap/Stack)."""
from __future__ import annotations

from ._compare import run


def main(argv: list[str] | None = None) -> int:
    return run(workload_file="outputs.txt", workload_label="outputs",
               default_prefix="outputs", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
