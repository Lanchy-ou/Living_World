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

## Production counter and scope

`deepseek-flash1017-byte-upper-bound/0.1` is a pure conservative token counter for
the frozen two-message, text-only, nonthinking, no-tool Responses lane. Adapter
version is `0.2`. It decodes the already verified retained wire bytes and computes
the bound below; it does not read these files, load a tokenizer, consult a service,
or count the transport JSON as if it were model text. Unknown counter identities
and versions still raise `INPUT_COUNTER_UNAVAILABLE` before transport access.
No arbitrary counter callback or certification flag is accepted. Complete also
enforces the bound against B-05, even if a caller bypasses admission.

The former unconditional refusal was safe but did **not** satisfy the mandatory
production proof deliverable. Acceptance finding P304-A1 supersedes that earlier
completion claim. This proof replaces it using the exact Flash-1017 release,
not the recipe's older Vision-Exp tokenizer or the synthetic fake's byte units.

### Reproducible evidence chain

[counter-sources.json](counter-sources.json) records immutable URLs, byte lengths
and SHA-256 hashes for every retained public artifact. Tests verify all of them
offline. Original licenses accompany the files; no source is modified or installed
as a dependency. The relevant pins are:

| Evidence | Immutable revision / identity |
| --- | --- |
| DeepSeek-V4.1-Flash-1017 model card, encoding reference, tokenizer | `08c8657f02291e11b6f6b63e0e16014f8e748518` |
| Exact tokenizer SHA-256 | `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b` |
| DeepSeek recipe, including Responses converter and V4.1 renderer | `935817c66f5d6e64838f419692545f06787e485f` (0.2.0) |
| DeepInfer API-alignment statement | `a679bb86ce36e883a98a97733492b686e5b9a08e` |
| Hugging Face tokenizers ByteLevel, Split and BPE semantics | `f383101a26663708484cac0727792aad74f78234` (v0.22.2) |

The retained [exact release card](flash1017-model-card.md.txt), "Prompt Encoding",
identifies its standalone Python reference and says recipe provides the same
prompt format for Responses as well as other protocols. The retained
[DeepInfer Q&A](deepinfer-api-alignment.md.txt) documents alignment of recipe's
processing with the official API and the separation of structural tokens from
ordinary text. Combined with the current official alias evidence above, these
establish the model/template correspondence used here. This is a documented model
contract, not a claim that the mutable hosted alias can never change. Registration
must revalidate alias/version evidence and pin this counter's implementation hash
before any future live run. A changed model/template requires a new reviewed proof;
the pure adapter cannot check hosted identity and does not perform network preflight.

Recipe 0.2.0 is essential: its [changelog](recipe-changelog.md.txt) says 0.1 accepted
but ignored JSON Schema. This proof includes the schema prompt added by 0.2.0.

### Complete charged prompt

The [Responses converter](recipe-responses-convert.rs.txt) `into_content` keeps a
string as plain text; `convert` preserves the ordered system/user messages, with no
extra `instructions` field in our wire. `convert_text_format` places only
`text.format.schema` in `ResponseFormat::JsonSchema`. Its separately normalized
constraint schema is used for output decoding, not appended to the prompt. The
format name/type, model alias, maximum output, stream flag and tool-choice fields
control processing and are not additional prompt text. Empty tools add no prompt.
[Reasoning resolution](recipe-reasoning.rs.txt) makes explicit `none` nonthinking,
overriding any default, with no reasoning-effort preamble.

The [V4.1 renderer](recipe-dsv41.rs.txt), `render_conversation` and `render_message`,
therefore renders exactly:

```text
BOS + SYSTEM + system_content + schema_prefix + spaced_schema_json
    + USER + user_content + ASSISTANT + THINKING_END
```

There is no EOS or history. The exact schema prefix is the following Python string:

```python
"\n\n## Response Format:\n\nYou MUST strictly adhere to the following schema to reply:\n"
```

[JSON formatting](recipe-json.rs.txt) uses unescaped Unicode and `, ` / `: `
separators, matching `json.dumps(schema, ensure_ascii=False)` for the frozen schema.
The schema has only ASCII strings and integer numeric values; no float/escape
formatting difference is involved. Object key order does not affect byte length.
The exact-release [Python reference](flash1017-encoding.py.txt) independently
renders the same complete string in the fixture tests, including empty messages,
escaped controls, multilingual text, literal framing spellings and long inputs.

The five inserted registered tokens and IDs in the exact tokenizer are BOS
`<｜begin▁of▁sentence｜>` / 0, SYSTEM `<｜System｜>` / 128799, USER `<｜User｜>` /
128803, ASSISTANT `<｜Assistant｜>` / 128804 and THINKING_END `</think>` / 128822.
They are registered single IDs; only BOS has the tokenizer JSON `special=true`
flag. Recipe's [prompt tokenizer](recipe-tokenizer.rs.txt) selects one ID for each
explicit structural span and disables added vocabulary on ordinary spans. Literal marker text
inside a message remains ordinary text and receives the full byte allowance.

### Tokenizer nonexpansion proof

For every valid UTF-8 ordinary-text segment `s`, token count is at most `len(s)` in
bytes. This follows from the complete retained tokenizer, not sample ratios:

1. The normalizer is an empty sequence (identity). Each of the three `Split`
   pretokenizers partitions the string with `Isolated` delimiters and inserts no
   characters. See [Split semantics](tokenizers-split.rs.txt).
2. The final ByteLevel pretokenizer has `add_prefix_space=false` and
   `use_regex=false`. Its [implementation](tokenizers-byte-level.rs.txt) maps each
   UTF-8 byte to exactly one alphabet scalar without prepending anything. Tests
   exhaustively verify all 256 scalars occur in this tokenizer's base vocabulary.
3. BPE has no dropout, unknown token, subword prefix, end suffix or byte fallback.
   [Initial symbol construction](tokenizers-bpe-model.rs.txt) therefore starts
   with at most one ID for each byte. Each [BPE merge](tokenizers-bpe-word.rs.txt)
   replaces two adjacent symbols with one. It never increases their number.
   Tests verify all 127,741 merge operands are nonempty and their concatenations
   exist in the 128,000-entry vocabulary.
4. The ByteLevel postprocessor adds zero token IDs and only adjusts offsets and
   sequence IDs. Its `add_prefix_space=true` does **not** insert an input space;
   that setting belongs to a different operation from pretokenization. Padding
   and truncation are disabled. Ordinary recipe spans do not match structural
   tokens; even generic added-token matching could only replace a nonempty span
   with one ID. All 1,283 registered strings are verified nonempty.

Thus, writing `utf8(x)` for the byte length of text `x`, the complete input bound is:

```text
U = 5 + utf8(system_content) + utf8(schema_prefix + spaced_schema_json)
      + utf8(user_content)
actual input tokens <= U
```

The five is an exact count of structural IDs, not an empirical margin. Segmentation
or extra BPE merges cannot invalidate the inequality. All Unicode scalars and
escapes are covered by UTF-8 byte expansion; invalid surrogates are rejected by
the existing DTO/canonical serializer. HTTP headers and JSON escape bytes are not
model input and are not mistakenly added to the model text. Schema appears both
inside a resident prompt if supplied there and in provider framing; both copies
are included. No content is truncated to fit this bound.

Tests check the artifact premises exhaustively, compare full framing against the
independent retained reference, exercise generated Unicode and injection-like
strings, require exact retained/count/record/send byte identity, forbid counter
file/network IO, and verify B-05 at 32,768 and 32,769 plus B-08 overflow. The bound
can conservatively reject requests that a precise tokenizer would admit; that is
intentional. No paid observations or network token-count endpoint validate it.

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
