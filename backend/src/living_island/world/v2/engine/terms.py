"""Check agreement references against speaker exposure, without testing feasibility."""

from ..protocol import ExactItemSpec, KindItemSpec, Terms
from .kernel import exposed
from .state import WorldState
from .validate import EnginePack


def valid_terms(
    state: WorldState,
    pack: EnginePack,
    speaker_id: str,
    addressee_id: str,
    terms: Terms,
    tick: int,
) -> bool:
    parties = {speaker_id, addressee_id}
    if {terms.promisor_id, terms.promisee_id} != parties:
        return False
    if terms.due_tick is not None and terms.due_tick <= tick:
        return False

    what = terms.what
    match what.kind:
        case "give_item":
            match what.item:
                case ExactItemSpec(item_id=item_id):
                    return exposed(state, speaker_id, item_id)
                case KindItemSpec(archetype_id=archetype_id):
                    return archetype_id in pack.archetypes
        case "return_item":
            return exposed(state, speaker_id, what.item_id)
        case "be_at":
            position = what.position
            smap = state.static_map
            return (
                smap.contains(position)
                and smap.index(position) in state.explored_tiles_by_resident[speaker_id]
            )
        case "contribute":
            return exposed(state, speaker_id, what.process_id)
