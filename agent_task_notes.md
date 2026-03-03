## 已完成的优化内容（截至当前）

- **Gemini 调用 token 统计**  
  - 在 `src/analyzer.py` 中为 `GeminiAnalyzer` 增加了 Prompt 预估 token 数（`count_tokens`）和实际调用返回的 `usage_metadata` 日志输出，终端日志中可以看到每次调用的 prompt/output/total token 数。

- **多风格分析师角色定义**  
  - 新增 `src/core/debate_profile.py`：定义了仓位分档枚举 `PositionBucket`、工具函数 `bucket_position`，以及 4 类虚拟分析师角色（防守型、进攻型、技术派、基本面派），并提供 `to_prompt_block()` 便于在 Prompt 中嵌入人设说明。

- **个人持仓模型与示例**  
  - 新增 `src/core/position_profile.py`：定义 `HoldingPosition`（单标的持仓）和 `PortfolioSnapshot`（组合快照），以及工具函数：  
    - `get_position_for_code` / `get_position_pct_for_code`：按代码查找仓位。  
    - `describe_position_bucket`：把精确仓位映射为仓位档位（空仓/轻仓/中仓/重仓）+ 一句中文描述。  
  - 新增 `debug_position_profile.py`：构造示例组合并在终端打印每个标的的仓位分档和描述，用于快速验证持仓模型逻辑。

- **Telegram 与代理调试（流程层面）**  
  - 明确了 `.env` 中 `USE_PROXY/PROXY_HOST/PROXY_PORT` 与系统/Clash 代理的关系，并通过临时脚本验证 Telegram `chat_id` 和代理是否生效（这些脚本本身不再修改）。

- **多风格分析师辩论服务层（基础版 + 上下文扩展）**  
  - 新增 `src/services/debate_service.py`：  
    - 定义 `DebateAnalystView` / `DebateResult`，封装多位虚拟分析师的观点、互评与综合结论，并通过 `to_markdown()` 生成可直接拼接到报告的 Markdown 段落。  
    - `DebateService.run_debate(base_result, position_pct, guru_context)`：  
      - 基于已有 `AnalysisResult`、个人仓位百分比和大佬持仓上下文构造多角色辩论 Prompt；  
      - 调用 `GeminiAnalyzer.run_custom_prompt`；  
      - 解析模型返回的 JSON，填充 `DebateResult`。  
    - Prompt 中已经显式注入：  
      - 当前标的与用户仓位（轻仓/中仓/重仓 + 具体百分比）；  
      - （可选）多个大佬在该标的上的权重、加减仓动作及逻辑摘要。

- **主流程集成 JSON 驱动的个人持仓 + 大佬持仓**  
  - 在 `src/core/position_profile.py` / `src/core/guru_profile.py` 基础上，通过 `user_portfolio.json` 和 `guru_holdings.json` 定义结构化输入：  
    - `user_portfolio.json`：描述个人账户名、总资产、每只股票的 `position_pct`、成本价与备注。  
    - `guru_holdings.json`：描述多位大佬组合快照（`GuruPortfolioSnapshot`），包括每个标的的权重、最近动作、仓位变化与投资逻辑。  
  - 在 `StockAnalysisPipeline` 中：  
    - 在初始化时加载上述 JSON，构造 `PortfolioSnapshot` 和 `GuruHoldingsContext` 并挂在 `self.user_portfolio` / `self.guru_context`。  
    - 在单股即时推送路径中：  
      - 用 `get_position_pct_for_code(self.user_portfolio, code)` 推导当前标的仓位；  
      - 调用 `DebateService.run_debate(result, position_pct=..., guru_context=self.guru_context)`，并将 `debate.to_markdown()` 追加到单股报告后部。  
    - 日志中可见加载结果与实际用于辩论的仓位值，例如：  
      `已加载用户组合快照（X 个标的）用于辩论模块。`  
      `已加载 Y 位大佬持仓用于辩论模块。`  
      `[PDD] 已附加多风格分析师辩论模块（仓位=20.0%）`。

## 后续实现计划（按推荐顺序）

1. **第二轮单股分析的缓存与轻量微调（降低 token 成本）**  
   - 基于 `AnalysisHistory` 为第二轮单股分析增加缓存层：  
     - 在 `AnalysisRepository` 中增加 `get_latest_for_code` 方法，用于按股票代码获取最近一次分析记录。  
     - 在 `StockAnalysisPipeline.analyze_stock` 中优先尝试从缓存还原 `AnalysisResult`，满足“时间/价格/新闻变动阈值”时才重跑完整大模型。  
   - 设计轻量 Prompt，用于在复用历史结果的基础上做“行情/新闻微调建议”，而不是每次都跑完整第二轮分析。

2. **在 pipeline 中真正利用动态持仓信息**  
   - 使用 `HoldingPosition.shares` + 实时行情，计算 `runtime_price` / `runtime_market_value` / `runtime_position_pct` 并填充到 `PortfolioSnapshot` 中。  
   - 在第一轮、第三轮、第四轮的 Prompt 中，优先使用 `runtime_position_pct` 展示真实仓位结构，而不是依赖静态 `position_pct`。  
   - 在日志与报告中增加一处“组合动态仓位概览”，便于肉眼校验持仓权重是否正确。

3. **进一步收紧四轮 Prompt 的结构化输出**  
   - 为第一/三/四轮设计清晰的 JSON Schema（例如 `user_portfolio_summary`、`guru_insights_summary`、`target_total_position_pct` 等），并在服务层解析为 dataclass。  
   - 在第四轮（终稿）中优先使用这些结构化字段，而不是完全依赖自由文本，从而便于后续与回测/风控模块联动。

4. **汇总日报中可选集成多风格辩论与组合四轮结论**  
   - 当前多风格辩论仅在单股即时推送路径和组合第四轮中使用，汇总日报（`_send_notifications` + `generate_dashboard_report`）暂未集成这些结论。  
   - 后续可以考虑在日报末尾增加一个“附录：重点标的大佬+多风格辩论/组合结论摘要”小节：  
     - 只对评分最高或关注度最高的 N 只股票附加精简版辩论与组合结论（例如每只 3–5 行）。  
     - 通过配置项（例如 `DEBATE_APPEND_TO_DAILY_REPORT=true`、`PORTFOLIO_ROUNDS_APPEND_TO_DAILY=true`）控制是否启用，以平衡可读性与长度。