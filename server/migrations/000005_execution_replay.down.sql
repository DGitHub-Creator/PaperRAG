-- Do not discard replay inputs while accepted executions are still unfinished.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ai_executions WHERE status IN ('queued', 'running') AND request_payload IS NOT NULL) THEN
        RAISE EXCEPTION 'unfinished executions must be completed or cancelled before rollback';
    END IF;
END $$;
ALTER TABLE ai_executions DROP COLUMN request_payload;
