"""Tests for cli/album.py — ingest and rescan subcommand parsing."""

from __future__ import annotations

import argparse

import pytest

from cli.album import add_album_subparser


@pytest.fixture()
def album_parser():
    root = argparse.ArgumentParser()
    subs = root.add_subparsers(dest="command")
    add_album_subparser(subs)
    return root


class TestAlbumIngestParsing:
    def test_ingest_requires_source(self, album_parser):
        with pytest.raises(SystemExit):
            album_parser.parse_args(["album", "ingest"])

    def test_ingest_parses_source(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/some/dir"])
        assert args.source == "/some/dir"

    def test_ingest_limit_flag(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/dir", "--limit", "10"])
        assert args.limit == 10

    def test_ingest_limit_short_flag(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/dir", "-n", "5"])
        assert args.limit == 5

    def test_ingest_album_label_flag(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/dir", "--album-label", "Race"])
        assert args.album_label == "Race"

    def test_ingest_album_id_flag(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/dir", "--album-id", "abc123"])
        assert args.album_id == "abc123"

    def test_ingest_limit_defaults_to_none(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/dir"])
        assert args.limit is None

    def test_ingest_has_cmd(self, album_parser):
        args = album_parser.parse_args(["album", "ingest", "/dir"])
        assert hasattr(args, "_cmd")


class TestAlbumRescanParsing:
    def test_rescan_requires_identifier(self, album_parser):
        with pytest.raises(SystemExit):
            album_parser.parse_args(["album", "rescan"])

    def test_rescan_parses_identifier(self, album_parser):
        args = album_parser.parse_args(["album", "rescan", "6dde41fd"])
        assert args.identifier == "6dde41fd"

    def test_rescan_parses_index(self, album_parser):
        args = album_parser.parse_args(["album", "rescan", "47"])
        assert args.identifier == "47"

    def test_rescan_has_cmd(self, album_parser):
        args = album_parser.parse_args(["album", "rescan", "6dde41fd"])
        assert hasattr(args, "_cmd")


class TestExistingSubcommands:
    def test_list_still_works(self, album_parser):
        args = album_parser.parse_args(["album", "list"])
        assert args.album_command == "list"

    def test_forget_still_works(self, album_parser):
        args = album_parser.parse_args(["album", "forget", "abc"])
        assert args.album_id == "abc"
