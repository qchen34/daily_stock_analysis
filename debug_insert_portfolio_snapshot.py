from datetime import datetime, timedelta

from src.storage import get_db

db = get_db()

account_name = "美股主账户"

now = datetime.now()

# 举例插入三条快照（你可以按自己实际资产改数值）
snapshots = [
    (now - timedelta(days=60), 10000.0, 2000.0),  # 60 天前
    (now - timedelta(days=30), 11000.0, 2500.0),  # 30 天前
    (now,                    12000.0, 3000.0),    # 今天
]

for as_of, total_equity, cash in snapshots:
    db.save_portfolio_account_snapshot(
        account_name=account_name,
        as_of=as_of,
        total_equity=total_equity,
        cash=cash,
        positions_value=total_equity - cash,
        base_currency="USD",
        notes="debug insert",
    )

print("插入完成")

from src.storage import get_db, PortfolioAccount, PortfolioAccountSnapshot

db = get_db()

with db.get_session() as session:
    accounts = session.query(PortfolioAccount).all()
    print("=== PortfolioAccount 列表 ===")
    for acc in accounts:
        print(f"- id={acc.id}, name={acc.name}, base_currency={acc.base_currency}, created_at={acc.created_at}")

    print("\n=== PortfolioAccountSnapshot 列表 ===")
    snaps = session.query(PortfolioAccountSnapshot).order_by(
        PortfolioAccountSnapshot.account_id,
        PortfolioAccountSnapshot.as_of,
    ).all()
    for s in snaps:
        print(
            f"account_id={s.account_id}, as_of={s.as_of}, "
            f"total_equity={s.total_equity}, cash={s.cash}, positions_value={s.positions_value}"
        )