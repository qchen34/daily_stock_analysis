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

- **多分析师辩论模块 - 第一阶段落地**  
  - 在 `src/analyzer.py` 中为 `GeminiAnalyzer` 增加了通用调用方法 `run_custom_prompt()`，可以在不走内置 SYSTEM_PROMPT 的前提下，复用现有的重试与降级逻辑执行自定义 Prompt（后续多角色辩论等扩展能力统一走这一入口）。  
  - 新建 `src/services/debate_service.py`：实现 `DebateService` / `DebateResult` / `DebateAnalystView`，支持基于已有 `AnalysisResult` + 当前标的仓位百分比构造专用 Prompt，调用 LLM 完成多分析师辩论，并输出结构化结果与 `to_markdown()`。  
  - 新增 `debate_test_script.py`：提供一个独立的可行性测试脚本，从数据库中读取最近一次分析历史记录，还原 `AnalysisResult`，调用 `DebateService.run_debate()`，并把 `## 多风格分析师辩论` 章节的 Markdown 打印到终端及保存到 `reports/debate_*.md`，方便离线调试与 Prompt 迭代。

## 后续实现计划（按推荐顺序）

1. **多分析师辩论服务层（集成与迭代阶段）**  
   - 基于当前已实现的 `DebateService`：  
     - 补充与 `PortfolioSnapshot` 的集成入口（例如从 WebUI 或配置中注入当前组合快照，再在调用 `DebateService` 时自动获取 `position_pct`）。  
     - 根据实际调用效果继续打磨辩论 Prompt：包括角色说话风格、互评深度、综合结论的结构等。  
     - 如需要，对 `DebateResult` 的字段做小幅调整，使其与个股 Markdown 报告的拼接更自然。

2. **在报告生成流程中挂接辩论模块（只针对个股报告）**  
   - 在个股分析结果生成 Markdown 的位置（例如 `NotificationService` 中与个股报告相关的 formatter，或 `core/pipeline` 汇总代码）引入一个可选步骤：  
     - 当配置 `ENABLE_DEBATE_MODULE=true` 时：  
       - 根据当前标的代码从 `PortfolioSnapshot` 拿到仓位信息。  
       - 调用 `DebateService` 生成辩论 Markdown，并在个股报告末尾追加一个章节：`## 多风格分析师辩论`。  
     - 当开关关闭时，保持现有输出不变。

3. **为辩论模块添加单元测试**  
   - 新建 `tests/test_debate_service.py`：  
     - 用假 `AnalysisResult` 和假 `PortfolioSnapshot` 构造场景，mock 掉真实 LLM 调用。  
     - 验证：Prompt 中包含分析师人设与仓位描述；解析逻辑能正确得到 `DebateResult` 并输出预期的 Markdown 结构。

4. **逐步优化 Prompt 与仓位使用策略**  
   - 根据实际调用效果调优：  
     - 分析师角色数量与风格描述。  
     - 仓位分档的阈值与文字描述。  
     - 辩论结果中对空仓者/持仓者的差异化建议（例如针对轻仓/重仓给出不同目标仓位与操作节奏）。  
   - 如有需要，再考虑将主分析与辩论合并为一次 LLM 调用，以降低总 token 成本。

