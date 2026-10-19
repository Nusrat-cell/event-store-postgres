/* Events are written once and read by user and by time, so the table is partitioned by day. */
CREATE TABLE IF NOT EXISTS events (
    event_id    uuid        NOT NULL,
    user_id     bigint      NOT NULL,
    campaign_id integer     NOT NULL,
    event_type  text        NOT NULL CHECK (event_type IN ('impression', 'click', 'conversion')),
    occurred_at timestamptz NOT NULL,
    payload     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

/* Events outside every daily partition land here instead of failing the whole batch. */
CREATE TABLE IF NOT EXISTS events_default PARTITION OF events DEFAULT;
