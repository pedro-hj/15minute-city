"""Medições da árvore uv/CLI e contexto da máquina; unidades no nome dos campos."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import platform
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

MONITOR_ERRORS = (OSError, RuntimeError, ValueError) + (
    (psutil.Error,) if psutil is not None else ()
)
try:
    import resource
except ImportError:
    resource = None

MIB = 1024**2
SCHEMA_VERSION = "1.0"
METRIC_FIELDS = [
    "measurement_status",
    "started_at_utc",
    "finished_at_utc",
    "wall_seconds",
    "cpu_user_seconds",
    "cpu_system_seconds",
    "cpu_total_seconds",
    "cpu_time_method",
    "cpu_mean_percent_one_core",
    "cpu_mean_percent_machine",
    "logical_cpus_visible",
    "rss_peak_sampled_mib",
    "rss_mean_sampled_mib",
    "rss_peak_sampled_percent_machine",
    "processes_peak_sampled",
    "samples",
    "samples_with_processes",
    "sample_interval_seconds",
    "machine_cpu_mean_percent",
    "machine_cpu_peak_sampled_percent",
    "machine_ram_peak_percent",
    "machine_ram_available_min_mib",
    "machine_swap_peak_mib",
    "machine_disk_read_bytes",
    "machine_disk_write_bytes",
    "machine_network_sent_bytes",
    "machine_network_received_bytes",
    "process_block_inputs",
    "process_block_outputs",
    "process_minor_page_faults",
    "process_major_page_faults",
    "sample_errors",
    "series_csv",
    "metrics_json",
]
SAMPLE_FIELDS = [
    "timestamp_utc",
    "elapsed_seconds",
    "processes",
    "rss_mib",
    "cpu_observed_seconds",
    "cpu_interval_percent_one_core",
    "cpu_interval_percent_machine",
    "machine_cpu_percent",
    "machine_ram_percent",
    "machine_ram_available_mib",
    "machine_swap_mib",
]


def utc_now():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def require_psutil():
    if psutil is None:
        raise RuntimeError(
            "O monitor requer psutil. Execute pelo lançador .sh/.ps1 atualizado ou use: "
            "uv run --no-project --with psutil==7.2.2 python lote.py [argumentos]"
        )


def sha256_file(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * MIB), b""):
            result.update(chunk)
    return result.hexdigest()


def file_metadata(path, full_hash=False):
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256_file(path) if full_hash else None,
    }


def small_command(command, cwd):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def environment_metadata(project, pbf, grid, interval, full_hash=False):
    require_psutil()
    cpu_model = platform.processor()
    if sys.platform.startswith("linux"):
        try:
            cpu_model = next(
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            )
        except (OSError, StopIteration):
            pass
    try:
        affinity = psutil.Process().cpu_affinity()
    except (AttributeError, psutil.Error):
        affinity = None
    cgroup = {}
    for filename in ("cpu.max", "memory.max", "cpuset.cpus.effective"):
        try:
            cgroup[filename] = (Path("/sys/fs/cgroup") / filename).read_text().strip()
        except OSError:
            pass
    paths = list((project / ".venv" / "lib").glob("python*/site-packages"))
    if (project / ".venv" / "Lib" / "site-packages").is_dir():
        paths.append(project / ".venv" / "Lib" / "site-packages")
    packages = {}
    for distribution in importlib.metadata.distributions(path=[str(p) for p in paths]):
        name = distribution.metadata.get("Name")
        if name:
            packages[name] = distribution.version
    venv_config = project / ".venv" / "pyvenv.cfg"
    git_changes = small_command(
        ["git", "status", "--porcelain", "--untracked-files=no"], project
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "recorded_at_utc": utc_now(),
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "cpu_model": cpu_model,
            "logical_cpus_visible": psutil.cpu_count(),
            "physical_cores_visible": psutil.cpu_count(logical=False),
            "cpu_affinity": affinity,
            "ram_total_bytes_visible": psutil.virtual_memory().total,
            "swap_total_bytes_visible": psutil.swap_memory().total,
            "cgroup_v2_limits_if_visible": cgroup,
        },
        "software": {
            "monitor_python": sys.version,
            "monitor_python_executable": sys.executable,
            "psutil_version": psutil.__version__,
            "uv_version": small_command(["uv", "--version"], project),
            "project_git_commit": small_command(["git", "rev-parse", "HEAD"], project),
            "project_tracked_changes": git_changes,
            "project_venv_config": venv_config.read_text()
            if venv_config.is_file()
            else None,
            "project_venv_packages_before_batch": packages,
            "uv_lock": file_metadata(project / "uv.lock", True)
            if (project / "uv.lock").is_file()
            else None,
        },
        "inputs": {
            "pbf": file_metadata(pbf, full_hash),
            "population_grid": file_metadata(grid, full_hash),
        },
        "monitor_sources": {
            p.name: sha256_file(p) for p in Path(__file__).parent.glob("*.py")
        },
        "measurement": {
            "scope": "uv run fifteen-minute-city and descendants; whole CLI invocation",
            "sample_interval_seconds": interval,
            "cpu_method_unix": "delta getrusage(RUSAGE_CHILDREN) before spawn/after wait, for reaped children",
            "cpu_method_other": "sum of last observed own user/system counters per PID and creation time; lower-bound estimate",
            "cpu_one_core_percent": "100 * cpu_total_seconds / wall_seconds; may exceed 100",
            "cpu_machine_percent": "one_core_percent / logical CPUs visible; not adjusted for cgroup quotas",
            "memory": "sampled sum of RSS for observed living processes; shared pages may be counted more than once",
            "memory_mean": "time-weighted left-step estimate; zero at final sample has zero weight",
            "machine_metrics": "whole OS view, includes other jobs, database, monitor and shared caches; no causal attribution",
            "external_services": "PostgreSQL, API workers and remote services are outside the measured process tree",
            "disk_counters": "OS aggregate block-device counters; device stacking and caches affect interpretation",
            "cache_state": "not classified; command time includes cache reads/builds, downloads, uv setup and database writes",
            "input_hashing": "full SHA256 before timing"
            if full_hash
            else "path/size/mtime only; no content identity guarantee",
            "missing_data": "null in JSON / empty CSV field; never substituted with zero",
            "limits": "short-lived descendants and sub-interval peaks may be missed; sampling adds overhead",
        },
    }


def usage_snapshot():
    return resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None


def counter_delta(before, after, name):
    if before is None or after is None:
        return None
    delta = getattr(after, name) - getattr(before, name)
    return delta if delta >= 0 else None


def machine_cpu_percent(before, after):
    if before is None or after is None:
        return None
    fields = [name for name in after._fields if name not in {"guest", "guest_nice"}]
    total = sum(getattr(after, f) - getattr(before, f) for f in fields)
    idle = sum(getattr(after, f, 0) - getattr(before, f, 0) for f in ("idle", "iowait"))
    return max(0.0, min(100.0, 100 * (total - idle) / total)) if total > 0 else None


class ResourceMonitor:
    def __init__(self, pid, series_path, interval, started, started_utc):
        require_psutil()
        self.pid, self.interval, self.started, self.started_utc = (
            pid,
            interval,
            started,
            started_utc,
        )
        self.series_path = series_path
        self.logical_cpus = psutil.cpu_count() or 1
        self.ram_total = psutil.virtual_memory().total
        self.stop_event = threading.Event()
        self.known = {}
        self.last_counters = {}
        self.last_sample = None
        self.cpu_last = None
        self.rss_area = self.rss_seconds = self.machine_cpu_area = (
            self.machine_cpu_seconds
        ) = 0.0
        self.samples = self.samples_with_processes = self.errors = self.process_peak = 0
        self.rss_peak = self.machine_cpu_peak = self.ram_peak = self.swap_peak = (
            self.available_min
        ) = None
        self.disk_before = self.safe(psutil.disk_io_counters)
        self.net_before = self.safe(psutil.net_io_counters)
        self.cpu_before = self.safe(psutil.cpu_times)
        self.thread = None
        self.stream = None

    def safe(self, function):
        try:
            return function()
        except (psutil.Error, OSError, NotImplementedError):
            self.errors += 1
            return None

    def start(self):
        self.stream = self.series_path.open("w", encoding="utf-8-sig", newline="")
        self.writer = csv.DictWriter(self.stream, fieldnames=SAMPLE_FIELDS)
        self.writer.writeheader()
        self.sample()
        self.thread = threading.Thread(
            target=self.loop, name="resource-monitor", daemon=True
        )
        self.thread.start()

    def loop(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.sample()
            except MONITOR_ERRORS:
                self.errors += 1

    def processes(self):
        try:
            parent = psutil.Process(self.pid)
            for process in [parent, *parent.children(recursive=True)]:
                try:
                    self.known[(process.pid, process.create_time())] = process
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            self.errors += 1
        return list(self.known.items())

    def sample(self):
        now = time.monotonic()
        rss = count = 0
        for identity, process in self.processes():
            try:
                if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                    continue
                with process.oneshot():
                    memory = process.memory_info()
                    cpu = process.cpu_times()
                rss += memory.rss
                count += 1
                old = self.last_counters.get(identity, (0, 0))
                self.last_counters[identity] = (
                    max(old[0], cpu.user),
                    max(old[1], cpu.system),
                )
            except psutil.NoSuchProcess:
                pass
            except (psutil.AccessDenied, OSError):
                self.errors += 1
        total_cpu = sum(sum(values) for values in self.last_counters.values())
        machine_times = self.safe(psutil.cpu_times)
        machine_cpu = machine_cpu_percent(self.cpu_before, machine_times)
        self.cpu_before = machine_times
        vm, swap = self.safe(psutil.virtual_memory), self.safe(psutil.swap_memory)
        dt = max(0, now - self.last_sample["time"]) if self.last_sample else 0
        cpu_percent = None
        if self.last_sample and dt:
            cpu_percent = max(0, total_cpu - self.last_sample["cpu"]) / dt * 100
            if self.last_sample["processes"]:
                self.rss_area += self.last_sample["rss"] * dt
                self.rss_seconds += dt
            if machine_cpu is not None:
                self.machine_cpu_area += machine_cpu * dt
                self.machine_cpu_seconds += dt
        self.last_sample = {
            "time": now,
            "cpu": total_cpu,
            "rss": rss,
            "processes": count,
        }
        self.samples += 1
        if count:
            self.samples_with_processes += 1
            self.rss_peak = max(self.rss_peak or 0, rss)
            self.process_peak = max(self.process_peak, count)
        if machine_cpu is not None:
            self.machine_cpu_peak = max(self.machine_cpu_peak or 0, machine_cpu)
        if vm:
            self.ram_peak = max(self.ram_peak or 0, vm.percent)
            self.available_min = min(
                self.available_min if self.available_min is not None else vm.available,
                vm.available,
            )
        if swap:
            self.swap_peak = max(self.swap_peak or 0, swap.used)
        self.writer.writerow(
            {
                "timestamp_utc": utc_now(),
                "elapsed_seconds": round(now - self.started, 6),
                "processes": count,
                "rss_mib": rss / MIB if count else None,
                "cpu_observed_seconds": total_cpu if self.last_counters else None,
                "cpu_interval_percent_one_core": cpu_percent,
                "cpu_interval_percent_machine": cpu_percent / self.logical_cpus
                if cpu_percent is not None
                else None,
                "machine_cpu_percent": machine_cpu,
                "machine_ram_percent": vm.percent if vm else None,
                "machine_ram_available_mib": vm.available / MIB if vm else None,
                "machine_swap_mib": swap.used / MIB if swap else None,
            }
        )
        self.stream.flush()

    def finish(self, before, after, finished, finished_utc):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        try:
            self.sample()
        finally:
            if self.stream:
                self.stream.close()
        wall = max(0, finished - self.started)
        if before is not None and after is not None:
            user, system = (
                counter_delta(before, after, "ru_utime"),
                counter_delta(before, after, "ru_stime"),
            )
            method = "rusage_children_delta"
        else:
            user = (
                sum(v[0] for v in self.last_counters.values())
                if self.last_counters
                else None
            )
            system = (
                sum(v[1] for v in self.last_counters.values())
                if self.last_counters
                else None
            )
            method = "sampled_observed_process_counters_lower_bound"
        cpu = user + system if user is not None and system is not None else None
        percent = cpu / wall * 100 if cpu is not None and wall else None
        disk_after, net_after = (
            self.safe(psutil.disk_io_counters),
            self.safe(psutil.net_io_counters),
        )
        return {
            "measurement_status": "PARTIAL"
            if self.errors or not self.samples_with_processes
            else "OK",
            "started_at_utc": self.started_utc,
            "finished_at_utc": finished_utc,
            "wall_seconds": wall,
            "cpu_user_seconds": user,
            "cpu_system_seconds": system,
            "cpu_total_seconds": cpu,
            "cpu_time_method": method,
            "cpu_mean_percent_one_core": percent,
            "cpu_mean_percent_machine": percent / self.logical_cpus
            if percent is not None
            else None,
            "logical_cpus_visible": self.logical_cpus,
            "rss_peak_sampled_mib": self.rss_peak / MIB
            if self.rss_peak is not None
            else None,
            "rss_mean_sampled_mib": self.rss_area / self.rss_seconds / MIB
            if self.rss_seconds
            else None,
            "rss_peak_sampled_percent_machine": self.rss_peak / self.ram_total * 100
            if self.rss_peak is not None
            else None,
            "processes_peak_sampled": self.process_peak
            if self.samples_with_processes
            else None,
            "samples": self.samples,
            "samples_with_processes": self.samples_with_processes,
            "sample_interval_seconds": self.interval,
            "machine_cpu_mean_percent": self.machine_cpu_area / self.machine_cpu_seconds
            if self.machine_cpu_seconds
            else None,
            "machine_cpu_peak_sampled_percent": self.machine_cpu_peak,
            "machine_ram_peak_percent": self.ram_peak,
            "machine_ram_available_min_mib": self.available_min / MIB
            if self.available_min is not None
            else None,
            "machine_swap_peak_mib": self.swap_peak / MIB
            if self.swap_peak is not None
            else None,
            "machine_disk_read_bytes": counter_delta(
                self.disk_before, disk_after, "read_bytes"
            ),
            "machine_disk_write_bytes": counter_delta(
                self.disk_before, disk_after, "write_bytes"
            ),
            "machine_network_sent_bytes": counter_delta(
                self.net_before, net_after, "bytes_sent"
            ),
            "machine_network_received_bytes": counter_delta(
                self.net_before, net_after, "bytes_recv"
            ),
            "process_block_inputs": counter_delta(before, after, "ru_inblock"),
            "process_block_outputs": counter_delta(before, after, "ru_oublock"),
            "process_minor_page_faults": counter_delta(before, after, "ru_minflt"),
            "process_major_page_faults": counter_delta(before, after, "ru_majflt"),
            "sample_errors": self.errors,
            "series_csv": str(self.series_path),
        }
