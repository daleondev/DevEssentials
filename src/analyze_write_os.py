"""Idle baseline vs 'Benchmark Write OS' workload (CPU/Heap/Stack + RTT)."""
from __future__ import annotations

from ._compare import run


def main(argv: list[str] | None = None) -> int:
    return run(workload_file="write_os.txt", workload_label="write_os",
               default_prefix="write_os", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
