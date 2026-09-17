from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging
import psycopg
from psycopg.rows import dict_row

from config import settings

log = logging.getLogger(__name__)

EXTRACT_SQL = """
SELECT
    f.fill_id, f.order_id, c.client_id, c.client_segment,
    a.account_id, a.account_number,
    i.instrument_id, i.symbol, i.instrument_type, i.exchange,
    o.side, f.quantity, f.price AS execution_price,
    (f.quantity * f.price) AS notional,
    i.quote_currency AS currency,
    p.bid_price, p.ask_price, p.quote_source,
    o.submitted_at, o.accepted_at, f.filled_at
FROM trading.fills f
JOIN trading.orders o ON o.order_id = f.order_id
JOIN trading.accounts a ON a.account_id = o.account_id
JOIN identity.clients c ON c.client_id = a.client_id
JOIN trading.instruments i ON i.instrument_id = o.instrument_id
JOIN audit.pricing_decisions p ON p.order_id = o.order_id
WHERE (f.filled_at, f.fill_id) > (%s, %s)
ORDER BY f.filled_at, f.fill_id
LIMIT %s
"""

UPSERT_SQL = """
INSERT INTO dw.trade_activity (
 fill_id, order_id, client_id, client_segment, account_id, account_number,
 instrument_id, symbol, instrument_type, exchange, side, quantity,
 execution_price, notional, currency, bid_price, ask_price, quote_source,
 submitted_at, accepted_at, filled_at, trade_date, trade_year, trade_month,
 trade_day, trade_day_of_week
) VALUES (
 %(fill_id)s, %(order_id)s, %(client_id)s, %(client_segment)s, %(account_id)s, %(account_number)s,
 %(instrument_id)s, %(symbol)s, %(instrument_type)s, %(exchange)s, %(side)s, %(quantity)s,
 %(execution_price)s, %(notional)s, %(currency)s, %(bid_price)s, %(ask_price)s, %(quote_source)s,
 %(submitted_at)s, %(accepted_at)s, %(filled_at)s, %(trade_date)s, %(trade_year)s, %(trade_month)s,
 %(trade_day)s, %(trade_day_of_week)s
)
ON CONFLICT (fill_id) DO UPDATE SET
 execution_price=EXCLUDED.execution_price, notional=EXCLUDED.notional,
 bid_price=EXCLUDED.bid_price, ask_price=EXCLUDED.ask_price,
 quote_source=EXCLUDED.quote_source, loaded_at=CURRENT_TIMESTAMP
"""


def _watermark(conn):
    row = conn.execute("SELECT last_filled_at, last_fill_id FROM dw.etl_watermark WHERE pipeline_name='trade_activity'").fetchone()
    return row[0], row[1] or "00000000-0000-0000-0000-000000000000"


def run_once() -> int:
    with psycopg.connect(settings.warehouse_dsn) as dw:
        last_time, last_id = _watermark(dw)
        with psycopg.connect(settings.oltp_dsn, row_factory=dict_row) as oltp:
            rows = oltp.execute(EXTRACT_SQL, (last_time, last_id, settings.batch_size)).fetchall()
        if not rows:
            log.info("No new fills after %s", last_time)
            return 0
        with dw.transaction():
            for row in rows:
                filled: datetime = row["filled_at"]
                record = dict(row)
                record.update({
                    "trade_date": filled.date(),
                    "trade_year": filled.year,
                    "trade_month": filled.month,
                    "trade_day": filled.day,
                    "trade_day_of_week": filled.isoweekday(),
                })
                dw.execute(UPSERT_SQL, record)
            final = rows[-1]
            dw.execute("""
                UPDATE dw.etl_watermark
                SET last_filled_at=%s, last_fill_id=%s, updated_at=CURRENT_TIMESTAMP
                WHERE pipeline_name='trade_activity'
            """, (final["filled_at"], final["fill_id"]))
        log.info("Loaded %d trade(s); watermark=%s", len(rows), rows[-1]["filled_at"])
        return len(rows)
