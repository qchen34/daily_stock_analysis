# -*- coding: utf-8 -*-
"""
Telegram / 多渠道 报告推送测试脚本（模仿 main.py 合并推送）：
- 加载 .env 与配置，按 main.py 设置代理
- 从 reports 目录读取：market_review_*.md（大盘复盘）、report_*.md（个股报告）
- 按 main.py Issue #190 方式合并：大盘复盘 + 个股报告，用 "\\n\\n---\\n\\n" 拼接
- 调用 notifier.send(combined_content, email_send_to_all=True) 推送到所有已配置渠道

用法：在项目根目录执行  python script.py
"""
import os
import sys
import logging
from pathlib import Path

# 项目根目录（即 daily_stock_analysis）
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import setup_env, get_config


def find_latest_md_by_prefix(reports_dir: Path, prefix: str) -> Path | None:
    """在 reports_dir 下找文件名以 prefix 开头、修改时间最新的 .md 文件"""
    files = [p for p in reports_dir.glob(f"{prefix}*.md")]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    setup_env()
    config = get_config()

    # 与 main.py 一致的代理设置
    if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "true").lower() == "true":
        proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
        proxy_port = os.getenv("PROXY_PORT", "7890")
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url
        print(f"已设置代理: {proxy_url}")

    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        print(f"reports 目录不存在: {reports_dir}")
        return 1

    # 模仿 main.py：先大盘复盘，再个股报告
    parts = []

    market_file = find_latest_md_by_prefix(reports_dir, "market_review_")
    if market_file:
        try:
            content = market_file.read_text(encoding="utf-8")
            parts.append(f"# 📈 大盘复盘\n\n{content}")
            print(f"已加入: {market_file.name}")
        except Exception as e:
            print(f"读取大盘复盘失败 {market_file.name}: {e}")

    report_file = find_latest_md_by_prefix(reports_dir, "report_")
    if report_file:
        try:
            content = report_file.read_text(encoding="utf-8")
            parts.append(f"# 🚀 个股报告\n\n{content}")
            print(f"已加入: {report_file.name}")
        except Exception as e:
            print(f"读取个股报告失败 {report_file.name}: {e}")

    if not parts:
        print("reports 下未找到 market_review_*.md 或 report_*.md")
        return 1

    combined_content = "\n\n---\n\n".join(parts)
    print("合并后总长度:", len(combined_content), "字符")

    from src.notification import NotificationService

    notifier = NotificationService()
    if not notifier.is_available():
        print("当前未配置任何通知渠道，请检查 .env")
        return 1

    print("正在通过 notifier.send(..., email_send_to_all=True) 推送到所有已配置渠道...")
    ok = notifier.send(combined_content, email_send_to_all=True)

    if ok:
        print("合并推送成功，请在 Telegram / 邮件等渠道查收。")
        return 0
    print("合并推送失败，请查看上方各渠道 ERROR 日志。")
    return 1


if __name__ == "__main__":
    sys.exit(main())