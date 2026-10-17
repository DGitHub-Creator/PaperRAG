-- Remove only non-unique id indexes duplicated by an existing PRIMARY KEY.
-- Preserve all business data, foreign-key indexes and unique filename indexes.
-- Duplicate workspace memberships fail the unique-index build; never delete data to force success.
BEGIN;
DROP INDEX IF EXISTS public.ix_users_id;
DROP INDEX IF EXISTS public.ix_workspaces_id;
DROP INDEX IF EXISTS public.ix_workspace_members_id;
DROP INDEX IF EXISTS public.ix_chat_sessions_id;
DROP INDEX IF EXISTS public.ix_chat_messages_id;
DROP INDEX IF EXISTS public.ix_citation_edges_id;
DROP INDEX IF EXISTS public.ix_glossary_entries_id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_member ON workspace_members (workspace_id, user_id);
COMMIT;
