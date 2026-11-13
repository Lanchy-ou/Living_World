"""Registered P3 smoke/fake launch, immutable inputs and shared allocation ownership.

Live model calls are possible only in run/resume after registration, fresh public
provider preflight and existing allocation checks. Validation never reads a key.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.request import urlopen

from living_island.agents.llm.fallback import FrozenRuleFallbackAdapter
from living_island.agents.llm.provider import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    COUNTER_ID,
    COUNTER_MODEL_VERSION,
    COUNTER_TOKENIZER_SHA256,
    COUNTER_VERSION,
    MODEL_ID,
    DeepSeekResponsesAdapter,
    HTTPSByteTransport,
)
from living_island.agents.p3.context import assemble_context
from living_island.agents.p3.ports import FallbackAdapter, ProviderAdapter
from living_island.agents.p3.prompts import (
    RESIDENT_TEMPLATE,
    build_model_action_contract,
    render_provider_request,
)
from living_island.agents.p3.runtime import create_p3_runtime
from living_island.agents.p3.types import (
    BudgetCaps,
    CaseAllocationP3,
    ContextProfile,
    P3Model,
    P3PolicyConfig,
    PricingPin,
    ProfileDocument,
    ProviderRequest,
    ProviderResult,
    ResidentIdentity,
    WireRequest,
)
from living_island.contract.p3_save import (
    ActorPolicyConfig,
    ImplementationPin,
    InputPin,
    TrialRegistration,
)
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.persistence.characters import resolve_identity
from living_island.persistence.p3 import (
    git_source_reader,
    read_checkpoint_p3,
    validate_inputs,
)
from living_island.persistence.p3_allocation import (
    AllocationStore,
    _atomic_write,
    _ProcessLock,
    allocation_key,
    initialize_fake,
    initialize_pilot,
)
from living_island.sim.p3 import P3RunResult, reexecute_p3, resume_p3, run_p3
from living_island.world.content import (
    WorldContent,
    build_world_content,
    map_bytes_from_rows,
)
from living_island.world.ports import create_engine
from pydantic import Field, model_validator

WORLD_COMMIT = "7c13d78ffd7d89006f6008c8a09f37ae97c253db"
WORLD_CONFIG = "content/worlds/default.toml"
WORLD_MAP = "content/worlds/default-island.map"
SMOKE_SEED = 1292387875
PREFLIGHT_PATH = "backend/tests/fixtures/p3/one_resident/live_preflight.json"
PRICE_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
GUIDE_URL = "https://api-docs.deepseek.com/guides/responses_api/"
API_URL = "https://api-docs.deepseek.com/api/create-response/"
PROFILE_PATHS = tuple(
    f"content/characters/{name}.json" for name in ("cautious", "cooperative", "explorer")
)
PROMPT_PATH = "content/prompts/p3-v0.1/resident.txt"
CONTEXT_PATH = "content/prompts/p3-v0.1/context-profile.json"
MODULE_PATHS = {
    "adapter": ["backend/src/living_island/agents/llm/provider.py"],
    "counter": ["backend/src/living_island/agents/llm/provider.py"],
    "goal": ["backend/src/living_island/agents/p3/cognition.py"],
    "runtime": ["backend/src/living_island/agents/p3/runtime.py"],
    "schema": [
        "backend/src/living_island/agents/p3/prompts.py",
        "backend/src/living_island/agents/p3/types.py",
    ],
    "selector": [
        "backend/src/living_island/memory/p3_types.py",
        "backend/src/living_island/memory/retrieval.py",
    ],
}
SMOKE_CAPS = BudgetCaps(attempts=48, input_tokens=1572864, output_tokens=98304, micro_cny=5000000)


class LiveEvidence(P3Model):
    evidence_version: Literal["0.1"]
    checked_on: str
    model_id: Literal[MODEL_ID]
    model_version: Literal[COUNTER_MODEL_VERSION]
    pricing: PricingPin
    counter_id: Literal[COUNTER_ID]
    counter_version: Literal[COUNTER_VERSION]
    counter_tokenizer_sha256: Literal[COUNTER_TOKENIZER_SHA256]
    adapter_id: Literal[ADAPTER_ID]
    adapter_version: Literal[ADAPTER_VERSION]
    responses_supported: Literal[True]
    json_schema_supported: Literal[True]
    reasoning_none_supported: Literal[True]
    source_urls: list[str]

    @model_validator(mode="after")
    def _approved(self) -> LiveEvidence:
        if self.source_urls != [PRICE_URL, API_URL, GUIDE_URL] or (
            self.pricing.source_url,
            self.pricing.input_micro_cny_per_million_tokens,
            self.pricing.output_micro_cny_per_million_tokens,
        ) != (PRICE_URL, 2000000, 8000000):
            raise ValueError("UNAPPROVED_PROVIDER_PIN")
        datetime.strptime(self.checked_on, "%Y-%m-%d")
        return self


class _Document(HTMLParser):
    """Read visible table cells; expand row/column spans before selecting the model."""

    def __init__(self, raw: bytes) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, int, int]]]] = []
        self.text: list[str] = []
        self.table: list[list[tuple[str, int, int]]] | None = None
        self.row: list[tuple[str, int, int]] | None = None
        self.cell: list[str] | None = None
        self.spans = (1, 1)
        self.hidden = 0
        self.feed(raw.decode("utf-8", errors="strict"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            attributes = dict(attrs)
            self.spans = (
                int(attributes.get("rowspan") or "1"),
                int(attributes.get("colspan") or "1"),
            )
            if not all(1 <= n <= 32 for n in self.spans):
                raise ValueError("PUBLIC_PREFLIGHT_LAYOUT_UNSUPPORTED")
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"td", "th"} and self.cell is not None:
            assert self.row is not None
            self.row.append(("".join(self.cell), *self.spans))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            assert self.table is not None
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.text.append(data)
            if self.cell is not None:
                self.cell.append(data)

    def grids(self) -> list[list[list[str]]]:
        grids = []
        for table in self.tables:
            pending: dict[int, tuple[str, int]] = {}
            rows = []
            for cells in table:
                occupied = {column: value for column, (value, _) in pending.items()}
                pending = {
                    column: (value, left - 1)
                    for column, (value, left) in pending.items()
                    if left > 1
                }
                column = 0
                for value, height, width in cells:
                    while column in occupied:
                        column += 1
                    for index in range(column, column + width):
                        if index in occupied:
                            raise ValueError("PUBLIC_PREFLIGHT_LAYOUT_UNSUPPORTED")
                        occupied[index] = _plain(value)
                        if height > 1:
                            pending[index] = (_plain(value), height - 1)
                    column += width
                rows.append([occupied.get(i, "") for i in range(max(occupied, default=-1) + 1)])
            grids.append(rows)
        return grids


def _plain(text: str) -> str:
    return re.sub(r"[\s\u200b]+", "", text)


def fetch_public_document(url: str) -> bytes:
    """Credential-free documentation GET, never a paid provider probe."""
    if url not in {PRICE_URL, API_URL, GUIDE_URL}:
        raise ValueError("PUBLIC_PREFLIGHT_URL_NOT_APPROVED")
    try:
        with urlopen(url, timeout=30) as response:
            if not response.geturl().startswith("https://api-docs.deepseek.com/"):
                raise ValueError("PUBLIC_PREFLIGHT_REDIRECT_REFUSED")
            data = response.read(2_097_153)
        if len(data) > 2_097_152:
            raise ValueError("PUBLIC_PREFLIGHT_DOCUMENT_TOO_LARGE")
        return data
    except (OSError, ValueError) as exc:
        raise ValueError("PUBLIC_PREFLIGHT_UNAVAILABLE") from exc


def current_preflight(
    expected: LiveEvidence,
    *,
    fetch: Callable[[str], bytes] = fetch_public_document,
) -> dict[str, Any]:
    """Compare freshly fetched official metadata to immutable registration pins."""
    documents = {url: fetch(url) for url in expected.source_urls}
    price = _Document(documents[PRICE_URL])
    matches = [
        (table, index)
        for table in price.grids()
        for row in table
        for index, value in enumerate(row)
        if value.startswith(MODEL_ID)
    ]
    if len(matches) != 1:
        raise ValueError("PUBLIC_PREFLIGHT_MODEL_UNAVAILABLE")
    table, column = matches[0]

    def cell(*labels: str) -> str:
        rows = [
            row
            for row in table
            if all(any(label in value for value in row[:column]) for label in labels)
        ]
        if len(rows) != 1 or len(rows[0]) <= column:
            raise ValueError("PUBLIC_PREFLIGHT_LAYOUT_UNSUPPORTED")
        return rows[0][column]

    if cell("模型版本") != expected.model_version or cell("ResponsesAPI") != "支持":
        raise ValueError("PUBLIC_PREFLIGHT_MODEL_DRIFT")
    if "非思考" not in cell("思考模式"):
        raise ValueError("PUBLIC_PREFLIGHT_REASONING_DRIFT")

    def money(value: str) -> int:
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)元", value)
        if match is None:
            raise ValueError("PUBLIC_PREFLIGHT_PRICE_UNAVAILABLE")
        exact = Decimal(match[1]) * 1_000_000
        if exact != int(exact):
            raise ValueError("PUBLIC_PREFLIGHT_PRICE_UNAVAILABLE")
        return int(exact)

    if (
        money(cell("缓存未命中", "高峰时段")),
        money(cell("百万tokens输出", "高峰时段")),
    ) != (
        expected.pricing.input_micro_cny_per_million_tokens,
        expected.pricing.output_micro_cny_per_million_tokens,
    ):
        raise ValueError("PUBLIC_PREFLIGHT_PRICE_DRIFT")
    guide = _Document(documents[GUIDE_URL])
    api = _plain("".join(_Document(documents[API_URL]).text))
    rows = [
        row
        for table in guide.grids()
        if table and table[0] == ["Parameter", "SupportStatus"]
        for row in table
    ]
    text_rows = [row for row in rows if row and row[0] == "text"]
    reasoning_rows = [row for row in rows if row and row[0] == "reasoning"]
    if (
        len(text_rows) != 1
        or "formatfullysupported" not in "".join(text_rows[0]).lower()
        or len(reasoning_rows) != 1
        or "effortsupported" not in "".join(reasoning_rows[0]).lower()
        or "json_schema" not in api
        or "none" not in api
    ):
        raise ValueError("PUBLIC_PREFLIGHT_SCHEMA_DRIFT")
    return dict(
        observed_at=datetime.now(UTC).isoformat(),
        model_id=expected.model_id,
        model_version=expected.model_version,
        documents=[
            dict(url=url, sha256=sha256(documents[url]).hexdigest()) for url in expected.source_urls
        ],
    )


@lru_cache(maxsize=4096)
def _blob(repository: Path, commit: str, path: str) -> bytes:
    return git_source_reader(repository)(commit, path)


def _reader(repository: Path) -> Callable[[str, str], bytes]:
    return lambda commit, path: _blob(repository.resolve(), commit, path)


def git(repository: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repository.resolve().as_posix()}", *args],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("GIT_IDENTITY_UNAVAILABLE")
    return result.stdout


def _inventory(repository: Path, commit: str) -> list[str]:
    return sorted(
        git(
            repository,
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "backend/src",
            "scripts",
            "backend/pyproject.toml",
            "backend/uv.lock",
        )
        .decode()
        .splitlines()
    )


def _pins(repository: Path, commit: str, paths: list[str]) -> list[InputPin]:
    reader = _reader(repository)
    return [
        InputPin(path=p, sha256=sha256(reader(commit, p)).hexdigest()) for p in sorted(set(paths))
    ]


def _world(repository: Path, seed: int) -> WorldContent:
    reader = _reader(repository)
    data = tomllib.loads(reader(WORLD_COMMIT, WORLD_CONFIG).decode("utf-8"))
    data["meta"]["seed"] = seed
    return build_world_content(data, reader(WORLD_COMMIT, WORLD_MAP))


def _identities(
    repository: Path, commit: str, content: WorldContent
) -> tuple[list[Any], list[Any]]:
    reader = _reader(repository)
    profiles = [ProfileDocument.model_validate_json(reader(commit, p)) for p in PROFILE_PATHS]
    mapping = {p.profile_id: p for p in profiles}
    pairs = [
        resolve_identity(
            actor_id=r.id,
            display_name=r.name,
            profile_id=r.profile_id,
            initial_direction=r.initial_goal,
            profiles=mapping,
        )
        for r in sorted(content.config.residents, key=lambda r: r.id)
    ]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def build_registration(
    repository: Path,
    implementation_commit: str,
    *,
    purpose: str = "smoke",
    registration_id: str = "p3-smoke-r1",
    fake_fixture_path: str | None = None,
) -> TrialRegistration:
    """Build the approved one-Ella slice; this task does not open later trial arms."""
    if purpose not in {"smoke", "fake"}:
        raise ValueError("P3-05 supports smoke and isolated fake registrations only")
    commit = git(repository, "rev-parse", implementation_commit).decode().strip()
    content = _world(repository, SMOKE_SEED)
    identities, _ = _identities(repository, commit, content)
    reader = _reader(repository)
    profile = ContextProfile.model_validate_json(reader(commit, CONTEXT_PATH))
    action = build_model_action_contract()
    prices = PricingPin(
        currency="CNY",
        date="2026-11-12",
        source_url=PRICE_URL,
        input_micro_cny_per_million_tokens=2000000,
        output_micro_cny_per_million_tokens=8000000,
    )
    inputs = [
        *PROFILE_PATHS,
        PROMPT_PATH,
        CONTEXT_PATH,
        *(p for paths in MODULE_PATHS.values() for p in paths),
    ]
    if purpose == "smoke":
        evidence = LiveEvidence.model_validate_json(reader(commit, PREFLIGHT_PATH))
        prices = evidence.pricing
        inputs.append(PREFLIGHT_PATH)
    else:
        prices = prices.model_copy(
            update={
                "input_micro_cny_per_million_tokens": 0,
                "output_micro_cny_per_million_tokens": 0,
            }
        )
    fixture_id = "p3-one-resident"
    if fake_fixture_path is not None:
        if purpose != "fake" or not fake_fixture_path.startswith(
            "backend/tests/fixtures/p3/one_resident/"
        ):
            raise ValueError("FAKE_FIXTURE_PATH_INVALID")
        InputPin(path=fake_fixture_path, sha256="0" * 64)
        tape = FakeTape.model_validate_json(reader(commit, fake_fixture_path))
        fixture_id = tape.fixture_id
        inputs.append(fake_fixture_path)
    cfg = content.config
    common = dict(
        seed=SMOKE_SEED,
        max_plan_actions=cfg.agents.max_plan_actions,
        map_width=cfg.map.width,
        map_height=cfg.map.height,
    )
    templates = []
    for identity in identities:
        policy = P3PolicyConfig.model_validate(
            dict(
                config_schema_version="0.2",
                policy_id="llm-v0" if identity.actor_id == "ella" else "rule-based-v0",
                **common,
                identity_sha256=canonical_sha256(identity),
                prompt_version="p3-resident/0.1",
                prompt_sha256=sha256(RESIDENT_TEMPLATE).hexdigest(),
                action_schema_version=action.action_schema_version,
                action_schema_sha256=canonical_sha256(action),
                context_profile_id=profile.context_profile_id,
                adapter_id=ADAPTER_ID if purpose == "smoke" else "p3-closed-tape-v0",
                adapter_version=ADAPTER_VERSION if purpose == "smoke" else "0.1",
                model_id=MODEL_ID,
                provider_settings=dict(
                    api="deepseek-responses",
                    reasoning_effort="none",
                    store=False,
                    tools=[],
                    background=False,
                    stream=False,
                    input_counter_id=COUNTER_ID if purpose == "smoke" else "p3-tape-count",
                    input_counter_version=COUNTER_VERSION if purpose == "smoke" else "0.1",
                ),
                limits=dict(
                    profile_id="p3-bounded-v0.1",
                    max_attempts=2,
                    attempt_timeout_ms=30000,
                    decision_timeout_ms=60000,
                    retry_delay_ms=0,
                    max_input_tokens=32768,
                    max_output_tokens=2048,
                    max_request_bytes=131072,
                    max_response_bytes=262144,
                ),
                pricing=prices.model_dump(mode="json"),
                fallback_config=dict(
                    policy_id="rule-based-v0",
                    **common,
                    script_sha256=None,
                    source_trace_sha256=None,
                    rule_params=dict(
                        rule_params_version="0.1",
                        canteen_use="enabled",
                        cue_use="enabled",
                        fruit_carry_target=2,
                        failed_target_retry_ticks=36,
                    ),
                ),
                trial_registration_sha256="0" * 64,
            )
        )
        templates.append(
            {
                "actor_id": identity.actor_id,
                "config": policy.model_dump(mode="json", exclude={"trial_registration_sha256"}),
            }
        )
    caps = SMOKE_CAPS if purpose == "smoke" else SMOKE_CAPS.model_copy(update={"micro_cny": 0})
    return TrialRegistration.model_validate(
        dict(
            registration_schema_version="0.1",
            registration_id=registration_id,
            purpose=purpose,
            revision=1,
            implementation_commit=commit,
            implementation_pins=[
                p.model_dump() for p in _pins(repository, commit, _inventory(repository, commit))
            ],
            world_pin_commit=WORLD_COMMIT,
            world_config_path=WORLD_CONFIG,
            world_map_path=WORLD_MAP,
            world_config_sha256=content.config_hash,
            world_map_sha256=content.map_hash,
            input_pins=[p.model_dump() for p in _pins(repository, commit, inputs)],
            cases=[
                dict(
                    case_id=f"{registration_id}.s{SMOKE_SEED}",
                    seed=SMOKE_SEED,
                    ticks=24,
                    llm_actor_ids=["ella"],
                    policy_templates=templates,
                    caps=caps.model_dump(),
                )
            ],
            controls=[],
            aggregate_caps=caps.model_dump(),
            fake_fixture_id=fixture_id if purpose == "fake" else None,
        )
    )


def build_case_inputs(
    repository: Path, registration: TrialRegistration, case_id: str
) -> tuple[WorldContent, dict[str, bytes]]:
    case = next((c for c in registration.cases if c.case_id == case_id), None)
    if case is None:
        raise ValueError("CASE_NOT_REGISTERED")
    content = _world(repository, case.seed)
    identities, sources = _identities(repository, registration.implementation_commit, content)
    pins = {p.path: p for p in (*registration.implementation_pins, *registration.input_pins)}
    modules = {role: list(paths) for role, paths in MODULE_PATHS.items()}
    if registration.purpose == "fake":
        for role in ("adapter", "counter"):
            modules[role] = sorted([*modules[role], "scripts/p3_trials.py"])
    implementation = ImplementationPin.model_validate(
        dict(
            implementation_pin_version="0.1",
            code_commit=registration.implementation_commit,
            modules=[
                dict(role=role, files=[pins[p].model_dump() for p in paths])
                for role, paths in modules.items()
            ],
        )
    )
    expanded = [
        dict(
            actor_id=t["actor_id"],
            config={
                **t["config"],
                "trial_registration_sha256": canonical_sha256(registration),
            },
        )
        for t in case.policy_templates
    ]
    reader = _reader(repository)
    files = {
        "config.json": canonical_bytes(content.config),
        "map.txt": map_bytes_from_rows(content.map_rows),
        "identities.json": canonical_bytes([i.model_dump(mode="json") for i in identities]),
        "identity-sources.json": canonical_bytes([s.model_dump(mode="json") for s in sources]),
        "p3-policy-configs.json": canonical_bytes(expanded),
        "prompt.txt": reader(registration.implementation_commit, PROMPT_PATH),
        "action-schema.json": canonical_bytes(build_model_action_contract()),
        "context-profile.json": canonical_bytes(
            ContextProfile.model_validate_json(
                reader(registration.implementation_commit, CONTEXT_PATH)
            )
        ),
        "trial-registration.json": canonical_bytes(registration),
        "implementation.json": canonical_bytes(implementation),
    }
    validate_inputs(files, run_id=content.config.meta.run_id, source_reader=reader)
    return content, files


def validate_registration(repository: Path, registration_path: Path) -> TrialRegistration:
    """No provider, credential or allocation access; enforce complete source identity."""
    registration = TrialRegistration.model_validate_json(registration_path.read_bytes())
    tapes = [
        p.path
        for p in registration.input_pins
        if p.path.startswith("backend/tests/fixtures/p3/one_resident/") and p.path != PREFLIGHT_PATH
    ]
    if len(tapes) > 1:
        raise ValueError("AMBIGUOUS_FAKE_TAPE")
    expected = build_registration(
        repository,
        registration.implementation_commit,
        purpose=registration.purpose,
        registration_id=registration.registration_id,
        fake_fixture_path=tapes[0] if tapes else None,
    )
    if registration != expected:
        raise ValueError("REGISTRATION_PIN_OR_APPROVED_CASE_MISMATCH")
    head = git(repository, "rev-parse", "HEAD").decode().strip()
    git(
        repository,
        "merge-base",
        "--is-ancestor",
        registration.implementation_commit,
        head,
    )
    if _inventory(repository, head) != [p.path for p in registration.implementation_pins]:
        raise ValueError("IMPLEMENTATION_INVENTORY_DRIFT")
    if git(
        repository,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "backend/src",
        "scripts",
    ).strip():
        raise ValueError("UNTRACKED_IMPLEMENTATION_SOURCE")
    for pin in [*registration.implementation_pins, *registration.input_pins]:
        path = repository / pin.path
        if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != pin.sha256:
            raise ValueError("PINNED_SOURCE_DRIFT")
        if sha256(_blob(repository.resolve(), head, pin.path)).hexdigest() != pin.sha256:
            raise ValueError("EXECUTED_COMMIT_DRIFT")
    pins = {pin.path: pin.sha256 for pin in registration.implementation_pins}
    active = {"scripts/p3_trials.py": Path(__file__)}
    for name, module in list(sys.modules.items()):
        if name == "living_island" or name.startswith("living_island."):
            source = getattr(module, "__file__", None)
            if source is not None:
                path = Path(source)
                suffix = "/__init__.py" if path.name == "__init__.py" else ".py"
                active[f"backend/src/{name.replace('.', '/')}{suffix}"] = path
    if any(
        pins.get(name) != sha256(path.read_bytes()).hexdigest() for name, path in active.items()
    ):
        raise ValueError("ACTIVE_IMPLEMENTATION_SOURCE_DRIFT")
    for case in registration.cases:
        build_case_inputs(repository, registration, case.case_id)
    return registration


class CaseReceipt(P3Model):
    receipt_schema_version: Literal["0.1"]
    registration_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    registration_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    executed_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    case_id: str
    command: list[str]
    status: Literal["not_started", "running", "complete", "failed"]
    exit_code: int | None
    trace_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    failure: str | None
    run_directory: str
    allocation_key: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None

    @model_validator(mode="after")
    def _state(self) -> CaseReceipt:
        if self.status == "not_started":
            valid = (
                not self.command
                and self.exit_code is None
                and self.trace_sha256 is None
                and self.failure is None
            )
        elif self.status == "running":
            valid = (
                bool(self.command)
                and self.exit_code is None
                and self.trace_sha256 is None
                and self.failure is None
            )
        elif self.status == "complete":
            valid = (
                bool(self.command)
                and self.exit_code == 0
                and self.trace_sha256 is not None
                and self.failure is None
            )
        else:
            valid = bool(self.command) and self.failure is not None and self.trace_sha256 is None
        if not valid:
            raise ValueError("INVALID_RECEIPT_STATE")
        return self


class FakeStep(P3Model):
    actor_id: str
    decision_ordinal: Annotated[int, Field(ge=0)]
    attempt_index: Annotated[int, Field(ge=0, le=1)]
    expected_request: ProviderRequest
    expected_wire: WireRequest
    expected_input_tokens: Annotated[int, Field(ge=0)]
    result: ProviderResult


class FakeTape(P3Model):
    fake_schema_version: Literal["0.1"]
    fixture_id: str
    steps: list[FakeStep]

    @model_validator(mode="after")
    def _attempts(self) -> FakeTape:
        seen: dict[tuple[str, int], int] = {}
        previous: tuple[str, int] | None = None
        for step in self.steps:
            identity = (step.actor_id, step.decision_ordinal)
            if identity in seen and identity != previous:
                raise ValueError("FAKE_TAPE_NONCONTIGUOUS_DECISION")
            if step.attempt_index != seen.get(identity, 0):
                raise ValueError("FAKE_TAPE_ATTEMPT_SEQUENCE")
            seen[identity] = step.attempt_index + 1
            previous = identity
        return self


class TapeProvider:
    """Execute only a closed retained tape, checking exact bytes before every return."""

    def __init__(self, tape: FakeTape, *, offset: int = 0) -> None:
        self.tape = FakeTape.model_validate(tape.model_dump(mode="json"))
        if not 0 <= offset <= len(tape.steps):
            raise ValueError("FAKE_TAPE_OFFSET_INVALID")
        self.cursor = offset

    def _step(self, request: ProviderRequest, wire: WireRequest | None = None) -> FakeStep:
        if not 0 <= self.cursor < len(self.tape.steps):
            raise ValueError("FAKE_TAPE_EXHAUSTED")
        step = self.tape.steps[self.cursor]
        identity = json.loads(request.messages[1].content)["request"]
        if (
            request != step.expected_request
            or (wire is not None and wire != step.expected_wire)
            or (identity["actor_id"], identity["decision_ordinal"])
            != (step.actor_id, step.decision_ordinal)
        ):
            raise ValueError("FAKE_TAPE_REQUEST_MISMATCH")
        return step

    def prepare(self, request: ProviderRequest) -> WireRequest:
        return self._step(request).expected_wire.model_copy(deep=True)

    def count_input_tokens(self, request: ProviderRequest, wire: WireRequest) -> int:
        return self._step(request, wire).expected_input_tokens

    def complete(
        self, request: ProviderRequest, wire: WireRequest, timeout_ms: int
    ) -> ProviderResult:
        step = self._step(request, wire)
        if not 0 < timeout_ms <= 30000:
            raise ValueError("FAKE_TAPE_DEADLINE_INVALID")
        self.cursor += 1
        return step.result.model_copy(deep=True)

    def assert_consumed(self) -> None:
        if self.cursor != len(self.tape.steps):
            raise ValueError("FAKE_TAPE_CALLS_MISSING")


class NoExternalAccess:
    def __getattribute__(self, name: str) -> Any:
        raise AssertionError(f"offline replay accessed {name}")


def common_directory(repository: Path) -> Path:
    value = Path(git(repository, "rev-parse", "--git-common-dir").decode().strip())
    return (repository / value).resolve()


def live_locations(repository: Path) -> tuple[Path, Path]:
    directory = common_directory(repository) / "living-island-p3"
    return directory / "authority", directory / "pilot-approval.json"


def _persistent_lock(path: Path) -> _ProcessLock:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(b"\0")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        pass
    return _ProcessLock(path)


def initialize_authority(repository: Path) -> None:
    """Explicit one-time M8 action; loss of an issued root never makes another grant."""
    common = common_directory(repository)
    marker = common / "living-island-p3-enrollment.json"
    with _persistent_lock(common / "living-island-p3-enrollment.lock"):
        if marker.exists():
            raise ValueError("PILOT_ALREADY_INITIALIZED_OR_REQUIRES_REPAIR")
        root, approval = live_locations(repository)
        _atomic_write(
            marker,
            canonical_bytes(
                dict(
                    authority_root=str(root),
                    approval_path=str(approval),
                    ceiling_micro_cny=150000000,
                )
            ),
            None,
            "pilot_locator",
        )
        initialize_pilot(approval, root)


def _live_store(repository: Path) -> AllocationStore:
    root, approval = live_locations(repository)
    marker = common_directory(repository) / "living-island-p3-enrollment.json"
    expected = dict(
        authority_root=str(root),
        approval_path=str(approval),
        ceiling_micro_cny=150000000,
    )
    if not marker.is_file() or marker.read_bytes() != canonical_bytes(expected):
        raise ValueError("PILOT_ENROLLMENT_UNAVAILABLE")
    return AllocationStore(root, mode="live", approval_path=approval)


def _registration_commit(repository: Path, path: Path) -> str:
    relative = path.resolve().relative_to(repository.resolve()).as_posix()
    head = git(repository, "rev-parse", "HEAD").decode().strip()
    try:
        committed = git_source_reader(repository)(head, relative)
    except ValueError:
        raise ValueError("REGISTRATION_MUST_BE_COMMITTED") from None
    if committed != path.read_bytes():
        raise ValueError("REGISTRATION_MUST_BE_COMMITTED")
    commit = git(repository, "log", "-1", "--format=%H", "--", relative).decode().strip()
    if not commit:
        raise ValueError("REGISTRATION_MUST_BE_COMMITTED")
    return commit


def _receipt_directory(repository: Path, registration: TrialRegistration) -> Path:
    return (
        common_directory(repository).parent
        / "runs"
        / "p3"
        / registration.registration_id
        / "receipts"
    )


def enroll_registration(
    repository: Path, path: Path, *, fake_authority: Path | None = None
) -> list[str]:
    registration = validate_registration(repository, path)
    registration_commit = _registration_commit(repository, path)
    if registration.purpose == "fake":
        if fake_authority is None:
            raise ValueError("ISOLATED_FAKE_AUTHORITY_REQUIRED")
        store = AllocationStore(fake_authority, mode="fake")
    else:
        if fake_authority is not None:
            raise ValueError("LIVE_AUTHORITY_CANNOT_BE_OVERRIDDEN")
        store = _live_store(repository)
    receipts = _receipt_directory(repository, registration)
    with _persistent_lock(receipts / "receipt.lock"):
        keys = []
        for case in registration.cases:
            key = (
                store.enroll_fake(canonical_sha256(registration), case.case_id, case.caps)
                if registration.purpose == "fake"
                else store.enroll_live(
                    registration.purpose,
                    case.seed,
                    canonical_sha256(registration),
                    case.case_id,
                    case.caps,
                )
            )
            keys.append(key)
            receipt_path = receipts / f"{case.case_id}.json"
            expected = CaseReceipt(
                receipt_schema_version="0.1",
                registration_sha256=canonical_sha256(registration),
                registration_commit=registration_commit,
                executed_commit=git(repository, "rev-parse", "HEAD").decode().strip(),
                case_id=case.case_id,
                command=[],
                status="not_started",
                exit_code=None,
                trace_sha256=None,
                failure=None,
                run_directory="",
                allocation_key=key,
            )
            if receipt_path.exists():
                if CaseReceipt.model_validate_json(receipt_path.read_bytes()) != expected:
                    raise ValueError("RECEIPT_ALREADY_STARTED")
            else:
                _atomic_write(receipt_path, canonical_bytes(expected), None, "receipt_enroll")
        return keys


def _credential(path: Path) -> str:
    """Read only the explicit ignored .env file, without interpolation or environment fallback."""
    if path.name != ".env" or not path.is_file() or path.is_symlink():
        raise ValueError("DOTENV_CREDENTIAL_UNAVAILABLE")
    values = []
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if name.strip() == "DEEPSEEK_API_KEY" and separator:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values.append(value)
    except (OSError, UnicodeError):
        raise ValueError("DOTENV_CREDENTIAL_UNAVAILABLE") from None
    if len(values) != 1 or not values[0] or any(ord(c) < 33 or ord(c) > 126 for c in values[0]):
        raise ValueError("DOTENV_CREDENTIAL_INVALID")
    return values[0]


def _remaining(store: AllocationStore, key: str) -> dict[str, int]:
    case = CaseAllocationP3.model_validate_json(
        (store.root / "allocations" / f"{key}.json").read_bytes()
    )
    if case.allocation_key != key or case.status in {"offline_only", "complete"}:
        raise ValueError("ALLOCATION_CLOSED")
    amounts = dict(attempts=len(case.entries), input_tokens=0, output_tokens=0, micro_cny=0)
    for entry in case.entries:
        if entry.debit is None:
            amounts["input_tokens"] += entry.reservation.input_reserved
            amounts["output_tokens"] += entry.reservation.output_reserved
            amounts["micro_cny"] += entry.reservation.money_reserved
        else:
            amounts["input_tokens"] += entry.debit.input_charged
            amounts["output_tokens"] += entry.debit.output_charged
            amounts["micro_cny"] += entry.debit.money_charged
    remaining = {field: getattr(case.caps, field) - amount for field, amount in amounts.items()}
    if any(value <= 0 for value in remaining.values()):
        raise ValueError("NO_REMAINING_ALLOCATION")
    return remaining


def initial_request_preflight(
    content: WorldContent, files: dict[str, bytes]
) -> list[dict[str, int | str]]:
    """Build actual first-boundary requests without a journal, allocation or transport."""
    provider = DeepSeekResponsesAdapter()
    policies = {
        row["actor_id"]: ActorPolicyConfig.model_validate(row).config
        for row in json.loads(files["p3-policy-configs.json"])
    }
    identities = {
        row["actor_id"]: ResidentIdentity.model_validate(row)
        for row in json.loads(files["identities.json"])
    }
    profile = ContextProfile.model_validate_json(files["context-profile.json"])
    results = []
    for packet in create_engine(content, None).initial_commit().pending_deliveries:
        config = policies[packet.actor_id]
        if config.policy_id != "llm-v0":
            continue
        runtime = create_p3_runtime(
            packet.actor_id,
            config,
            identities[packet.actor_id],
            live_enabled=True,
            provider=provider,
            budget=NoExternalAccess(),
            attempts=NoExternalAccess(),
            fallback=NoExternalAccess(),
            run_id=content.config.meta.run_id,
            context_profile=profile,
            template=files["prompt.txt"],
            purpose="live",
        )
        runtime.ingest(packet)
        state = runtime.export_state()
        request = runtime.make_request(packet.observed_tick, packet.decision_triggers)
        assembly = assemble_context(packet.perception, state.cognitive_state, profile)
        if assembly.error is not None:
            raise ValueError("INITIAL_CONTEXT_MANDATORY_OVERSIZE")
        prepared = render_provider_request(assembly, request, config, files["prompt.txt"])
        wire = provider.prepare(prepared)
        count = provider.count_input_tokens(prepared, wire)
        if type(count) is not int or not 0 <= count <= config.limits.max_input_tokens:
            raise ValueError("INITIAL_CONTEXT_INPUT_LIMIT")
        money = (count * config.pricing.input_micro_cny_per_million_tokens + 999999) // 1000000 + (
            config.limits.max_output_tokens * config.pricing.output_micro_cny_per_million_tokens
            + 999999
        ) // 1000000
        results.append(
            dict(
                actor_id=packet.actor_id,
                input_tokens=count,
                output_tokens=config.limits.max_output_tokens,
                micro_cny=money,
            )
        )
    return results


def run_registration(
    repository: Path,
    path: Path,
    case_id: str,
    output: Path,
    *,
    live: bool = False,
    checkpoint: Path | None = None,
    offline_recovery: bool = False,
    ancestors: tuple[Path, ...] = (),
    dotenv: Path | None = None,
    fake_authority: Path | None = None,
    provider: ProviderAdapter | None = None,
    fallback: FallbackAdapter | None = None,
    tape_path: Path | None = None,
    command: list[str] | None = None,
    ticks: int | None = None,
    fetch: Callable[[str], bytes] = fetch_public_document,
) -> P3RunResult:
    registration = validate_registration(repository, path)
    registration_commit = _registration_commit(repository, path)
    if live and offline_recovery:
        raise ValueError("LIVE_AND_OFFLINE_RECOVERY_ARE_EXCLUSIVE")
    if offline_recovery and checkpoint is None:
        raise ValueError("OFFLINE_RECOVERY_REQUIRES_CHECKPOINT")
    is_fake = registration.purpose == "fake"
    if (is_fake and live) or (not is_fake and not live and not offline_recovery):
        raise ValueError("LIVE_MODE_DOES_NOT_MATCH_REGISTRATION")
    if not is_fake and (fake_authority is not None or provider is not None or fallback is not None):
        raise ValueError("LIVE_PORT_OR_AUTHORITY_OVERRIDE_REFUSED")
    content, files = build_case_inputs(repository, registration, case_id)
    policies = [
        ActorPolicyConfig.model_validate(row).config
        for row in json.loads(files["p3-policy-configs.json"])
    ]
    if not all(policy.fallback_config == policies[0].fallback_config for policy in policies):
        raise ValueError("FALLBACK_CONFIGURATION_MISMATCH")
    source_reader = _reader(repository)
    key = allocation_key(canonical_sha256(registration), case_id)
    if is_fake and fake_authority is None:
        raise ValueError("ISOLATED_FAKE_AUTHORITY_REQUIRED")
    store = AllocationStore(fake_authority, mode="fake") if is_fake else _live_store(repository)
    receipts = _receipt_directory(repository, registration)
    with _persistent_lock(receipts / "receipt.lock"):
        receipt_path = receipts / f"{case_id}.json"
        prior = CaseReceipt.model_validate_json(receipt_path.read_bytes())
        if (prior.registration_sha256, prior.case_id, prior.allocation_key) != (
            canonical_sha256(registration),
            case_id,
            key,
        ):
            raise ValueError("RECEIPT_ALLOCATION_MISMATCH")
        if prior.status == "complete" or (checkpoint is None and prior.status != "not_started"):
            raise ValueError("CASE_ALREADY_STARTED")
        if checkpoint is not None:
            verified = read_checkpoint_p3(
                checkpoint, ancestors=ancestors, source_reader=source_reader
            )
            if (
                verified.inputs["trial-registration.json"] != canonical_bytes(registration)
                or verified.save.run_budget.allocation_key != key
            ):
                raise ValueError("CHECKPOINT_REGISTRATION_MISMATCH")
            authority = CaseAllocationP3.model_validate_json(
                (store.root / "allocations" / f"{key}.json").read_bytes()
            )
            # A crash can leave the invocation receipt ahead of the durable head.
            # The authority, rather than the attempted output path, owns resume.
            matches = [
                head
                for head in (authority.head, authority.prepared_head)
                if head is not None
                and head.checkpoint_sha256 == sha256(verified.raw).hexdigest()
                and head.run_directory == str(checkpoint.parent.resolve())
            ]
            if not matches or authority.status == "complete":
                raise ValueError("CHECKPOINT_AUTHORITY_HEAD_MISMATCH")
            if not offline_recovery and (
                authority.status == "offline_only"
                or len(authority.entries) > len(verified.save.allocation_entries)
            ):
                raise ValueError("INTERRUPTED_CALL_RECOVERY_REQUIRED")
        output = output.resolve()
        allowed = repository.resolve() / "runs" / "p3" / registration.registration_id
        if not output.is_relative_to(allowed) or output.exists():
            raise ValueError("OUTPUT_MUST_BE_FRESH_REGISTERED_RUN_DIRECTORY")
        observation = None
        if not is_fake and not offline_recovery:
            evidence = LiveEvidence.model_validate_json(
                source_reader(registration.implementation_commit, PREFLIGHT_PATH)
            )
            observation = current_preflight(evidence, fetch=fetch)
            observation["remaining"] = _remaining(store, key)
            if checkpoint is None:
                observation["initial_requests"] = initial_request_preflight(content, files)
                for request in observation["initial_requests"]:
                    if any(
                        request[field] > observation["remaining"][field]
                        for field in ("input_tokens", "output_tokens", "micro_cny")
                    ):
                        raise ValueError("INSUFFICIENT_INITIAL_RESERVATION")
            if dotenv is None:
                raise ValueError("DOTENV_CREDENTIAL_UNAVAILABLE")
            provider = DeepSeekResponsesAdapter(HTTPSByteTransport(_credential(dotenv)))
        elif offline_recovery:
            provider = NoExternalAccess()
        elif provider is None:
            if tape_path is None:
                raise ValueError("PINNED_FAKE_TAPE_REQUIRED")
            relative = tape_path.resolve().relative_to(repository.resolve()).as_posix()
            if not any(
                pin.path == relative and pin.sha256 == sha256(tape_path.read_bytes()).hexdigest()
                for pin in registration.input_pins
            ):
                raise ValueError("FAKE_TAPE_NOT_PINNED")
            tape = FakeTape.model_validate_json(tape_path.read_bytes())
            if tape.fixture_id != registration.fake_fixture_id:
                raise ValueError("FAKE_TAPE_IDENTITY_MISMATCH")
            offset = 0 if checkpoint is None else len(verified.save.allocation_entries)
            provider = TapeProvider(tape, offset=offset)
        fallback = fallback or FrozenRuleFallbackAdapter(policies[0].fallback_config)
        assert provider is not None
        invocation = command or [
            "p3_trials.py",
            "resume" if checkpoint else "run",
            "--case",
            case_id,
            "--out",
            str(output),
        ]
        running = CaseReceipt.model_validate(
            {
                **prior.model_dump(mode="json"),
                "registration_commit": registration_commit,
                "executed_commit": git(repository, "rev-parse", "HEAD").decode().strip(),
                "command": invocation,
                "status": "running",
                "exit_code": None,
                "trace_sha256": None,
                "failure": None,
                "run_directory": str(output),
            }
        )
        history = receipts / "lineage" / case_id / sha256(canonical_bytes(running)).hexdigest()
        if history.exists():
            raise ValueError("RECEIPT_LINEAGE_ALREADY_EXISTS")
        history.mkdir(parents=True)
        _atomic_write(history / "previous.json", canonical_bytes(prior), None, "receipt_previous")
        if observation is not None:
            _atomic_write(
                history / "public-preflight.json",
                canonical_bytes(observation),
                None,
                "receipt_preflight",
            )
        _atomic_write(receipt_path, canonical_bytes(running), None, "receipt_running")
        try:
            if checkpoint is None:
                result = run_p3(
                    content,
                    files,
                    case_id,
                    output,
                    allocation_store=store,
                    provider=provider,
                    fallback=fallback,
                    source_reader=source_reader,
                    ticks=ticks,
                )
            else:
                result = resume_p3(
                    checkpoint,
                    output,
                    allocation_store=store,
                    provider=provider,
                    fallback=fallback,
                    source_reader=source_reader,
                    ancestors=ancestors,
                    ticks=ticks,
                    offline_recovery=offline_recovery,
                )
            if result.trace is not None and isinstance(provider, TapeProvider):
                provider.assert_consumed()
            if result.trace is not None:
                from living_island.sim.p3 import export_p3_replay

                export_p3_replay(
                    result.output,
                    result.output / "replay.json",
                    ancestors=result.ancestors,
                    source_reader=source_reader,
                )
            completed = CaseReceipt.model_validate(
                {
                    **running.model_dump(mode="json"),
                    "status": "complete" if result.trace is not None else "running",
                    "exit_code": 0 if result.trace is not None else None,
                    "trace_sha256": sha256(
                        (result.output / "decision-trace-p3.json").read_bytes()
                    ).hexdigest()
                    if result.trace
                    else None,
                }
            )
            _atomic_write(
                history / "receipt.json",
                canonical_bytes(completed),
                None,
                "receipt_lineage",
            )
            _atomic_write(receipt_path, canonical_bytes(completed), None, "receipt_final")
            return result
        except Exception as exc:
            failed = CaseReceipt.model_validate(
                {
                    **running.model_dump(mode="json"),
                    "status": "failed",
                    "exit_code": 1,
                    "failure": type(exc).__name__,
                }
            )
            _atomic_write(
                history / "receipt.json",
                canonical_bytes(failed),
                None,
                "receipt_lineage",
            )
            _atomic_write(receipt_path, canonical_bytes(failed), None, "receipt_failed")
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    subcommands = parser.add_subparsers(dest="operation", required=True)
    register = subcommands.add_parser(
        "register", help="build an immutable registration; commit it before enrollment"
    )
    register.add_argument("--implementation-commit", required=True)
    register.add_argument("--registration-id", default="p3-smoke-r1")
    register.add_argument("--purpose", choices=["smoke", "fake"], default="smoke")
    register.add_argument("--fake-fixture-path")
    register.add_argument("--out", type=Path, required=True)
    initialize = subcommands.add_parser(
        "initialize", help="explicit one-time authority initialization, no dispatch"
    )
    modes = initialize.add_mutually_exclusive_group(required=True)
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--fake-authority", type=Path)
    for name in ["validate", "enroll", "run", "resume"]:
        command_parser = subcommands.add_parser(name)
        command_parser.add_argument("--registration", type=Path, required=True)
        if name == "enroll":
            command_parser.add_argument("--fake-authority", type=Path)
        if name in {"run", "resume"}:
            command_parser.add_argument("--case", required=True)
            command_parser.add_argument("--out", type=Path, required=True)
            mode = command_parser.add_mutually_exclusive_group()
            mode.add_argument("--live", action="store_true")
            if name == "resume":
                mode.add_argument("--offline-recovery", action="store_true")
                command_parser.add_argument("--checkpoint", type=Path, required=True)
                command_parser.add_argument("--ancestor", type=Path, action="append", default=[])
            command_parser.add_argument("--dotenv", type=Path)
            command_parser.add_argument("--fake-authority", type=Path)
            command_parser.add_argument("--tape", type=Path)
            command_parser.add_argument(
                "--ticks",
                type=int,
                help="pause after this many ticks without changing the registered horizon",
            )
    replay = subcommands.add_parser(
        "replay", help="recorded execution with raising external-access sentinels"
    )
    replay.add_argument("--source-run", type=Path, required=True)
    replay.add_argument("--out", type=Path, required=True)
    replay.add_argument("--ancestor", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    repository = args.repository.resolve()
    try:
        if args.operation == "register":
            registration = build_registration(
                repository,
                args.implementation_commit,
                purpose=args.purpose,
                registration_id=args.registration_id,
                fake_fixture_path=args.fake_fixture_path,
            )
            output = args.out.resolve()
            if (
                not output.is_relative_to(repository / "content/experiments/p3/development")
                or output.exists()
            ):
                raise ValueError("REGISTRATION_OUTPUT_MUST_BE_FRESH")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(canonical_bytes(registration))
            print(f"registration_sha256={canonical_sha256(registration)}")
        elif args.operation == "initialize":
            if args.live:
                initialize_authority(repository)
            else:
                if args.fake_authority.resolve().is_relative_to(common_directory(repository)):
                    raise ValueError("FAKE_AUTHORITY_MUST_BE_ISOLATED")
                initialize_fake(args.fake_authority)
            print("authority initialized; no dispatch")
        elif args.operation == "validate":
            registration = validate_registration(repository, args.registration)
            print(f"VALID registration_sha256={canonical_sha256(registration)}; no dispatch")
        elif args.operation == "enroll":
            keys = enroll_registration(
                repository, args.registration, fake_authority=args.fake_authority
            )
            print(json.dumps({"allocation_keys": keys, "dispatches": 0}))
        elif args.operation == "replay":
            result = reexecute_p3(
                args.source_run,
                args.out,
                provider=NoExternalAccess(),
                fallback=NoExternalAccess(),
                allocation_store=NoExternalAccess(),
                source_reader=_reader(repository),
                ancestors=tuple(args.ancestor),
            )
            from living_island.sim.p3 import export_p3_replay

            export_p3_replay(
                result.output,
                result.output / "replay.json",
                ancestors=result.ancestors,
                source_reader=_reader(repository),
            )
            print(f"replayed tick={result.world.tick}; external_calls=0")
        else:
            result = run_registration(
                repository,
                args.registration,
                args.case,
                args.out,
                live=args.live,
                checkpoint=getattr(args, "checkpoint", None),
                offline_recovery=getattr(args, "offline_recovery", False),
                ancestors=tuple(getattr(args, "ancestor", [])),
                dotenv=args.dotenv,
                fake_authority=args.fake_authority,
                tape_path=args.tape,
                ticks=args.ticks,
                command=[
                    sys.executable,
                    str(Path(__file__).resolve()),
                    *(sys.argv[1:] if argv is None else argv),
                ],
            )
            ledger = result.checkpoint.run_budget
            print(
                f"tick={result.world.tick} complete={result.trace is not None} "
                f"charged_micro_cny={ledger.money_charged}"
            )
    except Exception as exc:
        # Never echo exception messages after a credential might have been injected.
        print(f"P3_TRIAL_REFUSED: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
