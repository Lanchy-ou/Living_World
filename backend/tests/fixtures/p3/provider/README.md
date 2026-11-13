# P3-04 provider evidence and offline counter proof

Checked 2026-11-13. Response JSON fixtures are synthetic protocol vectors, not
captured paid responses. The P305-U2 request fixture is derived from its supplied
offline context reproduction. No credentials or model API calls were used.

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

`deepseek-flash1017-byte-upper-bound/0.3` is a pure conservative token counter for
the frozen two-message, text-only, nonthinking, no-tool Responses lane. Adapter
version is `0.4`. It decodes the already verified retained wire bytes and computes
the rank-prefix bound below; it does not read these files, load a tokenizer, consult a service,
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
formatting difference is involved. Object key order does not affect byte length,
but **does affect BPE merges** in counter 0.2. The counter uses the parsed schema
from the canonical retained wire, whose object keys are already sorted, including
nested keys. Both order-preserving parsing and sorted-map parsing in the provider
retain that order; conversion passes this original schema to the renderer.
Counting insertion-ordered `request.response_schema` instead would be incorrect.
The exact-release [Python reference](flash1017-encoding.py.txt) independently
renders the same complete string in the fixture tests, including empty messages,
escaped controls, multilingual text, literal framing spellings and long inputs.

The five inserted registered tokens and IDs in the exact tokenizer are BOS
`<｜begin▁of▁sentence｜>` / 0, SYSTEM `<｜System｜>` / 128799, USER `<｜User｜>` /
128803, ASSISTANT `<｜Assistant｜>` / 128804 and THINKING_END `</think>` / 128822.
They are registered single IDs; only BOS has the tokenizer JSON `special=true`
flag. Recipe's [prompt tokenizer](recipe-tokenizer.rs.txt) selects one ID for each
explicit structural span and disables added vocabulary on ordinary spans. Literal
marker text inside a message is counted by the ordinary-text bound, never as an
inserted structural token.

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

Thus, writing `utf8(x)` for the byte length of text `x`, counter 0.1's complete
input bound was:

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
can conservatively reject requests that a precise tokenizer would admit. P305-U2
exposed an avoidable such rejection, addressed by the stronger bound below. No
paid observations or network token-count endpoint validate either bound.

### Counter 0.2 foundation: certified BPE prefix for complete ASCII spans

Let `P(s)` be the token count after executing only the first 4,096 ranked BPE rules
on each exact pretokenized part of an ASCII span `s`. Define:

```text
F(s) = P(s) if every character in s is ASCII, otherwise utf8(s)
U_0.2 = 5 + F(system_content + schema_prefix + spaced_schema_json)
          + F(user_content)
actual input tokens <= U_0.2 <= U_0.1
```

The combined system/schema is **one** ordinary span. Splitting it artificially and
independently applying BPE is not a general upper-bound argument: a boundary can
change the sequence of merge priorities. The actual USER structural token provides
the independent boundary before user content. Non-ASCII spans use the entire-span
byte proof; they are not heuristically partitioned around Unicode characters.

For ASCII spans the exact tokenizer pretokenizer specializes as follows:

1. `\p{N}{1,3}` isolates `[0-9]{1,3}`, preserving each unmatched gap.
2. The CJK/Japanese splitter matches no ASCII character.
3. In the final regex, `\p{L}` is `A-Za-z`, `\p{M}` is empty, and `\p{P}` union
   `\p{S}` is the 32 printable ASCII punctuation/symbol characters. All other
   alternatives, greediness and ordering are unchanged. The regex runs separately
   inside each part from step 1; all matches and unmatched gaps remain separate.
4. `re.ASCII` gives `\s = [\t\n\v\f\r ]`, matching the ASCII restriction of
   [Oniguruma's documented Unicode whitespace](oniguruma-regex.txt). Python's
   default Unicode `\s` additionally includes U+001C through U+001F and is **not**
   used. The retained [tokenizers regex wrapper](tokenizers-onig.rs.txt) documents
   the match/unmatched partition behavior.

The complete artifact certificate establishes that all vocabulary IDs and merge
pairs are unique. Consequently their spelling-derived ranks are the actual
ID-pair ranks, with no later duplicate overwriting an earlier rule. Of ranks
`[0,4096)`, exactly 2,472 pairs contain only ASCII bytes and are reachable from
ASCII initial symbols. The other 1,624 cannot become reachable: merging only
concatenates bytes. The embedded certificate retains every reachable pair and its
original rank, including gaps. It is a mechanically compressed table, not trained
or inferred data; its decompressed SHA-256 is
`c312cab30044f3f4150b2cb28f03e1c0300903d7a2363cad2e7553d9c95aa4bf`.
Tests regenerate all entries from the full pinned tokenizer and require equality.
No fixture or external package is loaded by production counting.

Each production step chooses the currently available minimum `(rank, original
left position)`, exactly as the retained BPE `merge_all` implementation. The left
position survives a merge; removed symbols and stale heap entries are ignored.
Neighbors are reconsidered immediately, so this is not a single ascending-rank
sweep. Until no retained pair is available, full BPE makes the same choices: every
omitted rule has a higher rank or is unreachable. The computed symbols therefore
form an exact prefix of full BPE execution. Subsequent higher-rank merges may
expose earlier ranks, but every step in that unexecuted continuation reduces the
number of symbols. Stopping is thus conservative for every input, not just the
regression case. Choosing 4,096 controls precision and local cost, not a safety
margin that depends on empirical token ratios.

The linked-list/heap implementation performs at most `n-1` merges. Its initial
heap has at most `n-1` entries and every merge enqueues at most two candidates:
at most `3(n-1)` pops, O(n log n) time and O(n) storage. A B-08-sized repetitive
word regression checks this operation bound without a machine-dependent timing
threshold. The certificate's longest merged symbol is 32 bytes, so concatenation
and dictionary-key hashing also have a fixed bound. Small randomized ASCII strings and overlapping/repeated words are
compared against an independent minimum-pair-rescan oracle, including all model
ranks to establish `exact <= prefix <= bytes`. Every ASCII character pair is
checked for identical source-derived splits, alongside digit and control cases.

### P305-U2 initial request regression (superseded by the full tape)

[The request fixture](p305-u2-first-request.json) is rendered from the supplied
offline Ella context using the unchanged production template/action contract.
[Provenance and hashes](p305-u2-first-request-evidence.json) pin the source main
commit, context/projection, decision, seed and exact prepared body. This is an
adapter-input fixture, not a copied run log or a model response.

| First Ella request, seed 1292387875 | Counter 0.1 | Counter 0.2 |
| --- | ---: | ---: |
| Combined system/schema | 29,465 | 14,550 |
| Non-ASCII user message | 15,691 | 15,691 |
| Structural IDs | 5 | 5 |
| Complete bound | 45,161 | **30,246** |

B-05 remains 32,768. The exact same outbound request body is admitted and sent
once to a local fake transport in the regression. Only counter metadata changes
from 0.1 to 0.2; body SHA-256 stays
`17113cf3943ec59fe8a77ee89486acf5bafe459cd4ef2d876cd9aab606433433`.
The preliminary 30,209 calculation used insertion-ordered schema JSON and is
superseded by the exact-wire value above.

For this fixed trusted system/schema, a non-ASCII user span may contain at most
18,213 UTF-8 bytes under this bound (2,522 more than the first request). Larger
spans still refuse honestly; a precise full tokenizer might admit them. The first
supplied reproduction had three tick-zero contexts (Ella/Mia/Ryan), only one of
which was Ella. Its first-request fix did **not** establish later admission.
P3-05 subsequently supplied a closed 24-request tape; 22 requests exceeded this
0.2 threshold. U2 therefore remained open until the following refinement.

### Counter 0.3: use the tokenizer's existing basic-Han boundaries

The supported whole-span domain is ASCII union U+4E00 through U+9FA5, not a list of
characters seen in one profile. Any code point outside this domain triggers the
original byte bound for the **entire** ordinary span. This includes adjacent
ideograph ranges, combining marks, fullwidth digits, Kana, punctuation such as
U+3002, accented Latin letters and emoji. No unknown category is guessed.

The retained [Oniguruma number-property table](oniguruma-unicode-properties.c.txt)
defines `CR_N` with 144 ranges. Tests establish that none intersects the entire
basic-Han domain and that its ASCII intersection is exactly digits 0 through 9.
The exact tokenizer's second Split contains the whole basic-Han range. Thus,
within the supported domain, the first two pretokenizers are reproduced exactly:

1. Isolate ASCII digit groups of one through three, preserving all gaps.
2. Inside each part, isolate basic-Han runs, again preserving all gaps.
3. Each remaining ASCII part receives the exact ASCII specialization of the final
   Split and the certified rank-prefix BPE already proved above.
4. Each Han part receives its full UTF-8 byte bound. Any further subdivision by
   the last Split and subsequent BPE cannot increase that byte bound.

The implementation follows this original order. It never inserts an artificial
BPE boundary: the Han boundaries already exist in the real second pretokenizer.
There can therefore be no cross-part BPE merge that invalidates the sum of the
component upper bounds. On pure ASCII inputs the second Split is still a no-op.
Consequently, for every supported ordinary span `s`, the sum over these parts is
a proven token upper bound; outside that domain the previous byte proof applies.
The outer five structural IDs and combined system/schema span remain unchanged.

No tokenizer dependency, runtime artifact read, Unicode normalization, request
rewriting or profile-specific dispatch rule is added. The same 2,472 embedded
ASCII pairs and source/model pins are used. Counter version becomes 0.3 and
adapter version 0.4; earlier counter versions are explicitly refused so their
different admission behavior is not silently substituted.

Tests verify all 20,902 supported Han code points against the real second Split,
the full numeric-property range exclusion, both Han endpoints and adjacent
unsupported code points, long digit runs beside Han, and generated mixed text.
An independent oracle uses captured regex splits from the source artifact and
rescans current minimum BPE pairs. It shares no production heap/iterator code.
The previous complete-ASCII and unsupported-span tests remain in force.

### Complete 24-request smoke admission evidence

[The compressed request fixture](p305-u2-smoke-requests.json.gz) contains only the
24 original expected request/wire pairs and expected bounds, derived from the
P3-05-owned closed offline tape. It does not copy response scripts, run logs or
integration implementation. [Its provenance](p305-u2-smoke-evidence.json) pins
source commit `c40ae94d17aa35ed6942f0214ef0093941820790`, original tape SHA-256
`68acba21ebed8b1b9c10edd458c7cc1f3f056e37b32db160adfd0d383889722f`, and both
compressed and decompressed fixture hashes.

All 24 complete request bodies remain byte-for-byte equal to their retained wire
envelopes after replacing only the non-wire fake-counter metadata with production
counter 0.3. Each is independently counted and sent once to a local fake transport.
The bounds by ordinal 0 through 23 are:

```text
23082, 24129, 25113, 26093, 27073, 27561,
27537, 27505, 27376, 27344, 27217, 27187,
27059, 27028, 26899, 26770, 26772, 26773,
26774, 26775, 26777, 26782, 26785, 26788
```

Every bound is below unchanged B-05 (32,768); maximum is 27,561 at ordinal 5. The
first user span is now bounded by 8,527, plus 14,550 system/schema and five framing
IDs, totaling 23,082. The largest retained user text is 24,545 UTF-8 bytes. No
required experience, goal, prompt, schema or DTO content is removed. The original
first-request wire hash above remains unchanged.

This closes admission for the supplied realistic closed tape, not every possible
future model-generated string. Unsupported Unicode still takes the whole-span
byte bound and can conservatively exceed B-05; its refusal is tested at the exact
limit and one byte over. P3-05 must repin adapter 0.4/counter 0.3 and implementation
hash before any registered smoke. No actual smoke or provider call occurred here.

### Response model evidence

A completed envelope with an explicit `model` other than the requested
`deepseek-flash` is rejected as `provider_error/RESPONSE_MODEL_MISMATCH`; proposal
text is withheld while raw bytes and reported usage remain available for audit.
No guessed dated alias or additional accepted model spelling is introduced.
Incomplete/error responses retain their existing rejection classifications.

An expected alias echo, or an absent echo, cannot attest hosted model weights.
An absent echo does not add a model/version claim to the frozen ProviderResult.
The official Responses reference describes this field as a model identifier,
not an immutable snapshot certificate. The registration owner's official
alias/version/pricing check and retained evidence remain necessary. A server that
silently changes weights while echoing the same alias is outside what this pure
counter or the existing result DTO can establish; no new DTO field or authority
is added to pretend otherwise.

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
locks and retry scheduling remain P3-03 responsibilities. The only shared-port
change is the owner's `InvalidFallbackPlan` contract, imported as an explicitly
approved dependency so the fallback adapter and coordinator use the same type.
No other shared-interface change, package dependency, budget authority or P3-05
integration is introduced.
