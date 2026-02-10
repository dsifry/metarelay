-- Create events table for storing GitHub webhook events
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    repo TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT '',
    ref TEXT,
    actor TEXT,
    summary TEXT,
    payload JSONB NOT NULL DEFAULT '{}',
    delivery_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for catch-up queries: fetch events by repo after a given ID
CREATE INDEX idx_events_repo_id ON events (repo, id);

-- Index for dedup on delivery_id (already covered by UNIQUE, but explicit)
CREATE INDEX idx_events_delivery_id ON events (delivery_id);

-- Index for filtering by event_type
CREATE INDEX idx_events_event_type ON events (event_type);

-- Enable Row Level Security
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- Policy: allow the service role and anon key to read events
CREATE POLICY "Allow read access" ON events
    FOR SELECT
    USING (true);

-- Policy: allow the service role to insert events (Edge Functions use service role)
CREATE POLICY "Allow insert from service role" ON events
    FOR INSERT
    WITH CHECK (true);

-- Enable Realtime for the events table
ALTER PUBLICATION supabase_realtime ADD TABLE events;
