"""Strategy gate tests — synthetic scenarios + real fixtures, never live calls."""
from __future__ import annotations

from datetime import datetime, timezone

from aria import config
from aria.models import Decision, MarketSnapshot, PortfolioState, Position
from aria.strategies import narrative_rotation, preservation, refine
from aria.strategies.mean_reversion import propose as mr_propose
from aria.strategies.breakout import propose as bo_propose
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


class TestMeanReversionReclaim:
    """Counter-trend oversold-reclaim — works in any regime, never catches knives."""

    def _snap(self, quotes: dict[str, dict]) -> MarketSnapshot:
        return MarketSnapshot(timestamp=NOW, token_quotes=quotes)

    def test_oversold_reclaim_buys(self):
        # ETH washed out (7d -14%, 30d -20%) AND turning up (24h +1.2%)
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_24h": 1.2, "percent_change_7d": -14.0,
                                   "percent_change_30d": -20.0, "volume_24h": "9 B"}})
        p = mr_propose(snap, portfolio())
        assert p.action == "buy"
        assert p.token_symbol == "ETH"
        assert p.target_pct == config.MR_TARGET_PCT

    def test_no_reclaim_holds_no_knife(self):
        # washed out but STILL falling (24h -3%) -> never catch the knife
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_24h": -3.0, "percent_change_7d": -14.0,
                                   "percent_change_30d": -20.0, "volume_24h": "9 B"}})
        p = mr_propose(snap, portfolio())
        assert p.action == "hold"
        assert "no reclaim" in p.rationale

    def test_not_washed_out_holds(self):
        # turning up but not actually oversold -> no setup
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_24h": 1.2, "percent_change_7d": -2.0,
                                   "percent_change_30d": -3.0, "volume_24h": "9 B"}})
        assert mr_propose(snap, portfolio()).action == "hold"

    def test_thin_liquidity_excluded(self):
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_24h": 1.2, "percent_change_7d": -14.0,
                                   "percent_change_30d": -20.0, "volume_24h": "100 K"}})
        assert mr_propose(snap, portfolio()).action == "hold"

    def test_dead_cat_1h_rolling_over_rejected(self):
        # washed + up on the day, but DUMPING this hour -> dead-cat guard rejects it
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_1h": -3.0, "percent_change_24h": 1.2,
                                   "percent_change_7d": -8.0, "percent_change_30d": -20.0,
                                   "volume_24h": "9 B"}})
        p = mr_propose(snap, portfolio())
        assert p.action == "hold"
        assert "rolling over" in p.rationale

    def test_volume_collapse_rejected(self):
        # clean reclaim but volume COLLAPSING -> weak bounce, rejected
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_1h": 0.3, "percent_change_24h": 1.2,
                                   "percent_change_7d": -8.0, "percent_change_30d": -20.0,
                                   "volume_change_24h": -60.0, "volume_24h": "9 B"}})
        p = mr_propose(snap, portfolio())
        assert p.action == "hold"
        assert "volume collapsing" in p.rationale

    def test_prefers_live_bounce_on_rising_volume(self):
        # two valid setups; the one reclaiming on rising volume + a live 1h wins
        base = {"percent_change_24h": 1.2, "percent_change_7d": -8.0,
                "percent_change_30d": -20.0, "volume_24h": "9 B"}
        snap = self._snap({
            "ETH": {"symbol": "ETH", "price": 1600.0, "percent_change_1h": 0.1,
                    "volume_change_24h": -10.0, **base},        # fading
            "LINK": {"symbol": "LINK", "price": 12.0, "percent_change_1h": 1.5,
                     "volume_change_24h": 40.0, **base},        # accumulation
        })
        p = mr_propose(snap, portfolio())
        assert p.action == "buy" and p.token_symbol == "LINK"

    # quality gates (the IP failure mode)
    _CLEAN = {"symbol": "ETH", "price": 1600.0, "percent_change_1h": 0.3,
              "percent_change_24h": 1.2, "percent_change_7d": -8.0,
              "percent_change_30d": -20.0, "volume_24h": "9 B"}

    def test_micro_cap_rank_excluded(self):
        snap = self._snap({"ETH": {**self._CLEAN, "rank": 400}})
        p = mr_propose(snap, portfolio())
        assert p.action == "hold" and "too small" in p.rationale

    def test_structurally_broken_1y_excluded(self):
        # a dying token (1y -90%) is a falling knife, not a reversion — like IP
        snap = self._snap({"ETH": {**self._CLEAN, "rank": 20, "percent_change_1y": -90.0}})
        p = mr_propose(snap, portfolio())
        assert p.action == "hold" and "structurally broken" in p.rationale

    def test_quality_oversold_not_over_filtered(self):
        # rank-20, washed but alive on the year -> still a valid buy
        snap = self._snap({"ETH": {**self._CLEAN, "rank": 20,
                                   "percent_change_1y": -40.0, "percent_change_90d": -20.0}})
        p = mr_propose(snap, portfolio())
        assert p.action == "buy" and p.token_symbol == "ETH"

    def test_early_1h_reclaim_buys_even_if_24h_flat(self):
        # 24h still slightly red, but turning up THIS hour -> broadened reclaim catches it
        snap = self._snap({"ETH": {"symbol": "ETH", "price": 1600.0,
                                   "percent_change_1h": 0.8, "percent_change_24h": -0.2,
                                   "percent_change_7d": -8.0, "percent_change_30d": -20.0,
                                   "volume_24h": "9 B"}})
        p = mr_propose(snap, portfolio())
        assert p.action == "buy" and p.token_symbol == "ETH"


class TestBreakout:
    """Momentum breakout — buy quality tokens breaking UP on real volume."""

    def _snap(self, quotes: dict[str, dict]) -> MarketSnapshot:
        return MarketSnapshot(timestamp=NOW, token_quotes=quotes)

    _MOVE = {"symbol": "ETH", "price": 1600.0, "percent_change_1h": 0.5,
             "percent_change_24h": 6.0, "percent_change_7d": 3.0,
             "volume_change_24h": 40.0, "volume_24h": "9 B", "rank": 2}

    def test_breakout_on_volume_buys(self):
        p = bo_propose(self._snap({"ETH": self._MOVE}), portfolio())
        assert p.action == "buy" and p.token_symbol == "ETH"

    def test_weak_volume_rejected(self):
        snap = self._snap({"ETH": {**self._MOVE, "volume_change_24h": 5.0}})
        assert bo_propose(snap, portfolio()).action == "hold"

    def test_not_moving_enough_holds(self):
        snap = self._snap({"ETH": {**self._MOVE, "percent_change_24h": 1.0}})
        assert bo_propose(snap, portfolio()).action == "hold"

    def test_micro_cap_excluded(self):
        snap = self._snap({"ETH": {**self._MOVE, "rank": 400}})
        assert bo_propose(snap, portfolio()).action == "hold"

    def test_already_ripped_excluded(self):
        snap = self._snap({"ETH": {**self._MOVE, "percent_change_7d": 60.0}})
        assert bo_propose(snap, portfolio()).action == "hold"


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
