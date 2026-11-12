# M8 owner decision sheet: P3 resident-agent foundation

> **Approved by the owner, 2026-11-12; amended the same day.** All eleven M8
> decisions are approved, with DeepSeek and a total CNY150 API ceiling replacing
> the earlier OpenAI/USD112 choice. Independent P3-01 Gate 2 passed at `659e1212`.
> This records implementation authority; live calls still require implemented
> gates, registered identities, preflight and the remaining approved allocation.

Package: [implementation plan](../../plans/p3-implementation-plan-v0.1.md),
[experience/context](../../spec/resident-experience-v0.1.md),
[cognition](../../spec/resident-cognition-v0.1.md),
[decision/recovery](../../spec/llm-decision-v0.1.md),
[evaluation](../../spec/p3-evaluation-v0.1.md),
[Accepted ADR 0006](../../adr/0006-p3-design.md),
[CR-005 exact amendment text](../../spec/open-questions.md#cr-005-exact-amendments-for-m8-not-applied).
Task cards: [02](P3-02.md), [03](P3-03.md), [04](P3-04.md), [05](P3-05.md),
[06](P3-06.md), [07](P3-07.md).

## 1. Decisions

Section 5 records every owner disposition. The following recommendations are now
the approved choices, amended for DeepSeek/CNY150. Changed frozen rules require a CR.

| ID | Choice and options | One recommendation | Blocks |
| --- | --- | --- | --- |
| M8-01 | Versioned P3 lane vs extending legacy types in place | Approve the separate P3 0.2 context/request/runtime/decision/save lane, 0.1 nested cognitive/log schemas and exact CR-005 amendments; preserve P1/P2 bytes and refuse unknown versions. | All implementation |
| M8-02 | Working memory/confidence: bounded typed samples vs ports only or psychological scoring | Approve E profile and delivered/null vs interpretation/unassessed confidence, with exact context/strategy/manifest bindings and pinned deterministic replay. Keep the alternate recent-only strategy fake-only; later cognitive systems remain named ports only. | P3-02/06; OQ-082; G2-R1-02 |
| M8-03 | Identity/goals: explicit profiles and one commitment vs infer personality or autonomous long-term scheduling | Approve the three exact profile value lists, immutable identity and configured direction; one continue/revise/abandon commitment with own-feedback completion and unverifiable receiving goals. | P3-02; OQ-084/085/086 |
| M8-04 | Fallback: frozen rule adapter with explicit inactive/return state vs reset all knowledge or rewrite the rule algorithm | Approve the llm-decision lifecycle, retaining shared experience and permitted learned rule state, with no retroactive LLM-action learning in frozen rule state. | P3-03/04; OQ-083 |
| M8-05 | Recovery: one persistent case allocation with exclusive continuation ownership vs treating each restored snapshot as a new grant | Approve the decision spec's enrolled authority, durable reservations, current-head/lock protocol and conservative offline recovery. Normal authorized clean continuation needs no renewed approval; repeated/concurrent restores and replay cannot replenish capacity. New/changed allocations need a new authorized registration. | P3-03/05; OQ-090; G2-R1-01 |
| M8-06 | Provider/model | DeepSeek Responses, deepseek-flash in non-thinking mode, structured JSON and no tools/stream/history. Preserve model-version evidence and reject detected drift; pin adapter/schema/counter/CNY prices before live use. | P3-04/live trials; OQ-087 |
| M8-07 | Credentials: ignored local .env vs external secret service/deferred live calls | Choose .env only, loaded by the outer launcher and injected only into the provider client; retain no secret in profiles, registrations, prompts, logs or Git. No credentials are needed for fake/recorded tests. | Live calls; OQ-088 |
| M8-08 | Limits: approve all proposed E/C/B rows below vs a revised versioned profile | Approve the listed values as one measured initial profile; publish actual high-water/overflow/failure measurements before proposing revisions. | P3-02/03/04; OQ-082 |
| M8-09 | Trials/pass lines: bounded separately budgeted pilot vs larger live matrix or fake-only deferral | Approve V profile: one 24-tick smoke, two 48-tick development runs, three fresh 144-tick acceptance runs; total maximum CNY150 across separate allocations. Require full technical validity and, for smoke/acceptance, zero wait substitutions and the V LLM-share threshold; live survival/effect size remains descriptive. | P3-05/07; OQ-082 |
| M8-10 | Character panel/debug view now vs explicit deferral | Include both in P3-07 via the separate versioned inspection artifact; leave ReplayBundle and its generated files unchanged. | P3-07/M10; OQ-089 |
| M8-11 | Delivery order: proposed 02..07 and M8/M9/M10 vs a separately approved split | Approve pure foundation first, parallel 03/04 with disjoint files, then serial 05/M9,06,07/M10. Apply CR-005 after this decision; no author-team Gate 2 or merge into main in P3-01. | Task scheduling |

### Provider evidence and approved price ceiling

Official DeepSeek documentation checked 2026-11-12 lists deepseek-flash, currently
DeepSeek-V4.1-Flash-1017, Responses support and peak uncached CNY2 input / CNY8
output per million tokens. The Responses API supports reasoning.effort=none and
JSON Schema output; it is stateless and does not support store/background request
parameters. The adapter must omit those parameters while retaining the semantic
false settings. This is documented capability, not a successful project integration.

- [DeepSeek CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)
- [DeepSeek Responses compatibility](https://api-docs.deepseek.com/guides/responses_api/)

Use integer micro-CNY and reserve peak uncached prices without discounts or FX.
The maximum attempt reserves (32768*2000000 + 2048*8000000)/1000000 = 81920
micro-CNY. Money caps may bind before attempt caps; the evaluation spec records
exact arithmetic and unchanged pass criteria. A missing counter, unavailable model,
changed price or model-version evidence refuses live startup. An alias is not an
immutable snapshot. P3-02 needs no API key or live call.

## 2. Approved limit register

This sheet mirrors the approved decision values; each rule, rationale and measurement
has a single owning specification. Zero-tolerance technical requirements and fixed
schema identities are not configurable implementation knobs. Existing world values
are unchanged references, not additional P3 limits.

### Experience and context (owner: resident-experience section 7)

| ID | Approved value and unit | Rationale | Measurement |
| --- | --- | --- | --- |
| E-01 | 1,024 retained records per resident | Bounded working history | High-water count, eviction and retained span |
| E-02 | 1,048,576 canonical UTF-8 bytes per records array | Bounded exact history | Bytes, oversized-record eviction, separate refs/goal size |
| E-03 | 16 recalled records per decision | Inspectable selection | Kinds, ages, omissions, fixture evidence coverage |
| E-04 | 65,536 canonical UTF-8 bytes per projection | Full current information before optional history | Mandatory/projected bytes, overflow and token counts |
| E-05 | 128 explored-static candidate tiles | Bounded optional geography | Omissions, route failures and request size |

### Cognition (owner: resident-cognition section 5)

| ID | Approved value and unit | Rationale | Measurement |
| --- | --- | --- | --- |
| C-01 | 1 current commitment per resident | Continuity without scheduler | State cardinality and transitions |
| C-02 | 1..240 Unicode scalars per goal text | Inspectable short intent | Length/rejection histogram, exact boundary fixtures |
| C-03 | 0..8 profile values, each 1..160 Unicode scalars | Small explicit identity | Rendered length and boundary fixtures |
| C-04 | Name 1..120; initial direction 1..500 Unicode scalars | Bounded mandatory identity | Startup cases and mandatory bytes |
| C-05 | Nullable reason; non-null 0..240 Unicode scalars | Short action explanation | Length/rejection count and null case |
| C-06 | 0..500 Unicode scalars per generated talk text | Bounded authored speech | Length/rejection count and boundary fixtures |
| C-07 | 8,192 UTF-8 bytes per trusted template | Bounded static prompt | Byte count/hash and full request size |

### Decision/provider limits

| ID | Approved value / unit | Rationale | Measurement / review |
| --- | --- | --- | --- |
| B-01 | 2 dispatched attempts per decision | One retry, finite cognition | Histogram; third-dispatch refusal |
| B-02 | 30,000 ms per attempt | Bound stalled synchronous world | Injected deadlines; p50/p95/max latency |
| B-03 | 60,000 ms total decision attempt time | Bound two waits | Clock-controlled frozen-boundary fixture |
| B-04 | 0 ms retry delay; 0 SDK retries; 1 concurrent call | One owner of retries/order | Instrument actual adapter invocation order/count |
| B-05 | 32,768 input tokens per attempt | Bounded context plus descriptions | Pinned counter; maximum and rejection frequency |
| B-06 | 2,048 output tokens per attempt | Bounded action/goal JSON | Length, invalid and truncation distribution |
| B-07 | 262,144 raw response bytes per attempt | Bounded malformed bodies with audit | Limit/limit+1 fixture; one sentinel byte is detection only |
| B-08 | 131,072 canonical request UTF-8 bytes per attempt | Bound schema/prompt plus projection | Worst registered input; observed maximum; boundary fixtures |
| B-09 | 1 rule execution per failed primary decision | No fallback loop | Malformed fallback causes one wait only |
| B-10 | 1 checkpoint per completed boundary | Explicit durable commit authority | Bytes/write latency per game day; crash matrix |

### Evaluation and independent live allocations

| ID | Approved value and unit | Rationale | Measurement / decision evidence |
| --- | --- | --- | --- |
| V-01 | Smoke: 1 seed, T=24 ticks, 1 LLM actor; caps attempts48,input1572864 tokens,output98304 tokens,money5000000 micro-CNY (CNY5) | Exercise one integration before broad spending; money admission may bind before the attempt cap | Actual calls/usage/latency and accepted share in M9 smoke. |
| V-02 | Development: 2 seeds, T=48 ticks, 3 LLM actors; per-case caps attempts288,input9437184 tokens,output589824 tokens,money20000000 micro-CNY (CNY20) | Small tuning set, separate from acceptance | Each case measures reservations, actual usage, fallback and mandatory size; total allocation CNY40. |
| V-03 | Acceptance: 3 fresh seeds, T=144 ticks, 3 LLM actors; per-case caps attempts864,input28311552 tokens,output1769472 tokens,money35000000 micro-CNY (CNY35) | One-day pilot with matched controls, not a seven-day survival claim | Three complete valid pairs, raw per-seed metrics and total allocation CNY105. |
| V-04 | Long fake proof: 1 smoke-seed run, T=1008 ticks, 3 P3 actors; fake caps attempts6048,input198180864 tokens,output12386304 tokens,money0; 0 real provider calls | Exercise seven-day artifact/cursor/overflow recovery without paid model variability | Explicit offline run, source/recorded hashes and sentinel count0. |
| V-05 | Every registered LLM actor in each smoke and acceptance case: llm_accepted_share>=4/5; wait_count0; evidence/privacy violations0; all 3 pairs technically valid | Prevent acceptance of a mostly-rule substitute while keeping behavior quality descriptive | Exact per-actor integer comparison 5*accepted>=4*L, L>0; invalid/missing case fails. |
| V-06 | 2,097,152 canonical UTF-8 bytes per inspection shard | Bound one UI parsing unit while retaining complete request/attempt data | Export sizes; exact limit/limit+1 fixture; report largest shard and actual UI import behavior. |
| V-07 | 8 retained experience records per boundary/actor inspection sample | Compact recent history; full selected recall stays in decision shard | Exact sequence selection and source comparison, count0/8/more-than8 fixtures. |

## 3. Deliberately unchanged or excluded

- No world/Perception/action/failure-code/ReplayBundle change. OQ-063 remains a
  separate historical spec/engine reach issue. Successful receiver attribution
  would require a separate Perception CR and is not required here.
- P1/P2 lanes keep their schema/bytes, rule tree and reference hashes. Matching
  P2 controls use frozen inputs; P3 rule-only actors still use P3 envelopes.
- No actual model call, credentials, code, dependency or generated type change
  belongs to P3-01. M8 approval is followed by implementation gates before any trial.
- No approved budget is transferred between trials, reused automatically for reruns
  or silently replenished after interruption. A missing/unknown amount is not zero.
  The same approved case may continue normally against its one remaining allocation
  without asking the owner again; a copied checkpoint supplies no spending authority.
  G2-R1-01/02 add ownership and identity precision, not new numerical limits or spend.

## 4. Evidence the owner receives at later gates

M9: one-LLM fake/smoke trace with linked inputs, goals, actual feedback, fallback,
unknown-usage behavior, living restore and no-call recorded re-execution.
Include BD-18..27 sequential/concurrent/crash ownership proofs, including ordinary
continuation without renewed approval and replay with zero authority access.
M10: three-resident semantic fixtures, registered live results including all failures,
matched P2 descriptive comparison, inspection UI, compatibility hashes, full CI and
one-page retrospective. Gate 2 is independent of each implementation's authors.
VF-20 must retain both real selector IDs and reproduce each source's EX-11/12
assembly/manifest with its own pinned algorithm; live use of the fixture ID refuses.

## 5. Owner record

| Field | Value |
| --- | --- |
| Independent P3-01 Gate 2 | PASS, outside-team review at 659e1212f16e3f84ab60b370d4141c85b1d15d36; see P3-01-review.md. M8 application review PASS by independent m8_application_review; see M8-application.md. |
| Owner / decision date | Project owner, 2026-11-12, explicit chat approval; subsequent DeepSeek/CNY150 instruction supersedes provider/USD selection. |
| M8-01 | Approved: versioned P3 lane and CR-005 amendments. |
| M8-02 | Approved: bounded experience and truthful retrieval identities. |
| M8-03 | Approved: exact profiles and one current commitment. |
| M8-04 | Approved: stateful frozen-rule fallback. |
| M8-05 | Approved: one case authority, exclusive continuation, conservative recovery. |
| M8-06 | Changed by owner: DeepSeek; initial implementation selects deepseek-flash, non-thinking, with alias/version evidence and pinned mapping. |
| M8-07 | Approved: ignored local .env; inject DEEPSEEK_API_KEY only into provider client. No secret required now. |
| M8-08 | Approved: E/C/B values unchanged; money units now micro-CNY. |
| M8-09 | Changed by owner: aggregate API spend ceiling CNY150; V-01 CNY5, V-02 CNY20 each, V-03 CNY35 each. Counts, horizons and pass lines unchanged. |
| M8-10 | Approved: character panel and debug view in P3-07. |
| M8-11 | Approved: P3-02, parallel 03/04, 05/M9, 06, 07/M10. |
| Superseded authorization | USD112 and OpenAI model selection revoked before any calls/spend. |
| Price identity | CNY; peak uncached input2000000/output8000000 micro-CNY per million; source/date above. |
| Registration/implementation identities | Not yet created; pin during P3-05/07. Six one-time approved slots only; no extra grant from a changed registration hash. |
| CR-005 application commit | `cc2bf87285e2728d7c433b92c265ce22bbd7e923` (reviewed application); P3-02 pins this SHA. |
| Authorized next task | P3-02, from the recorded M8 application baseline, independent application review passed. |

The CNY150 limit covers all P3 paid model calls, including failed/retried calls and
any paid compatibility probe. It is not a target to spend, a per-run refill, or an
approval of developer-agent subscriptions. No unused slot allocation transfers
without owner disposition. P3-02 is provider-independent and performs no live calls.
