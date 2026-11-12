// App-owned component. Never reach into Streamlit's React internals.
const copy = value => JSON.parse(JSON.stringify(value));
// These are observation calendar dates, not the viewer's local midnight.
// Explicit UTC keeps axis labels, tooltips and peaks on the same source day.
export const asTime = value => typeof value === 'number' ? value : Date.parse(
  typeof value === 'string' && /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$/.test(value)
    ? value.slice(0,10) + 'T00:00:00Z' : value);

// Weekly/monthly columns need widths based on their own observation cadence,
// even when daily price lines share the time axis. Never add calendar samples.
export function barPixelWidth(points, lower, upper, plotWidth) {
  const times = points.filter(point => Number.isFinite(point[1])).map(point => asTime(point[0]))
    .filter(Number.isFinite).sort((a,b) => a-b);
  const gaps = times.slice(1).map((time,index) => time-times[index]).filter(gap => gap > 0).sort((a,b) => a-b);
  if (!gaps.length || !(upper > lower)) return 8;
  return Math.max(1, Math.min(16, plotWidth*gaps[Math.floor(gaps.length/2)]/(upper-lower)*0.65));
}

// One fixed peak inside the selection; only observations on/after it belong
// to this path. The right selection handle never truncates the path to now.
export function peakDrawdown(points, lower, upper) {
  let peak = null, latest = -Infinity;
  for (const [day, value] of points) {
    const time = asTime(day);
    if (Number.isFinite(time) && Number.isFinite(value) && value > 0) latest = Math.max(latest, time);
    if (Number.isFinite(time) && Number.isFinite(value) && value > 0 &&
        time >= lower && time <= upper && (!peak || value > peak.value)) {
      peak = {day, time, value};
    }
  }
  return {peak, data:peak ? points.filter(point => asTime(point[0]) >= peak.time && asTime(point[0]) <= latest)
    .map(([day, value]) => [day, Number.isFinite(value) && value > 0 ?
      (value / peak.value - 1) * 100 : null, value]) : []};
}

export function drawdownDifference(equal, weighted) {
  const left = new Map(equal.map(p => [asTime(p[0]), p[1]]));
  const right = new Map(weighted.map(p => [asTime(p[0]), p[1]]));
  return [...new Set([...left.keys(), ...right.keys()])].sort((a,b)=>a-b)
    .map(day => [day, Number.isFinite(left.get(day)) && Number.isFinite(right.get(day))
      ? left.get(day)-right.get(day) : null]);
}

export function dailyPriceTooltip(params, labels) {
  const rows = (Array.isArray(params) ? params : [params]).filter(row => Array.isArray(row.value));
  if (!rows.length) return '';
  const rawDay = rows[0].value[0];
  const day = typeof rawDay === 'string' ? rawDay.slice(0,10) : new Date(rawDay).toISOString().slice(0,10);
  return [day, ...rows.map(row => {
    if (row.seriesId === 'macro-peak-drawdown-difference') {
      const value = row.value[1];
      return `等权回撤−加权回撤（RSP−SPX）：${Number.isFinite(value) ? value.toFixed(2)+'个百分点' : '暂无同日观测'}`;
    }
    const ratio = row.seriesId.startsWith('macro-peak-drawdown-');
    const index = Number(row.seriesId.split('-').at(-1));
    const value = row.value[1];
    const text = Number.isFinite(value) ? (ratio ? value.toFixed(2) + '%' :
      value.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})) : '暂无观测';
    return `${labels[index]} ${ratio ? '回撤比例' : '收盘'}：${text}`;
  })].join('\n');
}
export function compactLegend(option, labels, width) {
  const names = [...new Set(option.series.map(series => series.name))];
  const prior = option.legend || {};
  const fontSize = prior.textStyle?.fontSize || 12;
  const lineHeight = Math.max(prior.textStyle?.lineHeight || 0, fontSize + 4);
  const itemWidth = prior.itemWidth || 25, itemGap = 10;
  const usable = Math.max(width - 24, 80);
  const textWidth = text => [...text].reduce((n, char) =>
    n + (/[^\x00-\x7f]/.test(char) ? fontSize : fontSize * 0.65), 0);
  const displays = {};
  const packed = [];
  let used = 0, rowHeight = lineHeight, height = 0;
  for (const name of names) {
    // Wrap a long individual label too, so a narrow screen never clips it.
    const lines = [''], limit = Math.max(usable - itemWidth - 8, 32);
    for (const char of labels[name] || name) {
      if (lines.at(-1) && textWidth(lines.at(-1) + char) > limit) lines.push('');
      lines[lines.length - 1] += char;
    }
    displays[name] = lines.join('\n');
    const size = itemWidth + 8 + Math.max(...lines.map(textWidth));
    if (used && used + itemGap + size > usable) {
      packed.push('\n'); height += rowHeight + itemGap;
      used = 0; rowHeight = lineHeight;
    }
    packed.push(name);
    used += (used ? itemGap : 0) + size;
    rowHeight = Math.max(rowHeight, lines.length * lineHeight);
  }
  height += rowHeight;
  option.legend = {...prior, type:'plain', orient:'horizontal', top:26,
    left:8, right:8, padding:0, itemWidth, itemGap, data:packed,
    formatter:name => displays[name] || labels[name] || name,
    textStyle:{...prior.textStyle, fontSize, lineHeight}};
  option.grid.top = Math.max(Number(option.grid.top) || 0, 26 + height + 30);
  return option;
}

export function compactTooltip(params, labels) {
  const rows = (Array.isArray(params) ? params : [params]).filter(Boolean);
  if (!rows.length) return '';
  const first = rows[0], day = Array.isArray(first.value) ? first.value[0] : first.axisValue;
  const when = typeof day === 'number' ? new Date(day).toISOString().slice(0,10) : String(day || first.axisValueLabel || '').slice(0,10);
  return [when, ...rows.map(row => {
    const value = Array.isArray(row.value) ? row.value[1] : row.value;
    return `${labels[row.seriesName] || row.seriesName}：${Number.isFinite(value) ? value.toLocaleString('en-US', {maximumFractionDigits:4}) : '暂无观测'}`;
  })].join('\n');
}

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
  const labels = data.parameter_labels || {};
  const source = copy(data.option);
  source.useUTC = true;
  for (const series of source.series) series.data = series.data.map(point =>
    Array.isArray(point) ? [asTime(point[0]), ...point.slice(1)] : point);
  for (const zoom of source.dataZoom || []) {
    for (const key of ['startValue', 'endValue']) if (zoom[key] != null) zoom[key] = asTime(zoom[key]);
  }
  const base = copy(source);
  delete base.media;
  // Legend filtering must not change the time domain, especially when every
  // series is hidden. Bounds come only from existing observation dates.
  let first = Infinity, last = -Infinity;
  for (const series of base.series) for (const point of series.data) {
    const time = asTime(point[0]);
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
  const hasBars = base.series.some(series => series.type === 'bar');
  if (hasPriceGuides) base.series.forEach((series, index) => { series.id = `macro-price-${index}`; });
  const shortNames = hasPriceGuides ? base.series.map(series => series.markLine.data.find(line =>
    / · 最高收盘$/.test(line.name)).label.formatter.split(' 高 ')[0]) : [];
  const ratioNames = shortNames.map(name => `${name} 回撤比例`);
  const equalIndex = shortNames.indexOf('RSP'), weightedIndex = shortNames.indexOf('SPX');
  const hasDifference = equalIndex >= 0 && weightedIndex >= 0;
  const differenceName = '等权−加权 回撤比例';
  const ratioColors = ['#9333ea', '#db2777', '#0891b2'];
  const footerSpace = hasPriceGuides ? data.price_footer_height || 0 : 0;
  let drawdowns = [];
  const priceNumber = value => value.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
  function refreshPriceGuides(zooms) {
    if (!hasPriceGuides) return;
    const zoom = (zooms || [])[0] || {};
    const start = asTime(zoom.startValue), end = asTime(zoom.endValue);
    const lower = Number.isFinite(start) ? start : first + (last-first)*(zoom.start ?? 0)/100;
    const upper = Number.isFinite(end) ? end : first + (last-first)*(zoom.end ?? 100)/100;
    drawdowns = base.series.map(series => peakDrawdown(series.data, lower, upper));
    for (const [index, series] of base.series.entries()) {
      const high = (series.markLine?.data || []).find(line => / · 最高收盘$/.test(line.name || ''));
      if (!high) continue;
      const best = drawdowns[index].peak;
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

  function withDrawdownOverlay(option) {
    if (!hasPriceGuides) return option;
    const axisIndex = option.yAxis.length;
    const difference = hasDifference ? drawdownDifference(drawdowns[equalIndex].data, drawdowns[weightedIndex].data) : [];
    const active = drawdowns.some((path, index) => selected[ratioNames[index]] !== false && path.peak) ||
      (hasDifference && selected[differenceName] !== false && difference.some(p=>Number.isFinite(p[1])));
    const mobile = element.clientWidth <= 700;
    const spacing = mobile ? (element.clientWidth <= 360 ? 40 : element.clientWidth <= 480 ? 44 : 48) : 58;
    const rightAxes = option.yAxis.filter(axis => axis.position === 'right' && axis.show !== false).length;
    if (active) option.grid.right += mobile ? spacing : 70;
    option.yAxis.push({id:'macro-peak-drawdown-axis', type:'value', gridIndex:0,
      position:'right', offset:rightAxes * spacing, name:active ? '回撤比例 (%)' : '',
      nameLocation:'end', nameGap:12, nameTextStyle:{fontSize:11, align:'right'},
      scale:true, show:active,
      axisLabel:{formatter:value => `${Number(value.toFixed(2))}%`, fontSize:10,
        showMinLabel:false, showMaxLabel:false}, splitLine:{show:false},
      min:extent => Math.min(extent.min, 0), max:extent => Math.max(extent.max, 0)});
    option.series = [...base.series.map(series => copy(series)), ...drawdowns.map((path, index) => ({
      id:`macro-peak-drawdown-${index}`, name:ratioNames[index], type:'line',
      xAxisIndex:0, yAxisIndex:axisIndex, data:path.data, encode:{x:0, y:1, tooltip:[1]},
      showSymbol:true, symbol:'circle', symbolSize:3, connectNulls:false, animation:false, z:4,
      lineStyle:{color:ratioColors[index % ratioColors.length], width:3, type:'dashed', opacity:1},
      itemStyle:{color:ratioColors[index % ratioColors.length]},
      tooltip:{valueFormatter:value => `${Number(value).toFixed(2)}%`},
      markPoint:{symbol:'circle', symbolSize:6, label:{show:false},
        data:path.data.length ? [{coord:path.data[0].slice(0,2)}] : []},
      markLine:{silent:true, symbol:'none', label:{show:false},
        lineStyle:{color:'#94a3b8', type:'dashed', width:1}, data:[{yAxis:0}]}
    }))];
    const names = [...base.series.map(series => series.name), ...ratioNames];
    for (const name of ratioNames) labels[name] = `${name}（相对区间最高收盘）〔回撤轴 · %〕`;
    if (hasDifference) {
      option.series.push({id:'macro-peak-drawdown-difference', name:differenceName, type:'line',
        xAxisIndex:0, yAxisIndex:axisIndex, data:difference, connectNulls:false,
        showSymbol:false, animation:false, z:5,
        lineStyle:{color:'#0f766e',width:2.6,type:'solid'}, itemStyle:{color:'#0f766e'}});
      names.push(differenceName);
      labels[differenceName] = '等权回撤−加权回撤（RSP−SPX，百分点）〔回撤轴 · %〕';
    }
    option.legend.data = names;
    option.tooltip = {...option.tooltip, trigger:'axis', formatter:params => dailyPriceTooltip(params, shortNames)};
    // Price and percentage paths share one grid and one calendar axis.
    // Both slider handles clip both kinds of series to the same dates.
    option.dataZoom = option.dataZoom.map(zoom => ({...zoom, xAxisIndex:[0]}));
    return option;
  }

  function priceRatioFooter() {
    const assets = base.series.filter(series => (series.markLine?.data || []).some(isPriceGuide));
    const lines = assets.map((series, index) => {
      const high = series.markLine.data.find(line => / · 最高收盘$/.test(line.name));
      const current = series.markLine.data.find(line => / · 最新收盘$/.test(line.name));
      const short = high.label.formatter.split(' 高 ')[0];
      let text = '';
      if (selected[series.name] !== false || selected[ratioNames[index]] !== false) {
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
        style:{text, fill:ratioColors[index % ratioColors.length], fontSize:12, lineHeight:20}};
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
    const compactAxes = mobile && axes.length > 5 && element.clientWidth <= 480;
    const spacing = compactAxes ? 30 : mobile ? (element.clientWidth <= 360 ? 40 : element.clientWidth <= 480 ? 44 : 48) : 58;
    const lane = mobile ? spacing : 70;
    let visibleRight = 0, visibleLeft = 0;
    axes.forEach((axis, index) => {
      const show = used.has(index);
      axis.scale = !base.series.some(series => series.type === 'bar' &&
        (series.yAxisIndex || 0) === index && selected[series.name] !== false);
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

  function sizeBars(option, zooms) {
    if (!hasBars) return option;
    const zoom = (zooms || [])[0] || {};
    const start = asTime(zoom.startValue), end = asTime(zoom.endValue);
    const lower = Number.isFinite(start) ? start : first+(last-first)*(zoom.start ?? 0)/100;
    const upper = Number.isFinite(end) ? end : first+(last-first)*(zoom.end ?? 100)/100;
    const width = Math.max(80, element.clientWidth-option.grid.left-option.grid.right);
    for (const series of option.series) if (series.type === 'bar') {
      series.barWidth = barPixelWidth(series.data, lower, upper, width);
    }
    return option;
  }

  function updateLayout() {
    if (!chart || disposed) return;
    refreshPriceGuides(chart.getOption().dataZoom);
    const option = sizeBars(compactLegend(withDrawdownOverlay(axisLayout(presentation())), labels, element.clientWidth), chart.getOption().dataZoom);
    if (option.toolbox) option.toolbox.right = 54;
    // Price observations stay intact. Only derived paths and annotations
    // change with the selection; the live dataZoom bounds are preserved.
    if (!hasPriceGuides) option.tooltip = {...option.tooltip, formatter:params => compactTooltip(params, labels)};
    const patch = {legend: {...option.legend, selected}, grid: option.grid,
      yAxis: option.yAxis, xAxis: option.xAxis, toolbox: option.toolbox, tooltip:option.tooltip};
    if (hasPriceGuides) {
      patch.series = option.series.map((series, index) => index < base.series.length ?
        {id:series.id, name:series.name, markLine:copy(series.markLine)} : series);
      patch.graphic = priceRatioFooter();
    } else if (hasBars) {
      patch.series = option.series.map(series => ({name:series.name,
        ...(series.type === 'bar' ? {barWidth:series.barWidth} : {})}));
    }
    chart.setOption(patch, {silent:true, replaceMerge:['yAxis']});
    parentElement.__macroChartState = {selected:copy(selected), zoom:chart.getOption().dataZoom};
  }

  loadEngine().then(echarts => {
    if (disposed) return;
    if (hasPriceGuides) refreshPriceGuides(saved?.zoom || base.dataZoom);
    const option = compactLegend(withDrawdownOverlay(axisLayout(presentation())), labels, element.clientWidth);
    option.legend.selected = selected;
    option.aria = {enabled:true};
    option.tooltip = {...option.tooltip, renderMode:'richText',
      ...(!hasPriceGuides ? {formatter:params => compactTooltip(params, labels)} : {})};
    if (saved?.zoom) option.dataZoom = saved.zoom;
    sizeBars(option, option.dataZoom);
    // Keep toolbox clear of the download/fullscreen buttons.
    if (option.toolbox) option.toolbox.right = 54;
    chart = echarts.init(element, null, {renderer:'canvas'});
    element.__macroChart = chart;
    // Replace the whole option when Streamlit reuses a mounted chart element.
    chart.setOption(option, {notMerge:true});
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
      for (const name of ratioNames) selected[name] = true;
      if (hasDifference) selected[differenceName] = true;
      rememberSelection(); updateLayout();
    });
    chart.on('datazoom', () => {
      if (hasPriceGuides || hasBars) updateLayout();
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


