"""Report the first unequal field at a committed boundary."""

from typing import cast

from pydantic import JsonValue

from .projection import Frame, Projection, Values


def utterance_key(tick: int, speaker: str, addressee: str) -> str:
    # A resident can issue one utterance per tick in both lanes.
    return f"speech@{tick}/{speaker}/{addressee}"


def legacy_replies(oracle: Projection) -> Projection:
    """Replace v1 event references with their tick and request participants."""
    requests = {
        (frame.tick, utterance.speaker, utterance.addressee)
        for frame in oracle.frames
        for utterance in frame.utterances
        if utterance.act == "request"
    }
    reference = oracle.model_copy(deep=True)
    for frame in reference.frames:
        for decision in frame.decisions:
            for intent in decision.intents:
                reply = intent.parameters.get("in_reply_to")
                if not isinstance(reply, str):
                    continue
                # The archive retains raw IDs in plans, and committed requests in the frame.
                parts = reply.rsplit(":", 2)
                if len(parts) != 3 or not parts[1].isdigit():
                    continue
                target = cast(str, cast(Values, intent.target)["id"])
                request = (int(parts[1]), target, decision.actor_id)
                if request in requests:
                    intent.parameters["in_reply_to"] = utterance_key(*request)
    return reference


def _first(
    expected: JsonValue, actual: JsonValue, field: str
) -> tuple[str, JsonValue, JsonValue] | None:
    if expected == actual:
        return None
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            if key not in expected or key not in actual:
                return f"{field}.{key}", expected.get(key), actual.get(key)
            difference = _first(expected[key], actual[key], f"{field}.{key}")
            if difference is not None:
                return difference
    if isinstance(expected, list) and isinstance(actual, list):
        for index, (left, right) in enumerate(zip(expected, actual, strict=False)):
            difference = _first(left, right, f"{field}[{index}]")
            if difference is not None:
                return difference
        return f"{field}.length", len(expected), len(actual)
    return field, expected, actual


def first_difference(
    expected: Frame, actual: Frame, *, links: bool = True
) -> dict[str, JsonValue] | None:
    left = expected.model_dump(mode="json")
    right = actual.model_dump(mode="json")
    for frame in (left, right):
        # WAP §11.3 orders outcomes within each resident, independently of their
        # interleaving in the two event catalogs.
        outcomes = cast(list[Values], frame["outcomes"])
        outcomes.sort(key=lambda item: cast(str, item["actor_id"]))
    if not links:
        for frame in (left, right):
            for outcome in cast(list[Values], frame["outcomes"]):
                del outcome["next_decision_tick"]
    for field in Frame.model_fields:
        difference = _first(left[field], right[field], field)
        if difference is not None:
            path, expected_value, actual_value = difference
            return {
                "tick": expected.tick,
                "field": path,
                "expected": expected_value,
                "actual": actual_value,
            }
    return None
