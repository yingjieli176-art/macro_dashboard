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
            const values = [], references = [];
            let bars = false;
            model.eachSeries(series => {
                if ((series.get('yAxisIndex') || 0) !== axis.componentIndex) return;
                bars ||= series.subType === 'bar';
                for (const line of series.get('markLine')?.data || []) {
                    if (/ · (最高收盘|最新收盘)$/.test(line.name || '') && Number.isFinite(line.yAxis)) references.push(line.yAxis);
                }
                const data = series.getData();
                const dimension = data.mapDimension('y');
                for (let index=0; index<data.count(); index++) {
                    const value = data.get(dimension, index);
                    if (Number.isFinite(value)) values.push(value);
                }
            });
            axes.push({extent: axis.axis.scale.getExtent(),
                       observed: values.length ? [Math.min(...values), Math.max(...values)] : null,
                       samples: values.length, references, bars, scale: axis.get('scale')});
        });
        const grid = model.getComponent('grid').coordinateSystem.getRect();
        const slider = instance.getViewOfComponentModel(model.getComponent('dataZoom', 1));
        const handles = slider._displayables.handles.map(handle => {
            const rect = handle.getBoundingRect().clone();
            rect.applyTransform(handle.getComputedTransform());
            return {x:rect.x+rect.width/2, y:rect.y+rect.height/2};
        });
        return {zoom: model.getComponent('dataZoom').getPercentRange(), axes,
                handles, toolbox: !!model.getComponent('toolbox'),
                grid: {x:grid.x, y:grid.y, width:grid.width, height:grid.height},
                width:instance.getWidth(), height:instance.getHeight()};
    }""")


def assert_visible_axes(state, minimum_axes=2):
    populated = 0
    for axis in state["axes"]:
        assert axis["scale"] == (not axis["bars"]), axis
        if axis["observed"] is None:
            continue
        populated += 1
        low, high = axis["observed"]
        if axis["bars"]:
            low, high = min(low, 0), max(high, 0)
        references = axis.get("references", [])
        if references:
            low, high = min(low, *references), max(high, *references)
        minimum, maximum = sorted(axis["extent"])
        tolerance = max(abs(low), abs(high), 1)*1e-8
        assert minimum <= low+tolerance and maximum >= high-tolerance, axis
        # A full-history or shared-axis scale would be far wider than these
        # filtered samples. Allow ECharts' own nice-tick rounding and flat data.
        assert maximum-minimum <= max((high-low)*2, max(abs(low), abs(high), 1)*.05), axis
    assert populated >= minimum_axes, state


def assert_bar_baseline(chart, name):
    state = chart.evaluate("""(element,name) => {
        const chart=element.__macroChart, model=chart.getModel();
        const series=model.getSeries().find(series=>series.name===name);
        const axis=model.getComponent('yAxis',series.get('yAxisIndex')||0);
        const zero=chart.convertToPixel({yAxisIndex:axis.componentIndex},0), data=series.getData();
        const bars=[];
        for(let index=0;index<data.count();index++) {
            const value=data.get(data.mapDimension('y'),index), rect=data.getItemLayout(index);
            if(Number.isFinite(value)&&rect&&Number.isFinite(rect.y)&&Number.isFinite(rect.height))
                bars.push({zeroError:Math.min(Math.abs(rect.y-zero),Math.abs(rect.y+rect.height-zero)),width:rect.width});
        }
        return {type:series.subType,scale:axis.get('scale'),extent:axis.axis.scale.getExtent(),bars};
    }""", name)
    assert state['type'] == 'bar' and state['scale'] is False, state
    assert state['extent'][0] <= 0 <= state['extent'][1], state
    assert state['bars'] and all(bar['zeroError'] < 1 and 0 < bar['width'] <= 17 for bar in state['bars']), state
    return {'zero_baseline':True,'visible_bars':len(state['bars'])}


def exercise_client_zoom(page, chart, minimum_axes=2):
    chart.scroll_into_view_if_needed()
    before = chart_state(chart)
    assert before['toolbox'] is False, 'Removed zoom/back/reset toolbar is still present'
    tools = chart.locator('xpath=..').locator('.macro-chart-tools button')
    assert tools.count() == 2
    assert tools.nth(0).get_attribute('aria-label') == 'Download as PNG'
    assert tools.nth(1).get_attribute('aria-label') == 'Fullscreen'
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
    assert_visible_axes(slider, minimum_axes=minimum_axes)
    return {"before": before, "slider": slider, "download_and_fullscreen_only": True}


def assert_price_guides_follow_viewport(chart):
    values = chart.evaluate("""element => {
        const instance = (""" + INSTANCE_JS + """)(element), values = [];
        const option = instance.getOption();
        const graphics = (option.graphic || []).flatMap(group => group.elements || [group]);
        instance.getModel().eachSeries(series => {
            if (series.id.startsWith('macro-peak-drawdown-')) return;
            const data = series.getData(), y = data.mapDimension('y');
            const raw = instance.getOption().series.find(item => item.name === series.name).data;
            let best = null;
            for (let index=0; index<data.count(); index++) {
                const value = data.get(y, index);
                if (Number.isFinite(value) && (!best || value > best.value)) {
                    best = {value, date:raw[data.getRawIndex(index)][0].slice(0,10)};
                }
            }
            const guides = series.get('markLine').data;
            const high = guides.find(line => / · 最高收盘$/.test(line.name));
            const current = guides.find(line => / · 最新收盘$/.test(line.name));
            const index = option.series.findIndex(item => item.name === series.name);
            const footer = graphics.find(item => item.id === `macro-price-ratio-${index}`);
            values.push({name:series.name, expected:best, high:high.yAxis,
                label:high.label.formatter, current:current.yAxis,
                ratio_text:footer?.style?.text, footer_bottom:footer?.bottom,
                slider_bottom:option.dataZoom.find(zoom=>zoom.type==='slider').bottom,
                path:option.series.find(item => item.id === `macro-peak-drawdown-${index}`)?.data,
                expected_path:raw.filter(point => Date.parse(point[0]) >= Date.parse(best.date))
                    .map(point => [point[0], Number.isFinite(point[1]) && point[1] > 0 ?
                        (point[1]/best.value-1)*100 : null, point[1]]),
                grids:option.grid.length, x_axes:option.xAxis.length,
                overlay:option.series.find(item => item.id === `macro-peak-drawdown-${index}`),
                percent_axis:option.yAxis.at(-1),
                zoom_axes:option.dataZoom.map(zoom=>zoom.xAxisIndex),
                latest_time:Date.parse(raw.filter(point=>Number.isFinite(point[1])).at(-1)[0]),
                latest:raw.filter(point=>Number.isFinite(point[1])).at(-1)[1]});
        });
        return values;
    }""")
    assert values
    assert all(value['zoom_axes'] == [[0], [0]] for value in values), values
    assert all(value['grids'] == 1 and value['x_axes'] == 1 for value in values), values
    for value in values:
        assert value['expected'] is not None, value
        assert value['overlay']['xAxisIndex'] == 0, value
        assert value['overlay']['lineStyle']['type'] == 'dashed', value
        assert value['overlay']['name'].endswith(' 回撤比例'), value
        assert value['overlay']['name'] != value['name'], value
        assert value['percent_axis']['position'] == 'right', value
        assert abs(value['high'] - value['expected']['value']) < .00001, value
        assert value['expected']['date'] in value['label'], value
        assert abs(value['current'] - value['latest']) < .00001, value
        percent = (value['high']-value['current'])/value['high']*100
        label = '高于区间前高' if percent < 0 else '距区间前高回撤'
        assert f'{label} {abs(percent):.2f}%' in (value['ratio_text'] or ''), value
        assert value['footer_bottom'] < value['slider_bottom'], value
        assert value['path'] == value['expected_path'], value
        assert value['path'][0][1] == 0, value
        assert value['path'][0][0][:10] == value['expected']['date'], value
        assert abs(value['path'][-1][1] + percent) < .00001, value
        assert value['path'][-1][2] == value['latest'], value
    return values


def exercise_price_historical_window(page, chart):
    before = chart_state(chart)
    box = chart.bounding_box()
    handle = before['handles'][1]
    distance = before['grid']['width'] * (before['zoom'][1]-before['zoom'][0])/100 * .55
    page.mouse.move(box['x']+handle['x'], box['y']+handle['y'])
    page.mouse.down()
    page.mouse.move(box['x']+handle['x']-distance, box['y']+handle['y'], steps=12)
    page.mouse.up()
    page.wait_for_timeout(200)
    after = chart_state(chart)
    assert after['zoom'][1] < before['zoom'][1]-.1, (before, after)
    assert_visible_axes(after, minimum_axes=1)
    return {'zoom':after['zoom'], 'guides':assert_price_guides_follow_viewport(chart)}


def exercise_price_path_legend(page, chart):
    """Daily drawdown is an independent named parameter in the same plot."""
    before = chart_state(chart)['zoom']
    names = chart.evaluate("element => element.__macroChart.getOption().legend[0].data.filter(name=>name!=='\\n')")
    for name in names + names:
        point = chart.evaluate("""(element,name) => {
            const chart=element.__macroChart, legend=chart.getModel().getComponent('legend');
            const index=legend.getData().findIndex(item=>item.get('name')===name);
            const view=chart.getViewOfComponentModel(legend);
            const item=view._contentGroup.children().find(item=>item.__legendDataIndex===index);
            const rect=item.getBoundingRect().clone(); rect.applyTransform(item.getComputedTransform());
            return {x:rect.x+rect.width/2,y:rect.y+rect.height/2};
        }""", name)
        chart.scroll_into_view_if_needed()
        box=chart.bounding_box()
        page.mouse.click(box['x']+point['x'],box['y']+point['y'])
        page.wait_for_timeout(100)
        state=chart.evaluate("""element => {
            const chart=element.__macroChart, option=chart.getOption(), visible=[];
            chart.getModel().eachSeries(series=>visible.push({name:series.name,kind:series.id.startsWith('macro-peak-drawdown-')?'drawdown':'price'}));
            return {selected:option.legend[0].selected, visible,
                panel_show:option.yAxis.at(-1).show};
        }""")
        for asset in names:
            assert [s['kind'] for s in state['visible'] if s['name']==asset] == (
                [] if state['selected'].get(asset) is False else ['drawdown' if asset.endswith(' 回撤比例') else 'price']), state
        assert state['panel_show'] == any(s['kind']=='drawdown' for s in state['visible']), state
        assert chart_state(chart)['zoom'] == before
    assert_price_guides_follow_viewport(chart)
    tooltip = chart.evaluate("""element => {
        const chart=element.__macroChart, option=chart.getOption();
        const series=option.series.find(s=>s.id.startsWith('macro-peak-drawdown-') && s.data.length>1);
        const point=series.data[1];
        return {text:option.tooltip[0].formatter([{seriesId:series.id,value:point}]),
            expected:point[1].toFixed(2)+'%',date:point[0].slice(0,10)};
    }""")
    assert '回撤比例' in tooltip['text'] and tooltip['expected'] in tooltip['text'], tooltip
    assert tooltip['date'] in tooltip['text'], tooltip
    return {'independent_daily_drawdown_parameters':True,'all_off_and_restore':True}


def exercise_equity_drawdown(page):
    page.get_by_text('11. SPX / RSP · 价格走势与区间高点', exact=True).wait_for(timeout=30000)
    assert page.get_by_text('9B.', exact=False).count() == 0
    baseline = None
    ranges = []
    for period in ("5Y", "1Y", "6M", "3M", "1M", "1Y"):
        page.get_by_test_id("stButtonGroup").nth(10).get_by_text(period, exact=True).click()
        chart = page.locator(f'.st-key-us_equity_drawdown_echarts_{period}').get_by_test_id(
            re.compile(r"^(macro|st)EChartsChart$"))
        chart.wait_for(timeout=30000)
        page.wait_for_function("selector => document.querySelector(selector)?.getAttribute('aria-busy') === 'false'",
                               arg=f'.st-key-us_equity_drawdown_echarts_{period} [data-testid$="EChartsChart"]',
                               timeout=30000)
        points = chart.evaluate("""element => {
            const chart = (""" + INSTANCE_JS + """)(element);
            return chart.getOption().series.filter(series => !series.id.startsWith('macro-peak-drawdown-')).map(series => ({name: series.name,
                latest: series.data.filter(point => Number.isFinite(point[1])).at(-1),
                guides: series.markLine?.data.map(line => ({name:line.name,value:line.yAxis,label:line.label.formatter}))}));
        }""")
        assert len(points) == 2 and all(p['latest'][1] > 0 for p in points), points
        assert all(len(p['guides']) == 2 for p in points), points
        assert_price_guides_follow_viewport(chart)
        if baseline is None:
            baseline = [point['latest'] for point in points]
        assert [point['latest'] for point in points] == baseline, 'Changing the viewport changed the current price'
        ranges.append(period)
    assert page.get_by_text('SPX 最新收盘：', exact=False).count() == 1
    assert page.get_by_text('RSP 最新收盘：', exact=False).count() == 1
    chart = page.locator('.st-key-us_equity_drawdown_echarts_1Y').get_by_test_id(
        re.compile(r"^(macro|st)EChartsChart$"))
    assert len(chart_state(chart)['axes']) == 3
    zoom = exercise_client_zoom(page, chart, minimum_axes=2)
    assert_price_guides_follow_viewport(chart)
    historical = exercise_price_historical_window(page, chart)
    legend = exercise_price_path_legend(page, chart)
    chart.screenshot(path='browser_equity_drawdown.png')
    return {'range_controls': ranges, 'latest_prices_and_guides': baseline,
            'visible_window_highs_verified': True, 'slider': zoom, 'historical_window':historical, 'path_legend':legend}


def exercise_china_drawdown(page):
    page.get_by_text('12. A股宽基 · 沪深300 / 中证1000 / 中证2000 价格走势', exact=True).wait_for(timeout=30000)
    baseline = None
    for period in ('5Y', '1Y', '6M', '3M', '1M', '1Y'):
        page.get_by_test_id('stButtonGroup').nth(11).get_by_text(period, exact=True).click()
        selector = f'.st-key-china_equity_drawdown_echarts_{period}'
        chart = page.locator(selector).get_by_test_id(re.compile(r'^(macro|st)EChartsChart$'))
        chart.wait_for(timeout=30000)
        page.wait_for_function("selector => document.querySelector(selector)?.getAttribute('aria-busy') === 'false'",
                               arg=selector+' [data-testid$="EChartsChart"]', timeout=30000)
        points = chart.evaluate("""element => {
            const instance = (""" + INSTANCE_JS + """)(element);
            return instance.getOption().series.filter(s => !s.id.startsWith('macro-peak-drawdown-')).map(s => ({name:s.name,
                latest:s.data.filter(p=>Number.isFinite(p[1])).at(-1),
                guides:s.markLine?.data.map(line=>({name:line.name,value:line.yAxis,label:line.label.formatter}))}));
        }""")
        assert [p['name'] for p in points] == ['沪深300', '中证1000', '中证2000'], points
        assert all(p['latest'][1] > 0 for p in points), points
        assert all(len(p['guides']) == 2 for p in points), points
        assert_price_guides_follow_viewport(chart)
        if baseline is None: baseline = [point['latest'] for point in points]
        assert [point['latest'] for point in points] == baseline, 'Changing the viewport changed China current prices'
    zoom = exercise_client_zoom(page, chart, minimum_axes=1)
    assert_price_guides_follow_viewport(chart)
    historical = exercise_price_historical_window(page, chart)
    legend = exercise_price_path_legend(page, chart)
    chart.screenshot(path='browser_china_drawdown.png')
    return {'latest_prices_and_guides':baseline, 'visible_window_highs_verified':True, 'slider':zoom, 'historical_window':historical, 'path_legend':legend}


def wait_for_page(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 18", timeout=60000)
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
            series:chart.getOption().series.map(s => ({name:s.name,axis:s.yAxisIndex,type:s.type,data:s.data})),
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
            for index, axis in enumerate(state['axes']):
                bars = any(s['type'] == 'bar' and s['axis'] == index for s in state['series'])
                assert axis['show'] and axis['name'] and axis['scale'] == (not bars), state
            assert state['grid']['width'] > 80, (width, state)
            if state['width'] <= 700:
                assert state['legend_type'] == 'plain', state
                assert state['legend_data'] == list(dict.fromkeys(series['name'] for series in state['series'])), state
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
        assert state['zoom'] == original['zoom'], ('Legend reset zoom', name, original['zoom'], state['zoom'])
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


def exercise_yen_legend(page):
    chart = page.locator('.st-key-japan_rates_adaptive_default_1Y').get_by_test_id(
        re.compile(r"^(macro|st)EChartsChart$"))
    chart.scroll_into_view_if_needed()
    inspect = """element => {
        const chart=element.__macroChart, option=chart.getOption();
        const yen=option.series.find(s=>s.name==='USD/JPY (R3)');
        const model=chart.getModel().getComponent('legend'), view=chart.getViewOfComponentModel(model);
        const index=model.getData().findIndex(item=>item.get('name')===yen.name);
        const item=view._contentGroup.children().find(item=>item.__legendDataIndex===index);
        const rect=item.getBoundingRect().clone(); rect.applyTransform(item.getComputedTransform());
        return {show:option.yAxis[yen.yAxisIndex].show!==false,data:yen.data,
            point:{x:rect.x+rect.width/2,y:rect.y+rect.height/2},
            zoom:chart.getModel().getComponent('dataZoom').getPercentRange()};
    }"""
    original = chart.evaluate(inspect)
    assert original['show'] and len(original['data']) > 200
    for expected in (False, True):
        box = chart.bounding_box()
        point = chart.evaluate(inspect)['point']
        page.mouse.click(box['x']+point['x'], box['y']+point['y'])
        page.wait_for_timeout(100)
        state = chart.evaluate(inspect)
        assert state['show'] is expected, state
        assert state['data'] == original['data'] and state['zoom'] == original['zoom']
    return {'completed_fx_observations':True, 'axis_hides_and_restores':True, 'data_and_zoom_preserved':True}


def exercise_range_legend_persistence(page, prefix, group_index):
    """Real legend clicks survive remounts while each requested period changes X."""
    inspect = """element => {
        const chart=element.__macroChart, option=chart.getOption();
        return {selected:option.legend[0].selected,
            axes:option.yAxis.map(a=>({show:a.show,offset:a.offset,scale:a.scale})),
            series:option.series.map(s=>({name:s.name,axis:s.yAxisIndex||0,type:s.type,data:s.data})),
            zoom:chart.getModel().getComponent('dataZoom').getPercentRange()};
    }"""
    def chart_for(period):
        chart=page.locator(f'.st-key-{prefix}_{period} [data-testid=macroEChartsChart][aria-busy=false]')
        chart.wait_for(timeout=30000)
        return chart

    def toggle(chart, name):
        chart.scroll_into_view_if_needed()
        point=chart.evaluate("""(element,name) => {
            const chart=element.__macroChart, model=chart.getModel().getComponent('legend');
            const index=model.getData().findIndex(item=>item.get('name')===name);
            const item=chart.getViewOfComponentModel(model)._contentGroup.children()
                .find(item=>item.__legendDataIndex===index);
            if(!item) throw new Error('Missing legend target: '+name);
            const rect=item.getBoundingRect().clone();rect.applyTransform(item.getComputedTransform());
            return {x:rect.x+rect.width/2,y:rect.y+rect.height/2};
        }""", name)
        box=chart.bounding_box()
        page.mouse.click(box['x']+point['x'],box['y']+point['y'])
        page.wait_for_timeout(100)

    chart=chart_for('1Y')
    original=chart.evaluate(inspect)
    last_axis=max(s['axis'] for s in original['series'])
    hidden=[s['name'] for s in original['series'] if s['axis']==last_axis]
    # A shared line/bar axis should regain a tight line scale when its bar
    # series is hidden, then restore zero when that bar is selected again.
    shared_bars=[s['name'] for s in original['series'] if s['type']=='bar' and s['axis']==0]
    hidden.extend(shared_bars)
    shared=[s['name'] for s in original['series'] if s['axis']==1]
    if last_axis != 1 and len(shared)>1:
        hidden.append(shared[0])
    for name in hidden:toggle(chart,name)
    expected=chart.evaluate(inspect)
    assert expected['axes'][last_axis]['show'] is False
    assert all(expected['selected'][name] is False for name in hidden)
    if shared_bars:
        assert original['axes'][0]['scale'] is False and expected['axes'][0]['scale'] is True
    if len(shared)>1:assert expected['axes'][1]['show'] is True
    windows={}
    for period in ('1M','6M','1Y'):
        page.get_by_test_id('stButtonGroup').nth(group_index).get_by_text(period,exact=True).click()
        chart=chart_for(period)
        state=chart.evaluate(inspect)
        assert all(state['selected'].get(name) is False for name in hidden), (prefix,period,state['selected'])
        assert state['axes']==expected['axes'], (prefix,period,state['axes'],expected['axes'])
        assert state['series']==original['series'], 'Range switch changed raw observations'
        windows[period]=state['zoom'][1]-state['zoom'][0]
    assert windows['1M'] < windows['6M'] < windows['1Y'], windows
    # A later re-selection is also carried into a different month.
    for name in hidden:toggle(chart,name)
    page.get_by_test_id('stButtonGroup').nth(group_index).get_by_text('3M',exact=True).click()
    state=chart_for('3M').evaluate(inspect)
    assert all(state['selected'].get(name,True) for name in hidden)
    assert all(axis['show'] for axis in state['axes'])
    page.get_by_test_id('stButtonGroup').nth(group_index).get_by_text('1Y',exact=True).click()
    assert all(axis['show'] for axis in chart_for('1Y').evaluate(inspect)['axes'])
    return {'hidden_choices_preserved':True,'axis_visibility_preserved':True,
            'reselected_choices_preserved':True,'period_windows':windows,'observations_unchanged':True}



def exercise_security_search(page):
    page.locator('.st-key-market_search_hk_open_button button:visible').filter(has_text='＋ 添加标的').click()
    search = page.locator('.st-key-market_search_hk input:visible')
    search.fill('小米')
    search.press('Enter')
    selected = page.locator('.st-key-market_search_hk_result_select').get_by_role('combobox').filter(visible=True)
    selected.wait_for(state='visible', timeout=15000)
    page.locator('.st-key-market_search_hk_confirm_selected button:visible').filter(has_text='确认添加').click()
    card = page.locator('.watch-card-body').filter(has_text='1810.HK')
    card.wait_for(timeout=15000)
    assert '小米集团-W' in card.inner_text()
    page.locator('[class*="st-key-market_search_hk_delete_"] button:visible').last.click()
    card.wait_for(state='detached', timeout=15000)
    assert card.count() == 0
    # A removed card can disappear before its full rerun registers all fragments.
    # Wait for the server's completion signal before clicking chart controls.
    page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'",
                           timeout=30000)
    return {'chinese_name':True, 'enter_to_search':True, 'confirmed_symbol':'1810.HK', 'add_remove':True}


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
            page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 18", timeout=60000)
            page.get_by_text("14. Japan Government Yields & Nikkei 225", exact=False).wait_for(timeout=60000)
            charts = page.get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            page.wait_for_function("document.querySelectorAll('[data-testid=macroEChartsChart][aria-busy=false], [data-testid=stEChartsChart][aria-busy=false]').length >= 8", timeout=60000)
            page.get_by_text("10. VIX & VIX3M Term Structure", exact=True).wait_for(timeout=30000)
            page.get_by_text("15. Precious Metals", exact=True).wait_for(timeout=30000)
            assert groups.count() == 18
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
            report["checks"].append({"chart_positions": 18, "painted_native_charts": len(paints),
                                      "missing_positions_are_explicit": True})
            report["equity_drawdown"] = exercise_equity_drawdown(page)
            report["china_drawdown"] = exercise_china_drawdown(page)
            report["security_search"] = exercise_security_search(page)
            # All five controls exist for every position, including unavailable charts.
            report["controls"] = groups.all_text_contents()
            for index in range(18):
                for label in ("5Y", "1Y", "6M", "3M", "1M"):
                    # React Aria's selected toggle changes its accessible
                    # name; the visible range label stays stable.
                    assert groups.nth(index).get_by_text(label, exact=True).count() == 1, (index, label, report["controls"][index])
            # Use a real HK chart to exercise every server range with raw prices.
            for label in ("5Y", "1Y", "6M", "3M", "1M", "1Y"):
                groups.nth(4).get_by_text(label, exact=True).click()
                page.locator(f".st-key-hk_5_range_adaptive_default_{label}").get_by_test_id(re.compile(r"^(macro|st)EChartsChart$")).wait_for(timeout=30000)
                page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'",
                                       timeout=30000)
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
            page.get_by_text("18. 日元套息分析", exact=False).wait_for()
            carry = page.locator('.st-key-yen_carry_adaptive_default_1Y').get_by_test_id(
                re.compile(r"^(macro|st)EChartsChart$"))
            report["yen_carry_zoom"] = exercise_client_zoom(page, carry, minimum_axes=4)
            report["cftc_columns"] = assert_bar_baseline(carry, 'CFTC JPY speculative net (R3)')
            report["yen_carry_ranges"] = exercise_range_legend_persistence(
                page, 'yen_carry_adaptive_default', 17)
            chart = page.locator('.st-key-hk_5_range_adaptive_default_1Y').get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            report["client_zoom"] = exercise_client_zoom(page, chart)
            report["monthly_growth_columns"] = assert_bar_baseline(chart, 'M2 MoM')
            report["mobile_layout"] = check_mobile_layout(page)
            liquidity = page.locator('.st-key-normal_liquidity_range_echarts_1Y').get_by_test_id(
                re.compile(r"^(macro|st)EChartsChart$"))
            report['legend_axes_desktop'] = exercise_legend_axes(page, liquidity)
            page.set_viewport_size({'width':390, 'height':844})
            page.wait_for_timeout(300)
            report['legend_axes_mobile'] = exercise_legend_axes(page, liquidity)
            report['yen_legend_mobile'] = exercise_yen_legend(page)
            page.set_viewport_size({'width':1440, 'height':1000})
            report['yen_legend_desktop'] = exercise_yen_legend(page)
            report['range_legend_desktop'] = {
                'liquidity':exercise_range_legend_persistence(page,'normal_liquidity_range_echarts',3),
                'hong_kong':exercise_range_legend_persistence(page,'hk_5_range_adaptive_default',4),
                'volatility':exercise_range_legend_persistence(page,'vix_term_structure_adaptive_default',9),
            }
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(300)
            report['range_legend_mobile'] = {
                'liquidity':exercise_range_legend_persistence(page,'normal_liquidity_range_echarts',3),
                'hong_kong':exercise_range_legend_persistence(page,'hk_5_range_adaptive_default',4),
                'volatility':exercise_range_legend_persistence(page,'vix_term_structure_adaptive_default',9),
            }
            page.set_viewport_size({'width':1440,'height':1000})
            freshness = page.get_by_text(re.compile(r'^数据最新时间 · 18 张图'))
            freshness.click()
            page.get_by_test_id('stDataFrame').first.wait_for()
            assert page.get_by_test_id('stDataFrame').count() >= 2
            assert page.get_by_text('独立数据源核对', exact=True).count() == 0
            page.screenshot(path='browser_freshness.png')
            freshness.click()
            report['all_source_freshness_overview'] = {'chart_positions':18,'observation_dates_visible':True}
            report["checks"].append({"slider": True, "download_and_fullscreen_only": True,
                                      "processed_observations_fit_independent_axes": True})
            # Two separate browser contexts produce independent Streamlit
            # sessions. Session B must not overwrite session A's range.
            # Fix A's choice before opening B. B's cold start can complete a
            # shared background fetch and cause a full rerun in A; clicking
            # A's old fragment during that rerun tests a stale event race,
            # rather than whether B preserves A's already selected period.
            groups.nth(4).get_by_text('1M', exact=True).click()
            expected_a = page.locator('[class*="st-key-hk_5_range_adaptive_default"][class*="_1M"]').get_by_test_id(re.compile(r"^(macro|st)EChartsChart$"))
            expected_a.wait_for(timeout=30000)
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
            page_b.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'", timeout=30000)
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
