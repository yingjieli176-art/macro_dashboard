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

## Fed policy corridor (r88)

`2026-11-04-fed-corridor-srf-r88` adds the observed Standing Repo Facility
operation rate (FRED `SRFTSYD`) as a dashed line in chart 1. ON RRP
(`RRPONTSYAWARD`) remains alongside IORB, EFFR and SOFR. All five series
use annualized percent, never facility usage amounts. The SRF offering rate
is an upper backstop for eligible counterparties, not a hard market-wide ceiling.
Verified observations are bundled for cold starts and included in the existing
FRED refresh job, rate validation and source audits. Actual source calendars
and missing observations are preserved without filling or estimates.

## Japan 30Y and country order (r87)

`2026-11-03-japan-30y-country-order-r87` adds MOF 30-year observations to
Japan yields (chart 8), with 30Y−10Y on the spread axis in percentage points.
The collector backfills official five-year history, persists all three tenors,
and retains the last good snapshot on validation failure. Spreads require
both legs on the same observation date; missing values are never forward filled.

Chart 1 retains its policy corridor. US rates, VIX and US equities lead; Japan
rates and yen carry follow; China and Hong Kong follow Japan. Titles, source
inventory and browser checks share the stable chart identity mapping.

## Yen carry analysis (chart 9)

`2026-10-30-position-growth-columns-r81` displays CFTC yen speculative net
positions and chart 5's monthly M2 MoM growth as columns from zero. Prices,
rates and YoY trends remain lines. Column width follows the series' own weekly
or monthly spacing and the visible date window, including on mobile. Legend
filtering and native recovery retain the chart type and original observations.

`2026-10-30-yen-carry-analysis-r80` adds four independently scaled series:

- US 10Y Treasury yield (FRED DGS10) minus Japan 10Y government yield (Japan MOF),
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
| 1–3 | Fed policy corridor, US nominal/real yields and Treasury curve |
| 4–6 | US VIX/VIXEQ, VIX term structure, SPX/RSP prices and drawdowns |
| 7 | S&P 500 / Nikkei 225 relative strength |
| 8–9 | Japan 2Y/10Y/30Y, curve spreads, Nikkei/USDJPY and yen carry |
| 10–11 | China yields and A-share broad indices |
| 12–15 | Hong Kong monetary pulse, bank liquidity, funding and HKD overlays |
| 16–18 | Precious metals, copper and crypto |

The 5Y / 1Y / 6M / 3M / 1M selectors must keep **both X and each Y axis
adaptive**. A Plotly compatibility view is not proof that native ECharts
X/Y autoscaling works.

Chart 4 displays VIX/VIXEQ on the left, S&P 500 on R1, the same-date
VIXEQ/VIX ratio on R2, and COR3M in original Cboe index points on R3.
The VIXEQ−VIX and COR1M series have been removed from this chart.
COR3M is a correlation index, not a volatility reading. Official Cboe histories
are bundled for cold start and refreshed each weekday by
`update-correlation-snapshot.yml`. Early history includes Cboe back-calculations.

Chart 3 includes original FRED DGS30 30-year nominal Treasury yields on the
same left percentage axis as 3M, 2Y and 10Y. The 10Y−2Y and same-date 30Y−10Y yield-curve
spreads stay on R1; 10Y−3M has been removed. DGS30 uses the shared last-good cache, scheduled collector,
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

Display order: 1–3 US monetary policy and Treasury yields; 4 S&P 500 / Nikkei 225 relative strength; 5–8 Hong Kong liquidity;
9 US equity risk; 10 VIX term structure; 11 US equity prices;
12 China equity prices; 13 China rates; 14 Japan rates/equity;
15 precious metals; 16 copper; 17 crypto; 18 yen carry.
Chart 4 replaces the former US Liquidity chart. It shows the same-date
S&P 500 / Nikkei 225 index-point ratio plus both component indices at their
actual integer closing levels. The ratio, S&P 500 and Nikkei 225 each use an
independent Y axis; no rebasing or normalization is applied. Dates without a
close in either market are omitted. The ratio is not an FX-adjusted total return.


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



r89：第17图增加 WTI 原油（CL=F 已完成日线，美元/桶）、铜油比及 Cboe 官方 VVIX 日收盘。铜油比 = 同日 COMEX HG（美元/磅）×2204.62262185÷WTI（美元/桶），单位桶/公吨；缺少任一同日收盘价时不计算，不跨日填充。三项各用独立坐标，图例、周期和滑块沿用原图控制。采集任务保留各字段最后有效历史，源站失败、未来日期、非有限数值或明显截短的响应不能覆盖已有数据；新增字段包含在日期审计和源站核对中。`python scripts/update_copper_snapshot.py --context-only` 可只更新这两个原始字段并保留已有铜数据。


r90：第3图以同日 DGS30−DGS10 的 30Y−10Y 利差替换 10Y−3M，保留10Y−2Y和四条原始收益率曲线。利差在R1按百分点显示，缺少任一同日观测时保持缺失；图例、悬停、说明及来源同步更新。



r91：第5张VIX/VIX3M期限结构图增加SKEW（R2）和VVIX（R3），各用独立指数点坐标；保留原VIX、VIX3M和同日差值。采用Cboe官方已完成日收盘，打包五年历史并自动更新；缺失不补值、失败保留最后有效数据。SKEW为尾部风险定价指标，不是暴跌概率；VVIX衡量VIX自身预期波动。


r92：第5图将VIX3M−VIX替换为VIX/VIX3M，加入同日VIX9D/VIX（9D/30D）及SPX+SPXW成交量Put/Call，三项按倍数共用R1；SKEW、VVIX保留独立坐标。铜图移除VVIX显示。新增第19图NVIDIA USD senior unsecured CDS 1Y/5Y利差，单位bp；当前未取得授权原始利差，图中明确显示待接入，记录保持为空，不以ICE结算价格、票息或模型值代替。

NVIDIA CDS授权CSV导入：`python scripts/import_nvidia_cds.py --csv export.csv`。必需列：`issuer,observation_date,tenor,spread_bps,currency,seniority,quote_type,source,source_url`；期限为1Y/5Y，currency=USD，seniority=SENIOR_UNSECURED，quote_type=par_spread。只导入已有数据授权且允许在该看板展示的实际报价。

r93：第5图新增同日VVIX÷VIX的VVIX/VIX比值，以倍数在R1显示；复用原始VVIX与VIX观测，不跨日填充，任一腿缺失或VIX为0时留空。新增图例、悬停和参数说明，保留原VVIX独立指数点曲线及其R3坐标。

r94：第19图扩展为AI公司CDS历史曲线及最新观测表，展示Oracle、Intel、AMD、NVIDIA、CoreWeave和CDX IG的5Y利差（bp）。来源注明Open-Sourced Rates Observatory, irates.today；只提取公开`chart_data.json`中的CDS字段，不使用股票掉期价格。5Y为剩余期限4.4–5.6年的成交分组、按日聚合；CoreWeave以星号及虚线标注源站预付款推算利差（固定违约强度、40%回收率），不是直接成交利差。无数据日留空、实际观测用圆点显示；每家公司单独报告观测日期和样本数。英伟达1Y授权导入入口保留，不从5Y推算。`update-ai-cds.yml`定时刷新并原子发布快照，源站异常或历史明显截短时保留有效数据，加入独立日期审计。首次接入源站日历截至2026-11-03；NVIDIA最新为2026-10-29，不能称为11月3日实时报价。

第19图附联动观察说明：CDS与资本开支、美债期限溢价与美联储政策、日经和韩国股市与美硬件。均明确标为待检验假设，不把收盘时差或期限风险补偿当成已证实的领先规律。


r95：第17图加入Mysteel进口干净铜精矿现货TC/RC周指数（TC：美元/干吨；RC：美分/磅），R5/R6独立坐标，实际观测标记及图下最新值/日期表。RC按发布方公开方法论取TC数值÷10，并非独立采样或通用单位换算。初始仅收录原始文章可核实的2026-10-16、10-23、10-30三期，最新TC=-245.33、RC=-24.533；不使用第三方误标为10/30的旧TC=-241.07。负值与零值保留，不混入正库存/铜价校验，不补齐日线，不混入年度长协。独立定时任务从公开早读提取带明确观测日的指数，逐条保留原文URL、原子合并历史；失败、旧响应、非有限值及口径异常不能覆盖最后有效快照。频率总览和日期审计按周频检查。
