# 全量数据复查（2026-11-13）

生产检查：https://github.com/yingjieli176-art/macro_dashboard/actions/runs/43356749597

05:58 UTC 的 86 项来源检查触发了 DXY、铜/原油、HIBOR、日本回购利率补采。最终报告为 76 项与源最新日期一致、6 项仅实时读取、4 项未核实，不能据此宣称所有数据均已正常。SPX P/C、两项 OAS、日本回购利率仍需后续核实。

## 确认的问题与最小修复

- 期货日期：纽约已过午夜、芝加哥尚在前一天时，16:15 芝加哥收盘兜底错误使用纽约当天日期，提前接纳下一个交易日未收盘柱。改用芝加哥已结束的日期，保留显式交易时段判断。新增跨午夜回归测试。移除 05:58 UTC 补采错误保存的 11/13 铜和 WTI 未收盘行，保留修订后的 11/12 收盘及其他来源数据。
- FRED 配置：`data.py` 只读取 Streamlit secrets，未读取自动工作流已注入的环境密钥。优先使用非空环境配置，保留桌面 secrets 兜底，不输出密钥。这修复配置路径，源服务是否可用仍须生产复查。
- 信用利差显示：HY OAS 保留 R1，IG OAS 使用独立 R2，自适应比例，单位均为 %。不改变 OAS 数值、CDS 口径、缺失日或观测日。

## 延迟和覆盖不足须分开

- TGA、EFFR、SOFR 的 11/10 数据在本轮与官方最新一致；11/11 美国联邦假期影响后续发布，不能按自然日误报为漏更。
- TC/RC 的 10/30 数据与当前检查到的周度源一致。稀疏公司 CDS 必须以实际报价日显示，不能填充成每日新报价。
- USD/JPY 3M ATM Saxo 快照仅有 11/11、11/12 两点。当前公开日报没有历史下载入口；Internet Archive 2021 年以来仅检索到 49 次页面存档，且长时间断档，无法提供连续历史日线。纽约联储同类公开报价于 2013 年停止，不能满足当前五年窗口。LSEG 文档确认 `JPYVOL=` 链有历史 ATM 数据，但需要有权访问的会话。完整日线回补尚未完成；不得用现货已实现波动率、1M 波动率、插值或风险逆转代替。

参考：
- https://fxowebtools.saxobank.com/otc.html
- https://www.newyorkfed.org/markets/impliedvolatility
- https://community.developers.lseg.com/discussion/81902/how-to-get-historical-implied-volatility-data-of-fx-pairs/p1

## 告警机制

保留现有 `all_source_freshness.json`、来源时效审计及工作流日志机制，不新建重复告警。未核实项目继续保留失败状态；历史覆盖不足不冒充时效恢复。
