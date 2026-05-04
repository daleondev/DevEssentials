"""Walk a samples/ tree and produce a typed Dataset for the plotting layer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import parsers


_INTERVAL_RE = re.compile(r"^(\d+)ms$")
_WORKLOAD_FILES = ("write_os.txt", "outputs.txt", "outputs_interval.txt")


@dataclass
class BuildInfo:
    variant: str
    path: Path
    regions: dict[str, dict[str, float]]


@dataclass
class WorkloadRun:
    """A single parsed workload file inside an interval directory."""
    kind: str               # 'write_os' | 'outputs' | 'outputs_interval'
    interval_ms: int
    path: Path
    sections: dict[str, dict[str, float | None]]


@dataclass
class IntervalData:
    interval_ms: int
    runs: dict[str, WorkloadRun] = field(default_factory=dict)
    cpuload_write: list[float] | None = None
    cpuload_outputs: list[float] | None = None


@dataclass
class IdleData:
    cpu_samples: list[float] | None = None
    heap: dict[str, float] | None = None
    stack: pd.DataFrame | None = None


@dataclass
class RttData:
    path: Path
    sections: dict[str, dict[str, float | None]]


@dataclass
class DeviceData:
    scenario: str
    device: str
    root: Path
    idle: IdleData
    intervals: dict[int, IntervalData] = field(default_factory=dict)
    rtt: RttData | None = None


@dataclass
class Dataset:
    root: Path
    builds: dict[str, BuildInfo] = field(default_factory=dict)
    scenarios: dict[str, dict[str, DeviceData]] = field(default_factory=dict)

    # convenience
    def device(self, scenario: str, device: str) -> DeviceData | None:
        return self.scenarios.get(scenario, {}).get(device)

    def all_devices(self) -> list[DeviceData]:
        return [d for devs in self.scenarios.values() for d in devs.values()]


# --------------------------------------------------------------------------- #

def _load_idle(device_root: Path) -> IdleData:
    idle = IdleData()
    cpu = device_root / "cpuload_idle.txt"
    heap = device_root / "heap.txt"
    stack = device_root / "stack.txt"
    if cpu.is_file():
        idle.cpu_samples = parsers.parse_cpuload_log(str(cpu))
    if heap.is_file():
        idle.heap = parsers.parse_heap(str(heap))
    if stack.is_file():
        idle.stack = parsers.parse_stack(str(stack))
    return idle


def _load_interval(interval_root: Path, interval_ms: int) -> IntervalData:
    iv = IntervalData(interval_ms=interval_ms)
    for kind_file in _WORKLOAD_FILES:
        p = interval_root / kind_file
        if not p.is_file():
            continue
        kind = kind_file.removesuffix(".txt")
        iv.runs[kind] = WorkloadRun(
            kind=kind,
            interval_ms=interval_ms,
            path=p,
            sections=parsers.parse_workload_block(str(p)),
        )
    cw = interval_root / "cpuload_write.txt"
    co = interval_root / "cpuload_outputs.txt"
    if cw.is_file():
        iv.cpuload_write = parsers.parse_cpuload_log(str(cw))
    if co.is_file():
        iv.cpuload_outputs = parsers.parse_cpuload_log(str(co))
    return iv


def _load_device(scenario: str, device_root: Path) -> DeviceData:
    dev = DeviceData(
        scenario=scenario,
        device=device_root.name,
        root=device_root,
        idle=_load_idle(device_root),
    )
    for child in sorted(device_root.iterdir()):
        if not child.is_dir():
            continue
        m = _INTERVAL_RE.match(child.name)
        if not m:
            continue
        ms = int(m.group(1))
        dev.intervals[ms] = _load_interval(child, ms)
    rtt = device_root / "rtt.txt"  # device-level rtt.txt (not present today)
    if not rtt.is_file():
        # fall back to per-interval rtt.txt (250ms case)
        for ivdir in device_root.glob("*ms"):
            cand = ivdir / "rtt.txt"
            if cand.is_file():
                rtt = cand
                break
    if rtt.is_file():
        dev.rtt = RttData(path=rtt, sections=parsers.parse_rtt(str(rtt)))
    return dev


def discover(samples_root: str | Path) -> Dataset:
    root = Path(samples_root)
    ds = Dataset(root=root)
    # build_*.txt at the root
    for p in sorted(root.glob("build_*.txt")):
        variant = p.stem.removeprefix("build_")
        ds.builds[variant] = BuildInfo(variant=variant, path=p,
                                       regions=parsers.parse_build(str(p)))
    # scenarios = top-level dirs containing devices
    for scenario_dir in sorted(root.iterdir()):
        if not scenario_dir.is_dir():
            continue
        devices: dict[str, DeviceData] = {}
        for device_dir in sorted(scenario_dir.iterdir()):
            if not device_dir.is_dir():
                continue
            devices[device_dir.name] = _load_device(scenario_dir.name, device_dir)
        if devices:
            ds.scenarios[scenario_dir.name] = devices
    return ds


if __name__ == "__main__":  # pragma: no cover - smoke print
    import sys
    ds = discover(sys.argv[1] if len(sys.argv) > 1 else "samples")
    print(f"builds: {list(ds.builds)}")
    for sc, devs in ds.scenarios.items():
        for name, d in devs.items():
            ivs = sorted(d.intervals)
            print(f"  {sc}/{name}: idle={'cpu' if d.idle.cpu_samples else '-'}/"
                  f"{'heap' if d.idle.heap else '-'}/"
                  f"{'stack' if d.idle.stack is not None else '-'}, "
                  f"intervals={ivs}, rtt={'yes' if d.rtt else 'no'}")
