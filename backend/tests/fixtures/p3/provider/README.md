# P3-04 provider evidence and offline counter proof

Checked 2026-11-12. JSON fixtures are synthetic protocol vectors, not captured paid
responses. No credentials or API calls were used.

## Frozen mapping

The [Responses reference](https://api-docs.deepseek.com/api/create-response/)
and [compatibility guide](https://api-docs.deepseek.com/guides/responses_api/)
specify ordered role/content input, `reasoning.effort=none`, `text.format` JSON
schema, and assistant message `output_text` content. `usage.input_tokens` and
`usage.output_tokens` are totals; cache/reasoning details are subsets and are not
subtracted. Missing, null, boolean, negative or noninteger usage remains unknown.
Incomplete envelopes never produce proposal text. Proposal validation and state
commitment belong to the runtime.

The [pricing page](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
identifies `deepseek-flash` as DeepSeek-V4.1-Flash-1017 with peak uncached CNY2/CNY8
per million input/output tokens, consistent with M8. This is documentation evidence,
not a registration pin or live availability check. The alias is not immutable.
Future live registration must retain and revalidate version/pricing evidence.

`prepare_request` checks the frozen schema/model, emits canonical UTF-8 JSON, and
omits unsupported store/background parameters. `verified_body` verifies the entire
retained envelope and returns its original decoded bytes. Complete sends those
bytes without a JSON encoder or SDK. Stdlib HTTP follows no redirects and performs
no implicit retries. Authentication is injected only into a header; neither headers
nor exception messages are returned. No credential loader or live entry point is
added. The retained raw response distinguishes absent, empty and invalid UTF-8.

## Production counter: explicit refusal

This revision has **no certified production input counter**. Production count and
complete raise `INPUT_COUNTER_UNAVAILABLE` before transport access regardless of
the supplied counter ID. The startup owner must invoke count before admission;
complete checks independently. No arbitrary counter callback/certification flag is
accepted. Pure preparation remains available for audit.

The [token guide](https://api-docs.deepseek.com/quick_start/token_usage/) gives
plain-text tokenization and approximate character ratios, not a complete billed
request bound. The [official inference Q&A](https://github.com/deepseek-ai/DeepInfer/blob/main/doc/inference_deployment_qa.md)
states general API/recipe alignment. The [V4.1 renderer](https://github.com/deepseek-ai/deepseek-recipe/blob/main/deepseek-recipe-encoding/src/v4/dsv41.rs)
and [JSON serializer](https://github.com/deepseek-ai/deepseek-recipe/blob/main/deepseek-recipe-core/src/json.rs)
suggest five special tokens plus system/user/schema text in this restricted lane.
But a byte-length bound requires proof of tokenizer nonexpansion and exact hosted
Flash-1017 to renderer/tokenizer revision correspondence.

The [bundled tokenizer provenance](https://github.com/deepseek-ai/deepseek-recipe/blob/main/static/tokenizers/v41/README.md)
instead names DeepSeek-V4-Flash-Vision-Exp revision
`6821d6ad3681a4b137b066b76094fa82ebd0a380` and tokenizer SHA-256
`81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99`.
These are not a certified hosted Flash-1017 pin. The complete tokenizer normalizer
and pretokenizer were not verified. No five-token/byte heuristic or empirical
margin is shipped. A future reviewed adapter revision must supply missing proof,
immutable artifacts, implementation hash and fixtures before live use.

## Offline counter: exact finite proof

`fixture-wire-bytes/0.1` belongs only to `FakeProviderAdapter`. Its synthetic input
unit is one byte of the complete prepared request. For every finite byte string b,
there is exactly one unit at each index in [0,len(b)); the exact count and upper
bound are therefore len(b). The wire includes messages, escaping, role names,
settings and the complete schema. UTF-8 bytes are counted individually. This proof
asserts nothing about DeepSeek's tokenizer or billed units.

Tests cover multilingual/escaped strings, B-05/B-08 boundaries, retained-wire
mismatch, production refusal with the fixture identity, and equality of counted,
retained, hashed and sent bytes. Fake time is logical and deterministic.

## Transport and authority boundaries

Transport reads at most B-07+1 raw bytes and retains B-07; the extra byte is a
sentinel. Total deadline expiry closes the socket and rejects late completion.
An unresolved DNS worker is daemonized and prevents another exchange on that
transport until it exits. Timeout/uncertain dispatch has unknown usage, never a
local resend. Tests use local fake connections, not external sockets.

The frozen port carries no call ID, allocation, replay mode or ledger handle.
Duplicate-call exclusion, denied allocation, recorded-mode provider omission,
locks and retry scheduling remain P3-03 responsibilities. No shared interface
change, dependency change, budget authority or P3-05 integration is introduced.
