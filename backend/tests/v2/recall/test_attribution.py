"""Adopted-act citation bindings and decision dispatch exposure."""

import json

import pytest

from living_island.memory.v2.projections import ResidentView

TURN = "ella:t000002"


def call(name):
    from living_island.agents.v2.calls.guard import Call

    return Call(call_id=name, resident_id="ella", period_id="p:ella:1", tick=7, turn_id=TURN)


def act(*ids):
    wait = dict(
        action="wait", verb=None, target=None, instruments=[], inputs=[], params={}, reason=None
    )
    return dict(
        step="act",
        action={"kind": "intent", "intent": wait},
        utterance=None,
        intention=None,
        mute=[],
        cite=ids,
    )


def send(prepared, journal, exchange, *, n=1):
    from living_island.agents.v2.calls.provider import attempt

    clock, transport = exchange
    return attempt(
        prepared, n=n, has_running_action=False, journal=journal, transport=transport, clock=clock
    )


def state_for(packet, intention=None):
    from living_island.agents.v2.context.state import render_current_state

    return render_current_state(
        packet(tick=7), reasons=("notification",), time_of_day="dawn", intention=intention
    )


def trimmed(context, state, audit, monkeypatch, name, *, view, stage="decision"):
    from living_island.agents.v2.calls import guard

    # One token below full forces the actual guard to omit its first eligible part.
    full = context.prepare_decision(call(name + "-measure"), state, audit, view=view, stage=stage)
    with monkeypatch.context() as sizing:
        sizing.setattr(guard, "WINDOW", full.record.candidates[0].manifest.tokens_total - 1)
        return context.prepare_decision(call(name), state, audit, view=view, stage=stage)


def recall_index(name, records, version, audit):
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.guard import Assembly, Part, Ref, prepare

    parts = tuple(
        Part("index", Ref(kind="index", id=r.ref.id, version=str(version)), r.index_line)
        for r in records
    )
    return prepare(
        call(name), Contract("recall"), Assembly(parts, (), frozenset(range(len(parts)))), audit
    )


def test_dl_21_citations_only_from_kept_entries_and_memories(
    audit, packet, working_context, add_record, fake_exchange, monkeypatch, tmp_path
):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.recall.attribution import bind_adopted_act
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    kept = add_record(store)
    unseen = add_record(store)
    view = store.snapshot.resident(memory_on=True)
    first, _ = view.records
    context = working_context(memories=(first,))
    omitted = context.log.response(0, "earlier", "an older observation " * 20)
    for i in range(20):
        newest = context.log.response(6, f"t{i}", f"entry {i}")
    prepared = trimmed(context, state_for(packet), audit, monkeypatch, "adopted", view=view)
    answer = act(newest.id, kept.id, omitted.id, "d:unknown", unseen.id)
    returned = send(prepared, audit, fake_exchange([answer]))
    assert returned.dispatch.sent.omitted == (omitted.part.source,)
    result = bind_adopted_act(returned, context.log.entries, audit)
    assert [item.id for item in result.valid] == [newest.id, kept.id]
    assert result.invalid == (omitted.id, "d:unknown", unseen.id)
    assert [fragment.sha256 for item in result.valid for fragment in item.fragments] == [
        newest.fragment_sha256,
        context.prefix.memories[0].sha256,
    ]
    assert (result.call_id, result.attempt, result.request_sha256) == (
        "adopted",
        1,
        returned.dispatch.request_sha256,
    )
    assert json.loads((tmp_path / Journal.cursor("adopted", "1.citations")).read_bytes()) == (
        result.model_dump(mode="json")
    )


def test_dl_28_first_dispatch_credits_and_local_intention_citations(
    audit, packet, working_context, add_record, fake_exchange, monkeypatch, tmp_path
):
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls import guard
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.context.entries import DeliberateRecall, LocalRecall
    from living_island.agents.v2.recall.attribution import (
        bind_adopted_act,
        crediting_journal,
        store_credit,
    )
    from living_island.memory.v2.records import Observed
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    for i in range(5):
        add_record(store, gist=f"Landmark {i}")
    store.set_intention(tick=2, turn_id="t1", text="Look north", source=Observed(entry_id="e1"))
    start = store.snapshot
    view = start.resident(memory_on=True)
    kept, omitted, recipe, deliberate, index_only, intention = view.records
    state = state_for(packet, intention)
    context = working_context(memories=(kept, omitted))
    local = LocalRecall(mode="recipe", turn_id=TURN, ordinal=1)
    remembered = context.log.recall(7, local, recipe)
    assert remembered.ref == local and remembered.delivery_id is None
    error = TransportResponse(503, b"", True)
    exchange = fake_exchange([error, {"step": "recall", "query": "north?"}])
    before_exchange = []

    apply = store_credit(store)

    def credit(batch, publish):
        before_exchange.append(len(exchange[1].dispatches))
        return apply(batch, publish)

    journal = crediting_journal(audit, context.log.entries, credit)
    with monkeypatch.context() as sizing:
        sizing.setattr(guard, "WINDOW", 0)
        stopped = context.prepare_decision(call("never"), state, audit, view=view)
        assert send(stopped, journal, exchange) is None
    assert not before_exchange and store.snapshot is start

    initial = trimmed(context, state, audit, monkeypatch, "initial", view=view)
    failed = send(initial, journal, exchange)
    assert failed.terminal.error_class == "server_error" and before_exchange == [0]
    used = store.snapshot
    assert used.version == start.version + 1 and used.credited_ids == {kept.ref.id, recipe.ref.id}
    use = json.loads((tmp_path / Journal.cursor("initial", "1.use")).read_bytes())
    assert [rev["id"] for rev in use["credited"]] == [kept.ref.id, recipe.ref.id]
    assert (use["turn_id"], use["call_id"], use["before_version"], use["after_version"]) == (
        TURN,
        "initial",
        start.version,
        used.version,
    )
    retry = send(initial, journal, exchange, n=2)
    assert retry.parsed.step == "recall" and store.snapshot is used

    query = recall_index("query", (deliberate, index_only), used.version, audit)
    send(query, journal, fake_exchange([{"ids": [deliberate.ref.id]}]))
    assert store.snapshot is used
    context.log.recall(7, DeliberateRecall(call_id="query"), deliberate)
    after = trimmed(
        context, state, audit, monkeypatch, "after", view=view, stage="decision_after_recall"
    )
    journal = crediting_journal(audit, context.log.entries, apply)
    answer = send(after, journal, fake_exchange([act(intention.ref.id)]))
    assert store.snapshot.version == used.version + 1
    assert [(r.use_count, r.last_used_tick) for r in store.snapshot.records()] == [
        (1, 7),
        (0, None),
        (1, 7),
        (1, 7),
        (0, None),
        (0, None),
    ]
    on = bind_adopted_act(answer, context.log.entries, audit)
    assert on.valid[0].fragments[0].memory_revision == intention.ref

    off = working_context(period="p:ella:2")
    empty = off.log.empty_recall(7, TURN, 1)
    assert empty.ref == LocalRecall(mode="off_empty", turn_id=TURN, ordinal=1)
    off_view = start.resident(memory_on=False)
    off_intention = off_view.current_intention
    off_call = call("off").model_copy(update={"period_id": "p:ella:2"})
    off_request = off.prepare_decision(
        off_call,
        state_for(packet, off_intention),
        audit,
        view=off_view,
        stage="decision_after_recall",
    )
    returned = send(off_request, audit, fake_exchange([act(off_intention.ref.id, recipe.ref.id)]))
    off_cites = bind_adopted_act(returned, off.log.entries, audit)
    assert off_cites.valid[0].fragments[0].memory_revision == off_intention.ref
    assert off_cites.invalid == (recipe.ref.id,)


def test_dl_30_bind_old_projected_revision_only_in_adopted_request(
    audit, packet, working_context, add_record, fake_exchange, monkeypatch, tmp_path
):
    from living_island.agents.v2.context.entries import DeliberateRecall
    from living_island.agents.v2.recall.attribution import bind_adopted_act
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    private_id = "private-acceptance-123"
    promise = add_record(
        store,
        kind="commitment",
        sources=[],
        content={
            "agreement_id": private_id,
            "role": "promisee",
            "counterpart_id": "mia",
            "terms": {
                "promisor_id": "mia",
                "promisee_id": "ella",
                "due_tick": None,
                "what": {"kind": "return_item", "item_id": "cup"},
            },
            "due_tick": None,
            "heard_counterpart": False,
            "status": "open",
            "status_note": None,
        },
    )
    previous = add_record(store)
    unseen = add_record(store)
    view = store.snapshot.resident(memory_on=True)
    old, prior, index_only = view.records
    context = working_context(memories=(prior,))
    state = state_for(packet)
    before = context.prepare_decision(call("before"), state, audit, view=view)
    first = send(before, audit, fake_exchange([{"step": "recall", "query": "the cup?"}]))
    assert prior.ref.id in [part.source.id for part in first.dispatch.sent.manifest.entries]
    index = recall_index("index", (old, index_only), old.ref.store_version, audit)
    selected = send(index, audit, fake_exchange([{"ids": [old.ref.id]}]))
    assert selected.parsed.ids == [old.ref.id]
    entry = context.log.recall(7, DeliberateRecall(call_id="index"), old)
    prepared = trimmed(
        context, state, audit, monkeypatch, "final", view=view, stage="decision_after_recall"
    )
    exchange = fake_exchange([act(previous.id, unseen.id, promise.id, entry.id)])
    returned = send(prepared, audit, exchange)
    assert private_id.encode() not in exchange[1].dispatches[0]
    assert returned.dispatch.sent.omitted == (context.prefix.memories[0].part.source,)

    revised = promise.model_copy(
        update={
            "updated_tick": 8,
            "content": promise.content.model_copy(update={"heard_counterpart": True}),
        }
    )
    store.apply(store.snapshot.version, "mechanical", [revised])
    assert store.snapshot.ref(promise.id).content_hash != old.ref.content_hash
    bound = bind_adopted_act(returned, context.log.entries, audit)
    assert bound.invalid == (previous.id, unseen.id)
    assert [item.id for item in bound.valid] == [promise.id, entry.id]
    for citation in bound.valid:
        (sent,) = citation.fragments
        assert (sent.source, sent.sha256, sent.memory_revision) == (
            entry.part.source,
            entry.fragment_sha256,
            old.ref,
        )
        assert (tmp_path / sent.sha256).read_bytes() == entry.part.text.encode()
    assert "I did not hear their answer" in entry.part.text


def test_non_act_response_cannot_supply_citations(audit, packet, working_context, fake_exchange):
    from living_island.agents.v2.recall.attribution import bind_adopted_act

    context = working_context()
    prepared = context.prepare_decision(
        call("asking"), state_for(packet), audit, view=ResidentView((), None)
    )
    returned = send(prepared, audit, fake_exchange([{"step": "recall", "query": "where?"}]))
    with pytest.raises(ValueError, match="only a returned act"):
        bind_adopted_act(returned, context.log.entries, audit)


def test_decision_attribution_requires_its_turn_id(audit, packet, working_context, fake_exchange):
    from living_island.agents.v2.recall.attribution import bind_adopted_act

    context = working_context()
    unbound = call("unbound").model_copy(update={"turn_id": None})
    prepared = context.prepare_decision(
        unbound, state_for(packet), audit, view=ResidentView((), None)
    )
    returned = send(prepared, audit, fake_exchange([act()]))
    with pytest.raises(ValueError, match="requires a turn ID"):
        bind_adopted_act(returned, context.log.entries, audit)


def test_failed_credit_write_can_recover_the_durable_dispatch(
    audit, packet, working_context, add_record, fake_exchange, tmp_path
):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.calls.provider import Dispatch
    from living_island.agents.v2.recall.attribution import (
        credit_dispatch,
        crediting_journal,
        store_credit,
    )
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    add_record(store)
    start = store.snapshot
    view = start.resident(memory_on=True)
    (memory,) = view.records
    context = working_context(memories=(memory,))
    prepared = context.prepare_decision(call("interrupted"), state_for(packet), audit, view=view)
    use_cursor = Journal.cursor("interrupted", "1.use")

    def write_then_fail(key, data):
        audit.keep(key, data)
        if key == use_cursor:
            raise OSError("journal acknowledgement lost")

    credit = store_credit(store)
    faulty = crediting_journal(Journal(write_then_fail, audit.create), context.log.entries, credit)
    exchange = fake_exchange([])
    with pytest.raises(OSError, match="acknowledgement lost"):
        send(prepared, faulty, exchange)
    assert store.snapshot is start and not exchange[1].dispatches
    dispatch = Dispatch.model_validate_json(
        (tmp_path / Journal.cursor("interrupted", "1.dispatch")).read_bytes()
    )
    write = credit_dispatch(dispatch, context.log.entries, credit, audit)
    assert write.credited == (memory.ref,) and store.snapshot.version == start.version + 1
    assert credit_dispatch(dispatch, context.log.entries, credit, audit) is None
    assert (
        json.loads((tmp_path / use_cursor).read_bytes())["store_hash"] == store.snapshot.store_hash
    )
