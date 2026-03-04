## 本地二次开发版变更记录（相对上游 ZhuLinsen/daily_stock_analysis）

> 本文件仅记录本仓库在上游项目基础上的**新增/修改部分**，方便后续迁移、对比与维护。  
> 上游项目的完整变更请参考原仓库的 `docs/CHANGELOG.md`。

---

### 一、核心配置与入口层

- **`main.py`**
  - 新增 `--mode` 参数，用于选择运行模式：
    - `full`：原始完整流程（与不传 `--mode` 行为等价）。  
    - `stock`：仅运行第二轮个股 + 大盘分析；强制关闭个股辩论模块（`enable_debate_module = False`）。  
    - `portfolio`：仅运行第一轮组合分析（Round 1），生成 `portfolio_round1_*.md` 并推送到 Telegram。  
    - `debate`：仅运行第三轮组合决策（Round 3），基于最近的 Round1 + Round2 报告生成 `round3_decision_*.md` 并推送到 Telegram。  
    - `final_decision`：仅运行第四轮最终执行指南（Round 4），基于最近的 Round1 + Round2 + Round3 生成 `round4_final_*.md` 并推送到 Telegram。  
  - 抽取 `_create_reports_run_dir() -> Tuple[Path, str]`：为当前运行创建带时间戳的 `reports/子目录` 并设置 `REPORTS_RUN_DIR`。  
  - 在 `run_full_analysis` 中：
    - 增加 `USE_PORTFOLIO_STOCK_LIST` 支持：当 `Config.use_portfolio_stock_list=true` 时，如果 `StockAnalysisPipeline.user_portfolio` 存在，则优先使用 `user_portfolio.json` 中的持仓代码作为第二轮分析的 `stock_codes`。  
    - 对合并推送逻辑（Issue #190）增加分支：当启用组合四轮模式时跳过第二轮合并推送，由第四轮终稿统一推送。  

- **`src/config.py`**
  - 新增配置字段：
    - `enable_portfolio_rounds: bool = False`（目前已改为通过 `--mode` 控制，不再自动触发）。  
    - `use_portfolio_stock_list: bool = False`：是否在第二轮分析时优先使用 `user_portfolio.json` 中的持仓代码列表。  
  - 从 `.env` 读取对应环境变量：
    - `ENABLE_PORTFOLIO_ROUNDS`、`USE_PORTFOLIO_STOCK_LIST`。

---

### 二、组合 & 持仓数据模型层（`src/core/`）

- **`src/core/position_profile.py`（新增）**
  - 数据结构：
    - `HoldingPosition`：
      - 静态字段：`code`, `name`, `position_pct`, `cost_price`, `notes`, `shares`。  
      - 动态字段：`runtime_price`, `runtime_market_value`, `runtime_position_pct`（为后续动态仓位计算预留）。  
    - `PortfolioSnapshot`：  
      - `positions: Dict[str, HoldingPosition]`  
      - `total_equity`, `as_of`, `account_name`。  
  - 工具函数：
    - `get_position_for_code(portfolio, code) -> Optional[HoldingPosition]`  
    - `get_position_pct_for_code(portfolio, code) -> float`：优先返回 `runtime_position_pct`，否则回退到静态 `position_pct`。  
    - `describe_position_bucket(position_pct) -> Tuple[PositionBucket, str]`：结合 `debate_profile.PositionBucket` 输出仓位档位与人类可读描述。

- **`src/core/guru_profile.py`（新增）**
  - 数据结构：
    - `GuruPosition`：`code`, `name`, `weight_pct`, `latest_action`, `change_pct`, `thesis`。  
    - `GuruPortfolioSnapshot`：`guru_name`, `style_tagline`, `positions: Dict[str, GuruPosition]`, `as_of`, `notes`。  
    - `GuruHoldingsContext`：`portfolios: List[GuruPortfolioSnapshot]`。

- **`src/core/debate_profile.py`（新增）**
  - `PositionBucket` 枚举：`EMPTY`, `LIGHT`, `MEDIUM`, `HEAVY`。  
  - `bucket_position(position_pct) -> PositionBucket`：按数值映射仓位档位。  
  - `AnalystProfile`：多风格虚拟分析师人设（防守/进攻/技术/基本面派等），含 `to_prompt_block()` 方法便于拼装 Prompt。  
  - `get_default_analyst_profiles()` / `get_analyst_profile_map()`：返回默认人设列表与 Map。

- **`user_portfolio.json`（新增，根目录）**
  - 结构示例：
    - `account_name`, `as_of`, `total_equity`, `cash_usd`。  
    - `positions`: 数组，每项包含 `code`, `name`, `position_pct`, `shares`, `cost_price`, `notes`。

- **`guru_holdings.json`（新增，根目录）**
  - 结构示例：
    - `portfolios`: 数组，每项为一个 Guru 的持仓快照，包含 `guru_name`, `style_tagline`, `as_of`, `notes` 与 `positions`（每个 `GuruPosition`）。

- **`watchlist.json`（新增，根目录）**
  - 存放观察名单标的及其逻辑备注，不参与仓位计算与第二轮分析，仅作为提示信息。

---

### 三、单股多风格辩论服务（`src/services/debate_service.py`）

- 新增文件 `src/services/debate_service.py`：
  - 数据结构：
    - `DebateAnalystView`：单个虚拟分析师在辩论中的视角。  
    - `DebateResult`：多分析师辩论的整体结果，包含：
      - `stock_code`, `stock_name`, `position_pct`, `position_bucket`, `position_description`；  
      - `analysts: List[DebateAnalystView]`；  
      - `consensus_summary`, `consensus_action_no_position`, `consensus_action_has_position`；  
      - `consensus_risks`, `consensus_opportunities`；  
      - `raw_json`, `raw_text`。  
    - `DebateResult.to_markdown()`：将结果转换为可直接拼接到个股报告末尾的 Markdown 段落。
  - 服务类 `DebateService`：
    - `run_debate(base_result: AnalysisResult, position_pct: float, analyst_profiles: Optional[List[AnalystProfile]] = None, guru_context: Optional[GuruHoldingsContext] = None) -> Optional[DebateResult]`  
      - 构造多角色辩论 Prompt，显式注入：  
        - 当前标的与用户仓位（档位 + 百分比）；  
        - （可选）多个大佬在该标的上的权重、加减仓动作及逻辑摘要；  
        - 单股原始分析结果中的核心结论、风险提示、新闻摘要等。  
      - 调用 `GeminiAnalyzer.run_custom_prompt`；  
      - 使用 `json_repair` 等解析 JSON，填充 `DebateResult`，解析失败时降级为 `raw_text`。

- 在 `src/core/pipeline.py` 中集成单股辩论：
  - 在单股推送路径下，条件 `config.enable_debate_module == True` 时：
    - 从 `self.user_portfolio` 推导当前标的仓位百分比；  
    - 构造 `DebateService` 并调用 `run_debate(result, position_pct=..., guru_context=self.guru_context)`；  
    - 将 `debate.to_markdown()` 追加到单股报告末尾；  
    - 在日志中记录加载的用户组合与大佬持仓数量以及单股附加辩论信息。

---

### 四、组合四轮服务（`src/services/portfolio_*.py`）

#### 1. Round 1：`portfolio_analysis_service.py`（新增）

- 负责基于 `PortfolioSnapshot` + `GuruHoldingsContext` 进行组合视角的第一轮分析。  
- 当前版本：
  - 接受 `PortfolioSnapshot` 与可选 `GuruHoldingsContext`，拼装 Markdown Prompt；  
  - 调用 `GeminiAnalyzer.run_custom_prompt`，返回 `PortfolioRound1Output(raw_text)`；  
  - 在 `main.py --mode portfolio` 和四轮集成逻辑中，将 `raw_text` 写入 `portfolio_round1_*.md`。  
  - Prompt 已包含统一的输出结构说明与固定免责声明段落。
- 后续计划：升级为严格 JSON 输出（`PortfolioRound1Result`），并由 `to_markdown()` 负责渲染报告。

#### 2. Round 3：`portfolio_decision_service.py`（新增）

- 负责基于 Round1 + Round2 的文本输出，生成第三轮「风险与仓位管理综合决策」。  
- 接口：
  - `synthesize_decision(portfolio_round1_text: str, round2_report_text: str) -> Optional[PortfolioRound3Output]`。  
  - 内部构造 Prompt，要求模型输出包含：
    - 今日整体态度（进攻/观望/防守）与理由；  
    - 建议的目标总仓位区间与现金比例；  
    - 各重点持仓标的的操作建议与简短理由；  
    - 不宜激进操作的原因列表；  
    - 未来数日的执行节奏建议；  
    - 固定免责声明。  
  - 返回 `PortfolioRound3Output(raw_text)` 并写入 `round3_decision_*.md`。

#### 3. Round 4：`portfolio_debate_service.py`（新增）

- 负责在前三轮结果基础上，以“投资委员会”视角生成最终执行指南（第四轮）。  
- 接口：
  - `debate_decision(round1_text: str, round2_text: str, round3_text: str) -> Optional[PortfolioRound4Output]`。  
  - Prompt 要求模型严格按以下结构输出 Markdown：
    - 一、今日组合执行总览  
    - 二、个人持仓与大佬持仓概览  
    - 三、组合层面仓位与风险控制  
    - 四、重点标的操作清单  
    - 五、风险提示清单  
    - 六、执行节奏与复盘提醒  
    - 免责声明。  
  - 返回 `PortfolioRound4Output(raw_text)` 并写入 `round4_final_*.md`。

---

### 五、CLI 模式与 `reports/` 目录约定

- 新增统一时间戳子目录：  
  - 每次运行 `run_full_analysis` 或 `--mode portfolio` 等模式时，通过 `_create_reports_run_dir()` 创建 `reports/YYYYMMDD_HHMMSS/`，并设置 `REPORTS_RUN_DIR` 以便各服务共用。  

- 各轮输出文件命名约定：
  - Round 1：`portfolio_round1_*.md`。  
  - Round 2（组合用统一文本）：`round2_combined_*.md`（旧名 `combined_report_*.md` 仍保留兼容）。  
  - Round 3：`round3_decision_*.md`。  
  - Round 4：`round4_final_*.md`。  

- `--mode debate` 与 `--mode final_decision` 的跨目录查找逻辑：
  - 不再局限于最新时间戳目录，而是在 `reports/` 下使用 `glob("**/pattern")` 方式，跨所有子目录中选择**修改时间最新**的 Round1/Round2/Round3 报告作为输入，保证在多次运行后仍能正确对接最近一次完整四轮链路。  
  - Round3 输出会写回与 Round1 报告相同的目录，以保证同一批次的结果聚合在一起。

---

### 六、后续计划（概述）

- Round1 输入/输出强类型化（`PortfolioRound1Input` / `PortfolioRound1Result`）。  
- 第二轮单股分析的缓存与轻量微调机制（基于 `AnalysisHistory`）。  
- pipeline 中的动态仓位填充与展示（利用 `shares` + 实时行情填充 `runtime_position_pct`）。  
- Round1/3/4 Prompt 与输出 Schema 的进一步收紧，减少对自由文本的依赖。 

