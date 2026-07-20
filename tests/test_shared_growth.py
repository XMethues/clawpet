import math
import unittest

from clawchat_pet.growth import GrowthEvent, SharedGrowth


class SharedGrowthInterfaceTests(unittest.TestCase):
    def test_fresh_snapshot_exposes_only_scene_neutral_growth_slots(self):
        growth = SharedGrowth.fresh(clock=lambda: 1_000.0)

        observed = growth.observe()

        self.assertEqual(0, observed.stage.index)
        self.assertEqual("minor", observed.stage.kind)
        self.assertEqual(
            {
                "primary",
                "stability",
                "risk",
                "insight",
                "fortune",
                "strain",
            },
            set(observed.dimensions),
        )
        self.assertEqual("balanced", observed.strategy.id)
        self.assertEqual(
            ("balanced", "advance", "stabilize", "learn", "recover"),
            observed.strategy.choices,
        )
        self.assertEqual("born", observed.recent_facts[-1].kind)

    def test_current_serialized_format_is_validated_at_the_module_boundary(self):
        with self.assertRaisesRegex(ValueError, "invalid shared growth state"):
            SharedGrowth.load({"version": 1}, clock=lambda: 1_000.0)

    def test_success_event_round_trips_as_scene_neutral_growth(self):
        now = 1_000.0
        growth = SharedGrowth.fresh(clock=lambda: now)

        status = growth.apply(
            GrowthEvent(
                event_id="success-1",
                occurred_at=now,
                kind="work_succeeded",
                capability_id="file-inspection",
            )
        )
        observed = growth.observe()

        self.assertEqual("accepted", status)
        self.assertEqual(2.4, observed.dimensions["primary"].value)
        self.assertEqual("work_succeeded", observed.recent_facts[-1].kind)
        self.assertEqual(
            "file-inspection", observed.recent_facts[-1].capability_id
        )
        self.assertEqual(2.4, observed.recent_facts[-1].data["primary_gain"])

        reloaded = SharedGrowth.load(growth.serialize(), clock=lambda: now)
        self.assertEqual(observed, reloaded.observe())

    def test_nonfinite_event_time_is_rejected_before_state_changes(self):
        growth = SharedGrowth.fresh(clock=lambda: 1_000.0)

        with self.assertRaisesRegex(ValueError, "occurred_at must be finite"):
            growth.apply(
                GrowthEvent(
                    event_id="bad-time",
                    occurred_at=math.nan,
                    kind="work_succeeded",
                    capability_id="file-inspection",
                )
            )

        self.assertEqual(
            SharedGrowth.fresh(clock=lambda: 1_000.0).observe(),
            growth.observe(),
        )

    def test_strategy_selection_is_scene_neutral_and_explicit(self):
        growth = SharedGrowth.fresh(clock=lambda: 1_000.0)

        growth.select_strategy("advance")
        observed = growth.observe()

        self.assertEqual("advance", observed.strategy.id)
        self.assertEqual("strategy_selected", observed.recent_facts[-1].kind)
        self.assertEqual(
            "advance", observed.recent_facts[-1].data["strategy_id"]
        )
        with self.assertRaisesRegex(ValueError, "unknown strategy"):
            growth.select_strategy("rush")

    def test_observation_settles_idle_time_once(self):
        now = [1_000.0]
        growth = SharedGrowth.fresh(clock=lambda: now[0])
        now[0] += 2 * 86_400

        first = growth.observe()
        second = growth.observe()

        self.assertEqual(2, first.dormancy.stage)
        self.assertEqual(0.75, first.dimensions["risk"].value)
        self.assertEqual(0.93, first.dimensions["stability"].value)
        self.assertEqual(first, second)
        self.assertEqual(
            ("idle_decay", "idle_decay"),
            tuple(fact.kind for fact in first.recent_facts[-2:]),
        )

    def test_idle_milestones_apply_the_selected_strategy_profile(self):
        now = [1_000.0]
        growth = SharedGrowth.fresh(clock=lambda: now[0])
        growth.apply(
            GrowthEvent(
                event_id="success-1",
                occurred_at=now[0],
                kind="work_succeeded",
                capability_id="file-inspection",
            )
        )
        now[0] += 4 * 86_400

        observed = growth.observe()

        self.assertEqual(4, observed.dormancy.stage)
        self.assertEqual(1.9, observed.dimensions["primary"].value)
        self.assertEqual(3.25, observed.dimensions["risk"].value)
        self.assertEqual(0.75, observed.dimensions["stability"].value)

    def test_failure_event_is_settled_once(self):
        growth = SharedGrowth.fresh(clock=lambda: 1_000.0)
        failed = GrowthEvent(
            event_id="failure-1",
            occurred_at=1_000.0,
            kind="work_failed",
            capability_id="command-execution",
        )

        self.assertEqual("accepted", growth.apply(failed))
        first = growth.observe()
        self.assertEqual("duplicate", growth.apply(failed))
        second = growth.observe()

        self.assertEqual(3.38, first.dimensions["risk"].value)
        self.assertEqual(1.12, first.dimensions["strain"].value)
        self.assertEqual("work_failed", first.recent_facts[-1].kind)
        self.assertEqual(first, second)

    def test_work_builds_scene_neutral_capability_and_asset_progress(self):
        growth = SharedGrowth.fresh(clock=lambda: 1_000.0)

        growth.apply(
            GrowthEvent(
                event_id="start-1",
                occurred_at=1_000.0,
                kind="work_started",
                capability_id="file-inspection",
            )
        )
        growth.apply(
            GrowthEvent(
                event_id="success-1",
                occurred_at=1_001.0,
                kind="work_succeeded",
                capability_id="file-inspection",
            )
        )
        observed = growth.observe()

        self.assertEqual(0.0, observed.dimensions["strain"].value)
        self.assertEqual(2.8, observed.capabilities["file-inspection"].xp)
        self.assertEqual(1.7, observed.assets["file-inspection"].xp)

    def test_growth_advances_stage_without_scene_names(self):
        growth = SharedGrowth.fresh(clock=lambda: 1_000.0)
        for index in range(13):
            growth.apply(
                GrowthEvent(
                    event_id=f"success-{index}",
                    occurred_at=1_000.0 + index,
                    kind="work_succeeded",
                    capability_id="file-inspection",
                )
            )

        observed = growth.observe()

        self.assertEqual(1, observed.stage.index)
        self.assertEqual(0.0, observed.dimensions["primary"].value)
        advanced = [
            fact for fact in observed.recent_facts if fact.kind == "stage_advanced"
        ]
        self.assertEqual(1, len(advanced))
        self.assertEqual({"from_index": 0, "to_index": 1}, advanced[0].data)


if __name__ == "__main__":
    unittest.main()
