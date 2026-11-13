# P3-05 offline single-resident evidence

Closed tape: 24 steps, 3279688 bytes, SHA-256
`68acba21ebed8b1b9c10edd458c7cc1f3f056e37b32db160adfd0d383889722f`.
The first scripted input count is 49 fake units.

These are local fake fixtures. They contain no hosted response, key, invoice, or
claim that scripted input units are production DeepSeek tokens.

`slice_smoke_tape.json` is one closed 24-tick tape over the frozen default island,
with only the M8 smoke seed override (1292387875). Ella is the sole primary LLM
actor; Mia and Ryan execute the frozen rule policy inside P3 envelopes. The
principal test uses the actual launcher's registration and input builders and
`TapeProvider`. Every step pins its whole typed provider request, retained wire
bytes, scripted input count, attempt ordinal, and complete mapped response.
Requests, missing calls, extra calls, and wire mismatches fail closed. Tests never
regenerate this tape when a comparison fails.

Execution registrations pin the executing repository's committed HEAD, including
the exact tape input blob and complete launcher implementation inventory. This
permits documentation-only descendants without depending on an unpublished child
branch's Git objects. The historical authoring commits below document provenance;
they are not source-reader dependencies of the tests.

The tape was authored once using the approved pure builders at launcher commit
`fcd70fbef526f4ac773d80a8954246775d1408ec`, the real DeepSeek Responses wire renderer
and response mapper, and injected local byte transport. Every local proposal is
`wait` with an explicit `continue` delta. The retained local Responses envelope
reports 10 input units and 20 output units; deterministic diagnostic latency is
1 ms. At authoring time, the scripted input count was chosen by the exact fixture
rule `ceil(len(retained_wire_bytes) / 1024)`. At execution, the launcher returns
the exact retained count under `p3-tape-count/0.1`; it does not invoke that rule
or a production tokenizer. Adapter identity is `p3-closed-tape-v0/0.1`, with
zero prices and zero micro-CNY. The model label describes the actual wire shape.

Focused mechanics tests use `slice_fake_counter.py`, introduced at
`a7fd50fdcbdb8c7d74d6293c9655adee3017e404` and input-pinned at execution HEAD, under the distinct
`fixture-p3-05-wire-chunks/0.1` identity. They execute the real wire mapper and
frozen fallback over a custom tiny island solely to make exact goal, death,
budget, action, and feedback oracles practical. The active/queued action fixture
uses full visibility of that tiny island so new-sight interrupts do not obscure
the continuation oracle. These focused fixtures are not the principal tape or
evidence about unchanged production token admission.

The accepted production byte-bound counter at baseline
`522762f81ef83d8ad51a52a9d021e13134810422` counted the first default-world Ella
request as 45161 input tokens, above B-05's 32768. That independent startup probe
refused dispatch with `INPUT_LIMIT`. P3-05 reported it to P3-04; fake counting
does not fix or waive the production blocker.

## VF coverage map

The P3-05 executor runs the complete inherited suite as well as these integration
seams. Names below identify actual owner tests; this map does not claim an
additional full-suite execution by the fixture author.

| Vector | Evidence |
| --- | --- |
| VF-01 | `test_frozen_smoke_world_one_model_actor_and_zero_call_replay`; transaction `test_bd01_stages_whole_transaction_then_publishes_once` |
| VF-02 | `test_rejected_attempt_then_success_commits_only_one_goal[malformed]`; transaction deep-JSON/retry tests |
| VF-03 | `test_two_bad_responses_use_real_fallback_then_return_to_model`; transaction BD-03 |
| VF-04 | Transaction `test_timeout_uses_remaining_decision_deadline_and_records_both_attempts`, BD-17 |
| VF-05 | `test_rejected_attempt_then_success_commits_only_one_goal[provider_error]`; provider HTTP/status mapping |
| VF-06 | Transaction BD-02; cognition CG-05/06 |
| VF-07 | Context EX-06; transaction BD-04 and `test_input_token_limit_zero_calls_and_null_dispatchable_request` |
| VF-08 | `test_single_attempt_malformed_response_cannot_retry`; `test_real_allocation_money_one_below_reservation_prevents_runtime_dispatch` uses the actual case authority with positive synthetic integer pricing and a cap exactly one micro-CNY below the reservation |
| VF-09 | `test_unknown_usage_consumes_full_reservation_and_budget_fallback_is_visible`; transaction BD-05/06 |
| VF-10 | Transaction `test_provider_overrun_retains_terminal_then_halts_without_retry_or_fallback` |
| VF-11 | Provider raw-body boundary/empty/null tests and context response sentinel boundary |
| VF-12 | Allocation BD-18..27, real process/crash vectors, enrollment vectors; `test_interrupted_real_mapping_recovers_once_without_model_access`; repeated zero-tick continuations |
| VF-13 | Existing persistence/recovery prefix/version/hash tests; `test_replay_export_refuses_missing_and_corrupt_intermediate_checkpoints` |
| VF-14 | Real fallback entry/return/reentry tests; `test_two_bad_responses_use_real_fallback_then_return_to_model` |
| VF-15 | Transaction `test_real_fallback_malformed_plan_commits_one_wait_and_preserves_all_private_state` and `test_real_fallback_programming_and_io_failures_stop_runtime` |
| VF-16 | Experience EX-01..10 and context EX-09; transaction ingestion idempotence tests |
| VF-17 | `test_engine_transfer_feedback_requires_own_completed_give`: real engine request/accept, failed give, recipient inventory change, then exact own completed give; cognition CG-01..12 and single-resident goal lifecycle |
| VF-18 | `test_three_runtime_contexts_keep_conflicting_claims_and_nonhearing_store_separate` assembles actual contexts for one LLM/two rule runtimes with two contradictory delivered claims and a third empty hearing store; malicious strings remain user data with no extra role/tool. Principal slice additionally checks every actor's own store and request identity |
| VF-19 | `test_live_checkpoint_with_active_and_queued_actions_resumes_exactly`; every completed `run_p3` scenario uses raising provider, fallback, and authority replay sentinels |

The replay continuation test compares all five logs, full checkpoint state, private
state, cognition and cursors, T+1 observer frames, exported display bundles, and
source bytes. It includes two zero-tick clean continuations with identical boundary
checkpoint hashes before the resumed suffix. Export negative cases remove exactly
one intermediate checkpoint, corrupt one checkpoint, or replace it with a valid
checkpoint from a different decision lineage. No authority or provider participates
in recorded reexecution or export.

The transfer fixture uses one Ella model runtime and explicit engine-protocol
intents for the other actors. Its world oracles correspond to
`backend/tests/unit/test_engine_dialogue.py::test_request_reply_and_hearing_event_order`,
`backend/tests/unit/test_engine_actions.py::test_eat_drink_fill_and_give_effects`, and
`backend/tests/invariants/test_legal_physical_sequences.py::test_item_5_give_needs_an_adjacent_recipient_and_owned_items`.
The new seam feeds their actual engine boundary deliveries into P3 ingestion; it
does not synthesize successful or failed transfer feedback.

## CR-006 schema 0.2 fixture

`slice_smoke_tape.json` remains the historical 0.1 tape, and the two old
registrations retain their original implementation and input pins. The current
adapter refuses the old schema. Historical validation and replay use the exact
pinned implementation as recorded in [M9 evidence](../../../../../docs/tasks/p3/M9-evidence.md).

`slice_smoke_schema02_tape.json` contains 24 separate offline test steps
(3353152 bytes, SHA-256
`ccc5f2c0bc3c1ac5374a867bcea79ea3bfc15a491be80f0debdf718d83919056`).
The new fixture copies the old user messages, scripted input units and mapped
local responses. It substitutes the current canonical action contract in the
system message and response schema and renders each wire through the production
adapter. The retained fake units remain explicit integers for the new fixture.
The arithmetic rule described above was used when authoring the historical
tape. Production token admission is independently verified by the P3-04 tests.

The principal test uses the new `p3-slice-fake-schema02-r1` test registration
with the new fixture pinned to the executing commit. It verifies all 24 wire
envelopes, completes 24 ticks on the frozen island, and reexecutes the entire
run with raising sentinels and byte-identical outputs. The tests also pin the
old tape hash and exercise refusal of its schema under the new adapter.
