"""Execute native charts in Chromium; this is CI evidence, not Cloud acceptance."""
import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--output", default="browser_acceptance.json")
    args = parser.parse_args()
    report = {"environment": "CI offline repository snapshots", "url": args.url,
              "cloud_verified": False, "checks": [], "status": "failed"}
    started = time.perf_counter()
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            groups = page.get_by_test_id("stButtonGroup")
            page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 13", timeout=60000)
            page.get_by_text("13. China & Japan Government Yield Curves", exact=False).wait_for(timeout=60000)
            charts = page.get_by_test_id("stEChartsChart")
            page.wait_for_function("document.querySelectorAll('[data-testid=stEChartsChart][aria-busy=false]').length >= 8", timeout=60000)
            assert groups.count() == 13
            assert charts.count() >= 8
            assert page.get_by_test_id("stException").count() == 0
            assert page.get_by_test_id("stEChartsChartError").count() == 0
            # Confirm actual canvas paint, not just a server-emitted option.
            paints = charts.evaluate_all("""elements => elements.map(element => {
                const canvases = [...element.querySelectorAll('canvas')];
                return canvases.some(canvas => {
                    if (!canvas.width || !canvas.height) return false;
                    const data = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
                    for (let i=3; i<data.length; i+=4) if(data[i]>0) return true;
                    return false;
                });
            })""")
            assert all(paints), paints
            assert page.get_by_text("该图表目前没有可验证的有效观测数据", exact=False).count() > 0
            report["checks"].append({"chart_positions": 13, "painted_native_charts": len(paints),
                                      "missing_positions_are_explicit": True})
            # All five controls exist for every position, including unavailable charts.
            report["controls"] = groups.all_text_contents()
            for index in range(13):
                for label in ("5Y", "1Y", "6M", "3M", "1M"):
                    # React Aria's selected toggle changes its accessible
                    # name; the visible range label stays stable.
                    assert groups.nth(index).get_by_text(label, exact=True).count() == 1, (index, label, report["controls"][index])
            # Use a real HK chart to exercise every server range and both market modes.
            for label in ("5Y", "1Y", "6M", "3M", "1M", "1Y"):
                groups.nth(4).get_by_text(label, exact=True).click()
                page.locator(f".st-key-hk_5_range_adaptive_Raw_{label}").get_by_test_id("stEChartsChart").wait_for(timeout=30000)
                assert page.get_by_test_id("stEChartsChartError").count() == 0
            for label in ("Rebased 100", "Raw"):
                page.get_by_test_id("stRadio").nth(0).get_by_text(label, exact=True).click()
                prefix = "Raw" if label == "Raw" else "Rebased"
                page.locator(f'[class*="st-key-hk_5_range_adaptive_{prefix}"]').get_by_test_id("stEChartsChart").wait_for(timeout=30000)
                assert page.get_by_test_id("stEChartsChartError").count() == 0
            assert not errors, errors
            page.screenshot(path="browser_acceptance.png", full_page=True)
            report["checks"].append({"hk_ranges": 5, "hk_modes": ["Raw", "Rebased 100"]})
            report["status"] = "passed"
            browser.close()
    except Exception as error:
        report["failure"] = str(error)
        raise
    finally:
        report["page_errors"] = errors
        report["seconds"] = round(time.perf_counter()-started, 3)
        Path(args.output).write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    main()
