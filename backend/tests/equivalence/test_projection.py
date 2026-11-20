"""Verify archive integrity, compatibility registry and scripted v1 evidence."""

from __future__ import annotations

import importlib
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from living_island.sim.equivalence.projection import Projection, fixture_bytes, read_projection

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "backend/tests/fixtures/v1_projection"


@pytest.fixture(scope="module")
def generator():
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(ROOT / "scripts"))
        yield importlib.import_module("gen_v1_projections")


@pytest.fixture(scope="module")
def registry(generator):
    return generator.load_registry(ROOT)


def scripted(name: str) -> Projection:
    projection = read_projection(FIXTURES / "scripted" / f"{name}.json.gz")
    assert projection.case == name
    assert projection.scripted_evidence is not None
    return projection


def frame(projection: Projection, tick: int):
    return projection.frames[tick - projection.frames[0].tick]


def evidence(projection: Projection, tick: int) -> dict[str, Any]:
    assert projection.scripted_evidence is not None
    data = projection.scripted_evidence[tick - projection.frames[0].tick]
    assert data["tick"] == tick
    return data


def backoff(projection: Projection, tick: int, actor: str) -> list[dict[str, Any]]:
    return evidence(projection, tick)["policy_states"][actor]["failed_targets"]


def packet(projection: Projection, tick: int, actor: str = "ella") -> dict[str, Any]:
    return next(p for p in evidence(projection, tick)["deliveries"] if p["actor_id"] == actor)


def result(projection: Projection, tick: int, actor: str = "ella"):
    return next(item for item in frame(projection, tick).outcomes if item.actor_id == actor)


def resident(projection: Projection, tick: int, actor: str = "ella"):
    return next(person for person in frame(projection, tick).residents if person.id == actor)


def queue(projection: Projection, tick: int, actor: str = "ella") -> list[str]:
    return [
        intent["action_type"]
        for plan in evidence(projection, tick)["queued_plans"]
        if plan["actor_id"] == actor
        for intent in plan["intents"]
    ]


def active(projection: Projection, tick: int, actor: str = "ella") -> list[str]:
    return [
        entry["intent"]["action_type"]
        for entry in evidence(projection, tick)["active_actions"]
        if entry["intent"]["actor_id"] == actor
    ]


def assert_identity(projection: Projection, generator, registry) -> None:
    _, expected = generator.effective(
        projection.config, *registry[projection.config], projection.source.seed
    )
    assert projection.source == expected


def test_matrix_fixture_set_and_provenance(generator, registry) -> None:
    cases = generator.matrix_cases()
    assert len(cases) == len({case.name for case in cases}) == 160
    assert sum(case.suite == "acceptance" for case in cases) == 20
    paths = set((FIXTURES / "matrix").glob("*.json.gz"))
    assert paths == {FIXTURES / "matrix" / f"{case.name}.json.gz" for case in cases}
    for case in cases:
        projection = read_projection(FIXTURES / "matrix" / f"{case.name}.json.gz")
        assert (projection.case, projection.config, projection.policy, projection.source.seed) == (
            case.name,
            case.config,
            case.variant,
            case.seed,
        )
        assert projection.frames[0].tick == 0
        assert projection.frames[-1].tick == 1008
        assert projection.scripted_evidence is None
        assert_identity(projection, generator, registry)


def test_scripted_fixture_set_and_provenance(generator, registry) -> None:
    from living_island.sim.equivalence.v1_extract import scripted_projections

    mechanics, _ = generator.effective("mechanics", *registry["mechanics"], 20261108)
    expected = {name: (config, seed) for name, config, seed, _ in scripted_projections(mechanics)}
    paths = set((FIXTURES / "scripted").glob("*.json.gz"))
    assert paths == {FIXTURES / "scripted" / f"{name}.json.gz" for name in expected}
    for name, (config, seed) in expected.items():
        projection = scripted(name)
        assert (projection.config, projection.source.seed) == (config, seed)
        assert_identity(projection, generator, registry)
        assert evidence(projection, projection.frames[-1].tick)


def test_substitutions_and_fixture_budget(generator, registry) -> None:
    configs = FIXTURES / "configs"
    assert {path.stem for path in configs.glob("*.toml")} == generator.SUBSTITUTIONS.keys()
    for name, (_, _, digest) in generator.SUBSTITUTIONS.items():
        raw = (configs / f"{name}.toml").read_bytes()
        assert raw == registry[name][0]
        assert sha256(raw).hexdigest() == digest
    assert sum(path.stat().st_size for path in FIXTURES.rglob("*") if path.is_file()) <= 50 << 20


def test_admission_refuses_before_v1_load(monkeypatch, generator, registry) -> None:
    raw, map_raw = registry["production"]

    def never(*args):
        pytest.fail("v1 must not load a refused config")

    monkeypatch.setattr(generator, "build_world_content", never)
    with pytest.raises(ValueError, match="unlisted config"):
        generator.effective("unlisted", raw, map_raw, 1)
    with pytest.raises(ValueError, match="config blob SHA-256"):
        generator.effective("production", raw + b"\n", map_raw, 1)
    with pytest.raises(ValueError, match="map blob SHA-256"):
        generator.effective("production", raw, map_raw + b"\n", 1)


def test_canonical_gzip_is_reproducible() -> None:
    case = "wap23-stamina-asleep-control"
    projection = scripted(case)
    data = (FIXTURES / "scripted" / f"{case}.json.gz").read_bytes()
    assert fixture_bytes(projection) == fixture_bytes(projection) == data


@pytest.mark.parametrize(
    ("need", "mode", "threshold"),
    [
        ("satiety", "awake", 3000),
        ("satiety", "asleep", 3000),
        ("hydration", "awake", 3000),
        ("hydration", "asleep", 3000),
        ("stamina", "awake", 2500),
    ],
)
def test_wap23_crossing_stays_in_one_band(need, mode, threshold) -> None:
    projection = scripted(f"wap23-{need}-{mode}-crossing")
    first, second = (packet(projection, tick) for tick in (0, 1))
    assert first["perception"]["own_condition"][need] == second["perception"]["own_condition"][need]
    assert (
        getattr(resident(projection, 0), need) > threshold >= getattr(resident(projection, 1), need)
    )
    assert "URGENT_NEED" in second["decision_triggers"]
    assert ("WOKE" in second["decision_triggers"]) == (mode == "asleep")
    if need == "stamina":
        # A successful wait leaves the old queue at the pre-ingest boundary.
        # The urgent trigger discards that queue when the policy next decides.
        assert queue(projection, 1) == ["wait"]
        old_id = evidence(projection, 1)["queued_plans"][0]["intents"][0]["intent_id"]
        assert old_id not in {e["intent_id"] for e in evidence(projection, 2)["events"]}
    else:
        assert queue(projection, 1) == []
    assert result(projection, 1).next_decision_tick == 1


def test_wap23_sleep_stamina_control() -> None:
    projection = scripted("wap23-stamina-asleep-control")
    assert resident(projection, 0).stamina < resident(projection, 1).stamina
    assert packet(projection, 1)["decision_triggers"] == []
    assert active(projection, 1) == ["sleep"]
    assert queue(projection, 1) == ["wait"]


def test_wap23_simultaneous_trigger_order() -> None:
    projection = scripted("wap23-priority-urgent-speech-sight")
    expected = [
        "ACTION_INTERRUPTED",
        "URGENT_NEED",
        "DIRECT_SPEECH",
        "NEW_SIGHT",
        "UTTERANCE_HEARD",
    ]
    assert packet(projection, 1)["decision_triggers"] == expected
    feedback = result(projection, 1)
    assert feedback.code == "URGENT_NEED"
    assert (
        next(d for d in frame(projection, 1).decisions if d.actor_id == "ella").triggers == expected
    )


@pytest.mark.parametrize(
    ("name", "actor", "code"),
    [
        ("dialogue-limit", "ryan", "DIALOGUE_LIMIT"),
        ("out-of-hearing", "ella", "OUT_OF_HEARING"),
        ("invalid-reply", "ryan", "INVALID_REPLY"),
    ],
)
def test_wap23_failed_accept_joins_and_discards_followup(name, actor, code) -> None:
    projection = scripted(f"wap23-reply-{name}")
    failure = result(projection, 2, actor)
    assert (failure.status, failure.code, failure.tick_started, failure.tick_finished) == (
        "failure",
        code,
        1,
        2,
    )
    observed = packet(projection, 2, actor)
    assert observed["perception"]["last_action_feedback"]["intent_id"] == failure.intent_id
    assert observed["decision_triggers"] == ["ACTION_FAILED"]
    assert queue(projection, 2, actor) == []
    assert backoff(projection, 3, actor) == [
        {
            "action": "talk",
            "target": {"id": "ryan" if actor == "ella" else "ella", "kind": "resident"},
            "code": code,
            "retry_after_tick": 38,
        }
    ]
    assert failure.next_decision_tick == 2


def test_wap23_request_and_first_reply() -> None:
    projection = scripted("wap23-reply-first-reply")
    request = frame(projection, 1).utterances[0]
    assert request.act == "request"
    assert request.request is not None and request.request.item_type == "fruit"
    assert frame(projection, 2).utterances[0].act == "accept"
    assert queue(projection, 2, "ryan") == ["give"]
    assert resident(projection, 3).fruit_count == 2


@pytest.mark.parametrize(
    ("name", "actor", "tick", "code"),
    [
        ("gather-empty-at-start", "ella", 1, "RESOURCE_TAKEN"),
        ("gather-last-fruit-contested", "ryan", 2, "RESOURCE_TAKEN"),
        ("gather-no-stamina", "ella", 1, "EXHAUSTED"),
        ("gather-no-room", "ella", 1, "INVENTORY_FULL"),
        ("give-same-tile", "ella", 1, "OUT_OF_REACH"),
        ("give-too-few-items", "ella", 1, "NO_ITEM"),
        ("pickup-contested-last-fruit", "ryan", 1, "ITEM_TAKEN"),
        ("fill-target-tree", "ella", 1, "INVALID_TARGET"),
        ("fill-target-canteen", "ella", 1, None),
        ("give-fruit-by-kind", "ella", 1, None),
        ("give-canteen-by-kind", "ella", 1, None),
    ],
)
def test_wap23_physical_actions(name, actor, tick, code) -> None:
    projection = scripted(f"wap23-{name}")
    outcome = result(projection, tick, actor)
    assert (outcome.status, outcome.code, outcome.tick_started) == (
        "success" if code is None else "failure",
        code,
        0,
    )
    if code:
        assert queue(projection, tick, actor) == []
        assert "ACTION_FAILED" in packet(projection, tick, actor)["decision_triggers"]
    elif name == "give-fruit-by-kind":
        assert resident(projection, tick, "ryan").fruit_count == 2
    elif name == "give-canteen-by-kind":
        assert frame(projection, tick).canteen.holder_id == "ryan"
    else:
        assert frame(projection, tick).canteen.servings == 2


@pytest.mark.parametrize(
    ("name", "status", "reason"),
    [("unfinished", "interrupted", "DEATH"), ("after-completion", "success", None)],
)
def test_wap23_death_preserves_world_result_without_delivery(name, status, reason) -> None:
    projection = scripted(f"wap23-death-{name}")
    outcome = result(projection, 1)
    assert (outcome.status, outcome.code, outcome.next_decision_tick) == (status, reason, None)
    assert not resident(projection, 1).alive
    assert queue(projection, 1) == []
    assert "ella" not in {entry["actor_id"] for entry in evidence(projection, 1)["deliveries"]}


@pytest.mark.parametrize(
    ("name", "giver", "end", "failure"),
    [
        ("completion-away", "ella", 3, "OUT_OF_REACH"),
        ("completion-returned", "ella", 3, None),
        ("one-tick-control", "ella", 1, "OUT_OF_REACH"),
        ("ryan-recipient-start-order", "ella", 1, "OUT_OF_REACH"),
        ("ella-recipient-start-order", "ryan", 3, None),
    ],
)
def test_wap27_give_start_and_completion_orders(name, giver, end, failure) -> None:
    projection = scripted(f"wap27-{name}")
    outcome = result(projection, end, giver)
    assert (outcome.tick_started, outcome.code) == (0, failure)
    assert outcome.next_decision_tick is not None
    for tick in range(1, end):
        assert active(projection, tick, giver) == ["give"]
        assert queue(projection, tick, giver) == ["wait"]
    if failure:
        assert queue(projection, end, giver) == []
        assert (
            packet(projection, end, giver)["perception"]["last_action_feedback"]["failure_code"]
            == failure
        )
        assert backoff(projection, end + 1, giver)[0]["code"] == failure
    else:
        recipient = "ryan" if giver == "ella" else "ella"
        assert resident(projection, end, recipient).fruit_count == 1


def test_wap28_spring_receipt_and_known_control() -> None:
    unknown = scripted("wap28-spring-unknown")
    assert result(unknown, 1).code == "OUT_OF_REACH"
    assert queue(unknown, 1) == []
    perception = packet(unknown, 1)["perception"]
    assert not any(tile["terrain"] == "spring" for tile in perception["explored_static_tiles"])
    state = evidence(unknown, 2)["policy_states"]["ella"]
    spring = {"x": 10, "y": 1}
    assert state["commitment"] is None or state["commitment"]["target"] != spring
    assert all(cue["position"] != spring for cue in state["cue_impressions"])
    known = scripted("wap28-spring-known-adjacent")
    assert result(known, 1).status == "success"
    assert resident(known, 1).hydration > resident(known, 0).hydration


@pytest.mark.parametrize(
    ("name", "speaker", "said"),
    [
        ("ella-speaker-enters-hearing", "ella", False),
        ("ryan-speaker-enters-hearing", "ryan", True),
        ("leaves-before-emission", "ella", False),
        ("in-hearing-at-both-checks", "ella", True),
    ],
)
def test_wap29_start_and_emission_hearing(name, speaker, said) -> None:
    projection = scripted(f"wap29-{name}")
    assert bool(frame(projection, 1).utterances) == said
    outcome = result(projection, 1, speaker)
    assert (outcome.tick_started, outcome.code) == (0, None if said else "OUT_OF_HEARING")
    assert (
        packet(projection, 1, speaker)["perception"]["last_action_feedback"]["intent_id"]
        == outcome.intent_id
    )
    assert queue(projection, 1, speaker) == (["wait"] if said else [])


def test_wap29_last_slot_resolves_next_to_wait() -> None:
    projection = scripted("wap23-wap29-two-talks-last-slot-with-wait")
    assert len(frame(projection, 1).utterances) == 1
    assert result(projection, 1, "mia").status == "success"
    assert [item.code for item in frame(projection, 1).outcomes].count("DIALOGUE_LIMIT") == 1


def test_wap30_successor_keeps_queue() -> None:
    projection = scripted("wap30-interruption-long-successor")
    assert result(projection, 1).status == "interrupted"
    assert result(projection, 1).next_decision_tick == 1
    for tick in (2, 3, 4):
        assert active(projection, tick) == ["sleep"]
        assert queue(projection, tick) == ["wait"]
        assert packet(projection, tick)["perception"]["last_action_feedback"] is None


@pytest.mark.parametrize(
    ("name", "tick", "code"), [("early", 1, "URGENT_NEED"), ("natural", 48, None)]
)
def test_wap32_final_sleep_interval_does_not_hear(name, tick, code) -> None:
    projection = scripted(f"wap23-wap32-{name}-wake-no-speech")
    assert result(projection, tick).code == code
    assert frame(projection, tick).utterances[0].addressee == "ella"
    assert not packet(projection, tick)["perception"]["heard_utterances"]
    assert "WOKE" in packet(projection, tick)["decision_triggers"]


def test_wap32_daylight_extends_footprint_while_sleeping() -> None:
    projection = scripted("wap23-wap32-daylight-footprint")
    before = packet(projection, 143)["perception"]["explored_static_tiles"]
    after = packet(projection, 144)["perception"]["explored_static_tiles"]
    assert len(after) > len(before)
    assert active(projection, 144) == ["sleep"]


def test_wap32_wap35_restore_defers_sight_and_retains_failure_evidence() -> None:
    projection = scripted("wap23-wap32-wap35-corpse-restore-before-wake")
    assert active(projection, 1) == ["sleep"]
    assert packet(projection, 1)["decision_triggers"] == ["NEW_SIGHT"]
    assert evidence(projection, 1)["restored"]
    receipts = next(r for r in evidence(projection, 1)["receipts"] if r["resident_id"] == "ella")
    assert "corpse@ryan" in {r["entity_id"] for r in receipts["entities"]}
    assert "NEW_SIGHT" not in packet(projection, 3)["decision_triggers"]
    decision = next(d for d in frame(projection, 3).decisions if d.actor_id == "ella")
    assert decision.triggers == ["ACTION_INTERRUPTED", "URGENT_NEED", "NEW_SIGHT", "WOKE"]
    assert result(projection, 4).code == "OUT_OF_HEARING"
    assert queue(projection, 4) == []
    assert backoff(projection, 5, "ella")[0]["code"] == "OUT_OF_HEARING"


@pytest.mark.parametrize("kind", ["move", "gather"])
def test_wap33_en23_exhaustion_does_not_enter_shuffle(kind) -> None:
    projection = scripted(f"wap23-wap33-en23-{kind}-exhaustion")
    assert result(projection, 1).code == "EXHAUSTED"
    assert resident(projection, 0).stamina == 1
    assert resident(projection, 1).stamina == 0
    assert {outcome.actor_id for outcome in frame(projection, 2).outcomes} == {"ryan"}
    assert len({evidence(projection, tick)["rng"] for tick in (0, 1, 2)}) == 1


@pytest.mark.parametrize(
    ("name", "code"),
    [("path-blocked-then-death", "PATH_BLOCKED"), ("exhaustion-and-death", "DEATH")],
)
def test_wap33_death_priority(name, code) -> None:
    projection = scripted(f"wap33-{name}")
    assert result(projection, 1).code == code
    assert not resident(projection, 1).alive


def test_wap35_legacy_novelty_is_by_identity() -> None:
    fruit = scripted("wap35-first-held-fruit-during-move")
    assert resident(fruit, 1).fruit_count == 1
    assert active(fruit, 1) == ["move_to"]
    assert queue(fruit, 1) == ["wait"]
    assert packet(fruit, 1)["decision_triggers"] == []
    canteen = scripted("wap35-first-held-canteen-during-move")
    assert resident(canteen, 1).canteen_id == "canteen_01"
    assert result(canteen, 1).code == "NEW_SIGHT"
    cue = scripted("wap35-near-cue-upgrade")
    for tick, detail in ((0, "distant"), (1, "near")):
        assert packet(cue, tick)["perception"]["environmental_cues"][0]["detail_level"] == detail
    assert packet(cue, 1)["decision_triggers"] == ["NEW_SIGHT"]
    split = scripted("wap35-known-ground-fruit-quantity-reduced")
    assert frame(split, 1).ground_fruit[0].quantity == 1
    assert packet(split, 1)["decision_triggers"] == []
    merged = scripted("wap35-ground-fruit-merged-on-death")
    assert frame(merged, 1).ground_fruit[0].quantity == 3
    initial, after = (packet(merged, tick)["perception"] for tick in (0, 1))
    known = {entity["entity_id"] for entity in initial["visible_entities"]}
    assert {entity["entity_id"] for entity in after["visible_entities"]} - known == {"corpse@ryan"}
    water = scripted("wap35-nested-water-no-novelty")
    assert frame(water, 1).canteen.servings == 1
    assert packet(water, 1)["decision_triggers"] == []


def test_ct15_and_ct17_bound_configuration_behavior() -> None:
    for name, stocks in (("regrowth-2", [5, 5]), ("regrowth-0", [3, 4])):
        projection = scripted(f"ct15-ct17-{name}")
        assert [tree.stock for tree in frame(projection, 143).trees[:2]] == [3, 4]
        assert [tree.stock for tree in frame(projection, 168).trees[:2]] == stocks
    gathering = scripted("ct17-one-tick-gather")
    assert result(gathering, 1).status == "success"
    assert [
        event["payload"]["amount"]
        for event in evidence(gathering, 1)["events"]
        if event["type"] == "stamina_action_cost_applied"
    ] == [300]
    for servings in (0, 1, 2):
        canteen = scripted(f"ct17-canteen-{servings}-servings")
        assert frame(canteen, 0).canteen.servings == servings
        assert resident(canteen, 0).canteen_servings == servings
    for projection, names in (
        (
            scripted("wap23-ct15-refused-profiles"),
            {"talk-ticks-2", "sleep-ticks-60", "fruit-few-max-3"},
        ),
        (canteen, {"canteen-3-servings", "canteen-3999-servings"}),
    ):
        failures = evidence(projection, 0)["registry_rejections"]
        assert {failure["case"] for failure in failures} == names
        assert all("config blob SHA-256" in failure["error"] for failure in failures)
