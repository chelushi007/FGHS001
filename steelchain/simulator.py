import argparse
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

REGIONS = ["华北", "华东", "华南", "华中", "西南", "东北"]
CATEGORIES = ["重型废钢", "中型废钢", "小型废钢", "统料废钢", "钢筋切头", "钢筋压块", "工业边角料", "冷轧料", "热轧料", "炉料", "钢刨花", "铁屑", "铸钢件", "废钢筋", "汽车拆解料", "船板料", "优质废钢", "破碎料", "剪切料", "生铁"]
SCENARIOS = {"normal": 1.0, "demand_growth": 1.18, "demand_decline": .82, "regional_imbalance": 1.0}


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    return db


def migrate(db):
    migration = Path(__file__).resolve().parent.parent / "migrations" / "001_initial.sql"
    db.executescript(migration.read_text(encoding="utf-8-sig"))
    db.execute("INSERT OR IGNORE INTO migration_version VALUES(1,datetime('now'))")
    db.commit()


def generate(path, seed=20261122, scenario="normal", start=date(2023, 1, 1), days=1096):
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    rng = random.Random(seed)
    db = connect(path)
    migrate(db)
    # Reset dependent ledgers/maps as part of the same reproducible dataset lifecycle.
    # They may have been created by later migrations or by previous demo/API runs.
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ["shipments", "orders", "quota_ledger", "requirements", "offers", "category_taxonomy_map", "quotas", "inventory", "prices", "categories", "parties"]:
        if table in tables:
            db.execute(f"DELETE FROM {table}")
    if "sqlite_sequence" in tables:
        db.execute("DELETE FROM sqlite_sequence WHERE name='quota_ledger'")

    parties = []
    for role, count in [("STEEL_MILL", 12), ("RECYCLER", 30), ("INDIVIDUAL", 80)]:
        for i in range(count):
            pid = f"{role[:2]}-{i+1:03}"
            region = REGIONS[i % len(REGIONS)]
            parties.append((pid, f"{role}-{i+1:03}", role, region, 1, "SIMULATED"))
    db.executemany("INSERT INTO parties VALUES(?,?,?,?,?,?)", parties)
    db.executemany("INSERT INTO categories(id,name) VALUES(?,?)", list(enumerate(CATEGORIES, 1)))

    for p in parties:
        if p[2] != "INDIVIDUAL":
            for c in range(1, 21):
                db.execute("INSERT INTO inventory VALUES(?,?,?,?,?)", (f"I-{p[0]}-{c}", p[0], c, round(rng.uniform(150, 1800), 2), 0))
        else:
            c = rng.randint(1, 20)
            db.execute("INSERT INTO inventory VALUES(?,?,?,?,?)", (f"I-{p[0]}-{c}", p[0], c, round(rng.uniform(1, 30), 2), 0))

    years = sorted({(start + timedelta(days=i)).year for i in range(days)})
    for p in parties:
        if p[2] == "INDIVIDUAL":
            for year in years:
                db.execute("INSERT INTO quotas VALUES(?,?,?,?,?,?)", (f"Q-{p[0]}-{year}", p[0], year, 5000000, 0, 0))

    for p in parties:
        role = p[2]
        if role != "INDIVIDUAL":
            for c in range(1, 21):
                iid = f"I-{p[0]}-{c}"
                quantity = db.execute("SELECT quantity FROM inventory WHERE id=?", (iid,)).fetchone()[0] * .3
                db.execute("INSERT INTO offers VALUES(?,?,?,?,?,?,?,?)", (f"O-{p[0]}-{c}", p[0], c, iid, quantity, 2200+rng.random()*500, p[3], "SIMULATED"))
        else:
            iid_row = db.execute("SELECT id,category_id,quantity FROM inventory WHERE party_id=?", (p[0],)).fetchone()
            iid, category, quantity = iid_row
            db.execute("INSERT INTO offers VALUES(?,?,?,?,?,?,?,?)", (f"O-{p[0]}-{category}", p[0], category, iid, quantity, 2400+rng.random()*300, p[3], "SIMULATED"))
        if role in ("STEEL_MILL", "RECYCLER"):
            for c in range(1, 21):
                base_qty = rng.uniform(50, 250) * SCENARIOS[scenario]
                db.execute("INSERT INTO requirements VALUES(?,?,?,?,?,?,?)", (f"R-{p[0]}-{c}", p[0], c, round(base_qty, 2), 3100, p[3], "SIMULATED"))

    # Three years of daily regional/category prices, generated from an explicit synthetic process.
    price_rows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        trend = (offset / max(days, 1) - .5) * .18
        for region in REGIONS:
            imbalance = (1.35 if region in ("华北", "华东") else .72) if scenario == "regional_imbalance" else 1
            for c in range(1, 21):
                base = 2200 + c * 23
                price = base * (1 + trend) * SCENARIOS[scenario] * imbalance * (1 + rng.uniform(-.025, .025))
                price_rows.append((day.isoformat(), region, c, round(price, 2), scenario, "SIMULATED"))
    db.executemany("INSERT INTO prices(day,region,category_id,price,scenario,data_origin) VALUES(?,?,?,?,?,?)", price_rows)

    # Match compatible same-category offers to requirements; reserve inventory and allocate transport.
    offers = db.execute("SELECT o.id,o.party_id,o.category_id,o.inventory_id,o.quantity,o.price,o.region,p.role FROM offers o JOIN parties p ON p.id=o.party_id ORDER BY o.id").fetchall()
    requirements = db.execute("SELECT r.id,r.party_id,r.category_id,r.quantity,r.max_price,r.region FROM requirements r ORDER BY r.id").fetchall()
    used_req = set()
    for oi, offer in enumerate(offers):
        oid_offer, seller, category, inventory_id, offer_qty, price, origin, seller_role = offer
        match = next((r for r in requirements if r[0] not in used_req and r[2] == category and r[4] >= price and r[1] != seller), None)
        if not match:
            continue
        req_id, buyer, _, req_qty, _, destination = match
        quantity = round(min(offer_qty, req_qty, 25), 2)
        if quantity <= 0:
            continue
        used_req.add(req_id)
        trade_id = f"T-{oi+1:05}"
        db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?)", (trade_id, oid_offer, req_id, quantity, price, "COMPLETED", "SIMULATED"))
        db.execute("UPDATE inventory SET reserved=reserved+? WHERE id=?", (quantity, inventory_id))
        db.execute("INSERT INTO shipments VALUES(?,?,?,?,?,?,?,?)", (f"S-{oi+1:05}", trade_id, origin, destination, quantity, round(quantity*8, 2), "DELIVERED", "SIMULATED"))
        if seller_role == "INDIVIDUAL":
            order_year = start.year
            amount = round(quantity * price, 2)
            db.execute("UPDATE quotas SET used_amount=used_amount+? WHERE party_id=? AND year=? AND used_amount+reserved_amount+?<=limit_amount", (amount, seller, order_year, amount))
    db.commit()
    db.close()
    return {"seed": seed, "scenario": scenario, "parties": len(parties), "categories": len(CATEGORIES), "days": days, "database": str(path)}


def validate(path):
    db = connect(path)
    checks = {
        "foreign_keys": len(db.execute("PRAGMA foreign_key_check").fetchall()) == 0,
        "individual_no_buy": db.execute("SELECT COUNT(*) FROM requirements r JOIN parties p ON p.id=r.party_id WHERE p.role='INDIVIDUAL'").fetchone()[0] == 0,
        "individual_quota": db.execute("SELECT COUNT(*) FROM quotas WHERE limit_amount!=5000000 OR used_amount+reserved_amount>limit_amount").fetchone()[0] == 0,
        "order_refs_and_limits": db.execute("SELECT COUNT(*) FROM orders o JOIN offers f ON f.id=o.offer_id JOIN requirements r ON r.id=o.requirement_id WHERE f.category_id!=r.category_id OR o.quantity>f.quantity OR o.quantity>r.quantity OR r.max_price<o.unit_price OR o.quantity>(SELECT quantity FROM inventory WHERE id=f.inventory_id)").fetchone()[0] == 0,
        "inventory_reservations": db.execute("SELECT COUNT(*) FROM inventory WHERE reserved>quantity").fetchone()[0] == 0,
        "shipment_capacity": db.execute("SELECT COUNT(*) FROM shipments s JOIN orders o ON o.id=s.order_id WHERE s.capacity<o.quantity").fetchone()[0] == 0,
        "simulation_labels": db.execute("SELECT (SELECT COUNT(*) FROM parties WHERE data_origin!='SIMULATED')+(SELECT COUNT(*) FROM offers WHERE data_origin!='SIMULATED')+(SELECT COUNT(*) FROM requirements WHERE data_origin!='SIMULATED')+(SELECT COUNT(*) FROM prices WHERE data_origin!='SIMULATED')+(SELECT COUNT(*) FROM orders WHERE data_origin!='SIMULATED')+(SELECT COUNT(*) FROM shipments WHERE data_origin!='SIMULATED')").fetchone()[0] == 0,
        "categories_20": db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 20,
        "three_years_daily": db.execute("SELECT COUNT(DISTINCT day) FROM prices").fetchone()[0] >= 1095 and db.execute("SELECT COUNT(DISTINCT substr(day,1,4)) FROM prices").fetchone()[0] >= 3,
    }
    db.close()
    return checks


def stats(path):
    db = connect(path)
    tables = ["parties", "categories", "inventory", "prices", "offers", "requirements", "orders", "shipments", "quotas"]
    result = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
    result["price_days"] = db.execute("SELECT COUNT(DISTINCT day) FROM prices").fetchone()[0]
    result["scenario"] = db.execute("SELECT scenario FROM prices LIMIT 1").fetchone()[0] if result["prices"] else None
    db.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate reproducible, explicitly simulated SteelChain data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--db", default="data/steelchain.sqlite")
    gen.add_argument("--seed", type=int, default=20261122)
    gen.add_argument("--scenario", choices=SCENARIOS, default="normal")
    gen.add_argument("--days", type=int, default=1096)
    for name in ("validate", "stats"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--db", default="data/steelchain.sqlite")
    args = parser.parse_args()
    if args.cmd == "generate":
        print(json.dumps(generate(args.db, args.seed, args.scenario, days=args.days), ensure_ascii=False))
    elif args.cmd == "validate":
        checks = validate(args.db)
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        raise SystemExit(0 if all(checks.values()) else 1)
    else:
        print(json.dumps(stats(args.db), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
