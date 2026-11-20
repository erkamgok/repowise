"""``repowise delete`` exits 1 when nothing was deleted (issue #5980).

Each failure branch printed its message and returned normally, so a script or
agent could not tell a no-op from a delete.
"""

from __future__ import annotations

import asyncio

import pytest
from click.testing import CliRunner

from repowise.cli.main import cli


@pytest.fixture
def indexed_repo(tmp_path, monkeypatch):
    """A repo-local ``.repowise/wiki.db`` holding one repository row."""
    from repowise.core.persistence import (
        create_engine,
        create_session_factory,
        get_session,
        init_db,
        upsert_repository,
    )

    monkeypatch.delenv("REPOWISE_DB_URL", raising=False)
    monkeypatch.delenv("REPOWISE_DATABASE_URL", raising=False)
    repo_path = tmp_path / "repo"
    (repo_path / ".repowise").mkdir(parents=True)
    url = f"sqlite+aiosqlite:///{repo_path / '.repowise' / 'wiki.db'}"

    async def seed() -> None:
        engine = create_engine(url)
        await init_db(engine)
        sf = create_session_factory(engine)
        async with get_session(sf) as session:
            await upsert_repository(
                session, name=repo_path.name, local_path=str(repo_path.resolve())
            )
        await engine.dispose()

    asyncio.run(seed())
    return repo_path


def _delete(*args: str):
    return CliRunner().invoke(cli, ["delete", *args], catch_exceptions=False)


def test_unknown_id_exits_1(indexed_repo):
    result = _delete("no-such-repo", "--path", str(indexed_repo), "--force")

    assert result.exit_code == 1, result.output
    assert "Repository no-such-repo not found." in result.output


def test_unmatched_path_exits_1(indexed_repo, tmp_path, monkeypatch):
    # Point the store at the indexed repo's database, then name another path.
    db = indexed_repo / ".repowise" / "wiki.db"
    monkeypatch.setenv("REPOWISE_DB_URL", f"sqlite+aiosqlite:///{db}")
    unknown = tmp_path / "never-indexed"
    unknown.mkdir()

    result = _delete("--path", str(unknown), "--force")

    assert result.exit_code == 1, result.output
    assert "No repository in the database matches" in result.output


def test_invalid_selection_exits_1(indexed_repo, monkeypatch):
    monkeypatch.chdir(indexed_repo)

    result = CliRunner().invoke(cli, ["delete"], input="7\n", catch_exceptions=False)

    assert result.exit_code == 1, result.output
    assert "Invalid selection." in result.output


def test_missing_database_exits_1(tmp_path, monkeypatch):
    monkeypatch.delenv("REPOWISE_DB_URL", raising=False)
    monkeypatch.delenv("REPOWISE_DATABASE_URL", raising=False)
    repo_path = tmp_path / "repo"
    (repo_path / ".repowise").mkdir(parents=True)

    result = _delete("--path", str(repo_path), "--force")

    assert result.exit_code == 1, result.output
    assert "Database not found." in result.output


def test_quit_at_the_prompt_still_exits_0(indexed_repo, monkeypatch):
    monkeypatch.chdir(indexed_repo)

    result = CliRunner().invoke(cli, ["delete"], input="q\n", catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert "Deleted" not in result.output


def test_successful_delete_still_exits_0(indexed_repo):
    result = _delete("--path", str(indexed_repo), "--force")

    assert result.exit_code == 0, result.output
    assert "Deleted" in result.output
