"""Reproducible server-script timings. Not a browser/Cloud latency measurement."""
import argparse
import gc
import hashlib
import json
import logging
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def offline_http(*args, **kwargs):
    # Reusing one exception instance accumulates traceback frames and retains
    # prior app runs, creating a false linear RSS leak in the benchmark.
    raise requests.Timeout("benchmark offline")


def offline_urlopen(*args, **kwargs):
    raise OSError("benchmark offline")


def resources():
    gc.collect()
    try:
        resident_pages = int(Path('/proc/self/statm').read_text().split()[1])
        import os
        rss = resident_pages*os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError):
        rss = None
    return {"threads": threading.active_count(), "rss_bytes": rss}


def summary(samples, failures):
    values = sorted(samples)
    return {"samples": len(samples), "failures": failures,
            "failure_rate": failures/len(samples) if samples else None,
            "median_seconds": statistics.median(values) if values else None,
            "p95_seconds": values[max(0, int(len(values)*.95+.999)-1)] if values else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cold", type=int, default=3)
    parser.add_argument("--warm", type=int, default=100)
    parser.add_argument("--interactions", type=int, default=100)
    parser.add_argument("--child-cold", action="store_true")
    parser.add_argument("--output", default="runtime_benchmark.json")
    args = parser.parse_args()
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    if args.child_cold:
        with patch.object(requests.sessions.Session, "request", new=offline_http), \
             patch("urllib.request.urlopen", new=offline_urlopen):
            started = time.perf_counter()
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
            print(json.dumps({"seconds": time.perf_counter()-started,
                              "failed": bool(app.exception) or len(app.button_group) != 13}))
        return
    cold, cold_failed = [], 0
    for _ in range(args.cold):
        child = subprocess.run([sys.executable, __file__, "--child-cold"], cwd=ROOT,
                               capture_output=True, text=True, timeout=90, check=True)
        result = json.loads(child.stdout.splitlines()[-1])
        cold.append(result["seconds"]); cold_failed += result["failed"]
    warm, interactions, resource_samples = [], [], []
    warm_failed = interaction_failed = 0
    with patch.object(requests.sessions.Session, "request", new=offline_http), \
         patch("urllib.request.urlopen", new=offline_urlopen):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        for index in range(args.warm):
            started = time.perf_counter(); app.run()
            warm.append(time.perf_counter()-started)
            warm_failed += bool(app.exception) or len(app.button_group) != 13
            if (index+1) % 20 == 0:
                resource_samples.append({"phase": "warm", "sample": index+1, **resources()})
                print(f"Warm samples: {index+1}", flush=True)
        for index in range(args.interactions):
            selected = ("5Y", "1Y", "6M", "3M", "1M")[index % 5]
            started = time.perf_counter()
            app.segmented_control(key="hk_6_range_time_window").set_value(selected).run()
            interactions.append(time.perf_counter()-started)
            interaction_failed += bool(app.exception) or app.segmented_control(key="hk_6_range_time_window").value != selected
            if (index+1) % 20 == 0:
                resource_samples.append({"phase": "range_input", "sample": index+1, **resources()})
                print(f"Range-input samples: {index+1}", flush=True)
        native_bytes = sum(len(chart.proto.spec.encode()) for chart in app.get("echarts_chart"))
        resources_before = {"threads": threading.active_count(), "native_spec_bytes": native_bytes,
                            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        st.cache_resource.clear()
        deadline = time.monotonic()+5
        while threading.active_count() > 4 and time.monotonic() < deadline:
            time.sleep(.05)
        after_release = resources()
    report = {"environment": "AppTest server-script runtime, real snapshots, external requests immediately fail",
              "offline_transport": "fresh exception per request; no mock call-history accumulation",
              "limitations": ["No browser JS or transport latency measured", "AppTest range input reruns the script, not a browser fragment", "Cold samples use independent Python processes, not Cloud wake-ups", "Peak RSS is a process high-water mark, not evidence of memory convergence"],
              "cloud_verified": False, "cold_script": summary(cold, cold_failed),
              "warm_script": summary(warm, warm_failed),
              "range_input_script": summary(interactions, interaction_failed),
              "resource_sample": resources_before, "resource_samples": resource_samples,
              "resources_after_cache_release": after_release,
              "thread_names_after_release": [thread.name for thread in threading.enumerate()],
              "source_fingerprints": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in [ROOT/'app.py', *sorted((ROOT/'data_snapshots').rglob('*.json'))]}}
    Path(args.output).write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
