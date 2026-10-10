"""Execute native charts in Chromium; this is CI evidence, not Cloud acceptance."""
import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


# CI-only bridge for the pinned native Streamlit component. The production
# bundle has no global ECharts registry. Find its existing instance in React's
# hook chain, then inspect ECharts' actual processed data and scale extents.
# A framework change must fail this probe, never silently skip it. This does
# not replace, patch, or create any chart or observations.
INSTANCE_JS = """element => {
    const key = Object.keys(element).find(key => key.startsWith('__reactFiber$'));
    let fiber = element[key];
    for (let level=0; fiber && level<30; level++, fiber=fiber.return) {
        for (const candidate of [fiber, fiber.alternate]) {
            let hook = candidate && candidate.memoizedState;
            for (let step=0; hook && step<80; step++, hook=hook.next) {
                const value = hook.memoizedState;
                if (value && typeof value.getModel === 'function' &&
                    typeof value.getDom === 'function' && value.getDom() === element &&
                    !value.isDisposed()) return value;
            }
        }
    }
    throw new Error('Pinned Streamlit ECharts instance probe failed');
}"""


def chart_state(chart):
    return chart.evaluate("""element => {
        const instance = (""" + INSTANCE_JS + """)(element);
        const model = instance.getModel();
        const axes = [];
        model.eachComponent('yAxis', axis => {
            const values = [];
            model.eachSeries(series => {
                if ((series.get('yAxisIndex') || 0) !== axis.componentIndex) return;
                const data = series.getData();
                const dimension = data.mapDimension('y');
                for (let index=0; index<data.count(); index++) {
                    const value = data.get(dimension, index);
                    if (Number.isFinite(value)) values.push(value);
                }
            });
            axes.push({extent: axis.axis.scale.getExtent(),
                       observed: values.length ? [Math.min(...values), Math.max(...values)] : null,
                       samples: values.length, scale: axis.get('scale')});
        });
        const grid = model.getComponent('grid').coordinateSystem.getRect();
        const slider = instance.getViewOfComponentModel(model.getComponent('dataZoom', 1));
        const handles = slider._displayables.handles.map(handle => {
            const rect = handle.getBoundingRect().clone();
            rect.applyTransform(handle.getComputedTransform());
            return {x:rect.x+rect.width/2, y:rect.y+rect.height/2};
        });
        return {zoom: model.getComponent('dataZoom').getPercentRange(), axes,
                handles,
                grid: {x:grid.x, y:grid.y, width:grid.width, height:grid.height},
                width:instance.getWidth(), height:instance.getHeight()};
    }""")


def assert_visible_axes(state):
    populated = 0
    for axis in state["axes"]:
        assert axis["scale"], axis
        if axis["observed"] is None:
            continue
        populated += 1
        low, high = axis["observed"]
        minimum, maximum = sorted(axis["extent"])
        tolerance = max(abs(low), abs(high), 1)*1e-8
        assert minimum <= low+tolerance and maximum >= high-tolerance, axis
        # A full-history or shared-axis scale would be far wider than these
        # filtered samples. Allow ECharts' own nice-tick rounding and flat data.
        assert maximum-minimum <= max((high-low)*2, max(abs(low), abs(high), 1)*.05), axis
    assert populated >= 2, state


def exercise_client_zoom(page, chart):
    chart.scroll_into_view_if_needed()
    before = chart_state(chart)
    box = chart.bounding_box()
    grid = before["grid"]
    start, end = before["zoom"]
    handle = before['handles'][0]
    target = handle['x']+grid["width"]*(end-start)/100*.35
    y = handle['y']
    page.mouse.move(box["x"]+handle['x'], box["y"]+y)
    page.mouse.down()
    page.mouse.move(box["x"]+target, box["y"]+y, steps=12)
    page.mouse.up()
    page.wait_for_timeout(200)
    slider = chart_state(chart)
    assert slider["zoom"][0] > start+.1, (before, slider)
    assert_visible_axes(slider)
    # The first native toolbox icon selects an X-only zoom box. Its geometry
    # follows the unchanged three-icon toolbox in build_adaptive_echarts_option.
    page.mouse.click(box["x"]+before["width"]-67, box["y"]+8)
    page.mouse.move(box["x"]+grid["x"]+grid["width"]*.2,
                    box["y"]+grid["y"]+grid["height"]*.25)
    page.mouse.down()
    page.mouse.move(box["x"]+grid["x"]+grid["width"]*.8,
                    box["y"]+grid["y"]+grid["height"]*.75, steps=12)
    page.mouse.up()
    page.wait_for_timeout(200)
    selected = chart_state(chart)
    assert selected["zoom"][1]-selected["zoom"][0] < slider["zoom"][1]-slider["zoom"][0]-.1, (slider, selected)
    assert_visible_axes(selected)
    return {"before": before, "slider": slider, "box_zoom": selected}


def wait_for_page(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 13", timeout=60000)
    page.wait_for_function("document.querySelectorAll('[data-testid=stEChartsChart][aria-busy=false]').length >= 8", timeout=60000)


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
            wait_for_page(page, args.url)
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
            chart = page.locator('.st-key-hk_5_range_adaptive_Raw_1Y').get_by_test_id('stEChartsChart')
            report["client_zoom"] = exercise_client_zoom(page, chart)
            report["checks"].append({"slider": True, "box_zoom": True,
                                      "processed_observations_fit_independent_axes": True})
            # Two separate browser contexts produce independent Streamlit
            # sessions. Session B must not overwrite session A's range or mode.
            context_b = browser.new_context(viewport={"width": 1440, "height": 1000})
            page_b = context_b.new_page()
            page_b.on('pageerror', lambda error: errors.append(str(error)))
            wait_for_page(page_b, args.url)
            groups.nth(4).get_by_text('1M', exact=True).click()
            page.get_by_test_id('stRadio').nth(0).get_by_text('Rebased 100', exact=True).click()
            expected_a = page.locator('[class*="st-key-hk_5_range_adaptive_Rebased"][class*="_1M"]').get_by_test_id('stEChartsChart')
            expected_a.wait_for(timeout=30000)
            page_b.get_by_test_id('stButtonGroup').nth(4).get_by_text('3M', exact=True).click()
            expected_b = page_b.locator('.st-key-hk_5_range_adaptive_Raw_3M').get_by_test_id('stEChartsChart')
            expected_b.wait_for(timeout=30000)
            assert expected_a.count() == 1 and expected_b.count() == 1
            for current, expected in ((page, expected_a), (page_b, expected_b)):
                current.locator('.st-key-refresh_market_overview').get_by_role('button').click()
                current.locator('.st-key-refresh_watchlist_quotes').get_by_role('button').click()
                expected.wait_for(timeout=30000)
                assert current.get_by_test_id('stException').count() == 0
                assert current.get_by_test_id('stEChartsChartError').count() == 0
            assert expected_a.count() == 1 and expected_b.count() == 1
            report['checks'].append({'isolated_browser_sessions': 2,
                                     'manual_market_refresh': True, 'manual_watchlist_refresh': True,
                                     'range_and_mode_preserved': True})
            context_b.close()
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
