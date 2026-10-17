-- Persist the accepted request before acknowledging asynchronous execution.
ALTER TABLE ai_executions ADD COLUMN IF NOT EXISTS request_payload JSONB;
