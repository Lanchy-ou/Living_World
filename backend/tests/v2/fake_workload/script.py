"""Offline Responses script. Only the bytes sent to this resident drive its next reply."""

import json
import re
from collections import Counter, deque
from functools import lru_cache

from living_island.agents.llm.provider import TransportResponse
from living_island.agents.v2.calls.contracts import digest, json_bytes
from living_island.agents.v2.calls.fake import FakeClock
from v2.decision_harness.resident_vectors import act


@lru_cache(maxsize=256)
def route(rows, start, goal):
    """Pre-script walkable waypoints on the registered map between two camps."""
    queue = deque([start])
    parent = {start: None}
    while queue:
        point = queue.popleft()
        if point == goal:
            path = []
            while point != start:
                path.append(point)
                point = parent[point]
            return path[::-1]
        x, y = point
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            nx, ny = neighbor
            if (
                0 <= ny < len(rows)
                and 0 <= nx < len(rows[ny])
                and rows[ny][nx] not in "~^S"
                and neighbor not in parent
            ):
                parent[neighbor] = point
                queue.append(neighbor)
    raise ValueError(f"No fixture route between {start} and {goal}")


def intent(action="act", *, verb=None, target=None, inputs=(), params=None, **fields):
    output = json.loads(act(action, verb=verb, params=params))
    if action != "continue":
        output["action"]["intent"].update(target=target, inputs=list(inputs))
    return {**output, **fields}


def waypoint(rows, current, goal, view):
    x, y = map(int, re.search(r"Explored map from \((\d+),(\d+)\)", view).groups())
    explored = re.search(r"Explored map from .*?:\n(.*?)\n@ you", view, re.S)[1].splitlines()
    destination = current
    for px, py in route(rows, current, goal):
        if not (0 <= py - y < len(explored) and 0 <= px - x < len(explored[py - y])):
            break
        if explored[py - y][px - x] == "?":
            break
        destination = (px, py)
    if destination == current:
        destination = route(rows, current, goal)[0]
    return intent(
        "move_to", target={"kind": "tile", "position": dict(zip("xy", destination, strict=True))}
    )


def changes(words):
    # Ground an episodic addition in the exact observation selected from the sent log.
    observed = re.search(
        r"^\[([^ ]+) \| tick (\d+) \| observation\] (You see .+? at (\d+),(\d+)[^\n]*)$",
        words,
        re.M,
    )
    ops = [{"op_id": "missing", "op": "forget", "id": "m:absent:1"}]
    if observed:
        entry, tick, observation, x, y = observed.groups()
        ops.append(
            {
                "op": "add",
                "op_id": "observation",
                "ref": "new:1",
                "record": {
                    "kind": "episodic",
                    "gist": observation[:150],
                    "confidence": 3,
                    "about_tick": {"from": int(tick), "to": int(tick)},
                    "content": {"participants": [], "place": {"x": int(x), "y": int(y)}},
                    "sources": [{"kind": "observed", "entry_id": entry}],
                },
            }
        )
    return {"ops": ops}


class WorkloadTransport:
    def __init__(self, actor, rows, tree, spring):
        self.actor = actor
        self.rows = rows
        self.tree_id = tree.id
        self.orchard = (tree.position[0] - 1, tree.position[1])
        self.water = (spring[0] - 1, spring[1])
        self.forage = False
        self.gathers = 0
        self.rested_at_spring = False
        self.clear_intention = True
        self.counts = Counter()
        self.attempt_hashes = Counter()
        self.turns = 0
        self.sleep_duration = 36
        self.clock = FakeClock()

    def delay(self, seconds):
        self.clock.elapsed_ms += round(seconds * 1000)

    def choose(self, words):
        self.turns += 1
        state = words.rsplit("Turn reasons: ", 1)[1]
        if self.turns == 1:
            return intent(
                verb="rest",
                intention={"set": "Find drinking water."},
                mute=["discovery"],
                cite=[f"m:{self.actor}:1"],
                utterance={
                    "speech_act": "statement",
                    "text": "I am going for water.",
                    "addressee_id": None,
                    "terms": None,
                    "in_reply_to": None,
                },
            )
        if "Continue or replace this action" in state:
            return intent("continue")
        if self.clear_intention:
            self.clear_intention = False
            return intent("wait", intention={"clear": True})
        position = tuple(map(int, re.search(r"You are at \((\d+),(\d+)\)", state).groups()))
        body = re.search(r"You feel ([^\n]+)", state)[1]
        hungry = any(word + " satiety" in body for word in ("critical", "low", "moderate"))
        thirsty = any(word + " hydration" in body for word in ("critical", "low"))
        if re.search(r"(?m)^(?:Carrying: )?[\w:.-]+ \(fruit(?:,|\))", state):
            return intent(
                verb="eat",
                inputs=[{"item": {"kind": "held", "archetype_id": "fruit"}, "quantity": 1}],
            )
        if position == self.water and "strong hydration" not in body:
            return intent(verb="drink")
        if position == self.water and hungry and self.rested_at_spring:
            self.forage = True
            self.gathers = 0
            self.rested_at_spring = False
        if self.forage and position == self.orchard and not thirsty:
            if hungry and self.gathers < 2:
                self.gathers += 1
                return intent(verb="gather", target={"kind": "entity", "id": self.tree_id})
            self.forage = False
        if thirsty:
            self.forage = False
        goal = self.orchard if self.forage else self.water
        if position != goal:
            return waypoint(self.rows, position, goal, state)
        self.rested_at_spring = True
        return intent(verb="sleep", params={"duration_ticks": self.sleep_duration})

    def exchange(self, body, timeout_ms):
        request = json.loads(body)
        form = request["text"]["format"]
        kind = form["name"]
        assert body.count(json_bytes(form["schema"])) == 1
        assert not request["tools"] and request["tool_choice"] == "none"
        self.attempt_hashes[digest(body)] += 1
        self.clock.elapsed_ms += 1
        self.counts[kind] += 1
        n = self.counts[kind]
        words = request["input"][1]["content"]
        if kind == "decision" and n <= 4:
            status = (None, 429, 503, 200)[n - 1]
            if status is None:
                raise TimeoutError
            return TransportResponse(status, b"{}", True)
        if kind == "consolidation_selection" and n == 1 and self.actor == "ella":
            return TransportResponse(400, b"{}", True)
        if kind == "decision" and n == 7 and self.actor == "noah":
            return TransportResponse(400, b"{}", True)
        if kind == "decision" and (n == 5 or n % 12 == 0):
            answer = {"step": "recall", "query": "What do I remember about this place?"}
        elif kind in ("decision", "decision_after_recall"):
            answer = self.choose(words)
        elif kind in ("recall", "morning"):
            answer = {"ids": [f"m:{self.actor}:1"]}
        elif kind == "consolidation_selection":
            answer = {"read": [f"m:{self.actor}:1"]}
        else:
            answer = changes(words)
        message = {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(answer)}],
        }
        return TransportResponse(
            200, json_bytes({"status": "completed", "output": [message]}), True
        )
