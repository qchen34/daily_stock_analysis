# 组合相关配置文件说明（config/portfolio）

本目录用于存放**个人组合与观察名单**等与 Portfolio Round1/多轮组合分析相关的用户侧配置数据。

当前约定的文件如下：

1. `user_portfolio.json`  
   - 描述：单账号的静态持仓快照，主要用于构造 `PortfolioSnapshot`。  
   - 顶层字段（示例）：  
     - `account_name: str` — 账户名称，例如 `"美股主账户"`  
     - `as_of: "YYYY-MM-DD"` — 快照日期  
     - `total_equity: float` — 披露的总资产（可为 0 或缺省，后续可由实时市值动态回填）  
     - `cash_usd` / `cash_cny`: float — 现金头寸（按币种拆分，后续可扩展为 `cash: {"USD": ...}` 结构）  
     - `positions: HoldingPosition[]` — 持仓列表  
   - `positions` 内每一项建议与 `src/core/position_profile.HoldingPosition` 对齐：  
     - `code: str` — 标的代码（如 `AAPL`, `0700.HK`）  
     - `name: str` — 标的名称  
     - `position_pct: float` — 静态仓位百分比（0–100，可为 0，用于「目标权重」或占位）  
     - `shares: float` — 持股数量  
     - `cost_price: float` — 成本价  
     - `notes: str` — 备注，建议在自然语言前用前缀形式标出风格标签，例如：  
       - `"tags: core, buffett; note: 核心持仓（巴菲特/段永平逻辑）"`  

2. `watchlist.json`  
   - 描述：观察名单标的及其逻辑标签，仅用于 Round1 等分析中的「关注提示」，**不参与仓位计算**。  
   - 顶层字段（示例）：  
     - `as_of: "YYYY-MM-DD"` — 清单更新时间  
     - `items: WatchItem[]` — 观察标的列表  
   - `items` 内每一项结构建议为：  
     - `code: str` — 标的代码  
     - `name: str` — 标的名称  
     - `tags: [str]` — 逻辑/风格标签列表（如 `["DuanYongping", "Moat", "Value"]`），方便在 Prompt 中做结构化引用  
     - `notes: str` — 备注说明（可与 `tags` 保持冗余，主要面向人类可读性）  

> 后续：  
> - 所有组合相关服务（Round1/Round3/Round4、单股辩论、Portfolio Loader 等）应优先通过统一的 Loader 模块读取本目录下的配置，而不是直接硬编码 JSON 路径；  
> - 如需调整字段结构，优先修改 `src/core/position_profile` / `guru_profile` 等数据模型，再同步更新本 README 中的说明，避免 JSON 与代码模型长期漂移。

