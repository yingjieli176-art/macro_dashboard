// App-owned component. Never reach into Streamlit's React internals.
const copy = value => JSON.parse(JSON.stringify(value));
function merge(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      target[key] = merge(target[key] && typeof target[key] === "object" ? target[key] : {}, value);
    } else target[key] = copy(value);
  }
  return target;
}

function loadEngine() {
  // Share one module between charts. A failed load may be retried on a rerun.
  if (!window.__macroEChartsModule) {
    const asset = new URL("app/static/macro-echarts-6.0.0.js.txt", window.location.href);
    window.__macroEChartsModule = fetch(asset).then(response => {
      if (!response.ok) throw new Error(`图表组件加载失败 (${response.status})`);
      return response.text();
    }).then(async source => {
      if (!source.startsWith("\n/*")) throw new Error("图表组件资源格式错误");
      const url = URL.createObjectURL(new Blob([source], {type: "text/javascript"}));
      try { return await import(url); } finally { URL.revokeObjectURL(url); }
    }).catch(error => { delete window.__macroEChartsModule; throw error; });
  }
  return window.__macroEChartsModule;
}

export default function({data, parentElement}) {
  const element = parentElement.querySelector('[data-testid="macroEChartsChart"]');
  const shell = parentElement.querySelector('.macro-chart-shell');
  const error = parentElement.querySelector('.macro-chart-error');
  const buttons = parentElement.querySelectorAll('button');
  const source = copy(data.option);
  const base = copy(source);
  delete base.media;
  // Legend filtering must not change the time domain, especially when every
  // series is hidden. Bounds come only from existing observation dates.
  let first = Infinity, last = -Infinity;
  for (const series of base.series) for (const point of series.data) {
    const time = typeof point[0] === 'number' ? point[0] : Date.parse(point[0]);
    if (Number.isFinite(time)) { first = Math.min(first, time); last = Math.max(last, time); }
  }
  if (first < last) base.xAxis = {...base.xAxis, min:first, max:last};
  let chart, observer, disposed = false, frame = 0;
  const saved = parentElement.__macroChartState;
  // Period switches remount the component, so DOM-local state alone is lost.
  // Keep only legend choices in this app window, isolated by logical chart.
  // Zoom remains local: a new period must use its newly requested X window.
  const legendStates = window.__macroLegendStates ||= new Map();
  const legendKey = data.legend_state_key;
  let selected = copy((legendKey && legendStates.get(legendKey)) ||
    saved?.selected || base.legend?.selected || {});
  function rememberSelection() {
    if (legendKey) legendStates.set(legendKey, copy(selected));
  }
  element.style.height = `${data.height || 465}px`;

  const isPriceGuide = line => / · (最高收盘|最新收盘)$/.test(line.name || '');
  const hasPriceGuides = base.series.some(series => (series.markLine?.data || []).some(isPriceGuide));
  const footerSpace = hasPriceGuides ? data.price_footer_height || 0 : 0;
  const priceNumber = value => value.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
  function refreshPriceGuides(zooms) {
    if (!hasPriceGuides) return;
    const zoom = (zooms || [])[0] || {};
    const asTime = value => typeof value === 'number' ? value : Date.parse(value);
    const start = asTime(zoom.startValue), end = asTime(zoom.endValue);
    const lower = Number.isFinite(start) ? start : first + (last-first)*(zoom.start ?? 0)/100;
    const upper = Number.isFinite(end) ? end : first + (last-first)*(zoom.end ?? 100)/100;
    for (const series of base.series) {
      const high = (series.markLine?.data || []).find(line => / · 最高收盘$/.test(line.name || ''));
      if (!high) continue;
      let best = null;
      for (const [day, value] of series.data) {
        const time = asTime(day);
        if (Number.isFinite(time) && Number.isFinite(value) && time >= lower && time <= upper &&
            (!best || value > best.value)) best = {day, time, value};
      }
      high.label.show = !!best;
      high.lineStyle.opacity = best ? 1 : 0;
      if (best) {
        const short = high.label.formatter.split(' 高 ')[0];
        const date = typeof best.day === 'string' ? best.day.slice(0,10) : new Date(best.time).toISOString().slice(0,10);
        high.yAxis = best.value;
        high.label.formatter = `${short} 高 ${priceNumber(best.value)}\n${date}`;
      }
    }
  }

  function presentation() {
    const width = element.clientWidth;
    const result = copy(base);
    const matching = (source.media || []).filter(item => item.query && width <= item.query.maxWidth);
    if (matching.length) matching.forEach(item => merge(result, item.option));
    else {
      const fallback = (source.media || []).find(item => !item.query);
      if (fallback) merge(result, fallback.option);
    }
    if (footerSpace) {
      // Keep the original price plot height; the extra canvas space holds
      // exportable ratios below the date slider, including on phones.
      result.grid.bottom = (Number(result.grid.bottom) || 75) + footerSpace;
      result.dataZoom = result.dataZoom.map(zoom => zoom.type === 'slider' ?
        {...zoom, bottom:(Number(zoom.bottom) || 16) + footerSpace} : zoom);
    }
    return result;
  }

  function priceRatioFooter() {
    const assets = base.series.filter(series => (series.markLine?.data || []).some(isPriceGuide));
    const lines = assets.map((series, index) => {
      const high = series.markLine.data.find(line => / · 最高收盘$/.test(line.name));
      const current = series.markLine.data.find(line => / · 最新收盘$/.test(line.name));
      const short = high.label.formatter.split(' 高 ')[0];
      let text = '';
      if (selected[series.name] !== false) {
        if (high.label.show === false || !Number.isFinite(high.yAxis) || high.yAxis <= 0 ||
            !Number.isFinite(current?.yAxis)) text = `${short} · 所选区间暂无有效观测`;
        else {
          const percent = (high.yAxis-current.yAxis)/high.yAxis*100;
          const label = percent < 0 ? '高于区间前高' : '距区间前高回撤';
          text = `${short} · ${label} ${Math.abs(percent).toFixed(2)}%`;
        }
      }
      return {id:`macro-price-ratio-${index}`, type:'text', left:12,
        bottom:8+(assets.length-index-1)*20, silent:true,
        style:{text, fill:series.lineStyle?.color || '#475569', fontSize:12, lineHeight:20}};
    });
    element.setAttribute('aria-description', lines.map(line=>line.style.text).filter(Boolean).join('；'));
    return lines;
  }

  function axisLayout(option) {
    const axes = option.yAxis;
    const used = new Set(base.series.filter(series => selected[series.name] !== false)
      .map(series => series.yAxisIndex || 0));
    const right = axes.filter(axis => axis.position === 'right');
    const mobile = element.clientWidth <= 700;
    const spacing = mobile ? (element.clientWidth <= 360 ? 40 : element.clientWidth <= 480 ? 44 : 48) : 58;
    const lane = mobile ? spacing : 70;
    let visibleRight = 0, visibleLeft = 0;
    axes.forEach((axis, index) => {
      const show = used.has(index);
      // Price guides are annotations, not observations. Include visible
      // assets' high/latest levels in the viewport's native dynamic extent.
      const guides = base.series.filter(series => (series.yAxisIndex || 0) === index &&
        selected[series.name] !== false).flatMap(series =>
          (series.markLine?.data || []).filter(line =>
            isPriceGuide(line) && line.label?.show !== false).map(line => line.yAxis))
        .filter(Number.isFinite);
      if (guides.length) {
        const limits = extent => {
          const values = [extent.min, extent.max, ...guides].filter(Number.isFinite);
          const low = Math.min(...values), high = Math.max(...values);
          const padding = Math.max((high-low)*.07, Math.abs(high)*.002, .01);
          return [low-padding, high+padding];
        };
        axis.min = extent => limits(extent)[0];
        axis.max = extent => limits(extent)[1];
      }
      axis.id = `macro-axis-${index}`;
      axis.show = show;
      axis.axisLine = {...axis.axisLine, show: show && axis.axisLine?.show !== false};
      axis.axisTick = {...axis.axisTick, show: show && axis.axisTick?.show !== false};
      axis.axisLabel = {...axis.axisLabel, show};
      axis.axisPointer = {...axis.axisPointer, show};
      if (!show) axis.name = '';
      if (axis.position === 'right') axis.offset = show ? visibleRight++ * spacing : 0;
      else if (show) visibleLeft++;
    });
    option.grid.left = visibleLeft ? option.grid.left : 12;
    option.grid.right = visibleRight ? option.grid.right - (right.length - visibleRight) * lane : 12;
    return option;
  }

  function updateLayout() {
    if (!chart || disposed) return;
    refreshPriceGuides(chart.getOption().dataZoom);
    const option = axisLayout(presentation());
    if (option.toolbox) option.toolbox.right = 54;
    // Never replace observations or dataZoom. Only price annotations change
    // when the visible interval changes; other charts keep their series intact.
    const patch = {legend: {...option.legend, selected}, grid: option.grid,
      yAxis: option.yAxis, xAxis: option.xAxis, toolbox: option.toolbox};
    if (hasPriceGuides) {
      patch.series = base.series.map(series => ({name:series.name, markLine:copy(series.markLine)}));
      patch.graphic = priceRatioFooter();
    }
    chart.setOption(patch, {silent:true});
    parentElement.__macroChartState = {selected:copy(selected), zoom:chart.getOption().dataZoom};
  }

  loadEngine().then(echarts => {
    if (disposed) return;
    const option = axisLayout(presentation());
    option.legend.selected = selected;
    option.aria = {enabled:true};
    option.tooltip = {...option.tooltip, renderMode:'richText'};
    if (saved?.zoom) option.dataZoom = saved.zoom;
    // Keep toolbox clear of the download/fullscreen buttons.
    if (option.toolbox) option.toolbox.right = 54;
    chart = echarts.init(element, null, {renderer:'canvas'});
    element.__macroChart = chart;
    chart.setOption(option);
    if (hasPriceGuides) updateLayout();
    element.setAttribute('aria-busy', 'false');
    for (const event of ['legendselectchanged','legendselected','legendunselected',
                         'legendselectall','legendinverseselect']) {
      chart.on(event, params => {
        selected = {...selected, ...copy(params.selected || {})};
        rememberSelection(); updateLayout();
      });
    }
    chart.on('restore', () => {
      selected = Object.fromEntries(base.series.map(series =>
        [series.name, base.legend?.selected?.[series.name] !== false]));
      rememberSelection(); updateLayout();
    });
    chart.on('datazoom', () => {
      if (hasPriceGuides) updateLayout();
      else parentElement.__macroChartState = {selected:copy(selected), zoom:chart.getOption().dataZoom};
    });
    observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (disposed) return;
        element.style.height = `${document.fullscreenElement === shell ? innerHeight : data.height || 465}px`;
        chart.resize(); updateLayout();
      });
    });
    observer.observe(shell);
    buttons[0].onclick = () => {
      const link = document.createElement('a');
      link.download = 'macro-chart.png';
      link.href = chart.getDataURL({pixelRatio:2, backgroundColor:'#fff'});
      link.click();
    };
    buttons[1].onclick = () => {
      const result = document.fullscreenElement ? document.exitFullscreen() : shell.requestFullscreen?.();
      result?.catch(() => {});
    };
  }).catch(problem => {
    if (disposed) return;
    element.setAttribute('data-testid','macroEChartsChartError');
    element.setAttribute('aria-busy','false');
    error.hidden = false;
    error.textContent = problem.message || '图表加载失败，请刷新页面';
  });

  return () => {
    disposed = true; cancelAnimationFrame(frame); observer?.disconnect();
    if (chart) {
      parentElement.__macroChartState = {selected:copy(selected), zoom:chart.getOption().dataZoom};
      chart.dispose(); delete element.__macroChart;
    }
    buttons.forEach(button => { button.onclick = null; });
  };
}
