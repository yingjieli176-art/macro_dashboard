# Macro Dashboard

Market and macroeconomic data dashboard with 18 interactive charts and
watchlists. Production UI: <https://data-macromarket.streamlit.app/>.

**Stable application baseline:** `2026-10-09-tga-close-recovery-r38`. A green
GitHub Actions run confirms code/tests, **not** the deployed browser version.
Compare the build identifier printed above the first chart before filing a
UI regression.

## Run locally

Requires Python 3.12+ and a network connection for sources that have no
bundled observations.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Yen carry analysis (chart 18)

`2026-10-30-yen-carry-analysis-r80` adds four independently scaled series:

- US 2Y Treasury yield (FRED DGS2) minus Japan 2Y government yield (Japan MOF),
  in percentage points, calculated only where both have the same observation date.
- USD/JPY completed daily closes (Yahoo JPY=X), in yen per dollar. Falling values
  indicate yen appreciation and higher dollar costs of repaying yen principal.
- Yen appreciation over 20 valid FX observation intervals:
  `(USDJPY[t−20] / USDJPY[t] − 1) × 100`, in percent. Positive values indicate
  appreciation. Calculate before slicing the selected viewport; insufficient
  history or a missing current quote stays missing.
- CFTC Japanese Yen (097741), Legacy Futures Only: noncommercial outright long
  minus short, displayed in ten thousand contracts. Positive means net long yen;
  negative means net short yen. Weekly points use the actual position date,
  generally Tuesday, with release generally Friday. No daily filling or mixing
  with TFF leveraged funds or futures-and-options combined data. The snapshot
  retains the original long, short and open-interest counts for verification.

Narrowing spreads together with yen appreciation indicate deteriorating carry
conditions. The government yield spread is a nominal incentive proxy, not an
overnight funding spread or achievable return. Its annualized rate cannot be
directly subtracted from the 20-session FX return. This chart does not estimate
total carry positions, unwind volumes, leverage, or net P&L. The CFTC position
sample covers reported yen futures, not all cross-border carry trades. Existing
rates/FX refresh paths are reused; `update-cftc-yen.yml` checks the official CFTC
public data daily to accommodate delayed releases, retaining the last good data
if validation fails. The source audit handles positions as weekly observations.

If an external feed is unavailable, the dashboard may use a *dated, verified*
last-good snapshot, or display a missing-series warning. Do not read a cached
observation as a live quote.

Source freshness uses **each field's actual observation date**, not a JSON
download timestamp. Daily/weekly feeds receive seven weekdays of grace (this
is not an exchange holiday calendar). HK monthly monetary statistics allow
the following publication cycle plus a one-week buffer. Genuine late series
remain visible with their date, age and frequency; missing dates are not filled.

`Audit actual source freshness` runs daily and after snapshot updates. Its
Actions summary and `actual-source-freshness` artifact show field-level dates;
overdue or absent observations fail the audit even when a collector fetched
other series successfully. Run locally with `python scripts/audit_source_freshness.py`.

CME copper warehouse totals use **Activity Date**, not Report Date, and convert
short tons to metric tonnes. COCHILCO remains the historical backup. HKAB's
dated O/N and 3M HIBOR fixing supplements the lagging HKMA daily bulletin.
Snapshot publishers retry fetch/rebase/push races without force-pushing;
automatic data jobs never run the obsolete HSTECH code-wiring patch.

## Chart sections

| # | Section |
|---|---|
| 1–4 | Federal Reserve rates, nominal/real Treasury yields, curve, US liquidity |
| 5–8 | Hong Kong monetary pulse, bank liquidity, HIBOR funding, HKD / market overlays |
| 9 | US equity risk (VIX/VIXEQ, S&P 500, VIXEQ/VIX, COR3M) |
| 10 | Precious metals |
| 11 | Digital assets |
| 12 | Copper price/inventory |
| 13 | Asian rates and yield curves |

The 5Y / 1Y / 6M / 3M / 1M selectors must keep **both X and each Y axis
adaptive**. A Plotly compatibility view is not proof that native ECharts
X/Y autoscaling works.

Chart 9 displays VIX/VIXEQ on the left, S&P 500 on R1, the same-date
VIXEQ/VIX ratio on R2, and COR3M in original Cboe index points on R3.
The VIXEQ−VIX and COR1M series have been removed from this chart.
COR3M is a correlation index, not a volatility reading. Official Cboe histories
are bundled for cold start and refreshed each weekday by
`update-correlation-snapshot.yml`. Early history includes Cboe back-calculations.

Chart 3 includes original FRED DGS30 30-year nominal Treasury yields on the
same left percentage axis as 3M, 2Y and 10Y. The existing two yield-curve
spreads stay on R1. DGS30 uses the shared last-good cache, scheduled collector,
Treasury BC_30YEAR fallback, and source-freshness checks; missing dates stay missing.

## Validation

```bash
python -m unittest discover -s tests -p "test_maintenance_workflows.py" -v
python -m unittest discover -s tests -p "test_tga_closing_schema_2022.py" -v
python -m unittest discover -s tests -p "test_echarts_axes.py" -v
python -m unittest discover -s tests -p "test_app_runtime_smoke.py" -v
```

The full `Viewport Y-axis regression` GitHub workflow additionally tests
offline app startup, historical observations, data provenance and dynamic axes.
The separate `Maintenance workflow safety` workflow is intentionally fast
and does not contact external data vendors.

## Architecture and safe maintenance

Read [docs/MAINTENANCE.md](docs/MAINTENANCE.md) for the module boundaries,
data source provenance, automatic snapshot jobs vs. **manual-only obsolete
migration jobs**, a cautious performance optimization plan, and the merge
checklist.

Do not commit a plot or a new estimated rate as an original observation.
The Treasury DTS TGA closing account changed field placement in April 2022;
`macro_platform/treasury_cash.py` records the correct account-label-based
interpretation.

## SPX / RSP price chart (11)

SPX uses the S&P 500 float-adjusted market-cap-weighted **price index**;
RSP is the Invesco S&P 500 Equal Weight ETF. RSP is a fund, not an index:
its price reflects fund fees, distributions and tracking differences.
Both histories use completed US daily `quote.close` prices, split-adjusted
but **without dividend reinvestment**. Never mix Yahoo `adjclose` total-return
adjustments with the SPX price index. `range=max` monthly responses are rejected.

Chart 11 displays original close prices: SPX in index points on the left axis
and RSP in USD on the right axis. High guides are recomputed from the closing prices inside the current
coordinate time window, including client-side slider zoom. Dotted horizontal lines
mark interval highs and dashed lines mark latest closes. Captions retain the
latest actual close and observation date. The chart has its own fragment and time
controls, without a data table.

The data-only `update-us-equity-snapshot.yml` job refreshes both histories and
atomically publishes `data_snapshots/us_equity_daily.json`. Partial, stale,
future, non-daily or truncated responses cannot replace last-good data.


## China equity price chart (12)

The CSI 300 (000300), CSI 1000 (000852), and CSI 2000 (932000) share one
original index-points axis, with individual high/latest reference lines. Prices come from the CSI official historical API,
using completed mainland trading-day closes and each index's full available
history since its base date. Published pre-launch backcasts are retained;
carry-in API rows before the base date are excluded. The plotted high follows the visible coordinate window; historical dates
outside that window do not affect its reference line.

The data-only China equity workflow atomically updates all three histories.
Incomplete sessions, missing indices, shortened history and stale responses
cannot replace the last-good snapshot. Actual observation dates remain visible.

Display order: 1–4 US policy/rates/liquidity; 5–8 Hong Kong liquidity;
9 US equity risk; 10 VIX term structure; 11 US equity prices;
12 China equity prices; 13 China rates; 14 Japan rates/equity;
15 precious metals; 16 copper; 17 crypto. Internal builder keys stay stable.


## Equity price charts and reference lines (11–12)

Charts 11 and 12 display original daily closing prices, not normalized prices
or percentage drawdown curves. SPX uses the left points axis and RSP the right
USD axis. CSI 300/1000/2000 share an index-points axis. Each asset has a dotted
visible-window highest-close line and a dashed latest-close line with numeric
labels. The high and its original observation date update with every visible-window change.
Native reference lines follow the asset's legend visibility and remain inside
the dynamic Y range during time selection, slider zoom and resizing. They are
annotations and never enter observation counts or source freshness dates.
VIX is the official 30-calendar-day (~1M) index; the 1M/3M chart buttons change
the historical display window rather than the volatility forecast horizon.

### 全看板日期与取数核对（r73）

“数据最新时间”同时列出每条曲线的实际观测日、日/周/月频率和频率窗口状态；另列源站逐项核对结果及核对时间。“在频率窗口内”不等于已追上源站，工作日窗口也不是各市场节假日日历。

- `scripts/audit_source_freshness.py` 核对本地原始记录，包含日本国债、SPX/RSP及三只CSI指数；无效日期、未来日期、重复日期和非有限数值会使核对失败。
- `scripts/probe_all_sources.py --strict` 按当前17张图号核对55个源指标。相同接口的并发读取合并，报告记录耗时与共享请求复用次数；网络失败保持“未核实”，本地落后源站保持“落后”。
- 港股备用行情使用已完成的日线及交易所当地日期；不再用月线月初时间戳代替实际收盘日。临时传输失败保留原观测日的最后有效数据并短暂限制重试。
- SPX/RSP任务包含UTC周六补抓，覆盖周五美股收盘后的延迟发布；快照仍只在校验通过后原子替换。

2026-10-28核对结果：32份快照/51个原始字段未发现无效日期、未来日期、重复日期或非有限数值；55个源指标中10项快照滞后已补采，补采后47项与源站返回日期一致、7项页面实时构建、1项恒指源站导出较旧而保留本地较新已验记录。完整回归259项及浏览器交互通过。核对用时25.942秒，共享HTTP下载29次、复用8次；这些数字只覆盖共享HTTP层，不代表全部源站调用。记录见 `docs/evidence/date-source-audit-20261028.json`。

r74：SPX/RSP及A股三指数图底增加“距区间前高回撤”比例，随周期、滑块、图例同步更新并包含在图片导出中。公式为（所选区间最高收盘−最新收盘）÷所选区间最高收盘；若现价高于历史选区前高，明确显示高出比例。增加画布底部空间，不压缩原价格绘图区。美股采集器遇到有效但落后一个交易日的首选主机时，会核对第二主机并保留较新响应。

2026-10-28 10:25北京时间再次核对：40项源站日期一致、7项页面实时构建，8项HKMA指标因直连接口及代理回退不可用而保持“未核实”；未发现已确认的快照滞后。保留上次有效观测，最新核对状态以 `data_snapshots/all_source_freshness.json` 为准。r74完整回归261项和浏览器比例/滑块测试通过；源站核对仍严格保留这8项失败状态。


r75：第11、12图在原价格走势下方增加同画布回撤曲线。每条曲线独立选取当前价格时间选区内的最高收盘（并列取最早日），由该日0%起，固定基准计算（当日收盘÷最高收盘−1）×100%，延伸到最新实际收盘；不展示高点之前的回撤，不采用滚动前高。周期、左右滑块重选基准；下方独立时间轴确保历史选区也能画到现价。历史高点被后续价格超过时允许正值，不截断为0。上方原始价格不变，底部正数回撤幅度和PNG导出保留；图例联动两个绘图区。


r76：SPX/RSP与中证三指数的回撤曲线叠加到价格走势的同一绘图区，共用唯一日期轴；不再设置下方独立绘图区或增加画布高度。价格保留实线和原单位，回撤用同色虚线及右侧独立百分比轴。周期、左右滑块同时过滤价格与回撤，自动用可见时间范围最高收盘重选固定基准；底部仍列最新收盘相对该高点的幅度。


r77：逐日回撤以独立命名参数展示：SPX/RSP及中证三指数各自增加“回撤比例”图例项，可与价格独立开关。仍在原绘图区共用日期轴，从所选最高收盘日0%起逐日计算；独立日线直接显示每个交易日从高点起的回撤走势，底部另列最新比例。手机图例按新增参数完整换行，百分比轴只随回撤参数开关。
