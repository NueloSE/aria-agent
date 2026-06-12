"""Signal layer tests — fixtures only, never live calls (hard rule)."""
from __future__ import annotations

from aria.signals.client import fetch_snapshot_from_fixtures
from aria.signals.parsing import parse_float, parse_pct, parse_usd


class TestParsing:
    def test_usd_trillions(self):
        assert parse_usd("2.15 T") == 2.15e12

    def test_usd_billions_with_symbol(self):
        assert parse_usd("$75.6B") == 75.6e9

    def test_usd_millions(self):
        assert parse_usd("294.15 M") == 294.15e6

    def test_usd_plain_number(self):
        assert parse_usd(1234.5) == 1234.5

    def test_usd_garbage(self):
        assert parse_usd("Extreme fear") is None

    def test_pct_positive(self):
        assert parse_pct("+0.24838%") == 0.24838

    def test_pct_negative(self):
        assert parse_pct("-3.86%") == -3.86

    def test_pct_garbage(self):
        assert parse_pct("n/a") is None

    def test_float_plain(self):
        assert parse_float("590.63") == 590.63


class TestFixtureSnapshot:
    """Composed from the REAL Stage-1 captures — same composer as the live path."""

    def test_snapshot_builds(self):
        snap = fetch_snapshot_from_fixtures()
        assert snap.timestamp is not None

    def test_fear_greed_extracted(self):
        snap = fetch_snapshot_from_fixtures()
        assert snap.fear_greed_index == 15
        assert snap.fear_greed_label == "Extreme fear"

    def test_mcap_changes_are_floats(self):
        snap = fetch_snapshot_from_fixtures()
        assert isinstance(snap.total_mcap_change_24h_pct, float)
        assert isinstance(snap.total_mcap_change_7d_pct, float)

    def test_narratives_are_dicts_with_names(self):
        snap = fetch_snapshot_from_fixtures()
        assert len(snap.narratives) > 0
        assert all("categoryName" in n for n in snap.narratives)

    def test_quotes_keyed_by_symbol(self):
        # fixture is the multi-id table shape (ETH, CAKE, LINK, USDT, USDC)
        snap = fetch_snapshot_from_fixtures()
        for sym in ("ETH", "CAKE", "LINK", "USDT", "USDC"):
            assert sym in snap.token_quotes, f"missing {sym}"
        assert snap.token_quotes["ETH"]["price"] > 0

    def test_macro_events_flattened(self):
        snap = fetch_snapshot_from_fixtures()
        assert len(snap.macro_events) > 0
        assert all("_source" in e for e in snap.macro_events)

    def test_optional_payloads_present(self):
        snap = fetch_snapshot_from_fixtures()
        assert snap.mcap_ta            # captured fixture exists
        assert snap.derivatives
