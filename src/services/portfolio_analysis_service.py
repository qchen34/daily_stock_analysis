# -*- coding: utf-8 -*-
"""
第一轮：个人组合（Portfolio）总体分析服务。

职责：
1. 从 PortfolioSnapshot（以及可选的 GuruHoldingsContext）构造组合视角的 Prompt
2. 调用 GeminiAnalyzer.run_custom_prompt 执行一次 LLM 分析
3. 返回原始文本输出，后续可以逐步收紧为结构化 JSON
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from src.analyzer import GeminiAnalyzer
from src.core.position_profile import PortfolioSnapshot, HoldingPosition
from src.core.guru_profile import GuruHoldingsContext, GuruPortfolioSnapshot, GuruPosition
from src.services.portfolio_loader import Watchlist
from src.services.portfolio_account_service import PortfolioAccountPerformance, PortfolioAccountService


logger = logging.getLogger(__name__)


@dataclass
class PortfolioRound1Result:
    """
    第一轮输出结果。

    - raw_text: LLM 的原始输出（通常为 JSON 文本，解析失败时可直接查看）
    - 其余字段：在解析成功时填充结构化内容，用于后续 Markdown 渲染与多轮分析复用。
    """

    raw_text: str
    overview: Optional[dict] = None  # 组合整体概览（含风格、仓位评价、资金量档位等）
    risk_summary: Optional[List[str]] = None
    optimization_plan: Optional[List[str]] = None
    style_exposure: Optional[dict] = None
    per_symbol_notes: Optional[dict] = None  # 持仓标的的逐只备注
    watchlist_notes: Optional[dict] = None  # 观察名单标的的逐只备注
    meta: Optional[dict] = None

    def to_markdown(self) -> str:
        """
        将结构化结果转换为 Markdown 报告。

        若解析失败（overview 等字段为空），则直接返回 raw_text 以便调试 Prompt。
        """
        if not self.overview and not self.risk_summary and not self.optimization_plan:
            return self.raw_text

        lines: List[str] = []

        account = ""
        as_of = ""
        if isinstance(self.meta, dict):
            account = self.meta.get("account_name") or ""
            as_of = self.meta.get("as_of") or ""

        title = "组合第一轮分析报告"
        if account:
            title += f" - {account}"
        if as_of:
            title += f"（截至 {as_of}）"

        lines.append(f"# {title}")
        lines.append("")

        # 1. 组合整体概览
        if isinstance(self.overview, dict):
            lines.append("## 一、组合整体概览")
            style_summary = self.overview.get("style_summary") or ""
            position_comment = self.overview.get("position_comment") or ""
            capital_bucket = self.overview.get("capital_bucket") or ""
            capital_comment = self.overview.get("capital_bucket_comment") or ""
            sizing_pref = self.overview.get("sizing_preference_comment") or ""
            if style_summary:
                lines.append(f"- **风格总结**：{style_summary}")
            if position_comment:
                lines.append(f"- **仓位评价**：{position_comment}")
            if capital_bucket or capital_comment:
                label = {
                    "small": "小资金账户",
                    "medium": "中等资金账户",
                    "large": "大资金账户",
                }.get(str(capital_bucket).lower(), str(capital_bucket))
                if label:
                    lines.append(f"- **资金量档位**：{label}（{capital_comment}）")
                elif capital_comment:
                    lines.append(f"- **资金量点评**：{capital_comment}")
            if sizing_pref:
                lines.append(f"- **仓位配比偏好**：{sizing_pref}")
            lines.append("")

        # 2. 风险摘要
        if self.risk_summary:
            lines.append("## 二、需要关注的主要风险")
            for idx, r in enumerate(self.risk_summary, start=1):
                lines.append(f"{idx}. {r}")
            lines.append("")

        # 3. 优化建议
        if self.optimization_plan:
            lines.append("## 三、未来 3–6 个月的优化建议")
            for idx, idea in enumerate(self.optimization_plan, start=1):
                lines.append(f"{idx}. {idea}")
            lines.append("")

        # 4. 风格与集中度暴露
        if isinstance(self.style_exposure, dict) and self.style_exposure:
            lines.append("## 四、风格与集中度暴露")
            value_vs_growth = self.style_exposure.get("value_vs_growth") or ""
            conc = self.style_exposure.get("concentration_comment") or ""
            risk_budget = self.style_exposure.get("risk_budget_comment") or ""
            if value_vs_growth:
                lines.append(f"- **价值 vs 成长**：{value_vs_growth}")
            if conc:
                lines.append(f"- **集中度评价**：{conc}")
            if risk_budget:
                lines.append(f"- **风险预算使用情况**：{risk_budget}")
            lines.append("")

        # 5. 重点标的备注
        if isinstance(self.per_symbol_notes, dict) and self.per_symbol_notes:
            lines.append("## 五、重点标的备注（per_symbol_notes）")
            lines.append("")
            lines.append("| 代码 | 角色(role) | 风险(risk) | 操作提示(action_hint) |")
            lines.append("|------|------------|------------|------------------------|")
            for code, info in self.per_symbol_notes.items():
                if not isinstance(info, dict):
                    continue
                role = (info.get("role") or "").replace("\n", " ")
                risk = (info.get("risk") or "").replace("\n", " ")
                action = (info.get("action_hint") or "").replace("\n", " ")
                lines.append(f"| {code} | {role} | {risk} | {action} |")
            lines.append("")

        # 6. 观察名单重点标的（watchlist_notes）—— 仅在有结构化备注时展示
        if isinstance(self.watchlist_notes, dict) and self.watchlist_notes:
            lines.append("## 六、观察名单重点标的（watchlist_notes）")
            lines.append("")
            lines.append("| 代码 | 角色(role) | 关注理由(watch_reason) | 风险(risk) | 触发条件(trigger_hint) |")
            lines.append("|------|------------|------------------------|------------|------------------------|")
            for code, info in self.watchlist_notes.items():
                if not isinstance(info, dict):
                    continue
                role = (info.get("role") or "").replace("\n", " ")
                watch_reason = (info.get("watch_reason") or "").replace("\n", " ")
                risk = (info.get("risk") or "").replace("\n", " ")
                trigger = (info.get("trigger_hint") or "").replace("\n", " ")
                lines.append(f"| {code} | {role} | {watch_reason} | {risk} | {trigger} |")
            lines.append("")

        # 7. 免责声明
        lines.append("## 七、免责声明")
        lines.append(
            "本报告基于 AI 模型生成，可能存在理解偏差或事实错误，仅供学习与交流，不构成任何投资建议。"
            "实际投资决策请结合个人风险承受能力与专业意见谨慎判断。"
        )

        return "\n".join(lines)


@dataclass
class PortfolioRound1Input:
    """
    第一轮组合分析的标准化输入。

    - portfolio: 用户当前组合快照（必填）
    - watchlist: 观察名单（可选，用于补充「关注但未持仓」的上下文）
    - guru_context: 大佬持仓上下文（可选，用于风格对照）
    """

    portfolio: PortfolioSnapshot
    watchlist: Optional[Watchlist] = None
    guru_context: Optional[GuruHoldingsContext] = None


class PortfolioAnalysisService:
    """
    第一轮：基于个人组合的总体分析。
    """

    def __init__(self, analyzer: Optional[GeminiAnalyzer] = None):
        self._analyzer = analyzer or GeminiAnalyzer()

    def analyze_portfolio(
        self,
        portfolio: PortfolioSnapshot,
        *,
        guru_context: Optional[GuruHoldingsContext] = None,
        watchlist: Optional[Watchlist] = None,
    ) -> Optional[PortfolioRound1Result]:
        """
        对当前组合做一轮总体分析总结。

        - 输入：PortfolioSnapshot（必须），可选 GuruHoldingsContext
        - 输出：目前为一段 Markdown/纯文本，后续可以改为结构化 JSON
        """
        if not self._analyzer.is_available():
            logger.warning("LLM 分析器不可用，跳过组合第一轮分析")
            return None

        # 可选：加载账户绩效信息（如果数据库中已有快照）
        account_perf: Optional[PortfolioAccountPerformance] = None
        try:
            if portfolio.account_name:
                perf_service = PortfolioAccountService()
                account_perf = perf_service.get_performance_for_account(
                    account_name=portfolio.account_name,
                    days=365,
                )
        except Exception:
            logger.debug("加载账户绩效信息失败（已忽略）。", exc_info=True)

        prompt = self._build_prompt(
            portfolio=portfolio,
            guru_context=guru_context,
            watchlist=watchlist,
            account_performance=account_perf,
        )

        raw_text = self._analyzer.run_custom_prompt(
            prompt,
            max_output_tokens=2048,
            log_prefix="[组合第一轮分析]",
        )

        if not raw_text:
            return None

        result = PortfolioRound1Result(raw_text=raw_text)

        # 尝试解析 JSON，填充结构化字段
        try:
            data = self._parse_round1_json(raw_text)
            if data:
                result.overview = data.get("overview")
                result.risk_summary = data.get("risk_summary") or []
                result.optimization_plan = data.get("optimization_plan") or []
                result.style_exposure = data.get("style_exposure") or {}
                result.per_symbol_notes = data.get("per_symbol_notes") or {}
                result.watchlist_notes = data.get("watchlist_notes") or {}
                result.meta = data.get("meta") or {}
        except Exception:
            logger.warning("解析 Round1 JSON 失败，将仅保留 raw_text 用于调试。", exc_info=True)

        return result

    def _parse_round1_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        解析 Round1 的 JSON 输出。

        - 自动去除 ```json ``` 包裹
        - 使用 json_repair 修复常见格式问题
        """
        import json
        from json_repair import repair_json

        if not raw_text:
            return None

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            # 去掉可能的 markdown 代码块标记
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        try:
            repaired = repair_json(cleaned)
            data = json.loads(repaired)
            if not isinstance(data, dict):
                return None
            return data
        except Exception as exc:
            logger.warning("Round1 JSON 解析失败: %s", exc)
            return None

    def _build_prompt(
        self,
        *,
        portfolio: PortfolioSnapshot,
        guru_context: Optional[GuruHoldingsContext] = None,
        watchlist: Optional[Watchlist] = None,
        account_performance: Optional[PortfolioAccountPerformance] = None,
    ) -> str:
        """
        构造第一轮组合分析的 Prompt（强规范化版本）。

        - 使用表格形式展示账户信息、持仓列表与观察名单；
        - 明确要求输出固定 JSON Schema（PortfolioRound1Result），便于后续结构化解析。
        """
        lines: List[str] = []

        account = portfolio.account_name or "未命名账户"
        lines.append("你是一名专业的资产配置与风险管理顾问。")
        lines.append("下面是某位投资者的当前股票/ETF 组合、观察名单以及（可选）大佬持仓快照。")
        lines.append("你需要基于这些结构化信息，输出一个严格符合 Schema 的 JSON 结果，用于 Round1 组合分析。")
        lines.append("")

        # 账户与整体信息（表格）
        lines.append("## 账户与整体信息")
        lines.append("")
        lines.append("| 字段 | 数值 | 说明 |")
        lines.append("|------|------|------|")
        lines.append(f"| 账户名称 | {account} | 用户自定义账户别名 |")
        if portfolio.total_equity is not None:
            lines.append(
                f"| 披露的总资产 | {portfolio.total_equity:.2f} | 可能为静态配置，真实市值可与后续动态数据结合 |"
            )
        else:
            lines.append("| 披露的总资产 | 未配置 | 如为 0 或未配置，请仅做相对评估 |")
        lines.append("")

        # 账户历史绩效概览（若有）
        if account_performance:
            lines.append("## 账户历史绩效概览（基于数据库快照，如有）")
            lines.append("")
            lines.append("| 指标 | 数值 | 说明 |")
            lines.append("|------|------|------|")
            if account_performance.start_date and account_performance.end_date:
                lines.append(
                    f"| 观察区间 | {account_performance.start_date} ~ {account_performance.end_date} | 来自 portfolio_account_snapshots 表 |"
                )
            if account_performance.start_equity is not None and account_performance.end_equity is not None:
                lines.append(
                    f"| 起始/当前总资产 | {account_performance.start_equity:.2f} → {account_performance.end_equity:.2f} | 未必等于真实资产，仅供趋势参考 |"
                )
            if account_performance.total_return_pct is not None:
                lines.append(
                    f"| 区间总收益率 | {account_performance.total_return_pct:.2f}% | 基于起始/当前总资产粗略估算 |"
                )
            if account_performance.max_drawdown_pct is not None:
                lines.append(
                    f"| 最大回撤 | {account_performance.max_drawdown_pct:.2f}% | 仅基于总资产曲线的粗略计算 |"
                )
            lines.append(
                f"| 快照数量 | {account_performance.snapshot_count} | 越多越有利于评估长期绩效和风险 |"
            )
            lines.append("")

        # 当前持仓列表（表格）
        lines.append("## 当前持仓列表（来自 user_portfolio.json 的静态快照）")
        lines.append("")
        if not portfolio.positions:
            lines.append("当前未持有任何标的。")
        else:
            lines.append("| 代码 | 名称 | 静态仓位% | 股数 | 成本价 | 备注 |")
            lines.append("|------|------|----------|------|--------|------|")
            for code, pos in portfolio.positions.items():
                name = pos.name or code
                cost = f"{pos.cost_price:.2f}" if pos.cost_price is not None else "未知"
                shares = "未知"
                if hasattr(pos, "shares"):
                    val = getattr(pos, "shares", None)
                    shares = f"{val:.2f}" if val is not None else "未知"
                static_pct = f"{pos.position_pct:.1f}%" if pos.position_pct else "未配置"
                note = (pos.notes or "").replace("\n", " ")
                lines.append(
                    f"| {code} | {name} | {static_pct} | {shares} | {cost} | {note} |"
                )
        lines.append("")

        # 观察名单（watchlist）
        lines.append("## 观察名单（watchlist.json）")
        lines.append("")
        if not watchlist or not watchlist.items:
            lines.append("当前未配置观察名单。")
        else:
            lines.append("| 代码 | 名称 | 标签(tags) | 备注 |")
            lines.append("|------|------|------------|------|")
            for item in watchlist.items:
                tags = ", ".join(item.tags) if item.tags else ""
                notes = (item.notes or "").replace("\n", " ")
                name = item.name or item.code
                lines.append(f"| {item.code} | {name} | {tags} | {notes} |")
        lines.append("")
        lines.append(
            "在后续分析中，请特别注意：观察名单中的标的是“重要关注但暂未持仓或持仓较轻”的标的，"
            "你需要在整体风格判断和 per_symbol_notes 中显式体现这些标的的角色与风险/机会。"
        )
        lines.append(
            "标签(tags) 字段可以直接用于判断标的是偏价值/成长、偏单一企业逻辑还是宏观/行业/主题逻辑，"
            "并用来辅助给出 style_exposure 与 risk_summary 中的集中度和主题暴露评价。"
        )
        lines.append("")

        # 可选：大佬组合的整体印象
        if guru_context and guru_context.portfolios:
            lines.append("## 大佬组合快照（用于风格对照）")
            lines.append("")
            for snap in guru_context.portfolios:
                assert isinstance(snap, GuruPortfolioSnapshot)
                lines.append(
                    f"- 大佬：{snap.guru_name} | 风格：{snap.style_tagline or '未注明'} | as_of={snap.as_of or '未知'}"
                )
                if not snap.positions:
                    continue
                top_codes = list(snap.positions.keys())[:5]
                brief_list = []
                for c in top_codes:
                    p: GuruPosition = snap.positions[c]
                    brief_list.append(f"{p.name or c}({c}) 权重约 {p.weight_pct:.1f}%")
                if brief_list:
                    lines.append(f"  - 代表性持仓：{'; '.join(brief_list)}")
            lines.append("")
            lines.append(
                "在分析时，请用一句话概括各位大佬的典型风格（如价值型/高成长/趋势跟随等），"
                "并在 style_exposure 中用他们的组合作为对照，判断本账户的风格是否与某位大佬高度重合、部分借鉴，"
                "还是风格分散。"
            )
            lines.append(
                "当 per_symbol_notes 中的标的同时出现在大佬组合里时，请在该标的 role 或 action_hint 中简要提及这一点，"
                "例如“同时为某某大佬核心持仓，但需结合个人风险承受能力谨慎控制仓位”。"
            )
            lines.append("")

        # 输出 JSON Schema 约定
        lines.append("## 输出格式要求：PortfolioRound1Result JSON")
        lines.append("")
        lines.append(
            "请严格按照以下 JSON Schema 输出一个对象，不要输出任何额外的自然语言说明或 Markdown 标题："
        )
        lines.append("")
        lines.append("```json")
        lines.append("{")
        lines.append('  "overview": {')
        lines.append('    "style_summary": "用 2-4 句话概括当前组合整体风格、进攻/防守倾向",')
        lines.append('    "position_comment": "对当前整体仓位高低及是否适合当前市况的评价（可以基于静态信息做合理推断）",')
        lines.append('    "capital_bucket": "small/medium/large 等资金量档位，基于总资产与标的规模做合理推断",')
        lines.append('    "capital_bucket_comment": "一句话解释该档位账户在风险承受/分散化上的特点",')
        lines.append('    "sizing_preference_comment": "结合账户资金量与组合特征，给出推荐的仓位配比偏好（例如小资金适合集中 3-5 只，大资金需适度分散等）"')
        lines.append("  },")
        lines.append('  "risk_summary": [')
        lines.append('    "风险点1：...",')
        lines.append('    "风险点2：..."')
        lines.append("  ],")
        lines.append('  "optimization_plan": [')
        lines.append('    "优化建议1：...",')
        lines.append('    "优化建议2：..."')
        lines.append("  ],")
        lines.append('  "style_exposure": {')
        lines.append('    "value_vs_growth": "例如：偏成长/偏价值/较均衡，并给出简单理由",')
        lines.append('    "concentration_comment": "对个股/行业集中度的评价",')
        lines.append('    "risk_budget_comment": "对组合风险预算使用情况的大致判断"')
        lines.append("  },")
        lines.append('  "per_symbol_notes": {')
        lines.append('    "AAPL": {')
        lines.append('      "role": "例如：核心底仓/卫星仓/战术仓位/观察标的",')
        lines.append('      "risk": "该标的最需要关注的 1-2 条风险",')
        lines.append('      "action_hint": "在未来 3-6 个月的大致操作思路（如：维持、适度减仓、观察加仓条件等）"')
        lines.append("    },")
        lines.append('    "VTI": {')
        lines.append('      "role": "...",')
        lines.append('      "risk": "...",')
        lines.append('      "action_hint": "..."')
        lines.append("    }")
        lines.append("  },")
        lines.append('  "watchlist_notes": {')
        lines.append('    "TSLA": {')
        lines.append('      "role": "例如：高波动观察标的/潜在进攻仓位",')
        lines.append('      "watch_reason": "关注理由（可结合 watchlist.tags 和 notes，例如 AI/Auto 主题）",')
        lines.append('      "risk": "该标的最需要关注的 1-2 条风险",')
        lines.append('      "trigger_hint": "观察/建仓触发条件（如估值回落、确认某类财报、趋势转强等）"')
        lines.append("    }")
        lines.append("  },")
        lines.append('  "meta": {')
        lines.append('    "account_name": "账户名称（如上表）",')
        lines.append('    "as_of": "组合快照日期（如 user_portfolio.json.as_of）"')
        lines.append("  }")
        lines.append("}")
        lines.append("```")
        lines.append("")
        lines.append("请只输出上述 JSON 对象本身，不要包含反引号、Markdown 标题或额外解释。")

        return "\n".join(lines)