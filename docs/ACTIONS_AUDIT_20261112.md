# GitHub Actions 故障分析与最小修复（2026-11-12）

范围：yingjieli176-art/macro_dashboard。只读取得四个作业完整日志、main 相关工作流/脚本、已保存逐源报告，并直接核对 Cboe、Federal Reserve PRATES、Treasury FiscalData 原始发布。分析基于 main 提交 9e90ce9f5c0fb3e5cdf4437d6b3a83b7257301fb。保留 V1.0、21 张图表、原始观测日期、指标定义和计算公式。

## 逐项证据与归因

| 工作流 / 运行 | 日志证据 | 归因 |
|---|---|---|
| [数据源时效审计 43131962872](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43131962872/job/130898015576) | 8 条频率超期：TC、RC、SPX、Alphabet CDS、Microsoft CDS、TGA、EFFR、SOFR；没有原始记录无效错误 | 混合：发布日历不准确 + 已知源数据陈旧/稀疏 + SPX 解析拒绝。不能把 8 条都当作采集故障 |
| [全图表日期验证 43113856763](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43113856763/job/130836634545) | 最终 64 项 at_source_latest、2 项 unverified、2 项 pipeline_lag、6 项 live_only、2 项 source_behind_repository | IORB/SPX 未核实；DXY/VIX9D 本地落后；严格门槛正确失败 |
| [SPX Put/Call 43091395770](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43091395770/job/130769082034) | 采集退出 0，无新提交；审计观测日 11/06、截止 11/10，退出 1 | 旧日期报告仍能下载，近期报告解析失败被收集进 errors；当 records 未变时直接返回 None，错误既未写入快照，也未打印 |
| [TGA 43090698711](https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43090698711/job/130766665679) | 官方数据未变，最新 11/09；1144 条，末值 0.922633 万亿美元；采集/语义检查/提交步骤成功，离线审计失败 | 官方返回未更新；离线使用香港日期 + BDay(2)，未排除 11/11 美国联邦假日，提前判超期 |

### SPX：上游产品定义变化，禁止静默替代

直接读取 [11/09 Cboe 原报](https://cdn.cboe.com/data/us/options/market_statistics/daily/2026-11-09_daily_options) 和 [11/10 原报](https://cdn.cboe.com/data/us/options/market_statistics/daily/2026-11-10_daily_options)：明确名称都是 SPX + SPXW + SPXO PUT/CALL RATIO，顶层 volume 篮子也已变成 SPX + SPXW + SPXO。现有代码只接受 SPX + SPXW，这是保护原口径的正确拒绝，不应换成 TOTAL/INDEX 或持仓比率。

最小处理：保留原数据和拒绝逻辑，使下载错误在历史未变时仍打印。恢复原口径需要找到能够独立核对 SPX 与 SPXW 成交量的官方数据；若只能取得新增 SPXO 的合计，应单独决定是否接受新口径，不在本次修复中接入。

### IORB：原始发布包含 UTC 次日行

全源作业的采集日志明确记录 _fetch_primary 和 _fetch_api 因 “observed date in the future” 被拒，CSV 另有超时。直接读取 [PRATES 原始 CSV](https://www.federalreserve.gov/datadownload/Output.aspx?rel=PRATES&series=c27939ee810cb2e929a920a6bd77d9f6&filetype=csv&label=include&layout=seriescolumn&type=package)，尾部包含 11/12 的 3.90；失败发生于 11/11 UTC，当时该行尚未来到。

最小处理：仅在 PRATES/IORB 特定解析处截取截至 UTC 当日的已生效记录。通用 validate_observations 的未来日期、数值和行数校验继续严格执行。FRED 镜像可用性问题仍可能独立发生。

### TGA、EFFR、SOFR：频率窗口与源最新分开

直接读取 [FiscalData DTS](https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance?sort=-record_date&page%5Bsize%5D=20&format=json)，最新 record_date 仍为 11/09；具名 Closing Balance 为 922633 百万美元，存于 open_today_bal，close_today_bal 为空。这与现有 schema 解析及快照一致。全源报告也确认 TGA/EFFR/SOFR 均与当次源站返回一致。

最小处理：仅离线审计的 TGA/EFFR/SOFR 使用美国联邦工作日的两日宽限，11/09 的截止由 11/11 调为 11/12，11/13 仍会超期。不会延伸、填充或改写观测日期，不调整股票/Cboe/香港日历。它仍只是频率提醒，实时逐源严格核对不放宽；应用图表的通用频率提示本次不改。

### 其余未解决项

- DXY：全源报告本地 11/09、源站 11/10；refresh_audited_sources.FAMILIES 无 DX-Y.NYB，仓库 scripts 中没有专用 DXY 更新器。属于恢复覆盖缺口，不能仅添加一个映射到不采 DXY 的脚本。下一步应复用 market_history 的身份、币种、完成日校验补专用快照更新，再接入现有审计恢复，禁止用美元 ETF 替代。
- VIX9D：初查未触发该项，因同组 VVIX_TERM 落后已运行 tail-risk 采集；复查却发现 VIX9D 本地 11/10、源站 11/11。现有流程只恢复一次，源发布与采集/复查可能竞态。当前日志不足以证明解析错误，应先复现同源响应和时间。可考虑只对复查新出现的明确 pipeline_lag 做一次有界重试，仍保留最终严格失败；本次不以重试掩盖问题。
- TC/RC、Alphabet/Microsoft CDS：离线超期，而当次独立源报告均 at_source_latest。它们仍陈旧/稀疏，不能称为已追到今日，也不能认定本地采集落后。报告需区分“频率超期”和“源站返回与本地一致”。

## 已有报告和重复告警

1. source-freshness-audit.yml：每 3 小时 + data_snapshots/** 推送触发；写 source_health.json、Actions Step Summary，always 上传 actual-source-freshness 工件。
2. all-source-freshness.yml：定时 + 特定代码推送触发；保存初查与严格复查 JSON，always 上传 complete-source-date-comparison；always 运行 publish_source_refresh 发布有效快照与未解决报告。失败后仍保存证据是已有设计。
3. 更新器自身还有定向离线日期审计；PR Dashboard regression 再跑离线/在线检查。
4. macro_platform/freshness_overview.py 已将全源 JSON 显示为页面逐源核对表，区分未核实、本地落后、源导出较旧与动态构建。
5. 未发现新增 Issue/邮件/Webhook 故障通知发送器或持久化告警指纹去重机制；打开的 Issues 查询只返回 PR。重复主要是同一 SPX 等异常在定向、全源、全局离线检查中多次令 Actions 失败。
6. 全源审计发布报告会引发 data_snapshots/** 的推送审计；不同并发组互不去重。现有 concurrency 只处理同工作流的运行重叠，不能合并跨工作流告警。不增加新监控工作流、不自动发送通知、不直接禁用现有门槛。若后续外部通知需要去重，可使用“源 ID + 故障类别 + 本地/源日期”的状态变化指纹，现有全源报告作为唯一通知输入。

## 本次最小实施

- scripts/audit_source_freshness.py：仅 TGA/EFFR/SOFR 离线发布日历改为联邦工作日。
- scripts/sync_fred_verified_cache.py：仅 PRATES 解析排除尚未生效的日期。
- scripts/update_spx_put_call_snapshot.py：即使没有数据变化，也输出逐日期采集拒绝原因。
- 新增 4 项回归测试：假日窗口及再次超期、未来日期仍失败、IORB 特例与通用严格校验、SPX unchanged 时错误仍可见。
- 不修改 app.py、macro_platform、工作流、快照或依赖版本。已有开放 [PR #105](https://github.com/yingjieli176-art/macro_dashboard/pull/105) 涉及更大范围刷新与 SPXO 篮子变化，本次没有合并、更新或照搬该口径改动；IORB 局部修复与它有意重叠，未来合并时需去重。

## 验证与限制

本地 Python 3.14，pandas 3.1.1 / plotly 7.1.0 / Streamlit 1.67.0，非仓库 CI 的 Python 3.12 固定依赖环境。
69 项相关测试通过：新回归 4、source freshness 13、full freshness 20、SPX 5、TGA schema 6、US liquidity 3、workflow safety 6、date-source audit 12。
一项既有真实 Git 发布竞态测试在 Windows/Bash 路径转换处失败（退出 127），未改写或删除该测试；待 PR 的 Linux CI 复核。首次 Windows 默认 GBK 导致的两个源码读取错误，使用 Python UTF-8 模式重跑已通过。
TGA 定向审计修复后通过，显示真实 11/09 观测日、11/12 截止；git diff --check 通过。
不宣称全部 Actions 已恢复；SPX 新产品篮子仍被拒绝，DXY/VIX9D 等问题仍会使严格全源审计失败。未重跑生产写入作业，未直接修改 main，未合并 PR。

