"""Tests for oracle CLI (v2.1)."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import pytest

from oracle_memory.cli import (
    build_parser,
    cmd_ask,
    cmd_demo,
    cmd_export,
    cmd_forget,
    cmd_remember,
    cmd_stats,
    cmd_trends,
    cmd_verify,
    main,
    _confidence_bar,
    _format_confidence,
    _make_agent,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a temporary SQLite database."""
    return str(tmp_path / "test_oracle.db")


def _args(**kwargs):
    """Build a namespace with defaults for CLI commands."""
    defaults = {"db": ":memory:", "user": "test-user", "limit": 5, "public": False, "output": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _seeded_db(db_path: str, facts: list[str] | None = None) -> str:
    """Seed a database with some facts, return the db path."""
    agent = _make_agent(db=db_path, user="test-user")
    for fact in (facts or [
        "Python was created by Guido van Rossum in 1991",
        "Flask is a micro web framework for Python",
        "SQLite is a self-contained SQL database engine",
        "HMAC-SHA256 is used for message signing in the oracle protocol",
    ]):
        agent.remember(fact, visibility="public")
    return db_path


# ── Helpers ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_confidence_bar_full(self):
        bar = _confidence_bar(1.0, width=10)
        assert bar == "█" * 10

    def test_confidence_bar_empty(self):
        bar = _confidence_bar(0.0, width=10)
        assert bar == "░" * 10

    def test_confidence_bar_half(self):
        bar = _confidence_bar(0.5, width=10)
        assert bar == "█" * 5 + "░" * 5

    def test_format_confidence_high(self):
        result = _format_confidence(0.85)
        assert "85%" in result
        assert "HIGH" in result

    def test_format_confidence_medium(self):
        result = _format_confidence(0.55)
        assert "55%" in result
        assert "MEDIUM" in result

    def test_format_confidence_low(self):
        result = _format_confidence(0.2)
        assert "20%" in result
        assert "LOW" in result


# ── Commands ─────────────────────────────────────────────────────────────

class TestCmdRemember:
    def test_remember_stores_claim(self, tmp_db, capsys):
        args = _args(db=tmp_db, text=["Python", "is", "great"])
        ret = cmd_remember(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "remembered" in out.lower() or "claim" in out.lower()

    def test_remember_empty(self, capsys):
        args = _args(text=[""])
        ret = cmd_remember(args)
        assert ret == 1

    def test_remember_public(self, tmp_db, capsys):
        args = _args(db=tmp_db, text=["Flask", "uses", "Jinja2"], public=True)
        ret = cmd_remember(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "public" in out.lower()


class TestCmdAsk:
    def test_ask_empty_db(self, tmp_db, capsys):
        args = _args(db=tmp_db, question=["who", "created", "Python"])
        ret = cmd_ask(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "no knowledge" in out.lower()

    def test_ask_with_results(self, tmp_db, capsys):
        _seeded_db(tmp_db)
        args = _args(db=tmp_db, question=["Python"])
        ret = cmd_ask(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Oracle says" in out or "result" in out.lower()

    def test_ask_empty_query(self, capsys):
        args = _args(question=[""])
        ret = cmd_ask(args)
        assert ret == 1

    def test_ask_limit(self, tmp_db, capsys):
        _seeded_db(tmp_db)
        args = _args(db=tmp_db, question=["Python"], limit=1)
        ret = cmd_ask(args)
        assert ret == 0


class TestCmdVerify:
    def test_verify_unknown(self, tmp_db, capsys):
        args = _args(db=tmp_db, statement=["quantum", "computing", "is", "easy"])
        ret = cmd_verify(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "UNKNOWN" in out

    def test_verify_with_evidence(self, tmp_db, capsys):
        _seeded_db(tmp_db)
        args = _args(db=tmp_db, statement=["Python", "was", "created", "by", "Guido"])
        ret = cmd_verify(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Verdict" in out

    def test_verify_empty(self, capsys):
        args = _args(statement=[""])
        ret = cmd_verify(args)
        assert ret == 1


class TestCmdTrends:
    def test_trends_empty(self, tmp_db, capsys):
        args = _args(db=tmp_db)
        ret = cmd_trends(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "empty" in out.lower()

    def test_trends_with_data(self, tmp_db, capsys):
        _seeded_db(tmp_db)
        args = _args(db=tmp_db)
        ret = cmd_trends(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Total claims" in out or "claims" in out.lower()


class TestCmdStats:
    def test_stats_empty(self, tmp_db, capsys):
        args = _args(db=tmp_db)
        ret = cmd_stats(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Oracle Protocol" in out

    def test_stats_with_data(self, tmp_db, capsys):
        _seeded_db(tmp_db)
        args = _args(db=tmp_db)
        ret = cmd_stats(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Claims" in out


class TestCmdExport:
    def test_export_stdout(self, tmp_db, capsys):
        _seeded_db(tmp_db)
        args = _args(db=tmp_db, output=None)
        ret = cmd_export(args)
        assert ret == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["claim_count"] >= 1
        assert "claims" in data

    def test_export_to_file(self, tmp_db, tmp_path, capsys):
        _seeded_db(tmp_db)
        outfile = str(tmp_path / "export.json")
        args = _args(db=tmp_db, output=outfile)
        ret = cmd_export(args)
        assert ret == 0
        data = json.loads(Path(outfile).read_text(encoding="utf-8"))
        assert data["claim_count"] >= 1


class TestCmdForget:
    def test_forget_nothing(self, tmp_db, capsys):
        args = _args(db=tmp_db, query=["nonexistent"])
        ret = cmd_forget(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "no matching" in out.lower()

    def test_forget_empty(self, capsys):
        args = _args(query=[""])
        ret = cmd_forget(args)
        assert ret == 1


class TestCmdDemo:
    def test_demo_runs(self, capsys):
        args = _args()
        ret = cmd_demo(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Demo complete" in out
        assert "oracle remember" in out.lower() or "remember" in out.lower()


# ── Main entry point ─────────────────────────────────────────────────────

class TestMain:
    def test_no_command_shows_help(self, capsys):
        ret = main([])
        assert ret == 0

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_demo_via_main(self, capsys):
        ret = main(["--db", ":memory:", "demo"])
        assert ret == 0

    def test_remember_via_main(self, tmp_path, capsys):
        db = str(tmp_path / "test.db")
        ret = main(["--db", db, "--user", "tester", "remember", "test fact"])
        assert ret == 0

    def test_ask_via_main(self, tmp_path, capsys):
        db = str(tmp_path / "test.db")
        main(["--db", db, "--user", "t", "remember", "hello world"])
        ret = main(["--db", db, "--user", "t", "ask", "hello"])
        assert ret == 0


class TestParser:
    def test_parser_creates(self):
        parser = build_parser()
        assert parser.prog == "oracle"

    def test_parse_ask(self):
        parser = build_parser()
        args = parser.parse_args(["ask", "test", "question"])
        assert args.command == "ask"
        assert args.question == ["test", "question"]

    def test_parse_verify(self):
        parser = build_parser()
        args = parser.parse_args(["verify", "some", "statement"])
        assert args.command == "verify"

    def test_parse_remember_public(self):
        parser = build_parser()
        args = parser.parse_args(["remember", "--public", "a", "fact"])
        assert args.public is True

    def test_parse_export_output(self):
        parser = build_parser()
        args = parser.parse_args(["export", "-o", "out.json"])
        assert args.output == "out.json"
