"""Tests for cli/benchmark.py shared argument helpers."""

from __future__ import annotations

import argparse

import pytest

from cli.benchmark import _add_common_filter_args


class TestAddCommonFilterArgs:
    """_add_common_filter_args adds --split, --set, and --quiet uniformly."""

    def _make_parser(self, **kwargs):
        parser = argparse.ArgumentParser()
        _add_common_filter_args(parser, **kwargs)
        return parser

    def test_split_defaults_to_iteration(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        assert args.split == "iteration"

    def test_split_short_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["-s", "full"])
        assert args.split == "full"

    def test_split_long_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["--split", "full"])
        assert args.split == "full"

    def test_split_rejects_invalid(self):
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--split", "bogus"])

    def test_set_stored_as_frozen_set(self):
        parser = self._make_parser()
        args = parser.parse_args(["-S", "jeugd-1"])
        assert args.frozen_set == "jeugd-1"

    def test_set_long_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["--set", "jeugd-1"])
        assert args.frozen_set == "jeugd-1"

    def test_set_defaults_to_none(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        assert args.frozen_set is None

    def test_quiet_defaults_to_false(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        assert args.quiet is False

    def test_quiet_short_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["-q"])
        assert args.quiet is True

    def test_split_default_override(self):
        """Commands can override the split default (e.g. tune defaults to None)."""
        parser = self._make_parser(split_default=None)
        args = parser.parse_args([])
        assert args.split is None

    def test_all_flags_together(self):
        parser = self._make_parser()
        args = parser.parse_args(["-s", "full", "-S", "jeugd-1", "-q"])
        assert args.split == "full"
        assert args.frozen_set == "jeugd-1"
        assert args.quiet is True


class TestSubcommandConsistency:
    """The run and tune subcommands both get the common filter args."""

    @pytest.fixture()
    def benchmark_parser(self):
        from cli.benchmark import add_benchmark_subparser

        root = argparse.ArgumentParser()
        subs = root.add_subparsers()
        add_benchmark_subparser(subs)
        return root

    def test_run_has_set_flag(self, benchmark_parser):
        args = benchmark_parser.parse_args(["benchmark", "run", "-S", "jeugd-1"])
        assert args.frozen_set == "jeugd-1"

    def test_tune_has_set_flag(self, benchmark_parser):
        args = benchmark_parser.parse_args(["benchmark", "tune", "-S", "jeugd-1", "--params", "X=1"])
        assert args.frozen_set == "jeugd-1"

    def test_run_and_tune_split_same_dest(self, benchmark_parser):
        run_args = benchmark_parser.parse_args(["benchmark", "run", "-s", "full"])
        tune_args = benchmark_parser.parse_args(["benchmark", "tune", "-s", "full", "--params", "X=1"])
        assert run_args.split == tune_args.split == "full"

    def test_run_and_tune_quiet_same_dest(self, benchmark_parser):
        run_args = benchmark_parser.parse_args(["benchmark", "run", "-q"])
        tune_args = benchmark_parser.parse_args(["benchmark", "tune", "-q", "--params", "X=1"])
        assert run_args.quiet is True
        assert tune_args.quiet is True
