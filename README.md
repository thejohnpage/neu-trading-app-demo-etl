# NEU Trading App Demo ETL

Scheduled reference ETL for the LEAP trading capstone. It keeps analytical/reporting work physically separate from the live trading database by flattening completed trades from the OLTP PostgreSQL database into a separate warehouse PostgreSQL instance.

The PostgreSQL warehouse is a stand-in for Snowflake when training licenses are unavailable. The extraction/transform boundary is intentionally simple enough to replace the destination adapter later.

## Data flow

```text
Trading PostgreSQL (Windows VM)
        |
        | every 60 seconds by default
        v
Python ETL
  - reads watermark
  - extracts new fills
  - joins/enriches OLTP data
  - derives date dimensions/notional
        |
        v
Warehouse PostgreSQL (Linux VM :55433)
        |
        v
dw.trade_activity
```

The watermark is `(filled_at, fill_id)`, which gives deterministic incremental extraction when multiple fills have the same timestamp. Loads are idempotent because `fill_id` is the warehouse primary key and the load uses an upsert.

## Warehouse table

`dw.trade_activity` deliberately denormalizes client, account, instrument, pricing and trade facts. It is optimized for reporting queries rather than transactional writes.

## Linux warehouse PostgreSQL

The Neueda Linux VM already has PostgreSQL exposed on 5432. The demo warehouse therefore uses a separate PostgreSQL 18 container and host port 55433.

PostgreSQL 18+ Docker images should mount the parent `/var/lib/postgresql` directory rather than the older `/var/lib/postgresql/data` path:

```bash
docker run -d \
  --name trading-dw-postgres \
  --restart unless-stopped \
  -e POSTGRES_DB=trading_dw \
  -e POSTGRES_USER=trading_dw \
  -e POSTGRES_PASSWORD=trading_dw_change_me \
  -p 55433:5432 \
  -v trading-dw-data:/var/lib/postgresql \
  postgres:18
```

The Linux host does not need `psql` installed. Initialize the warehouse using the client included in the container, from the cloned repository directory:

```bash
docker exec -i trading-dw-postgres \
  psql -U trading_dw -d trading_dw \
  < sql/001_create_warehouse.sql
```

Inspect it with:

```bash
docker exec -it trading-dw-postgres \
  psql -U trading_dw -d trading_dw
```

Then in `psql`:

```sql
\dt dw.*
SELECT * FROM dw.etl_watermark;
```

## ETL configuration

Copy `.env.example` to `.env` and replace `WINDOWS_VM_IP` with the Windows VM address reachable from Linux.

The Windows PostgreSQL server must accept the Linux VM connection. Do not open PostgreSQL broadly; restrict `pg_hba.conf` and the VM/network firewall to the Linux VM address where possible.

## Run natively

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

## Run in Docker

```bash
docker build -t neu-trading-etl .
docker run -d \
  --name trading-etl \
  --restart unless-stopped \
  --env-file .env \
  neu-trading-etl
```

## Demonstration

1. Execute a trade through the Spring trading API.
2. Observe it become `FILLED` in OLTP.
3. Wait for the scheduled ETL interval (60 seconds by default).
4. Query the warehouse:

```sql
SELECT symbol, side, quantity, execution_price, notional, filled_at
FROM dw.trade_activity
ORDER BY filled_at DESC;
```

Trading remains independent if the warehouse or ETL is unavailable; the next successful ETL run resumes from the stored watermark.
