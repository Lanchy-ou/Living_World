"""Typed record envelopes, provenance and subject matter from the resident's world."""

import json
from collections.abc import Mapping
from hashlib import sha256
from operator import attrgetter
from typing import Annotated, ClassVar, Literal, Self, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SerializeAsAny, model_validator

from living_island.world.v2.protocol import (
    Coord,
    ExactItemSpec,
    InspectView,
    Quantity,
    Terms,
    Terrain,
    Tick,
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, serialize_by_alias=True)


Rating = Annotated[int, Field(ge=0, le=4)]
Gist = Annotated[str, Field(max_length=160, pattern=r"^[^\r\n\x0b\x0c\x1c-\x1e\x85\u2028\u2029]*$")]
Text = Annotated[str, Field(max_length=2000)]
MemoryId = Annotated[str, Field(pattern=r"^m:[^\r\n]+:[1-9][0-9]*$")]
Topic = Literal["food", "water", "shelter", "tools", "materials", "people", "danger", "other"]
TraitId = Literal["curiosity", "caution", "sociability", "trustfulness", "diligence"]


class Observed(Model):
    kind: Literal["observed"] = "observed"
    entry_id: str


class Told(Model):
    kind: Literal["told"] = "told"
    utterance_id: str
    speaker_id: str


class Inferred(Model):
    kind: Literal["inferred"] = "inferred"
    memory_ids: Annotated[list[MemoryId], Field(min_length=1), AfterValidator(sorted)]
    call_id: str


class Innate(Model):
    kind: Literal["innate"] = "innate"


Source = Annotated[Observed | Told | Inferred | Innate, Field(discriminator="kind")]


def _source_key(source: Source) -> tuple[int, tuple[str, ...]]:
    match source:
        case Observed():
            return 0, (source.entry_id,)
        case Told():
            return 1, (source.utterance_id, source.speaker_id)
        case Inferred():
            return 2, (*source.memory_ids, source.call_id)
        case Innate():
            return 3, ()


Sources = Annotated[list[Source], AfterValidator(lambda values: sorted(values, key=_source_key))]


class AboutTick(Model):
    start: Tick = Field(alias="from")
    end: Tick = Field(alias="to")

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError("about_tick ends before it starts")
        return self


def single_line(text: str) -> str:
    return " ".join(text.splitlines())[:160]


class Content(Model):
    """Registered schemas may override flags and the resident-visible content/gist."""

    kind: ClassVar[str]

    def flags(self) -> tuple[str, ...]:
        return ()

    def resident_fields(self, gist: str, links: Mapping[str, str]) -> tuple[str, Model]:
        return gist, self


class Episodic(Content):
    kind = "episodic"
    participants: list[str]
    place: Coord | None


class Subject(Model):
    kind: Literal["place", "entity", "resident", "kind_of_thing", "general"]
    ref: str | None


class Belief(Content):
    kind = "belief"
    subject: Subject
    stance: Literal["stable", "dated", "guess"]
    topics: Annotated[list[Topic], AfterValidator(lambda values: sorted(set(values)))]


class Transfer(Model):
    archetype_id: str
    quantity: Quantity


Transfers = Annotated[
    list[Transfer], AfterValidator(lambda xs: sorted(xs, key=attrgetter("archetype_id")))
]


class SocialFacts(Model):
    given: Transfers
    received: Transfers
    agreements: list[str]
    last_seen_tick: Tick | None
    last_heard_tick: Tick | None


class Social(Content):
    kind = "social"
    about: str
    trust: Rating
    impression: str
    facts: SocialFacts

    def mechanical_gist(self) -> str:
        return single_line(f"{self.about} (trust {self.trust}) {self.impression}".rstrip())

    def resident_fields(self, gist: str, links: Mapping[str, str]) -> tuple[str, Model]:
        # The agreement writer may have delivered the fact before the local commitment write.
        local_ids = sorted(links[key] for key in self.facts.agreements if key in links)
        facts = self.facts.model_copy(update={"agreements": local_ids})
        return gist, self.model_copy(update={"facts": facts})


class Word(Model):
    property_id: str
    word: str


class Look(Model):
    archetype_id: str | None
    material_id: str | None
    descriptors: Annotated[
        list[Word], AfterValidator(lambda xs: sorted(xs, key=attrgetter("property_id")))
    ]

    @classmethod
    def perceived(cls, view: InspectView) -> Self:
        return cls(
            archetype_id=view.archetype_id,
            material_id=view.material_id,
            descriptors=[Word(property_id=d.property_id, word=d.value) for d in view.descriptors],
        )


class TerrainTarget(Model):
    terrain: Terrain


class SkillInput(Model):
    look: Look
    quantity: Quantity


class SkillHypothesis(Model):
    verb: str
    target: Look | TerrainTarget | None
    instruments: list[Look]
    inputs: list[SkillInput]
    circumstances: str | None
    expected: list[str]


class SkillEvidence(Model):
    attempts: Tick = 0
    matched_expected: Tick = 0
    other_outcomes: Tick = 0
    watched: Tick = 0
    watched_matched: Tick = 0
    last_attempt_tick: Tick | None = None


class Skill(Content):
    kind = "skill"
    hypothesis: SkillHypothesis
    evidence: SkillEvidence
    status: Literal["active", "doubtful", "refuted"]

    def flags(self) -> tuple[str, ...]:
        return ("refuted",) if self.status == "refuted" else ()


class VisibleCommitment(Model):
    role: Literal["promisor", "promisee"]
    counterpart_id: str
    terms: Terms
    due_tick: Tick | None
    heard_counterpart: bool
    status: Literal["open", "kept", "broken", "expired"]
    status_note: str | None

    def summary(self) -> str:
        what = self.terms.what
        if what.kind == "give_item":
            item = what.item
            detail = (
                item.item_id
                if isinstance(item, ExactItemSpec)
                else f"{item.quantity} {item.archetype_id}"
            )
            action = f"give {detail}"
        elif what.kind == "return_item":
            action = f"return {what.item_id}"
        elif what.kind == "be_at":
            action = f"be at ({what.position.x},{what.position.y})"
        else:
            action = f"contribute {what.work_ticks} ticks to {what.process_id}"
        who = (
            f"I promised {self.counterpart_id}"
            if self.role == "promisor"
            else f"{self.counterpart_id} agreed"
        )
        due = "" if self.due_tick is None else f" by tick {self.due_tick}"
        unheard = "" if self.heard_counterpart else " (I did not hear their answer)"
        # Reserve room for the hearing qualifier even for long item or resident names.
        return single_line(f"{who} to {action}{due}")[: 160 - len(unheard)] + unheard


class Commitment(VisibleCommitment, Content):
    kind = "commitment"
    agreement_id: str

    def flags(self) -> tuple[str, ...]:
        return ("open",) if self.status == "open" else ()

    def resident_fields(self, gist: str, links: Mapping[str, str]) -> tuple[str, Model]:
        visible = VisibleCommitment.model_construct(
            **{key: getattr(self, key) for key in VisibleCommitment.model_fields}
        )
        return gist, visible


class Intention(Content):
    kind = "intention"
    set_turn: str
    state: Literal["current", "replaced", "cleared", "reset"]
    ended_turn: str | None


class TraitChange(Model):
    tick: Tick
    previous: Rating = Field(alias="from")
    current: Rating = Field(alias="to")
    sources: Annotated[Sources, Field(min_length=1)]


class Trait(Model):
    trait_id: TraitId
    base: Rating
    value: Rating
    min: Rating
    max: Rating
    changes: list[TraitChange]


class Personality(Content):
    kind = "personality"
    traits: list[Trait]

    @model_validator(mode="after")
    def has_five_traits(self) -> Self:
        if sorted(t.trait_id for t in self.traits) != sorted(get_args(TraitId)):
            raise ValueError("personality requires one of each trait")
        return self


class Envelope(Model):
    id: MemoryId
    owner_id: str
    kind: str
    created_tick: Tick
    updated_tick: Tick
    about_tick: AboutTick | None
    sources: Sources
    confidence: Rating
    last_used_tick: Tick | None
    use_count: Tick
    supersedes: MemoryId | None
    superseded_by: MemoryId | None
    needs_review: bool
    gist: Gist
    text: Text | None


class MemoryRecord(Envelope):
    speech_derived: bool
    content: SerializeAsAny[Content]

    @model_validator(mode="after")
    def check_envelope(self) -> Self:
        if self.id.rsplit(":", 1)[0] != f"m:{self.owner_id}":
            raise ValueError("record ID does not belong to its owner")
        if self.kind != self.content.kind:
            raise ValueError("record kind does not match content schema")
        if not self.sources and self.kind != "commitment":
            raise ValueError("only commitments may have empty sources")
        if self.updated_tick < self.created_tick:
            raise ValueError("updated_tick precedes creation")
        if isinstance(self.content, Episodic) and self.about_tick is None:
            raise ValueError("episodic memory requires about_tick")
        if isinstance(self.content, Belief):
            if self.content.stance == "dated" and self.about_tick is None:
                raise ValueError("dated belief requires about_tick")
            if self.content.stance == "stable" and self.about_tick is not None:
                raise ValueError("stable belief cannot have about_tick")
        return self

    @property
    def history(self) -> bool:
        return self.superseded_by is not None or (
            isinstance(self.content, Intention) and self.content.state != "current"
        )

    @property
    def archived(self) -> bool:
        return isinstance(self.content, Commitment) and self.content.status != "open"

    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"use_count", "last_used_tick"}))


def digest(value: object) -> str:
    """SHA-256 of the canonical JSON form of already typed memory data."""
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
