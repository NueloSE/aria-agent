"""Strategy gate tests — synthetic scenarios + real fixtures, never live calls."""
from __future__ import annotations

from datetime import datetime, timezone

from aria import config
from aria.models import Decision, MarketSnapshot, PortfolioState, Position
from aria.strategies import narrative_rotation, preservation, refine
from aria.strategies.mean_reversion import propose as mr_propose
from aria.signals.client import fetch_snapshot_from_fixtures

NOW = datetime.now(timezone.utc)


def snapshot_with(narratives: list[dict], quotes: dict[str, dict]) -> MarketSnapshot:
    return MarketSnapshot(timestamp=NOW, narratives=narratives, token_quotes=quotes)


def portfolio(positions: list[Position] | None = None) -> PortfolioState:
    return PortfolioState(
        timestamp=NOW, total_value_usd=100.0, peak_value_usd=100.0,
        stable_balance_usd=100.0, positions=positions or [],
    )


def narrative(name: str, pct_7d: str, coins: list[str]) -> dict:
    return {
        "categoryName": name,
        "marketCapChangePercentage7d": pct_7d,
        "topCoinList": {"headers": ["coinSymbol"], "rows": [[c] for c in coins]},
    }


GOOD_QUOTE = {"price": 1.0, "volume_24h": 50_000_000}
THIN_QUOTE = {"price": 1.0, "volume_24h": 1_000}


class TestNarrativeGates:
    def test_happy_path_picks_top_eligible_liquid(self):
        snap = snapshot_with(
            [narrative("AI", "+8.5%", ["FET", "CAKE", "LINK"])],
            {"FET": GOOD_QUOTE, "CAKE": GOOD_QUOTE, "LINK": GOOD_QUOTE},
        )
        p = narrative_rotation.propose(snap, portfolio())
        assert p.action == "buy"
        assert p.token_symbol == "FET"
        assert p.stop_loss_pct == config.NR_STOP_LOSS_PCT
        assert p.size_pct <= config.MAX_POSITION_PCT

    def test_negative_momentum_narrative_skipped(self):
        snap = snapshot_with(
            [narrative("Dying", "-12%", ["FET"]), narrative("Rising", "+5%", ["CAKE"])],
            {"FET": GOOD_QUOTE, "CAKE": GOOD_QUOTE},
        )
        p = narrative_rotation.propose(snap, portfolio())
        assert p.token_symbol == "CAKE"
        assert "Dying" in p.rationale

    def test_all_narratives_negative_holds(self):
        snap = snapshot_with([narrative("Dying", "-12%", ["FET"])], {"FET": GOOD_QUOTE})
        p = narrative_rotation.propose(snap, portfolio())
        assert p.action == "hold"

    def test_ineligible_token_excluded(self):
        # BTC is NOT on the official list — must never survive, however liquid
        snap = snapshot_with(
            [narrative("L1", "+5%", ["BTC", "CAKE"])],
            {"BTC": GOOD_QUOTE, "CAKE": GOOD_QUOTE},
        )
        p = narrative_rotation.propose(snap, portfolio())
        assert p.token_symbol == "CAKE"
        assert "BTC: not on eligible list" in p.rationale

    def test_stables_not_rotation_targets(self):
        snap = snapshot_with(
            [narrative("Stables", "+1%", ["USDT", "CAKE"])],
            {"USDT": GOOD_QUOTE, "CAKE": GOOD_QUOTE},
        )
        p = narrative_rotation.propose(snap, portfolio())
        assert p.token_symbol == "CAKE"

    def test_no_quote_data_means_no_trade(self):
        snap = snapshot_with([narrative("AI", "+5%", ["FET"])], {})
        p = narrative_rotation.propose(snap, portfolio())
        assert p.action == "hold"
        assert "no quote data" in p.rationale

    def test_thin_liquidity_excluded(self):
        snap = snapshot_with([narrative("AI", "+5%", ["FET"])], {"FET": THIN_QUOTE})
        p = narrative_rotation.propose(snap, portfolio())
        assert p.action == "hold"

    def test_brain_preference_honored_when_valid(self):
        snap = snapshot_with(
            [narrative("AI", "+5%", ["FET", "CAKE"])],
            {"FET": GOOD_QUOTE, "CAKE": GOOD_QUOTE},
        )
        p = narrative_rotation.propose(snap, portfolio(), preferred_token="CAKE")
        assert p.token_symbol == "CAKE"
        assert "honored" in p.rationale

    def test_brain_preference_overridden_when_invalid(self):
        snap = snapshot_with([narrative("AI", "+5%", ["FET"])], {"FET": GOOD_QUOTE})
        p = narrative_rotation.propose(snap, portfolio(), preferred_token="SCAMCOIN")
        assert p.token_symbol == "FET"
        assert "did NOT survive" in p.rationale

    def test_no_averaging_into_held_position(self):
        pos = Position(token_symbol="FET", amount=10, entry_price_usd=1.0, opened_at=NOW)
        snap = snapshot_with([narrative("AI", "+5%", ["FET"])], {"FET": GOOD_QUOTE})
        p = narrative_rotation.propose(snap, portfolio([pos]))
        assert p.action == "hold"
        assert "already holding" in p.rationale


class TestPreservation:
    def test_with_positions_closes_all(self):
        pos = Position(token_symbol="CAKE", amount=10, entry_price_usd=1.0, opened_at=NOW)
        p = preservation.propose(portfolio([pos]))
        assert p.action == "close_all"

    def test_in_stables_holds(self):
        p = preservation.propose(portfolio())
        assert p.action == "hold"


class TestMeanReversionDisabled:
    def test_always_holds(self):
        snap = fetch_snapshot_from_fixtures()
        assert mr_propose(snap, portfolio()).action == "hold"


class TestRefineRouter:
    async def test_brain_buy_gets_gated(self):
        """Brain says buy an ineligible token in narrative mode -> gates replace it."""
        snap = snapshot_with([narrative("AI", "+5%", ["FET"])], {"FET": GOOD_QUOTE})
        d = Decision(regime="trending", mode="narrative_rotation", action="buy",
                     token_symbol="BTC", size_pct=10, stop_loss_pct=5,
                     confidence=0.8, reasoning="brain says BTC")
        refined = await refine(d, snap, portfolio())
        assert refined.token_symbol == "FET"
        assert refined.regime == "trending"          # brain's regime kept
        assert "brain says BTC" in refined.reasoning  # audit trail merged

    async def test_preservation_close_all_without_positions_becomes_hold(self):
        snap = fetch_snapshot_from_fixtures()
        d = Decision(regime="high_risk", mode="preservation", action="close_all",
                     confidence=0.9, reasoning="panic")
        refined = await refine(d, snap, portfolio())
        assert refined.action == "hold"   # nothing to close

    async def test_fixture_extreme_fear_end_to_end(self):
        """Real fixture (F&G=15) through brain-mock semantics: preservation hold."""
        snap = fetch_snapshot_from_fixtures()
        d = Decision(regime="high_risk", mode="preservation", action="hold",
                     confidence=0.9, reasoning="extreme fear")
        refined = await refine(d, snap, portfolio())
        assert refined.action == "hold"
