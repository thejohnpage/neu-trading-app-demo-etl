# NEU Trading App Demo ETL

Scheduled reference ETL for the LEAP trading capstone. It keeps analytical/reporting work in a separate database instance from the live trading database by flattening completed trades from the OLTP PostgreSQL database into a separate warehouse PostgreSQL instance.

The PostgreSQL warehouse is a stand-in for Snowflake when training licenses are unavailable. The extraction/transform boundary is intentionally simple enough to replace the destination adapter later.

## Data flow

| Stage | Location / purpose |
| --- | --- |
| Live trading PostgreSQL (OLTP) | Existing PostgreSQL container on a Linux VM; source of completed trades |
| Python ETL | Linux VM process or container; extracts and enriches new fills every 60 seconds by default |
| Warehouse PostgreSQL | Separate PostgreSQL container on a Linux VM, host port `55433`; stores `dw.trade_activity` |

The deployment instructions below assume the live database is now containerized on Linux. Confirm the live database's VM, container name, database credentials, and published port before configuring the ETL. The live and warehouse containers may run on the same VM or on different Linux VMs.

The watermark is `(filled_at, fill_id)`, which gives deterministic incremental extraction when multiple fills have the same timestamp. Loads are idempotent because `fill_id` is the warehouse primary key and the load uses an upsert.

## Warehouse table

`dw.trade_activity` deliberately denormalizes client, account, instrument, pricing and trade facts. It is optimized for reporting queries rather than transactional writes.

## Linux warehouse PostgreSQL

The demo warehouse uses a separate PostgreSQL 18 container and host port `55433`, allowing it to coexist with a live PostgreSQL container published on host port `5432`. Verify the live container's actual mapping; its host port may differ.

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

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

The checked-in example still mentions `WINDOWS_VM_IP`, and its warehouse address is an example deployment address. Replace both DSNs with the actual Linux endpoints. Explicitly set both DSNs rather than relying on the defaults in `src/config.py`.

### Confirm the live database container

On the Linux VM hosting the live database:

```bash
docker context show
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker port <live-postgres-container> 5432/tcp
```

Replace `<live-postgres-container>` with the existing container name. These commands use the selected Docker context, so confirm it points at the intended VM. A mapping such as `127.0.0.1:5432` is reachable only on that VM; `0.0.0.0:5432` is published on its network interfaces, subject to firewall rules. Use the published **host** port when connecting from a VM process.

### Both databases on the ETL Linux VM

For a native ETL process, or the Linux host-network Docker command below, configure:

```dotenv
OLTP_DSN=postgresql://trading_demo:trading_demo_change_me@127.0.0.1:5432/trading_demo
WAREHOUSE_DSN=postgresql://trading_dw:trading_dw_change_me@127.0.0.1:55433/trading_dw
ETL_INTERVAL_SECONDS=60
ETL_BATCH_SIZE=500
```

Replace the sample credentials and database names with those used by the existing containers, and adjust the live host port if necessary. URL-encode special characters in DSN usernames or passwords.

### Live database on another Linux VM

An SSH tunnel lets the ETL reach a remote database even when its published port is bound to the remote VM's loopback interface. From the ETL VM, keep this command running in a separate terminal:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:55432:127.0.0.1:5432 \
  ec2-user@<live-db-linux-vm>
```

Replace `<live-db-linux-vm>` with the live database VM's reachable address, use its SSH username/key, and replace the final `5432` with the live container's published host port. Configure:

```dotenv
OLTP_DSN=postgresql://trading_demo:trading_demo_change_me@127.0.0.1:55432/trading_demo
WAREHOUSE_DSN=postgresql://trading_dw:trading_dw_change_me@127.0.0.1:55433/trading_dw
```

This warehouse DSN assumes the warehouse is on the ETL VM. If it is also remote, configure a reachable warehouse endpoint or a separate SSH tunnel. The tunnel must stay running while the ETL runs.

Alternatively, use the live VM's private address and published PostgreSQL port directly if VM routing, firewall/security-group rules, and PostgreSQL authentication permit it. Restrict access to the ETL VM.

### Docker network addressing

With the Linux `--network host` command below, `127.0.0.1` refers to the Linux host, so the same DSNs work for published database ports and host-side SSH tunnels.

With Docker bridge networking, `localhost` refers to the ETL container itself. For containers on the same VM and a shared user-defined Docker network, use the actual database container names and their internal PostgreSQL port `5432` instead of host ports. Docker container names are not automatically resolvable across different VMs.

## Run natively

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

## Run in Docker

On Linux, use host networking with the loopback DSNs above. Ensure the required database containers and any SSH tunnel are running first.

```bash
docker build -t neu-trading-etl .
docker run -d \
  --name trading-etl \
  --network host \
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
