"""Measure reading, core, export and readback in fresh sequential processes.

Fixture construction is excluded from timing but included in whole-process RSS.
Export timing includes the exporter's mandatory built-in audit. The separately
reported standalone audit is an additional full readback, not the export audit.
All data is synthetic and report bytes remain in memory.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
from time import perf_counter, process_time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sheetcheck import FileSpec, Mapping, Rules, Side, read_source, reconcile, validate
from sheetcheck.report import audit_xlsx, export_xlsx
from sheetcheck.models import APP_VERSION, RULES_VERSION


def _hardware():
    details = {"logical_cpu_count": os.cpu_count(), "processor": platform.processor()}
    if sys.platform == "darwin":
        try:
            values = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize"],
                                             text=True, stderr=subprocess.DEVNULL).splitlines()
            details.update(cpu_model=values[0], physical_memory_bytes=int(values[1]))
        except (OSError, subprocess.CalledProcessError, IndexError, ValueError):
            pass
    return details


def _rows(count, side, variant):
    yield ["id", "amount"]
    for index in range(count):
        identifier, amount = f"S{index:08d}", "12.30"
        if variant == "mixed":
            group, remainder = divmod(index, 10)
            if remainder == 1:
                identifier = f"中文订单_{index:08d}_" + "0" * 32
            elif remainder == 2 and side == Side.PAYMENT:
                amount = "12.31"
            elif remainder == 3:
                identifier = f"{side}_{index:08d}"
            elif remainder == 4 and side == Side.ORDER:
                amount = "invalid\namount"
            elif remainder == 5 and side == Side.ORDER:
                identifier = ""
            elif remainder in (6, 7):
                identifier = f"DUP{group:08d}"
            elif remainder == 8 and index + 1 < count:
                identifier, amount = "", ""
            elif remainder == 9:
                identifier = f'=HYPERLINK("https://invalid.example/{index}")'
        yield [identifier, amount]


def _fixture(fmt, count, side, variant):
    if fmt == "csv":
        buffer = StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerows(_rows(count, side, variant))
        return buffer.getvalue().encode("utf-8")
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Synthetic")
    for values in _rows(count, side, variant):
        # Fixture malicious prefixes are input text, not input formulas.
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def trial(fmt, count, variant):
    def peak_mib():
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / (1024 * 1024 if sys.platform == "darwin" else 1024)

    inputs = {side: _fixture(fmt, count, side, variant) for side in Side}
    peaks = {"after_fixture": peak_mib()}
    cpu_seconds = {}
    start = perf_counter()
    cpu_start = process_time()
    sources = [read_source(inputs[side], FileSpec(f"synthetic_{side}.{fmt}", side)) for side in Side]
    read_seconds = perf_counter() - start
    cpu_seconds["read"] = process_time() - cpu_start
    peaks["after_read"] = peak_mib()
    rules = Rules(period="synthetic", same_currency_confirmed=True, same_period_confirmed=True)
    start = perf_counter()
    cpu_start = process_time()
    result = reconcile(*(validate(table, Mapping(1, 2), rules) for table in sources), rules)
    core_seconds = perf_counter() - start
    cpu_seconds["core_including_audit"] = process_time() - cpu_start
    peaks["after_core"] = peak_mib()
    if len(result.ledger) != count * 2:
        raise RuntimeError("Benchmark source-ledger conservation failure")
    if any(summary.input_count != count for summary in result.manifest.summaries.values()):
        raise RuntimeError("Benchmark input-count failure")
    if variant == "clean":
        expected = {"EXACT_MATCH": count, "AMOUNT_MISMATCH": 0, "ONLY_ORDER": 0,
                    "ONLY_PAYMENT": 0, "DATA_ISSUE": 0, "SKIPPED_EMPTY": 0}
    elif count % 10 == 0:
        blocks = count // 10
        expected = {"EXACT_MATCH": 3 * blocks, "AMOUNT_MISMATCH": blocks,
                    "ONLY_ORDER": blocks, "ONLY_PAYMENT": 2 * blocks,
                    "DATA_ISSUE": 7 * blocks, "SKIPPED_EMPTY": 2 * blocks}
    else:
        expected = None
    if expected is not None and dict(result.manifest.status_counts) != expected:
        raise RuntimeError("Benchmark independently specified status-count failure")
    start = perf_counter()
    cpu_start = process_time()
    payload = export_xlsx(result)
    export_seconds = perf_counter() - start
    cpu_seconds["export_including_builtin_readback_audit"] = process_time() - cpu_start
    peaks["after_export_with_builtin_audit"] = peak_mib()
    start = perf_counter()
    cpu_start = process_time()
    audit_xlsx(payload, result)
    standalone_audit_seconds = perf_counter() - start
    cpu_seconds["additional_standalone_readback_audit"] = process_time() - cpu_start
    peaks["after_additional_audit"] = peak_mib()
    return {"status": "passed", "pid": os.getpid(),
            "read_seconds": read_seconds, "core_including_audit_seconds": core_seconds,
            "export_including_builtin_readback_audit_seconds": export_seconds,
            "additional_standalone_readback_audit_seconds": standalone_audit_seconds,
            "process_peak_rss_mib": peak_mib(), "cumulative_peak_rss_mib": peaks,
            "stage_process_cpu_seconds": cpu_seconds,
            "input_bytes": {str(side): len(data) for side, data in inputs.items()},
            "report_bytes": len(payload), "report_sha256": hashlib.sha256(payload).hexdigest(),
            "business_records": len(result.records),
            "ledger_rows": len(result.ledger), "status_counts": result.manifest.status_counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("csv", "xlsx"), default="csv")
    parser.add_argument("--variant", choices=("clean", "mixed"), default="mixed")
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--timeout", type=float, default=300,
                        help="Wall-clock timeout in seconds for each fresh child process")
    args = parser.parse_args()
    if args.rows < 1 or args.repeats < 1 or args.timeout <= 0:
        parser.error("--rows, --repeats and --timeout must be positive")
    if args.child:
        print(json.dumps(trial(args.format, args.rows, args.variant)))
        return
    trials = []
    for number in range(1, args.repeats + 1):
        start = perf_counter()
        try:
            completed = subprocess.run([
                sys.executable, __file__, "--format", args.format, "--variant", args.variant,
                "--rows", str(args.rows), "--child"], text=True, capture_output=True,
                timeout=args.timeout, check=False)
            if completed.returncode:
                trials.append({"status": "failed", "returncode": completed.returncode,
                               "stderr": completed.stderr[-4000:]})
            else:
                trials.append(json.loads(completed.stdout))
        except subprocess.TimeoutExpired:
            trials.append({"status": "timeout", "timeout_seconds": args.timeout})
        trials[-1]["trial"] = number
        trials[-1]["child_wall_seconds"] = perf_counter() - start
    successes = [trial for trial in trials if trial["status"] == "passed"]
    output = {"platform": platform.platform(), "machine": platform.machine(),
              "measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "app_version": APP_VERSION, "rules_version": RULES_VERSION,
              "dependencies": {name: importlib.metadata.version(name)
                               for name in ("openpyxl", "defusedxml", "streamlit")},
              "hardware": _hardware(), "python": platform.python_version(),
              "format": args.format, "variant": args.variant, "rows_per_side": args.rows,
              "repeats": args.repeats, "successful_trials": len(successes), "trials": trials,
              "child_timeout_seconds": args.timeout,
              "measurement": "Fresh sequential child process per trial. Fixture construction excluded "
                             "from timings and included in whole-process peak RSS. Export includes its "
                             "mandatory readback audit; standalone audit is a separate additional pass. "
                             "Stage RSS values are cumulative process high-water marks, not per-stage deltas. "
                             "All data synthetic; report bytes remain in memory."}
    if successes:
        for label, field in (("median_read_seconds", "read_seconds"),
                             ("median_core_seconds", "core_including_audit_seconds"),
                             ("median_export_including_builtin_audit_seconds", "export_including_builtin_readback_audit_seconds"),
                             ("median_additional_standalone_audit_seconds", "additional_standalone_readback_audit_seconds")):
            output[label] = statistics.median(t[field] for t in successes)
        output["max_process_peak_rss_mib"] = max(t["process_peak_rss_mib"] for t in successes)
        output["target_assessment"] = {
            "scope": "Blueprint suggested 10000 rows per side; other scales are observations only",
            "applicable": args.rows == 10000,
            "all_successful_trials_core_within_3_seconds": all(t["core_including_audit_seconds"] <= 3 for t in successes),
            "all_successful_trials_whole_process_within_512_mib": all(t["process_peak_rss_mib"] <= 512 for t in successes),
        }
    print(json.dumps(output, indent=2))
    if len(successes) != args.repeats:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
