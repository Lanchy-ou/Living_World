"""Party routing, delivered speech provenance and resident projections."""

from dataclasses import fields

import pytest

from v2.mechanical_memory.mechanical_agreement_support import (
    ACCEPTANCE,
    AGREEMENT,
    PROPOSAL,
    TERMS,
    accepted_event,
    agreement_exchange,
)


def _kind(records, kind):
    return next(record for record in records if record.kind == kind)


def test_mm_17_commitments_distinguish_hearing_from_speaking(packet, audit):
    from living_island.memory.v2.records import Observed, Told

    for resident, counterpart, heard, gist in (
        (
            "ella",
            "mia",
            False,
            "mia agreed to give 2 fruit by tick 300 (I did not hear their answer)",
        ),
        ("mia", "ella", True, "I promised ella to give 2 fruit by tick 300"),
    ):
        snapshot, log = agreement_exchange(resident, packet, audit)
        record = _kind(snapshot.records(), "commitment")
        said = next(entry for entry in log.entries if entry.type == "utterance_result")
        assert said.about == (f"spoke:{PROPOSAL if resident == 'ella' else ACCEPTANCE}",)
        expected = [Observed(entry_id=said.id)]
        if heard:
            expected.append(Told(utterance_id=PROPOSAL, speaker_id=counterpart))
        assert record.sources == expected
        assert record.content.counterpart_id == counterpart
        assert record.content.heard_counterpart is heard
        assert record.content.terms.model_dump() == TERMS
        assert record.gist == gist


def test_mm_21_resident_serialization_across_carriers(packet, audit):
    from living_island.agents.v2.context.prefix import FrozenPrefix, render_memory
    from living_island.agents.v2.context.working import WorkingContext
    from living_island.memory.v2.pending import PendingPeriod, PendingPeriods

    for resident in ("ella", "mia"):
        snapshot, log = agreement_exchange(resident, packet, audit)
        view = snapshot.resident(memory_on=True)
        fragments = tuple(render_memory(revision) for revision in view.records)
        visible = [revision.record for revision in view.records]
        commitment = _kind(visible, "commitment")
        social = _kind(visible, "social")
        assert social.content.facts.agreements == [commitment.id]
        assert _kind(snapshot.records(), "social").content.facts.agreements == [AGREEMENT]
        assert set(commitment.content.model_dump()) == {
            "terms",
            "role",
            "counterpart_id",
            "due_tick",
            "heard_counterpart",
            "status",
            "status_note",
        }
        records = [record.model_dump_json() for record in visible]
        gists_and_index = [*(record.gist for record in visible), *view.index()]
        record_carriers = [*records, *gists_and_index, *(f.part.text for f in fragments)]

        prefix = FrozenPrefix(log.period_id, (), (), fragments, None)
        frozen = WorkingContext(prefix, log).freeze()
        pending = PendingPeriods(resident)
        pending.append(PendingPeriod(resident, log.period_id, frozen))
        context_text = [part.text for part in pending.read()[0].context.parts]
        for text in [*record_carriers, *context_text]:
            assert AGREEMENT not in text and "private-call" not in text
            assert "agreement_id" not in text and "acceptance_id" not in text
            assert "proposal_id" not in text
        # Only B's delivered proposal can survive as a told citation in a memory
        # fragment. Both parties' own successfully delivered words also stay in their log.
        assert any(PROPOSAL in text for text in records) is (resident == "mia")
        assert all(ACCEPTANCE not in text for text in record_carriers)
        assert all(PROPOSAL not in text for text in gists_and_index)
        assert any(PROPOSAL in text for text in context_text)
        assert any(ACCEPTANCE in text for text in context_text) is (resident == "mia")


def test_mf_02_party_allowlist_applies_in_both_arms(packet, audit):
    from living_island.sim.v2.harness.agreement_facts import project_agreement_facts

    event = accepted_event()
    other_event = event.model_copy(update={"type": "utterance_spoken"})
    later_id = "island:0000000002:000011"
    later = event.model_copy(
        update={
            "event_id": later_id,
            "seq_in_tick": 11,
            "payload": {**event.payload, "agreement_id": later_id, "extra": "private detail"},
        }
    )
    for resident, role, counterpart in (("ella", "promisee", "mia"), ("mia", "promisor", "ella")):
        fact, following = project_agreement_facts([later, other_event, event], resident)
        assert following.agreement_id == later_id
        assert {field.name for field in fields(fact)} == {
            "agreement_id",
            "role",
            "counterpart_id",
            "terms",
            "due_tick",
            "accepted_tick",
            "proposal_id",
            "acceptance_id",
        }
        assert (fact.role, fact.counterpart_id, fact.terms.model_dump()) == (
            role,
            counterpart,
            TERMS,
        )
        assert (fact.agreement_id, fact.accepted_tick, fact.due_tick) == (AGREEMENT, 2, 300)
        assert (fact.proposal_id, fact.acceptance_id) == (PROPOSAL, ACCEPTANCE)
        on, _ = agreement_exchange(resident, packet, audit)
        off, _ = agreement_exchange(resident, packet, audit)
        assert on.records() == off.records() and on.store_hash == off.store_hash
        assert len(on.resident(memory_on=True).records) == 2
        assert off.resident(memory_on=False).records == ()
        social = _kind(on.records(), "social")
        assert social.content.facts.received == []
        commitment = _kind(on.records(), "commitment")
        assert commitment.content.heard_counterpart is (resident == "mia")
        assert any(source.kind == "told" for source in commitment.sources) is (resident == "mia")
    assert project_agreement_facts([event], "ryan") == ()
    nonparty, _ = agreement_exchange("ryan", packet, audit)
    assert nonparty.records() == ()


def test_reject_malformed_accepted_event_payload():
    from pydantic import ValidationError

    from living_island.sim.v2.harness.agreement_facts import project_agreement_facts

    event = accepted_event()
    malformed = event.model_copy(update={"payload": {**event.payload, "proposal_id": 101}})
    with pytest.raises(ValidationError, match="proposal_id"):
        project_agreement_facts([malformed], "ella")
