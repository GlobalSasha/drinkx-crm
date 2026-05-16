-- backfill_stage_history.sql
--
-- One-shot seed for the new lead_stage_history table (migration 0029).
-- For every active lead (archived_at IS NULL), insert ONE open row
-- pinned to its current stage_id with entered_at = COALESCE(assigned_at,
-- created_at). After this runs, every active lead has exactly one open
-- history row, which `app/automation/stage_change.move_stage` will
-- start closing on the next transition.
--
-- Idempotency: filter on `archived_at IS NULL` to skip closed leads,
-- and a NOT EXISTS guard prevents double-inserts if the script is
-- re-run. Stage_id NULL is skipped — a lead detached from the pipeline
-- has nothing meaningful to history.
--
-- DO NOT RUN AUTOMATICALLY. Run manually after `alembic upgrade head`
-- has applied 0029 on the target database:
--
--     psql "$DATABASE_URL" -f scripts/backfill_stage_history.sql

BEGIN;

INSERT INTO lead_stage_history (lead_id, stage_id, entered_at)
SELECT
    l.id,
    l.stage_id,
    COALESCE(l.assigned_at, l.created_at)
FROM leads l
WHERE l.archived_at IS NULL
  AND l.stage_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM lead_stage_history h
      WHERE h.lead_id = l.id
        AND h.exited_at IS NULL
  );

COMMIT;

-- Sanity:
--   SELECT COUNT(*) FROM lead_stage_history WHERE exited_at IS NULL;
--   should equal COUNT(*) FROM leads WHERE archived_at IS NULL
--                                      AND stage_id IS NOT NULL;
