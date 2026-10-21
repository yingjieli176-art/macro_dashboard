"""Execute native charts in Chromium; this is CI evidence, not Cloud acceptance."""
import argparse
import json
import re
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


# CI-only bridge for the pinned native Streamlit component. The production
# bundle has no global ECharts registry. Find its existing instance in React's
# hook chain, then inspect ECharts' actual processed data and scale extents.
# A framework change must fail this probe, never silently skip it. This does
# not replace, patch, or create any chart or observations.
INSTANCE_JS = """element => {
    if (element.__macroChart && !element.__macroChart.isDisposed()) return element.__macroChart;
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
        const toolbox = instance.getViewOfComponentModel(model.getComponent('toolbox'));
        const feature = typeof toolbox._features.get === 'function' ?
            toolbox._features.get('dataZoom') : toolbox._features.dataZoom;
        const icon = feature.model.iconPaths.zoom;
        const iconRect = icon.getBoundingRect().clone();
        iconRect.applyTransform(icon.getComputedTransform());
        return {zoom: model.getComponent('dataZoom').getPercentRange(), axes,
                handles,
                box_icon: {x:iconRect.x+iconRect.width/2, y:iconRect.y+iconRect.height/2},
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
    # Hit the existing zoom feature's real icon, including the native theme's
    # padding/item gap. Hard-coded guesses can accidentally click restore/back.
    icon = slider['box_icon']
    page.mouse.click(box["x"]+icon['x'], box["y"]+icon['y'])
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
    page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 14", timeout=60000)
    page.wait_for_function("document.querySelectorAll('[data-testid=macroEChartsChart][aria-busy=false], [data-testid=stEChartsChart][aria-busy=false]').length >= 8 || document.querySelector('[data-testid=macroEChartsChartError]')", timeout=60000)
    failures = page.locator('.macro-chart-error:not([hidden])').all_text_contents()
    assert not failures, failures


def check_mobile_layout(page):
    """Rotate the actual painted charts; no alternate renderer or test data."""
    probe = """element => {
        const chart = (""" + INSTANCE_JS + """)(element), model = chart.getModel();
        const grid = model.getComponent('grid').coordinateSystem.getRect();
        const legend = model.getComponent('legend');
        const view = chart.getViewOfComponentModel(legend);
        const rect = view.group.getBoundingRect().clone();
        rect.applyTransform(view.group.getComputedTransform());
        const axes = [];
        model.eachComponent('yAxis', axis => axes.push({
            show: axis.get('show'), name: axis.get('name'),
            scale: axis.get('scale'), offset: axis.get('offset')}));
        return {width:chart.getWidth(), grid:{x:grid.x,y:grid.y,width:grid.width},
            legend_type:legend.get('type'), legend_data:legend.get('data').filter(x => x !== '\\n'),
            legend_bounds:{x:rect.x,y:rect.y,width:rect.width,height:rect.height}, axes,
            series:chart.getOption().series.map(s => ({name:s.name,axis:s.yAxisIndex,data:s.data})),
            zoom:model.getComponent('dataZoom').getPercentRange()};
    }"""
    charts = page.get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
    before = charts.evaluate_all("elements => elements.map(element => (" + probe + ")(element))")
    report = []
    for width, height in ((390, 844), (844, 390), (360, 800), (1440, 1000)):
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(600)
        states = charts.evaluate_all("elements => elements.map(element => (" + probe + ")(element))")
        for original, state in zip(before, states):
            assert state['series'] == original['series'], (width, 'observations changed')
            assert state['zoom'] == original['zoom'], (width, 'zoom changed')
            assert len(state['axes']) == len(original['axes'])
            assert all(axis['show'] and axis['scale'] and axis['name'] for axis in state['axes']), state
            assert state['grid']['width'] > 80, (width, state)
            if state['width'] <= 700:
                assert state['legend_type'] == 'plain', state
                assert state['legend_data'] == [series['name'] for series in state['series']], state
                bounds = state['legend_bounds']
                assert bounds['x'] >= -1 and bounds['x']+bounds['width'] <= state['width']+1, state
                assert bounds['y']+bounds['height'] <= state['grid']['y']-24, state
                assert state['width']-state['grid']['width'] < original['width']-original['grid']['width'], state
            else:
                assert state['legend_type'] == original['legend_type'], state
                assert state['grid']['x'] == original['grid']['x'], state
                assert [axis['offset'] for axis in state['axes']] == [axis['offset'] for axis in original['axes']], state
        report.append({'viewport': [width, height], 'charts': len(states),
                       'min_plot_width': min(state['grid']['width'] for state in states)})
        if width == 390:
            charts.nth(3).scroll_into_view_if_needed()
            page.screenshot(path='browser_mobile.png')
    assert page.get_by_test_id(re.compile(r"^(macro|st)EChartsChartError$")).count() == 0
    return report


def exercise_legend_axes(page, chart):
    """Click real legend hit targets, including shared and re-packed axes."""
    chart.scroll_into_view_if_needed()
    state_js = """element => {
        const chart = (""" + INSTANCE_JS + """)(element), option = chart.getOption();
        const model = chart.getModel();
        const rect = model.getComponent('grid').coordinateSystem.getRect();
        return {axes:option.yAxis.map(a=>({show:a.show,offset:a.offset,inverse:a.inverse})),
            selected:option.legend[0].selected, width:rect.width,
            series:option.series.map(s=>({name:s.name,axis:s.yAxisIndex,data:s.data})),
            zoom:model.getComponent('dataZoom').getPercentRange()};
    }"""
    def snapshot():
        return chart.evaluate(state_js)

    def click(name):
        chart.scroll_into_view_if_needed()
        point = chart.evaluate("""(element,name) => {
            const chart = (""" + INSTANCE_JS + """)(element);
            const model = chart.getModel().getComponent('legend');
            const index = model.getData().findIndex(item=>item.get('name')===name);
            const view = chart.getViewOfComponentModel(model);
            const item = view._contentGroup.children().find(item=>item.__legendDataIndex===index);
            if(!item) throw new Error('Missing legend target: '+name);
            const rect = item.getBoundingRect().clone();
            rect.applyTransform(item.getComputedTransform());
            return {x:rect.x+rect.width/2,y:rect.y+rect.height/2};
        }""", name)
        box = chart.bounding_box()
        page.mouse.click(box['x']+point['x'], box['y']+point['y'])
        page.wait_for_timeout(100)
        state = snapshot()
        assert state['series'] == original['series'], 'Legend changed raw observations or axis mapping'
        assert state['zoom'] == original['zoom'], 'Legend reset zoom'
        assert [a['inverse'] for a in state['axes']] == [a['inverse'] for a in original['axes']]
        return state

    original = snapshot()
    names = [s['name'] for s in original['series']]
    shared = [s['name'] for s in original['series'] if s['axis']==1]
    last = next(s['name'] for s in original['series'] if s['axis']==2)
    state = click(last)
    assert state['axes'][2]['show'] is False and state['width'] > original['width']
    state = click(shared[0])
    assert state['axes'][1]['show'] is True, 'Shared axis disappeared with another series visible'
    viewport = page.viewport_size
    page.set_viewport_size({'width':844 if viewport['width'] < 700 else 390, 'height':844})
    page.wait_for_timeout(300)
    rotated = snapshot()
    assert rotated['axes'][2]['show'] is False
    assert rotated['selected'] == state['selected']
    assert rotated['series'] == original['series'] and rotated['zoom'] == original['zoom']
    page.set_viewport_size(viewport)
    page.wait_for_timeout(300)
    state = click(shared[1])
    assert state['axes'][1]['show'] is False
    state = click(last)
    assert state['axes'][2]['show'] is True and state['axes'][2]['offset'] == 0
    state = click(names[0])
    assert state['axes'][0]['show'] is False
    state = click(last)
    assert all(a['show'] is False for a in state['axes'])
    for name in names:
        state = click(name)
    assert state['axes'] == original['axes'], 'Restored axes changed identity or offsets'
    assert abs(state['width']-original['width']) < 1
    return {'shared_axis':True, 'empty_axis_hidden':True, 'spacing_reclaimed':True, 'rotation_preserved':True,
            'all_off_and_restore':True, 'data_and_zoom_preserved':True}


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
            page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 14", timeout=60000)
            page.get_by_text("14. Japan Government Yields & Nikkei 225", exact=False).wait_for(timeout=60000)
            charts = page.get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            page.wait_for_function("document.querySelectorAll('[data-testid=macroEChartsChart][aria-busy=false], [data-testid=stEChartsChart][aria-busy=false]').length >= 8", timeout=60000)
            assert groups.count() == 14
            assert charts.count() >= 8
            assert page.get_by_test_id("stException").count() == 0
            assert page.get_by_test_id(re.compile(r"^(macro|st)EChartsChartError$")).count() == 0
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
            report["checks"].append({"chart_positions": 14, "painted_native_charts": len(paints),
                                      "missing_positions_are_explicit": True})
            # All five controls exist for every position, including unavailable charts.
            report["controls"] = groups.all_text_contents()
            for index in range(14):
                for label in ("5Y", "1Y", "6M", "3M", "1M"):
                    # React Aria's selected toggle changes its accessible
                    # name; the visible range label stays stable.
                    assert groups.nth(index).get_by_text(label, exact=True).count() == 1, (index, label, report["controls"][index])
            # Use a real HK chart to exercise every server range with raw prices.
            for label in ("5Y", "1Y", "6M", "3M", "1M", "1Y"):
                groups.nth(4).get_by_text(label, exact=True).click()
                page.locator(f".st-key-hk_5_range_adaptive_default_{label}").get_by_test_id(re.compile(r"^(macro|st)EChartsChart$")).wait_for(timeout=30000)
                assert page.get_by_test_id(re.compile(r"^(macro|st)EChartsChartError$")).count() == 0
            assert page.get_by_test_id("stRadio").count() == 0
            assert page.get_by_text("Rebased 100", exact=True).count() == 0
            page.get_by_text("13. China Government Yields & US 5Y Real Yield", exact=False).wait_for()
            assert page.get_by_text("China & Japan Government Yield Curves", exact=False).count() == 0
            groups.nth(12).get_by_text("3M", exact=True).click()
            china_selected = page.locator(".st-key-china_rates_adaptive_default_3M").get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            china_selected.wait_for(timeout=30000)
            groups.nth(13).get_by_text("1M", exact=True).click()
            china_selected.wait_for(timeout=30000)
            groups.nth(12).get_by_text("1Y", exact=True).click()
            groups.nth(13).get_by_text("1Y", exact=True).click()
            report["checks"].append({"china_japan_separate": True, "country_ranges_independent": True})
            chart = page.locator('.st-key-hk_5_range_adaptive_default_1Y').get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            report["client_zoom"] = exercise_client_zoom(page, chart)
            report["mobile_layout"] = check_mobile_layout(page)
            liquidity = page.locator('.st-key-normal_liquidity_range_echarts_1Y').get_by_test_id(
                re.compile(r"^(macro|st)EChartsChart$"))
            report['legend_axes_desktop'] = exercise_legend_axes(page, liquidity)
            page.set_viewport_size({'width':390, 'height':844})
            page.wait_for_timeout(300)
            report['legend_axes_mobile'] = exercise_legend_axes(page, liquidity)
            page.set_viewport_size({'width':1440, 'height':1000})
            report["checks"].append({"slider": True, "box_zoom": True,
                                      "processed_observations_fit_independent_axes": True})
            # Two separate browser contexts produce independent Streamlit
            # sessions. Session B must not overwrite session A's range.
            context_b = browser.new_context(viewport={"width": 1440, "height": 1000})
            page_b = context_b.new_page()
            page_b.on('pageerror', lambda error: errors.append(str(error)))
            try:
                wait_for_page(page_b, args.url)
            except Exception:
                page_b.screenshot(path='browser_session_b.png', full_page=True)
                report['session_b_failure'] = {
                    'charts': page_b.get_by_test_id(re.compile(r"^(macro|st)EChartsChart$")).count(),
                    'exceptions': page_b.get_by_test_id('stException').all_text_contents(),
                    'renderer_errors': page_b.get_by_test_id(re.compile(r"^(macro|st)EChartsChartError$")).all_text_contents(),
                    'explicit_missing': page_b.get_by_text('该图表目前没有可验证的有效观测数据', exact=False).count(),
                }
                raise
            groups.nth(4).get_by_text('1M', exact=True).click()
            expected_a = page.locator('[class*="st-key-hk_5_range_adaptive_default"][class*="_1M"]').get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            expected_a.wait_for(timeout=30000)
            page_b.get_by_test_id('stButtonGroup').nth(4).get_by_text('3M', exact=True).click()
            expected_b = page_b.locator('.st-key-hk_5_range_adaptive_default_3M').get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            expected_b.wait_for(timeout=30000)
            assert expected_a.count() == 1 and expected_b.count() == 1
            for current, expected in ((page, expected_a), (page_b, expected_b)):
                current.locator('.st-key-refresh_market_overview').get_by_role('button').click()
                current.locator('.st-key-refresh_watchlist_quotes').get_by_role('button').click()
                expected.wait_for(timeout=30000)
                assert current.get_by_test_id('stException').count() == 0
                assert current.get_by_test_id(re.compile(r"^(macro|st)EChartsChartError$")).count() == 0
            assert expected_a.count() == 1 and expected_b.count() == 1
            report['checks'].append({'isolated_browser_sessions': 2,
                                     'manual_market_refresh': True, 'manual_watchlist_refresh': True,
                                     'range_preserved': True})
            context_b.close()
            assert not errors, errors
            page.screenshot(path="browser_acceptance.png", full_page=True)
            report["checks"].append({"hk_ranges": 5, "raw_prices_only": True})
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
