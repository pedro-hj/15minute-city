from __future__ import annotations

import os
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import psutil


def _bytes_to_mib(value: float) -> float:
    return round(value / (1024**2), 3)


def _cpu_model() -> str:
    if Path("/proc/cpuinfo").is_file():
        for line in (
            Path("/proc/cpuinfo")
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        ):
            if line.lower().startswith("model name"):
                return line.split(":", maxsplit=1)[1].strip()
    return platform.processor() or "unknown"


def collect_hardware_information() -> dict[str, Any]:
    """Describe the hardware and operating system used by a benchmark."""
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    frequency = psutil.cpu_freq()
    disk = psutil.disk_usage(Path.cwd().anchor or "/")
    return {
        "processor": {
            "model": _cpu_model(),
            "architecture": platform.machine(),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "frequency_mhz": (
                round(frequency.current, 3) if frequency is not None else None
            ),
        },
        "memory": {
            "ram_total_mib": _bytes_to_mib(memory.total),
            "swap_total_mib": _bytes_to_mib(swap.total),
        },
        "disk": {
            "filesystem": Path.cwd().anchor or "/",
            "total_mib": _bytes_to_mib(disk.total),
            "free_mib_at_start": _bytes_to_mib(disk.free),
        },
        "system": {
            "operating_system": platform.system(),
            "release": platform.release(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
    }


@dataclass(frozen=True, slots=True)
class PerformanceMeasurement:
    duration_seconds: float
    cpu_time_seconds: float
    cpu_average_percent_one_core: float
    cpu_average_percent_total_capacity: float
    ram_start_mib: float
    ram_end_mib: float
    ram_change_mib: float
    ram_peak_mib: float

    def to_dict(self) -> dict[str, float]:
        return {
            "duration_seconds": self.duration_seconds,
            "cpu_time_seconds": self.cpu_time_seconds,
            "cpu_average_percent_one_core": self.cpu_average_percent_one_core,
            "cpu_average_percent_total_capacity": (
                self.cpu_average_percent_total_capacity
            ),
            "ram_start_mib": self.ram_start_mib,
            "ram_end_mib": self.ram_end_mib,
            "ram_change_mib": self.ram_change_mib,
            "ram_peak_mib": self.ram_peak_mib,
        }


class ProcessTreeProfiler:
    """Sample CPU time and resident memory for this process and its children."""

    def __init__(self, *, sample_interval_seconds: float = 0.1) -> None:
        self.sample_interval_seconds = sample_interval_seconds
        self._process = psutil.Process(os.getpid())
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cpu_by_pid: dict[int, float] = {}
        self._start_cpu_by_pid: dict[int, float] = {}
        self._ram_start_bytes = 0
        self._ram_end_bytes = 0
        self._ram_peak_bytes = 0
        self._started_at = 0.0
        self._ended_at = 0.0

    def _process_tree(self) -> list[psutil.Process]:
        try:
            return [self._process, *self._process.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return [self._process]

    def _sample(self) -> int:
        total_rss = 0
        for process in self._process_tree():
            try:
                cpu = process.cpu_times()
                self._cpu_by_pid[process.pid] = max(
                    self._cpu_by_pid.get(process.pid, 0.0), cpu.user + cpu.system
                )
                total_rss += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self._ram_peak_bytes = max(self._ram_peak_bytes, total_rss)
        return total_rss

    def _monitor(self) -> None:
        while not self._stop_event.wait(self.sample_interval_seconds):
            self._sample()

    def __enter__(self) -> Self:
        self._sample()
        self._start_cpu_by_pid = dict(self._cpu_by_pid)
        self._ram_start_bytes = self._sample()
        self._started_at = time.perf_counter()
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        self._ram_end_bytes = self._sample()
        self._ended_at = time.perf_counter()

    def result(self) -> PerformanceMeasurement:
        if self._ended_at == 0:
            raise RuntimeError("profiler must finish before its result is read")
        duration = self._ended_at - self._started_at
        cpu_seconds = sum(
            final - self._start_cpu_by_pid.get(pid, 0.0)
            for pid, final in self._cpu_by_pid.items()
        )
        logical_cores = psutil.cpu_count(logical=True) or 1
        one_core_percent = 100.0 * cpu_seconds / duration if duration else 0.0
        return PerformanceMeasurement(
            duration_seconds=round(duration, 6),
            cpu_time_seconds=round(cpu_seconds, 6),
            cpu_average_percent_one_core=round(one_core_percent, 3),
            cpu_average_percent_total_capacity=round(
                one_core_percent / logical_cores, 3
            ),
            ram_start_mib=_bytes_to_mib(self._ram_start_bytes),
            ram_end_mib=_bytes_to_mib(self._ram_end_bytes),
            ram_change_mib=_bytes_to_mib(self._ram_end_bytes - self._ram_start_bytes),
            ram_peak_mib=_bytes_to_mib(self._ram_peak_bytes),
        )
