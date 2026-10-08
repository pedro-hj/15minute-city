import time

from fifteen_minute_city.infrastructure.performance import (
    ProcessTreeProfiler,
    collect_hardware_information,
)


def test_process_tree_profiler_reports_time_cpu_and_memory() -> None:
    with ProcessTreeProfiler(sample_interval_seconds=0.001) as profiler:
        sum(index * index for index in range(20_000))
        time.sleep(0.002)

    result = profiler.result()

    assert result.duration_seconds > 0
    assert result.cpu_time_seconds >= 0
    assert result.cpu_average_percent_one_core >= 0
    assert result.cpu_average_percent_total_capacity >= 0
    assert result.ram_start_mib > 0
    assert result.ram_end_mib > 0
    assert result.ram_peak_mib >= max(result.ram_start_mib, result.ram_end_mib)


def test_hardware_information_has_reproducibility_fields() -> None:
    information = collect_hardware_information()

    assert information["processor"]["model"]
    assert information["processor"]["logical_cores"] >= 1
    assert information["memory"]["ram_total_mib"] > 0
    assert information["system"]["python_version"]
    assert "hostname" not in information["system"]
