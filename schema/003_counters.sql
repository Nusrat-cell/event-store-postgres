CREATE TABLE IF NOT EXISTS campaign_counters (
    campaign_id integer PRIMARY KEY,
    clicks      bigint  NOT NULL DEFAULT 0
);
