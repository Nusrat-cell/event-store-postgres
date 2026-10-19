/* Last events of one user: the main read path. */
CREATE INDEX IF NOT EXISTS events_user_time_idx ON events (user_id, occurred_at DESC);

/* Conversions are about 3 percent of rows, so a partial index stays small. */
CREATE INDEX IF NOT EXISTS events_conversion_idx ON events (campaign_id, occurred_at) WHERE event_type = 'conversion';

/* Rows arrive in time order, so a BRIN index on time is tiny and good enough for range scans. */
CREATE INDEX IF NOT EXISTS events_time_brin ON events USING brin (occurred_at);
