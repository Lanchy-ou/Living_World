# M14 provider check

## Phase 1 preflight, 2026-11-24

The input is EV-05's retained Ella run at
`F:/p35-w1/ev05/runs/ev05-7e8_yjab/ella`. It contains one unmodified prepared
request per kind. The evidence uses the production DL-01 framing, contract,
counter, provider attempt and typed parser. Replay rebuilds the prepared
candidates, verifies the archived bytes, and exercises all six on fake
transport. Each retry sends the same admitted bytes and has its own dispatch
ordinal and journal record. [EV-05 evidence](M14-fake-workload.md)
[Owner disposition OQ-P3.5-M14-2](../../spec/open-questions.md#oq-p35-m14-2-evidence-sufficient-for-the-paid-provider-check-and-horizon)

| Immutable input | SHA-256 |
| --- | --- |
| `provider-check.sqlite` | `b5e626c9bad17a41683676ee37774a742161eef25eeb17854266a3f37fb6d85d` |
| Ella `receipt.json` | `89ed3f2f9597b735faa0d793bc013924bf00f8210ef469ca5320b5773e4bacbc` |
| Vocabulary TOML bytes | `5de460d9e649a1000080ad902b475026d8e1e88b571f2497557d565af3351a94` |
| Loaded vocabulary | `57554435492d6f3db83006a4510b292f8b0d1ebc70c3393663fd1a9ad94cf286` |

| Call kind | Wire bytes | Counted input bound | Wire SHA-256 |
| --- | ---: | ---: | --- |
| `decision` | 20,255 | 11,243 | `f06e24b143529d6a3a5a86458b5c2f60b7de6d8db2eb02c421b20331adae6674` |
| `decision_after_recall` | 20,083 | 11,181 | `012f7a1bce627ad2a60e62bbe857683e3a5cd0bc2c1452ab8387b98207ede974` |
| `recall` | 697 | 225 | `404f16d6bd06909b7178306aef1bce05ca03860eceb431694ea82b8c41db3a4f` |
| `morning` | 2,766 | 1,451 | `2f3ed5964fc9ae9a4e4e8d0e4ecb27f406440be3a5acf253ec6d29a48f4e59aa` |
| `consolidation_selection` | 10,049 | 8,840 | `f06317497ec4d6c19195dae57e4860cd845804ca607f8b77f784ecc64c96366a` |
| `consolidation_change_set` | 17,256 | 13,256 | `86bb2900f0e8192df6442bf416426699980dea8a2d2bc865c4395583edd75166` |

| Call kind | Prompt SHA-256 | Schema SHA-256 |
| --- | --- | --- |
| `decision` | `d5d56eeb6ecf335ba6a1158980177be5a2afdbca90d3ff502921725fa0e95e59` | `b0f886c6a8b97e5acb7ee34b641515698227445e2c75bbb7b68d73ff50402e79` |
| `decision_after_recall` | `e609af32a199d3706fbfe60969f4e51c044e83a49436cec2d418becd1457231e` | `7e54a844dbee89857b3527033cac2070575c11200b27481dc1c63d2b06728aaa` |
| `recall` | `a45fa240d106af635deb7ece270dc05806b70bcecd16ac6b0b4be440e355b8a7` | `0da6fe83896e9d6c7d128e9a77786d24e453208e320dabdb96c570e92581da48` |
| `morning` | `cf00e17e0c65c6221bbbb1847971743895595555255923a64008dd18c58add8a` | `222b2b22909bbf88ed6250cf659da3d9483375aadefe3eadde3c92577604134f` |
| `consolidation_selection` | `36296f858d97264577729c9ed437696266fd5695a1166115da0ed00fa3a6c08f` | `cef46249be695a469203dd188c50e7d27af77df4d1d1155a4c94d24f2b65f9c2` |
| `consolidation_change_set` | `b054e4d7055668a6616daef5978cd9093016c379c459153efe9c6f13ee957643` | `6e6313e5789b02f408b2ec363aac9670438aec2efd937a8d4de130ffa8b1fe61` |

The wire contains a single object schema at `text.format.schema`, no tools,
two text messages, no history field, and `reasoning.effort=none`. The DL-01
schema generator runs its DeepSeek regex preflight, including the scalar-value
restriction from M9's hosted surrogate-pattern rejection. The fake response
adds a separate reasoning item and checks the archived reasoning hash and the
unchanged parsed hash. The next outbound wire still matches EV-05. A synthetic
key echo, including one cut off in a partial response, is removed before the
adapter can retain its body. The transport only puts the key in the authorization
header. [DL-01 adapter handoff](P3.5-DL-01.md#handoff)
[Retained provider sources](../../../backend/tests/fixtures/p3/provider/counter-sources.json)

The offline run printed preflight SHA-256
`ebc49944a5c7d188e95ed730d7bcb782d6f772455a95f2237dbfa0e038ad488d`.
Generate it again for the reviewed release.

## Predeclared live scoring

Each of the six logical requests must be accepted and yield a typed output.
The two decision requests must both parse on their first dispatch to match
the final CR-008 P3 smoke's 22/22 first-pass parses with zero local rejections.
The report includes first-pass decisions out of two, parsed decision dispatches
out of all decision dispatches, and the same parsed/dispatch count across all
six kinds. The four non-decision kinds have their own rows. A retry, HTTP
rejection, invalid output, or interrupted dispatch remains in the attempt
denominator and ledger. Missing calls or unsettled provider-check costs hold
the provider gate. If the single-copy form fails, record the incompatibility
for an owner change request. [M9 CR-008 comparator](../p3/M9-evidence.md#cr-008-authorized-counter-04-smoke-result-2026-11-14)

Two decision inputs and one input of each other kind provide little precision.
For illustration, a 95% Wilson interval for a hypothetical 2/2 is about
34% to 100%, versus 85% to 100% for 22/22. The inputs are fixed workload cases.
The check gives a point comparison and compatibility evidence for these
requests. A resident run also needs the separate day-sizing review.

## Cost projection

The opening reconciliation is CNY 0 and the EV-05 runs charged CNY 0, with
CNY 0 outstanding in the available opening evidence. Projection uses EV-04's
ledger sizing and the 2026-11-14 M9 historical peaks of CNY 2 uncached input
and CNY 8 output per million tokens. The input bound counts the provider's
schema expansion and every attempt reserves the full 8,000 output tokens.
Deadline and server errors allow three retries each, rate limiting five,
and invalid output one. Their mix permits up to 13 attempts per
non-consolidation kind. The two consolidation kinds allow up to four attempts
each, including at most one parse retry. [Opening ledger](P3.5-spend-ledger.md)
[Decision loop 8.2](../../spec/decision-loop-v0.1.md#82-errors-and-retries)
[Memory formation 5](../../spec/memory-formation-v0.1.md#5-failure-and-the-pending-area)

| Call kind | First attempt hold, CNY | Max attempts | Max hold, CNY |
| --- | ---: | ---: | ---: |
| `decision` | 0.086486 | 13 | 1.124318 |
| `decision_after_recall` | 0.086362 | 13 | 1.122706 |
| `recall` | 0.064450 | 13 | 0.837850 |
| `morning` | 0.066902 | 13 | 0.869726 |
| `consolidation_selection` | 0.081680 | 4 | 0.326720 |
| `consolidation_change_set` | 0.090512 | 4 | 0.362048 |
| **Total** | **0.476392** | **60** | **4.643368** |

The maximum reserves 401,684 input and 480,000 output tokens, leaving
CNY 15.356632 of the CNY 20 phase ceiling at the recorded opening balance.
Any concurrent paid attempts and reservations must be in the release ledger.
Actual costs and day sizing await the separately authorized observation.

## Evidence and release for live dispatch

This section records the original `/0.1` release and commands on `0c70926`.
Use the [recheck procedure](#prepare-the-prompt-recheck) for the new prompts.

For the proposed UTC dispatch date, record official DeepSeek evidence resolving
`deepseek-flash` to `DeepSeek-V4.1-Flash-1017` and confirming the 1,000,000-token
window, 8,000-token output reserve, and Responses support for stateless
single-copy JSON Schema with reasoning disabled and tools off. Record the
documented schema restrictions applicable to all six pinned shapes. Tie this
to `deepseek-responses-v2/0.1` and the
`deepseek-flash1017-byte-upper-bound/0.4` counter, whose tokenizer hash is
`c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b` and
counter source hash is
`fdaf256a6f4558bf8722af2e744e10a816f312248768d3278b988820a36146bc`.
A changed mapping, unsupported wire form or window change goes to the owner
before dispatch. [DeepSeek model and CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
[Responses API](https://api-docs.deepseek.com/api/create-response/)
[Responses compatibility](https://api-docs.deepseek.com/guides/responses_api/)

Use the [EV-04 evidence bundle](P3.5-spend-ledger.md#assemble-the-evidence-bundle)
to reconcile all existing liabilities and pin the verified CNY cached input,
uncached input and output rates, plus maximum uncached input and output
rates across the released date. Record applicable peak periods, token tiers
and effective dates. The dated sources for model mapping and tariff go in
`model_evidence` and `source` on the tested tariff row. A missing tariff,
an unbounded liability, insufficient phase headroom, or a projection above
the owner's release amount blocks dispatch.

Put the owner-approved, nonsecret inputs at the absolute paths in the live
command. The release JSON has these fields.

| Field | Value |
| --- | --- |
| `dispatch_on` | Reviewed UTC date in `YYYY-MM-DD` form |
| `approval` | Owner's explicit release reference for this single check and allowance |
| `wire_evidence` | Dated Responses, schema/window and counter evidence reference |
| `preflight_sha256` | Hash printed by the fresh offline preflight |
| `ledger_sha256` | SHA-256 of the exact reconciled ledger JSON file bytes |
| `max_cny` | Owner-approved maximum as a decimal CNY string |

Run from the DL-06 worktree. The offline invocation is the default.

```powershell
uv run --offline --no-env-file --locked --directory backend python -m living_island.sim.v2.harness.provider_check --help
uv run --offline --no-env-file --locked --directory backend python -m living_island.sim.v2.harness.provider_check --sample-dir F:/p35-w1/ev05/runs/ev05-7e8_yjab/ella
```

The separately authorized invocation is below. It consumes
`DEEPSEEK_API_KEY` from the live process environment after pin and budget
validation. The `uv --offline` flag applies to package setup. The module's
explicit `--live` selects HTTPS.

```powershell
uv run --offline --no-env-file --locked --directory backend python -m living_island.sim.v2.harness.provider_check --sample-dir F:/p35-w1/ev05/runs/ev05-7e8_yjab/ella --live --release F:/p35-w1/dl06/runs/dl06-live-release.json --ledger F:/p35-w1/dl06/runs/dl06-live-ledger.json
```

A live invocation exclusively claims `runs/dl06-provider-live/` before the
first dispatch. Its audit preserves exact input, response, reasoning and
typed-output hashes. It exports a per-kind result and an EV-04 evidence bundle
and report with each dispatch and logical call priced separately. Reconcile
that evidence in the scheduled ledger writer slot and size the EV-06 day
prefix using the measured per-kind results, the EV-05 daily counts and the
later contexts. [M14 spend and sizing rules](M14-plan.md#5-paid-steps-and-phase-spend)

## Owner release on 2026-11-24

The owner told Claude Code “Authorize, max 5 CNY” on 2026-11-24. This releases
one bounded DL-06 check through the end of 2026-11-24 UTC, with
`max_cny` set to `"5.00"`. The owner operates the live terminal and injects
`DEEPSEEK_API_KEY` in its process environment.

Claude Code verified the official pages on 2026-11-24. The pricing page
resolves `deepseek-flash` to `DeepSeek-V4.1-Flash-1017` with a 1M-token
context, a 384K-token maximum output and Responses API support. DL-06
keeps its 8,000-token output reserve and pinned Flash-1017 counter.
The Responses guide confirms support for `text.format` and reasoning effort,
stateless requests without `previous_response_id` or `store`, function
tools only, and `tool_choice: none`. Unsupported parameters are silently
ignored. The offline preflight checked the six exact wires against the
pinned local form. [Official pricing and model mapping](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
[Official Responses compatibility guide](https://api-docs.deepseek.com/guides/responses_api/)

| Usage category | Off-peak CNY per million tokens | Peak CNY per million tokens |
| --- | ---: | ---: |
| Cache-hit input | 0.02 | 0.04 |
| Cache-miss input | 1.00 | 2.00 |
| Output | 4.00 | 8.00 |

Peak hours in Beijing are 09:00–12:00 and 14:00–18:00, Monday to Friday
excluding Chinese public holidays. All other hours are half price. The release
was prepared at 13:11 UTC (21:11 in Beijing) and expires at 08:00 Beijing time
the next morning. The entire remaining window is off-peak, so the dated tariff
row uses the off-peak usage rates and retains CNY 2 and CNY 8 for peak
uncached-input and output reservations. Both tariff date fields are
`2026-11-24`. [Official CNY tariffs](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

The EV-04 bundle reconciles CNY 0 opening spend, CNY 0 for EV-05’s fake runs,
and no outstanding liabilities. The fresh offline preflight rebuilt the
six wires and parsed all six fake responses. EV-04 and the live admission
function priced the same 60 permitted attempts at **CNY 4.643368**, within
the CNY 5.00 release and leaving CNY 15.356632 of phase headroom after the
projection. This is a reservation. [Opening reconciliation](P3.5-spend-ledger.md#opening-ledger)
[EV-05 outcome](M14-fake-workload.md)

| Local evidence | SHA-256 |
| --- | --- |
| Rebuilt preflight | `ebc49944a5c7d188e95ed730d7bcb782d6f772455a95f2237dbfa0e038ad488d` |
| `runs/dl06-live-ledger.json` | `ab95b90e79bdd7c5c1febdd5c27572ac48511d98c3903cea9b3a597cf1c074e6` |
| `runs/dl06-live-release.json` | `224f954959bdfccbd821f44e212dec25ef6cba58d30ae79bee88608ab9ef99e0` |

The release was validated against both pinned hashes without dispatching.
The [live invocation](#evidence-and-release-for-live-dispatch) references
the two local JSON files.

## First live result on 2026-11-24

The owner ran the original sample once. The eight requests dispatched between
14:28:01 and 14:28:11 UTC under the off-peak tariff. DeepSeek returned HTTP 200
for 8/8 attempts. Local parsing succeeded on 6/8 attempts and eventually on
all six logical calls. The decision subset parsed 2/3 dispatches and 1/2
first dispatches, below the final M9 smoke's 22/22 first-pass result. The D7
provider gate failed. EV-06 remains on hold.

| Kind | Parsed dispatches | First dispatch | Settled CNY |
| --- | ---: | --- | ---: |
| `decision` | 1/1 | Parsed | 0.00737000 |
| `decision_after_recall` | 1/2 | Invalid output | 0.00817490 |
| `recall` | 1/1 | Parsed | 0.00018000 |
| `morning` | 1/1 | Parsed | 0.00104000 |
| `consolidation_selection` | 1/1 | Parsed | 0.00294200 |
| `consolidation_change_set` | 1/2 | Invalid output | 0.00650096 |
| **Total** | **6/8** | **4/6 parsed** | **0.02620786** |

Both invalid outputs had a sentence of prose before a JSON object. At
offline inspection, the unchanged `/0.1` parser accepted each object alone.
The provider echoed `text.format` as `json_schema` with `strict: null` in
both responses. The Responses guide documents `text.format` support and
defines no `strict` flag. The observed behavior left the whole-output
requirement to the prompt and local parser. The original prompts had no
explicit JSON-only instruction. [Responses compatibility guide](https://api-docs.deepseek.com/guides/responses_api/)

`decision_after_recall`, attempt 0, assistant output excerpt

```text
I'll head toward the spring to the northeast to explore a sustainable water source, and greet my neighbors on the way.

{"action": {"kind": "intent", "intent": {"action": "move_to",
```

`consolidation_change_set`, attempt 0, assistant output excerpt

```text
I'll take a look around — I've only explored a small patch so far and curiosity is pulling me to see what's near the rock and woods edges.

{"ops":[{"op_id":"op1","op":"add","ref":"m:ella:5",
```

| Retained evidence | SHA-256 |
| --- | --- |
| Original paid audit `runs/dl06-provider-live/provider-check.sqlite` | `11e24dd942339fa7973d4ad9cfb4b0d754281a565bb2aa54e8458d5ae0eda931` |
| `decision_after_recall` attempt 0 raw response blob | `df826fb681179323796a1c415c8f0ed7996133c6bb6297f61223d6eb1ae7aa26` |
| `consolidation_change_set` attempt 0 raw response blob | `15c9eca50a5307e30f35c06a4f9c846f9b9a7870cde9608652d9129233d5879a` |
| Reconciled `runs/dl06-recheck-ledger.json` | `e8a92cc2514389c9a0eba43dd28e27a07378bc7f0e01508a47bc832171ff0ea2` |

The recheck ledger carries the eight original dispatches and their usage as
one settled paid run, with CNY 0 outstanding and CNY 19.97379214 of phase
headroom. The original release files and archived run retain their hashes.
The owner authorized one prompt recheck within the original CNY 5.00
authorization. The remaining recheck ceiling is **CNY 4.97379214**.

## Prepare the prompt recheck

Claude Code allocated `backend/src/living_island/agents/v2/calls/contracts.py`
to DL-06 for this change. Each of the six instructions appends “Reply with
only the JSON object that matches the response schema, with no other text
before or after it.” Each prompt advances to `<kind>/0.2`. The schema hashes
match the first check and the typed parser still rejects prefixed or suffixed
prose. The preflight takes the new sample and receipt SHA-256 pins explicitly
and the recheck has its own one-time `dl06-provider-recheck` run identity.
The recheck release must bind the fresh preflight and reconciled ledger and
fit the remaining CNY 4.97379214 ceiling.

| Prompt version | SHA-256 |
| --- | --- |
| `decision/0.2` | `aab0565735df4cf6de933b511ba83bb5c9f1ecb284a4fa87f364965f3e130fdf` |
| `decision_after_recall/0.2` | `0642904e2d212dd3da3ceb4abf5382d178d500387df23dbee75b85106bb7c66f` |
| `recall/0.2` | `28748f1a08fd5ad4aacaa4b7ecf0acf471f7bb85231c1f9459c95ab4cdea1781` |
| `morning/0.2` | `b12156ddc0387c4354bd1717e04a7f1fe7fa7fee1c2b8d98df8d92f760d79e05` |
| `consolidation_selection/0.2` | `01fae1a9993290a507d25b5dfc6085173255a0d9bb44154ee36eb5e45bfd902a` |
| `consolidation_change_set/0.2` | `12dc324c74c7eea449f70393fe5a8d5349878bb891e99c9d7ad5ea7e6a13c123` |

After the host lock is free, run the Ella-only EV-05 rehearsal from
`F:\p35-w1\dl06` in PowerShell. It claims the lock exclusively, creates a
fresh `runs/ev05-…/ella` directory, and prints the session path.

```powershell
uv run --offline --no-env-file --locked --directory backend/tests --project .. python -m v2.fake_workload.evidence --case ella --lock C:\Temp\li-heavy.lock | Tee-Object -Variable dl06EllaRun
```

After `ella passed`, run the new offline preflight in the same terminal.

```powershell
$dl06EllaSample = Join-Path ($dl06EllaRun | Select-Object -First 1) 'ella'
uv run --offline --no-env-file --locked --directory backend python -m living_island.sim.v2.harness.provider_check --sample-dir $dl06EllaSample --sample-sha256 ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $dl06EllaSample 'provider-check.sqlite')).Hash.ToLowerInvariant()) --receipt-sha256 ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $dl06EllaSample 'receipt.json')).Hash.ToLowerInvariant())
```
