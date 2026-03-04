# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 主调度程序
===================================

职责：
1. 协调各模块完成股票分析流程
2. 实现低并发的线程池调度
3. 全局异常处理，确保单股失败不影响整体
4. 提供命令行入口

使用方式：
    python main.py              # 正常运行
    python main.py --debug      # 调试模式
    python main.py --dry-run    # 仅获取数据不分析

交易理念（已融入分析）：
- 严进策略：不追高，乖离率 > 5% 不买入
- 趋势交易：只做 MA5>MA10>MA20 多头排列
- 效率优先：关注筹码集中度好的股票
- 买点偏好：缩量回踩 MA5/MA10 支撑
"""
import os
from src.config import setup_env
setup_env()

# 代理配置 - 通过 USE_PROXY 环境变量控制，默认关闭
# GitHub Actions 环境自动跳过代理配置
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "true").lower() == "true":
    # 本地开发环境，启用代理（可在 .env 中配置 PROXY_HOST 和 PROXY_PORT）
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "7897")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from src.core.pipeline import StockAnalysisPipeline
from src.core.market_review import run_market_review
from src.notification import NotificationService

from src.config import get_config, Config
from src.logging_config import setup_logging
from src.services.portfolio_analysis_service import PortfolioAnalysisService
from src.services.portfolio_decision_service import PortfolioDecisionService
from src.services.portfolio_debate_service import PortfolioDebateService


logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='A股自选股智能分析系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常运行
  python main.py --debug            # 调试模式
  python main.py --dry-run          # 仅获取数据，不进行 AI 分析
  python main.py --stocks 600519,000001  # 指定分析特定股票
  python main.py --no-notify        # 不发送推送通知
  python main.py --single-notify    # 启用单股推送模式（每分析完一只立即推送）
  python main.py --schedule         # 启用定时任务模式
  python main.py --market-review    # 仅运行大盘复盘
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式，输出详细日志'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅获取数据，不进行 AI 分析'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要分析的股票代码，逗号分隔（覆盖配置文件）'
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不发送推送通知'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='启用单股推送模式：每分析完一只股票立即推送，而不是汇总推送'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='并发线程数（默认使用配置值）'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='启用定时任务模式，每日定时执行'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='定时任务启动时不立即执行一次'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='仅运行大盘复盘分析'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳过大盘复盘分析'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='启动 Web 管理界面'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='仅启动 Web 服务，不执行自动分析'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='启动 FastAPI 后端服务（同时执行分析任务）'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='仅启动 FastAPI 后端服务，不自动执行分析'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='FastAPI 服务端口（默认 8000）'
    )

    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='FastAPI 服务监听地址（默认 0.0.0.0）'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='不保存分析上下文快照'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='运行回测（对历史分析结果进行评估）'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='仅回测指定股票代码'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='回测评估窗口（交易日数，默认使用配置）'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='强制回测（即使已有回测结果也重新计算）'
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['full', 'portfolio', 'stock', 'debate', 'final_decision'],
        default='full',
        help='运行模式：full=完整流程；portfolio=仅第一轮组合分析；stock=仅第二轮个股+大盘分析；debate=仅第三轮综合决策；final_decision=仅第四轮最终执行指南'
    )

    return parser.parse_args()


def _create_reports_run_dir() -> Tuple[Path, str]:
    """
    为当前运行创建/获取 reports 子目录，并设置 REPORTS_RUN_DIR。
    返回 (reports_dir, run_ts)。
    """
    reports_root = Path(__file__).parent / "reports"
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = reports_root / run_ts
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["REPORTS_RUN_DIR"] = str(run_dir)
    logger.info(f"本次运行的报告目录: {run_dir}")
    return run_dir, run_ts


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None
):
    """
    执行完整的分析流程（个股 + 大盘复盘）
    
    这是定时任务调用的主函数（完整 second-round 流程）
    """
    try:
        # 为本次运行创建 reports 子目录，便于归档与后续调用
        run_dir, run_ts = _create_reports_run_dir()

        # 命令行参数 --single-notify 覆盖配置（#55）
        if getattr(args, 'single_notify', False):
            config.single_stock_notify = True

        # Issue #190: 个股与大盘复盘合并推送
        merge_notification = (
            getattr(config, 'merge_email_notification', False)
            and config.market_review_enabled
            and not getattr(args, 'no_market_review', False)
            and not config.single_stock_notify
        )

        # 创建调度器
        save_context_snapshot = None
        if getattr(args, 'no_context_snapshot', False):
            save_context_snapshot = False
        query_id = uuid.uuid4().hex
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers,
            query_id=query_id,
            query_source="cli",
            save_context_snapshot=save_context_snapshot
        )

        # 解析第二轮要分析的股票列表：
        # 优先级：命令行 --stocks > USE_PORTFOLIO_STOCK_LIST=true 时从 user_portfolio.json 中提取 > .env 中的 STOCK_LIST（由 Config 管理）
        run_stock_codes = stock_codes
        if run_stock_codes is None and getattr(config, "use_portfolio_stock_list", False):
            if pipeline.user_portfolio and pipeline.user_portfolio.positions:
                run_stock_codes = list(pipeline.user_portfolio.positions.keys())
                logger.info("使用 user_portfolio.json 中的股票列表作为第二轮分析输入: %s", ", ".join(run_stock_codes))
            else:
                logger.warning("配置了 USE_PORTFOLIO_STOCK_LIST=true，但未能从 user_portfolio.json 加载到有效持仓，将回退到 STOCK_LIST。")

        # 1. 运行个股分析
        results = pipeline.run(
            stock_codes=run_stock_codes,
            dry_run=args.dry_run,
            send_notification=not args.no_notify,
            merge_notification=merge_notification
        )

        # Issue #128: 分析间隔 - 在个股分析和大盘分析之间添加延迟
        analysis_delay = getattr(config, 'analysis_delay', 0)
        if analysis_delay > 0 and config.market_review_enabled and not args.no_market_review:
            logger.info(f"等待 {analysis_delay} 秒后执行大盘复盘（避免API限流）...")
            time.sleep(analysis_delay)

        # 2. 运行大盘复盘（如果启用且不是仅个股模式）
        market_report = ""
        if config.market_review_enabled and not args.no_market_review:
            # 只调用一次，并获取结果
            review_result = run_market_review(
                notifier=pipeline.notifier,
                analyzer=pipeline.analyzer,
                search_service=pipeline.search_service,
                send_notification=not args.no_notify,
                merge_notification=merge_notification
            )
            # 如果有结果，赋值给 market_report 用于后续飞书文档生成
            if review_result:
                market_report = review_result

        # Issue #190: 合并推送（个股+大盘复盘）
        if merge_notification and (results or market_report) and not args.no_notify:
            parts = []
            if market_report:
                parts.append(f"# 📈 大盘复盘\n\n{market_report}")
            if results:
                dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                parts.append(f"# 🚀 个股决策仪表盘\n\n{dashboard_content}")
            if parts:
                combined_content = "\n\n---\n\n".join(parts)

                # 当未开启组合四轮模式时，沿用原有合并推送逻辑
                if not getattr(config, "enable_portfolio_rounds", False):
                    if pipeline.notifier.is_available():
                        if pipeline.notifier.send(combined_content, email_send_to_all=True):
                            logger.info("已合并推送（个股+大盘复盘）")
                        else:
                            logger.warning("合并推送失败")
                else:
                    logger.info("已启用组合四轮模式：跳过第二轮合并推送，由第四轮终稿统一推送。")

        # 输出摘要
        if results:
            logger.info("\n===== 分析结果摘要 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.trend_prediction}"
                )

        logger.info("\n任务执行完成")

        # === 新增：生成飞书云文档 ===
        try:
            from src.feishu_doc import FeishuDocManager

            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("正在创建飞书云文档...")

                # 1. 准备标题 "01-01 13:01大盘复盘"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 大盘复盘"

                # 2. 准备内容 (拼接个股分析和大盘复盘)
                full_content = ""

                # 添加大盘复盘内容（如果有）
                if market_report:
                    full_content += f"# 📈 大盘复盘\n\n{market_report}\n\n---\n\n"

                # 添加个股决策仪表盘（使用 NotificationService 生成）
                if results:
                    dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                    full_content += f"# 🚀 个股决策仪表盘\n\n{dashboard_content}"

                # 3. 创建文档
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"飞书云文档创建成功: {doc_url}")
                    # 可选：将文档链接也推送到群里
                    if not args.no_notify:
                        pipeline.notifier.send(f"[{now.strftime('%Y-%m-%d %H:%M')}] 复盘文档创建成功: {doc_url}")

        except Exception as e:
            logger.error(f"飞书文档生成失败: {e}")

        # === Auto backtest ===
        try:
            if getattr(config, 'backtest_enabled', True):
                from src.services.backtest_service import BacktestService
        
                logger.info("开始自动回测...")
                service = BacktestService()
                stats = service.run_backtest(
                    force=False,
                    eval_window_days=getattr(config, 'backtest_eval_window_days', 10),
                    min_age_days=getattr(config, 'backtest_min_age_days', 14),
                    limit=200,
                )
                logger.info(
                    f"自动回测完成: processed={stats.get('processed')} saved={stats.get('saved')} "
                    f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
                )
        except Exception as e:
            logger.warning(f"自动回测失败（已忽略）: {e}")

        # 组合四轮分析集成已改为通过 --mode 显式控制，这里不再自动执行。

    except Exception as e:
        logger.exception(f"分析流程执行失败: {e}")


def start_api_server(host: str, port: int, config: Config) -> None:
    """
    在后台线程启动 FastAPI 服务
    
    Args:
        host: 监听地址
        port: 监听端口
        config: 配置对象
    """
    import threading
    import uvicorn

    def run_server():
        level_name = (config.log_level or "INFO").lower()
        uvicorn.run(
            "api.app:app",
            host=host,
            port=port,
            log_level=level_name,
            log_config=None,
        )

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info(f"FastAPI 服务已启动: http://{host}:{port}")


def start_bot_stream_clients(config: Config) -> None:
    """Start bot stream clients when enabled in config."""
    # 启动钉钉 Stream 客户端
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Dingtalk Stream client: {exc}")

    # 启动飞书 Stream 客户端
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Feishu Stream client: {exc}")


def main() -> int:
    """
    主入口函数

    Returns:
        退出码（0 表示成功）
    """
    # 解析命令行参数
    args = parse_arguments()

    # 加载配置（在设置日志前加载，以获取日志目录）
    config = get_config()

    # 配置日志（输出到控制台和文件）
    setup_logging(log_prefix="stock_analysis", debug=args.debug, log_dir=config.log_dir)

    logger.info("=" * 60)
    logger.info("A股自选股智能分析系统 启动")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 验证配置
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    # 解析股票列表（仅在 full / stock 模式中使用）
    stock_codes: Optional[List[str]] = None
    if getattr(args, "stocks", None):
        stock_codes = [code.strip() for code in args.stocks.split(',') if code.strip()]
        logger.info(f"使用命令行指定的股票列表: {stock_codes}")

    mode = getattr(args, "mode", "full")

    # === 模式：仅第一轮组合分析 ===
    if mode == "portfolio":
        try:
            reports_dir, _ = _create_reports_run_dir()

            # 复用 Pipeline 加载 user_portfolio / guru_context 与 analyzer、notifier
            pipeline = StockAnalysisPipeline(
                config=config,
                max_workers=args.workers,
                query_id=uuid.uuid4().hex,
                query_source="cli-portfolio",
                save_context_snapshot=False,
            )

            if pipeline.user_portfolio is None:
                logger.error("未加载 user_portfolio（缺少 user_portfolio.json 或解析失败），无法执行第一轮组合分析。")
                return 1

            service = PortfolioAnalysisService(analyzer=pipeline.analyzer)
            round1 = service.analyze_portfolio(
                portfolio=pipeline.user_portfolio,
                guru_context=pipeline.guru_context,
            )
            if not round1:
                logger.error("第一轮组合分析服务未返回结果，请检查 LLM 配置。")
                return 1

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = reports_dir / f"portfolio_round1_{ts}.md"
            out_path.write_text(round1.raw_text, encoding="utf-8")
            logger.info("第一轮组合分析已保存到: %s", out_path)

            if not args.no_notify and pipeline.notifier.is_available():
                if pipeline.notifier.send_to_telegram(round1.raw_text):
                    logger.info("第一轮组合分析报告已发送到 Telegram。")
                else:
                    logger.warning("第一轮组合分析报告发送到 Telegram 失败。")

            return 0
        except Exception as e:
            logger.exception(f"组合第一轮分析执行失败: {e}")
            return 1

    # === 模式：仅第三轮综合决策 ===
    if mode == "debate":
        try:
            reports_root = Path(__file__).parent / "reports"
            if not reports_root.exists():
                logger.error("reports 目录不存在，无法查找历史第一/二轮报告。")
                return 1

            # 第一轮输入
            round1_files = list(reports_root.glob("**/portfolio_round1_*.md"))
            if not round1_files:
                logger.error("在 %s 下未找到任何 portfolio_round1_*.md，请先运行 --mode portfolio。", reports_root)
                return 1
            round1_path = max(round1_files, key=lambda p: p.stat().st_mtime)

            # 第二轮输入：优先 round2_combined_*.md，其次 combined_report_*.md / report_*.md
            candidates = (
                list(reports_root.glob("**/round2_combined_*.md"))
                or list(reports_root.glob("**/combined_report_*.md"))
                or list(reports_root.glob("**/report_*.md"))
            )
            if not candidates:
                logger.error("在 %s 下未找到 round2_combined_*.md / combined_report_*.md / report_*.md。", reports_root)
                return 1
            round2_path = max(candidates, key=lambda p: p.stat().st_mtime)

            round1_text = round1_path.read_text(encoding="utf-8")
            round2_text = round2_path.read_text(encoding="utf-8")

            service = PortfolioDecisionService()
            result = service.synthesize_decision(
                portfolio_round1_text=round1_text,
                round2_report_text=round2_text,
            )
            if not result:
                logger.error("第三轮综合决策服务未返回结果，请检查 LLM 配置。")
                return 1

            # 将第三轮输出写回与第一轮报告相同的目录，保持同一批次聚合
            reports_dir = round1_path.parent
            reports_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = reports_dir / f"round3_decision_{ts}.md"
            out_path.write_text(result.raw_text, encoding="utf-8")
            logger.info("第三轮综合决策报告已保存到: %s", out_path)

            notifier = NotificationService()
            if not args.no_notify and notifier.is_available():
                if notifier.send_to_telegram(result.raw_text):
                    logger.info("第三轮综合决策报告已发送到 Telegram。")
                else:
                    logger.warning("第三轮综合决策报告发送到 Telegram 失败。")

            return 0
        except Exception as e:
            logger.exception(f"组合第三轮决策执行失败: {e}")
            return 1

    # === 模式：仅第四轮最终执行指南 ===
    if mode == "final_decision":
        try:
            reports_root = Path(__file__).parent / "reports"
            if reports_root.exists():
                subdirs = [p for p in reports_root.iterdir() if p.is_dir()]
                if subdirs:
                    reports_dir = max(subdirs, key=lambda p: p.stat().st_mtime)
                else:
                    reports_dir = reports_root
            else:
                logger.error("reports 目录不存在，无法查找历史多轮报告。")
                return 1

            # 第一轮
            round1_files = list(reports_dir.glob("portfolio_round1_*.md"))
            if not round1_files:
                logger.error("在 %s 下未找到 portfolio_round1_*.md，请先运行 --mode portfolio。", reports_dir)
                return 1
            round1_path = max(round1_files, key=lambda p: p.stat().st_mtime)

            # 第二轮
            round2_candidates = (
                list(reports_dir.glob("round2_combined_*.md"))
                or list(reports_dir.glob("combined_report_*.md"))
                or list(reports_dir.glob("report_*.md"))
            )
            if not round2_candidates:
                logger.error("在 %s 下未找到 round2_combined_*.md / combined_report_*.md / report_*.md。", reports_dir)
                return 1
            round2_path = max(round2_candidates, key=lambda p: p.stat().st_mtime)

            # 第三轮
            round3_files = list(reports_dir.glob("round3_decision_*.md"))
            if not round3_files:
                logger.error("在 %s 下未找到 round3_decision_*.md，请先运行 --mode debate。", reports_dir)
                return 1
            round3_path = max(round3_files, key=lambda p: p.stat().st_mtime)

            round1_text = round1_path.read_text(encoding="utf-8")
            round2_text = round2_path.read_text(encoding="utf-8")
            round3_text = round3_path.read_text(encoding="utf-8")

            service = PortfolioDebateService()
            result = service.debate_decision(
                round1_text=round1_text,
                round2_text=round2_text,
                round3_text=round3_text,
            )
            if not result:
                logger.error("第四轮最终执行指南服务未返回结果，请检查 LLM 配置。")
                return 1

            reports_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = reports_dir / f"round4_final_{ts}.md"
            out_path.write_text(result.raw_text, encoding="utf-8")
            logger.info("第四轮最终执行报告已保存到: %s", out_path)

            notifier = NotificationService()
            if not args.no_notify and notifier.is_available():
                if notifier.send_to_telegram(result.raw_text):
                    logger.info("第四轮最终执行报告已发送到 Telegram。")
                else:
                    logger.warning("第四轮最终执行报告发送到 Telegram 失败。")

            return 0
        except Exception as e:
            logger.exception(f"组合第四轮终稿执行失败: {e}")
            return 1

    # 其余情况：mode == "full" 或 mode == "stock"，走原有完整流程
    # 对于 mode == "stock"，强制关闭个股报告中的辩论模块（只保留第二轮分析）
    if mode == "stock":
        config.enable_debate_module = False

    # === 处理 --webui / --webui-only 参数，映射到 --serve / --serve-only ===
    if args.webui:
        args.serve = True
    if args.webui_only:
        args.serve_only = True

    # 兼容旧版 WEBUI_ENABLED 环境变量
    if config.webui_enabled and not (args.serve or args.serve_only):
        args.serve = True

    # === 启动 Web 服务 (如果启用) ===
    start_serve = (args.serve or args.serve_only) and os.getenv("GITHUB_ACTIONS") != "true"

    # 兼容旧版 WEBUI_HOST/WEBUI_PORT：如果用户未通过 --host/--port 指定，则使用旧变量
    if start_serve:
        if args.host == '0.0.0.0' and os.getenv('WEBUI_HOST'):
            args.host = os.getenv('WEBUI_HOST')
        if args.port == 8000 and os.getenv('WEBUI_PORT'):
            args.port = int(os.getenv('WEBUI_PORT'))

    bot_clients_started = False
    if start_serve:
        try:
            start_api_server(host=args.host, port=args.port, config=config)
            bot_clients_started = True
        except Exception as e:
            logger.error(f"启动 FastAPI 服务失败: {e}")

    if bot_clients_started:
        start_bot_stream_clients(config)

    # === 仅 Web 服务模式：不自动执行分析 ===
    if args.serve_only:
        logger.info("模式: 仅 Web 服务")
        logger.info(f"Web 服务运行中: http://{args.host}:{args.port}")
        logger.info("通过 /api/v1/analysis/stock/{code} 接口触发分析")
        logger.info(f"API 文档: http://{args.host}:{args.port}/docs")
        logger.info("按 Ctrl+C 退出...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n用户中断，程序退出")
        return 0

    try:
        # 模式0: 回测
        if getattr(args, 'backtest', False):
            logger.info("模式: 回测")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"回测完成: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # 模式1: 仅大盘复盘
        if args.market_review:
            from src.analyzer import GeminiAnalyzer
            from src.core.market_review import run_market_review
            from src.search_service import SearchService

            logger.info("模式: 仅大盘复盘")
            notifier = NotificationService()

            # 初始化搜索服务和分析器（如果有配置）
            search_service = None
            analyzer = None

            if config.bocha_api_keys or config.tavily_api_keys or config.brave_api_keys or config.serpapi_keys:
                search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    brave_keys=config.brave_api_keys,
                    serpapi_keys=config.serpapi_keys,
                    news_max_age_days=config.news_max_age_days,
                )

            if config.gemini_api_key or config.openai_api_key:
                analyzer = GeminiAnalyzer(api_key=config.gemini_api_key)
                if not analyzer.is_available():
                    logger.warning("AI 分析器初始化后不可用，请检查 API Key 配置")
                    analyzer = None
            else:
                logger.warning("未检测到 API Key (Gemini/OpenAI)，将仅使用模板生成报告")

            run_market_review(
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=not args.no_notify
            )
            return 0

        # 模式2: 定时任务模式
        if args.schedule or config.schedule_enabled:
            logger.info("模式: 定时任务")
            logger.info(f"每日执行时间: {config.schedule_time}")

            # Determine whether to run immediately:
            # Command line arg --no-run-immediately overrides config if present.
            # Otherwise use config (defaults to True).
            should_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                should_run_immediately = False
            
            logger.info(f"启动时立即执行: {should_run_immediately}")

            from src.scheduler import run_with_schedule

            def scheduled_task():
                run_full_analysis(config, args, stock_codes)

            run_with_schedule(
                task=scheduled_task,
                schedule_time=config.schedule_time,
                run_immediately=should_run_immediately
            )
            return 0

        # 模式3: 正常单次运行
        run_full_analysis(config, args, stock_codes)

        logger.info("\n程序执行完成")

        # 如果启用了服务且是非定时任务模式，保持程序运行
        keep_running = start_serve and not (args.schedule or config.schedule_enabled)
        if keep_running:
            logger.info("API 服务运行中 (按 Ctrl+C 退出)...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        return 0

    except KeyboardInterrupt:
        logger.info("\n用户中断，程序退出")
        return 130

    except Exception as e:
        logger.exception(f"程序执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
