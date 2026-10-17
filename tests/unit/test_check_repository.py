import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("check_repository", Path(__file__).resolve().parents[2] / "scripts/check_repository.py")
assert _SPEC and _SPEC.loader
repository = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repository)


def test_paths_reject_case_collisions_and_runtime_files():
    errors = repository.check_paths(["src/App.py", "src/app.py", ".env", "frontend/node_modules/x.js"])
    assert len(errors) == 3


def test_document_links_ignore_urls_anchors_and_fenced_examples(tmp_path):
    source = tmp_path / "README.md"
    text = "[web](https://example.com) [anchor](#test)\n```md\n[demo](missing.md)\n```"
    assert repository.check_markdown(source, text) == []
    assert len(repository.check_markdown(source, "[bad](missing.md)")) == 1
    (tmp_path / "exists.md").touch()
    assert repository.check_markdown(source, "[ok](exists.md#heading) [ok](exists%2Emd)") == []


def test_migrations_reject_missing_pairs_and_duplicate_versions(tmp_path):
    migrations = tmp_path / "server/migrations"
    migrations.mkdir(parents=True)
    for name in ["000001_first.up.sql", "000001_first.down.sql", "000001_second.up.sql"]:
        (migrations / name).touch()
    assert len(repository.check_migrations(tmp_path)) == 2


def test_lock_audit_covers_alternative_platform_versions_without_conflicting_requirements():
    lock = {"package": [
        {"name": "library", "version": "1.0", "source": {"registry": "https://pypi.org/simple"}},
        {"name": "library", "version": "2.0", "source": {"registry": "https://pypi.org/simple"}},
        {"name": "other", "version": "3.0", "source": {"registry": "https://pypi.org/simple"}},
        {"name": "researchpilot", "version": "0.2", "source": {"editable": "."}},
    ]}
    batches = repository.lock_audit_batches(lock)
    assert {pin for batch in batches for pin in batch} == {"library==1.0", "library==2.0", "other==3.0"}
    assert all(len(batch) == len({pin.split("==")[0] for pin in batch}) for batch in batches)
