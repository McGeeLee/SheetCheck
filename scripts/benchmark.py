"""Run isolated synthetic trials. Timings exclude fixture construction.

Peak RSS includes interpreter, dependencies, fixture creation, reading and core.
It is a whole-process peak, not a claim about adversarial files or all machines.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import io
import json
import platform
import resource
import statistics
import subprocess
import sys
from time import perf_counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sheetcheck import FileSpec, Mapping, Rules, Side, read_source, reconcile, validate


def trial(fmt, count):
    if fmt == "csv":
        data = ("id,amount\n" + "".join(f"S{i:08d},12.30\n" for i in range(count))).encode()
    else:
        from openpyxl import Workbook
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("Synthetic")
        sheet.append(["id", "amount"])
        for i in range(count):
            sheet.append([f"S{i:08d}", "12.30"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        data = buffer.getvalue()
        workbook.close()
    start = perf_counter()
    sources = [read_source(data, FileSpec(f"synthetic.{fmt}", side)) for side in Side]
    read_seconds = perf_counter() - start
    rules = Rules(period="synthetic", same_currency_confirmed=True, same_period_confirmed=True)
    start = perf_counter()
    result = reconcile(*(validate(t, Mapping(1, 2), rules) for t in sources), rules)
    core_seconds = perf_counter() - start
    if len(result.records) != count or len(result.ledger) != 2 * count or result.manifest.status_counts["EXACT_MATCH"] != count:
        raise RuntimeError("Benchmark integrity failure")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"read_seconds": read_seconds, "core_including_audit_seconds": core_seconds,
            "process_peak_rss_mib": peak / (1024 * 1024 if sys.platform == "darwin" else 1024),
            "input_bytes_per_side": len(data), "business_records": len(result.records), "ledger_rows": len(result.ledger)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("csv", "xlsx"), default="csv")
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        print(json.dumps(trial(args.format, args.rows)))
        return
    trials = [json.loads(subprocess.check_output([sys.executable, __file__, "--format", args.format,
                                                 "--rows", str(args.rows), "--child"], text=True))
              for _ in range(args.repeats)]
    output = {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
              "format": args.format, "rows_per_side": args.rows, "repeats": args.repeats, "trials": trials,
              "median_core_seconds": statistics.median(t["core_including_audit_seconds"] for t in trials),
              "max_process_peak_rss_mib": max(t["process_peak_rss_mib"] for t in trials),
              "xlsx_export": "not measured by this core-only benchmark; use scripts/benchmark_export.py",
              "measurement": "fresh child process per trial; fixture creation excluded from timing, included in peak RSS"}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
