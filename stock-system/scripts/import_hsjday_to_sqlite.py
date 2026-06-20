"""Import local .day files into stock-picker SQLite daily table.

Only imports codes that already exist in stock_basic/stocks.
Source:
  <repo>/hsjday 2/{sh,sz,bj}/lday/*.day
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY_ROOT = ROOT / "hsjday 2"
# DB_PATH 支持 PICKER_DB_DIR 环境变量(联调时方便切到临时 DB)
import os
_DATA_DIR = os.environ.get('PICKER_DB_DIR') or str(ROOT / "stock-picker" / "data")
DB_PATH = Path(_DATA_DIR) / "stocks.db"
REC_SIZE = 32


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_existing_codes(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM stock_basic ORDER BY code")
    return [str(row["code"]) for row in cursor.fetchall()]


def locate_day_file(code: str) -> Path | None:
    # code 可能是 '000001' (6 位) 或 'sh000001',都按 6 位判断市场
    raw = code.lower()
    if raw.startswith("sh"):
        six = raw[2:]
    elif raw.startswith("sz") or raw.startswith("bj"):
        six = raw[2:]
    else:
        six = raw
    if not six.isdigit() or len(six) != 6:
        return None
    # 按股票代码首位判断市场
    if six.startswith(("60", "68")):  # 沪
        path = DAY_ROOT / "sh" / "lday" / f"sh{six}.day"
    elif six.startswith(("00", "30")):  # 深
        path = DAY_ROOT / "sz" / "lday" / f"sz{six}.day"
    else:
        return None
    return path if path.exists() else None


def parse_day_file(path: Path) -> list[tuple]:
    raw = path.read_bytes()
    if not raw:
        return []
    n = len(raw) // REC_SIZE
    if n <= 0:
        return []

    records = []
    previous_close = None
    for i in range(n):
        offset = i * REC_SIZE
        date_i, open_i, high_i, low_i, close_i, amount_f, volume_i, _ = struct.unpack(
            "<5if2i", raw[offset: offset + REC_SIZE]
        )
        if date_i <= 0:
            continue

        trade_date = f"{date_i:08d}"
        trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        open_p = open_i / 100.0
        high_p = high_i / 100.0
        low_p = low_i / 100.0
        close_p = close_i / 100.0
        amount = float(amount_f)
        volume = int(volume_i)
        pre_close = previous_close
        up = ((close_p - pre_close) / pre_close * 100.0) if pre_close and pre_close > 0 else 0.0

        records.append((
            trade_date,
            open_p,
            high_p,
            low_p,
            close_p,
            pre_close,
            volume,
            amount,
            up,
        ))
        previous_close = close_p
    return records


def import_one_code(conn: sqlite3.Connection, code: str, path: Path) -> int:
    rows = parse_day_file(path)
    if not rows:
        return 0

    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock_daily WHERE code = ?", (code,))
    cursor.executemany("""
        INSERT INTO stock_daily
        (code, date, open, high, low, close, pre_close, volume, amount, up)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (code, trade_date, open_p, high_p, low_p, close_p, pre_close, volume, amount, up)
        for trade_date, open_p, high_p, low_p, close_p, pre_close, volume, amount, up in rows
    ])
    return len(rows)


def main() -> None:
    if not DAY_ROOT.exists():
        raise SystemExit(f"Missing day root: {DAY_ROOT}")

    conn = get_conn()
    try:
        codes = load_existing_codes(conn)
        imported_codes = 0
        imported_rows = 0
        missing_files = 0

        # 预解析: 先把所有 .day 文件读进内存,再批量入库
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print(f"[Import] 预解析 {len(codes)} 个 .day 文件...")

        def _parse_one(code):
            path = locate_day_file(code)
            if path is None:
                return code, None
            return code, parse_day_file(path)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_parse_one, code): code for code in codes}
            parsed = {}
            for i, fut in enumerate(as_completed(futures), 1):
                code, rows = fut.result()
                if rows is not None:
                    parsed[code] = rows
                if i % 500 == 0:
                    print(f"[Import] 解析进度 {i}/{len(codes)}")
        print(f"[Import] 解析完成: {len(parsed)} 只有数据,开始入库...")

        # 单连接串行 INSERT,触发 schema migration 后 ALTER 已经加过列
        missing_files = len(codes) - len(parsed)
        for idx, (code, rows) in enumerate(parsed.items(), start=1):
            # rows 已经预解析过,直接 executemany 入库(增量 upsert)
            if not rows:
                continue
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT INTO stock_daily
                (code, date, open, high, low, close, pre_close, volume, amount, up)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    pre_close = excluded.pre_close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    up = excluded.up""",
                [(code, *row) for row in rows],
            )
            imported_codes += 1
            imported_rows += len(rows)

            if imported_codes % 200 == 0:
                conn.commit()
                print(
                    f"[{idx}/{len(codes)}] imported_codes={imported_codes} "
                    f"imported_rows={imported_rows}"
                )

        conn.commit()
        print(
            f"done imported_codes={imported_codes} imported_rows={imported_rows} "
            f"missing_files={missing_files} total_codes={len(codes)}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
