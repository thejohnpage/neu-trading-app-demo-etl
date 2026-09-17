CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.trade_activity (
    fill_id             UUID PRIMARY KEY,
    order_id            UUID NOT NULL UNIQUE,
    client_id           UUID NOT NULL,
    client_segment      VARCHAR(50),
    account_id          UUID NOT NULL,
    account_number      VARCHAR(30) NOT NULL,
    instrument_id       UUID NOT NULL,
    symbol              VARCHAR(30) NOT NULL,
    instrument_type     VARCHAR(20) NOT NULL,
    exchange            VARCHAR(30),
    side                VARCHAR(4) NOT NULL,
    quantity            NUMERIC(20,8) NOT NULL,
    execution_price     NUMERIC(20,8) NOT NULL,
    notional            NUMERIC(28,8) NOT NULL,
    currency            VARCHAR(10) NOT NULL,
    bid_price           NUMERIC(20,8) NOT NULL,
    ask_price           NUMERIC(20,8) NOT NULL,
    quote_source        VARCHAR(100) NOT NULL,
    submitted_at        TIMESTAMPTZ NOT NULL,
    accepted_at         TIMESTAMPTZ,
    filled_at           TIMESTAMPTZ NOT NULL,
    trade_date          DATE NOT NULL,
    trade_year          INTEGER NOT NULL,
    trade_month         INTEGER NOT NULL,
    trade_day           INTEGER NOT NULL,
    trade_day_of_week   INTEGER NOT NULL,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dw_trade_filled_at ON dw.trade_activity(filled_at DESC);
CREATE INDEX IF NOT EXISTS idx_dw_trade_symbol ON dw.trade_activity(symbol, filled_at DESC);
CREATE INDEX IF NOT EXISTS idx_dw_trade_segment ON dw.trade_activity(client_segment, filled_at DESC);
CREATE INDEX IF NOT EXISTS idx_dw_trade_date ON dw.trade_activity(trade_date);

CREATE TABLE IF NOT EXISTS dw.etl_watermark (
    pipeline_name       VARCHAR(100) PRIMARY KEY,
    last_filled_at      TIMESTAMPTZ NOT NULL,
    last_fill_id        UUID,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO dw.etl_watermark (pipeline_name, last_filled_at)
VALUES ('trade_activity', TIMESTAMPTZ '1970-01-01 00:00:00+00')
ON CONFLICT (pipeline_name) DO NOTHING;
