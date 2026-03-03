# -*- coding: utf-8 -*-
"""
Tests for DebateService and DebateResult.
"""

from __future__ import annotations

from typing import Any, Dict

from src.analyzer import AnalysisResult
from src.services.debate_service import DebateService, DebateResult


def _make_base_result() -> AnalysisResult:
    return AnalysisResult(
        code="600519",
        name="贵州茅台",
        sentiment_score=80,
        trend_prediction="看多",
        operation_advice="买入",
        analysis_summary="测试用主分析摘要。",
    )


def _make_fake_llm_json() -> str:
    # 构造一个最小可用的 JSON 响应，模拟 LLM 输出
    return """
{
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "position_pct": 25.0,
  "position_bucket": "LIGHT",
  "position_comment": "当前是轻仓，仓位尚有提升空间。",
  "analysts": [
    {
      "id": "defensive",
      "name": "防守型分析师",
      "stance": "观望",
      "summary": "更在意回撤风险，建议暂不加仓。",
      "arguments": [
        "当前位置估值偏高",
        "短期涨幅较大，回调风险存在"
      ],
      "advice_for_current_position": "控制在轻仓，等待更好的性价比。",
      "comment_on_others": {
        "aggressive": "略显激进，需要注意回撤管理。"
      }
    }
  ],
  "consensus": {
    "summary": "整体偏多但不宜盲目加仓。",
    "action_advice": {
      "no_position": "可小仓试探，控制总仓位在两成以内。",
      "has_position": "保持轻仓，分批低吸，不追涨。"
    },
    "risk_points": [
      "短期涨幅较大",
      "估值已不便宜"
    ],
    "opportunity_points": [
      "品牌护城河稳固",
      "中长期消费升级逻辑仍在"
    ]
  }
}
"""


class _FakeAnalyzer:
    """Fake GeminiAnalyzer for unit tests."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    def is_available(self) -> bool:
        return True

    def run_custom_prompt(
        self,
        prompt: str,
        max_output_tokens: int,
        log_prefix: str = "",
    ) -> str:
        # 简单 sanity check：Prompt 应该包含标的名称和“当前仓位”这些关键词
        assert "贵州茅台" in prompt
        assert "当前仓位" in prompt
        return self._response_text


def test_run_debate_parses_llm_json_correctly() -> None:
    base_result = _make_base_result()
    fake_json = _make_fake_llm_json()

    service = DebateService(analyzer=_FakeAnalyzer(fake_json))
    debate = service.run_debate(base_result, position_pct=25.0)

    assert isinstance(debate, DebateResult)
    assert debate.stock_code == "600519"
    assert debate.stock_name == "贵州茅台"
    assert abs(debate.position_pct - 25.0) < 1e-6
    assert debate.analysts, "应至少有一位分析师观点"

    first = debate.analysts[0]
    assert first.id == "defensive"
    assert "观望" in first.stance or first.stance != ""
    assert any("估值" in arg or "回调" in arg for arg in first.arguments)
    assert "轻仓" in first.advice_for_current_position

    # 检查综合结论部分
    assert "整体偏多" in debate.consensus_summary
    assert "空仓" in debate.consensus_action_no_position
    assert "轻仓" in debate.consensus_action_has_position
    assert debate.consensus_risks
    assert debate.consensus_opportunities

    # Markdown 输出至少应包含标题和标的信息
    md = debate.to_markdown()
    assert "多风格分析师辩论" in md
    assert "贵州茅台 (600519)" in md


def test_run_debate_fallback_on_invalid_json() -> None:
    base_result = _make_base_result()

    class _BadAnalyzer:
        def is_available(self) -> bool:
            return True

        def run_custom_prompt(
            self,
            prompt: str,
            max_output_tokens: int,
            log_prefix: str = "",
        ) -> str:
            return "THIS IS NOT JSON"

    service = DebateService(analyzer=_BadAnalyzer())
    debate = service.run_debate(base_result, position_pct=0.0)

    # 解析失败时，DebateResult 仍然存在，但 analysts 为空，raw_text 保存原文
    assert isinstance(debate, DebateResult)
    assert debate.analysts == []
    assert debate.raw_text == "THIS IS NOT JSON"

    md = debate.to_markdown()
    # 降级时 Markdown 中应包含原始内容提示或原文本身
    assert "原始" in md or "辩论" in md

