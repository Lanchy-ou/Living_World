# M12 equivalence report

The matrix compares the v2 engine running `compat-v1` and the frozen
rule-based policy with PR-03's committed `projection/0.1` fixtures under
[WAP §11.3](../../spec/world-agent-protocol-v0.1.md#113-equivalence-projection).
The full acceptance decision belongs to Gate 3.

## Owner-approved run scope

The owner narrowed M12 twice on 2026-11-23, following
[P2-04's OQ-060 disposition](../p2/P2-04.md#oq-060-disposition-for-this-round)
and [CR-011's reference to the P2 matrices](../../spec/open-questions.md#cr-011-compatibility-profiles-legacy-triggers-and-apparent-action-views-approved-2026-11-18).
The first decision selected 20 acceptance cases and six development seeds
across all seven arms. The second decision retained the 20 acceptance cases
and four already-completed S1 orig base cases. The other six development
arms each use the first two registered development seeds, `2195683955`
and `937154673`. Matrix A therefore covers 36 cases, with every
development arm represented on at least two seeds.

Matrix B independently repeats `2600456787`, `3335059634`,
`2733016023`, and `958049702`, the first four acceptance seeds in
registration order. The results must match the corresponding Matrix A receipts.
The owner assigned engine copy-cost work to P3.5-EN-08 in M13.

## Registered inputs

The v1 oracle source is `214228e7cdc0277a287f82ceae091158ac48daa6`.
The committed projection archive is Git tree
`292a2b74726990feb2f635f372754e221dbbd945` on the task base and implementation.
The matrix uses selected registered seeds, the original scenario arms, and the 1,008-tick
horizon from [P2 §§1–2](../../spec/p2-experiments-v0.1.md#1-scenario-matrix).
There are 1,009 boundaries per completed case, including initialization.

| Suite | Configuration | Policy | Cases | Raw TOML SHA-256 |
| --- | --- | --- | ---: | --- |
| Acceptance | S2 m6 (`production`) | base | 20 | `15c576c98be29ac1054e1154376508b6479e4fb57ebf1f07d241905f433dc128` |
| Development | S1 orig | base | 4 | `843331a01ff8ff7e3bff9a40bf4dcf294df6c6a14aa5ee30d059393d6893c263` |
| Development | S2 orig | base, canteen-restricted, cue-ignored | 6 | `c5599943abbb18830e9fad19222fbf4e2b3658fd1ee22e7afc89da54470de7fd` |
| Development | S3 orig | base | 2 | `111bb746979df3c96dbc3ec9b421d8b608db734f049cd0d5570c9844a123fc29` |
| Development | S4 orig | base, canteen-restricted | 4 | `a858afdee231e1d88272ed21e47a6fd02b8251ce4e74aefee902e632fe64091d` |

All matrix runs use map SHA-256
`007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c`.

Acceptance seeds in registration order:

```text
2600456787 3335059634 2733016023  958049702 3486741106
1557484054 4155892942 3501343423  330361958 3178109895
 969717619  857949281 2170312666 1007489817 2560155364
1802799976 1569596598  646834264 2122883013  598561891
```

The retained S1 orig base seeds are `1452436788`, `1883209505`,
`2195683955`, and `3459030352`. Each of the six other arms uses `2195683955`
and `937154673`.

## Reproduction

From the repository root, run
`uv sync --directory backend --locked`. For Matrix A, give the
`uv run --directory backend python -m living_island.sim.v2.cli equivalence`
command one `--case` for each Matrix A case below. For Matrix B, use the
four repeat seeds in the owner-approved scope above. Use distinct `--evidence` and `--output` paths for
each run and a maximum of four workers. The existing `--case` option
accepts repeated values and validates them against the registered cases.

The Windows run held `C:/Temp/li-heavy.lock` across both matrices. The
launcher ran up to four individual case invocations at once and retained
their durations beside the immutable receipts. It used the CLI again to
assemble each ordered report from those receipts. A restart passes the
same selected cases and evidence paths. The scope pin binds the evidence
to the executable source, dependency lock, archive, content and horizon.
The CLI skips completed cases and starts unfinished cases at their initial
boundary. The canonical four-case subset of Matrix A can be compared byte for
byte with Matrix B.

The command loads the pinned TOML and map through the compatibility
loader. `PolicySession` uses actual perceptions, the v1 rule planner
and the compatibility bridge. The extractor observes committed legacy intent
bindings and actual action results. It projects state, preserves utterance
order and each resident's outcome order, and links outcomes to the
resident's next actual plan decision. Reply references are compared by the
request's boundary, speaker and addressee because event identities differ
between the two catalogs. Scripted shuffle checks compare the original
completion order and RNG witness where that order affects resolution.

The matrix report records the per-case seed, config and map digests, v1
fixture gzip SHA-256, v2 rule-library SHA-256, and the v2 projection and
packet-receipt SHA-256 values for completed cases. A mismatch records its
case, boundary, field, expected value and actual value. The checksum of the
canonical packet digests covers the inputs acknowledged during each run.
Wall-clock time is written to stderr, outside the deterministic JSON report.
The CLI returns exit 1 on a trajectory difference or a WAP-26 exception.

## Matrix results

| Run | Acceptance matched | Development matched | Mismatched | CLI exit | Runtime (seconds) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 20 / 20 | 16 / 16 | 0 | 0 | 1249.743 |
| B | 4 / 4 | — | 0 | 0 | 1011.999 |

Matrix B is byte-identical to the canonical four-case acceptance subset of Matrix A.

| Run | Report SHA-256 | Execution commit |
| --- | --- | --- |
| A | `9b08bdfb2e3374e270b8fc9d992e2514e063d7a80a4193fb685aa5ea2e123189` | `c34da8d03f1b55f53bb528d184c8e600698ea54e` |
| B | `12a6ee49c546e31fb3b44d891a1185aae3f23431b701828a57826ac72b8e763e` | `c34da8d03f1b55f53bb528d184c8e600698ea54e` |
| A acceptance subset | `12a6ee49c546e31fb3b44d891a1185aae3f23431b701828a57826ac72b8e763e` | `c34da8d03f1b55f53bb528d184c8e600698ea54e` |

The complete JSON reports, logs and 36 Matrix A and four Matrix B case receipts
are under `E:/桌面/Living_World/runs`, in
`m12-pr07-matrix-a` and `m12-pr07-matrix-b`.

Matrix A reused 24 in-scope receipts across both scope reductions.
The Matrix A runtime in the table measures the final invocation.
The first four retained durations come from the original CLI on `b412d91`.
The rebase preserved the executable source, lockfile, content and oracle pins.
All other case times measure their individual case invocations.

### Case results

Each numeric result is the number of matching boundaries. A mismatch
lists the first differing boundary and field. Its retained JSON also
contains the expected and actual values. Case receipts record the effective
config, map and rule-library hashes and the packet digest when available.
Completed matching cases also contain the v2 projection digest.

| Case | Matrix A | A seconds | Matrix B | B seconds | Archived projection SHA-256 |
| --- | --- | ---: | --- | ---: | --- |
| `acceptance-production-base-1007489817` | 1009 | 851.239 | — | — | `3ecd7c46d4532950482c926cf630aec3c30a2960e858e581a425baacc3a38c42` |
| `acceptance-production-base-1557484054` | 1009 | 888.929 | — | — | `5616cb081ed2a3c2e9cc3a663b4ce46c0ea2e6b78bef0813ec4d55fb3e8bd8fc` |
| `acceptance-production-base-1569596598` | 1009 | 821.767 | — | — | `b4fa35dc792b0238cffb4a12dddf297607de3855939d82f7a8c1c62f96f0c42c` |
| `acceptance-production-base-1802799976` | 1009 | 885.802 | — | — | `a0558da2352b9ad832500de302bf3ba7bf433bce66eb5a9250e945deffe23f77` |
| `acceptance-production-base-2122883013` | 1009 | 815.535 | — | — | `3235befe3500669c1c5b4bf44c158ba5ade946b20b3284a6583ccb5677db2a47` |
| `acceptance-production-base-2170312666` | 1009 | 857.049 | — | — | `730a4e756fb3ce922cd576da0a0ba303f54f6d86503aa089f625096dbe0b55d8` |
| `acceptance-production-base-2560155364` | 1009 | 928.687 | — | — | `13e232989e3d7702df844e384d70d990a2c734f7f7e0a4824690a1ee4d9f3ba1` |
| `acceptance-production-base-2600456787` | 1009 | 865.630 | 1009 | 959.777 | `f3e1b056a151fe6ba62948a4a9dd44e03ab53d16b28a962863ec576443581315` |
| `acceptance-production-base-2733016023` | 1009 | 860.300 | 1009 | 968.632 | `395d98bd18c47f47848244176aeb66fa3d111b05da4fc1695dcdcd1c86ac5078` |
| `acceptance-production-base-3178109895` | 1009 | 910.162 | — | — | `82803508a78a34580db64c090efe6ab3236aed3d379168aa720d9d5167c0c28e` |
| `acceptance-production-base-330361958` | 1009 | 907.023 | — | — | `40fd037e9470a7f40d7780246f692514802a518660e61179c5fef401c7259ad3` |
| `acceptance-production-base-3335059634` | 1009 | 837.687 | 1009 | 953.239 | `b18bfc5cb4ea7929128a58524df3de555b614d50171af6e31871c0ae00944856` |
| `acceptance-production-base-3486741106` | 1009 | 907.843 | — | — | `55e734c3499daaf6c1ba4112725dbc2b0cbd69732a7c53f26382c05e23c715b6` |
| `acceptance-production-base-3501343423` | 1009 | 1007.627 | — | — | `7f039f9c1c574f03f7b2c5c670cec7863e716f598feb7dfdfed7a942846dd65b` |
| `acceptance-production-base-4155892942` | 1009 | 868.039 | — | — | `31569a8cd347dbc058874f4c3c44831a611ef24c16fca22598d99f5186127d2f` |
| `acceptance-production-base-598561891` | 1009 | 919.954 | — | — | `d46ae628ebcc05d0976a38db3e6d699888c67d261183ae327b10d1cf29618dbc` |
| `acceptance-production-base-646834264` | 1009 | 1065.212 | — | — | `01cfadcb5f86ef2739eac679a0a3c971644c214377222942e5df2bfc0b54d3c4` |
| `acceptance-production-base-857949281` | 1009 | 1048.915 | — | — | `718a38e81a9e90dca211b21256813e4bdbf41aea40f268925d0687e0d15446f4` |
| `acceptance-production-base-958049702` | 1009 | 1073.358 | 1009 | 1010.737 | `8ff53f54bd5e5d2313571f9ea6929d365ed7789f6a07c8981f38a1644f73b7ac` |
| `acceptance-production-base-969717619` | 1009 | 1018.783 | — | — | `c072fef50c5aa8fb50a706335fad821a120dd6ebe04238a08261fa9f34a05655` |
| `development-s1-orig-base-1452436788` | 1009 | 917.812 | — | — | `31078e3d659580d0e584b1ffa26bfb7212fd40d2564842bd4b1e992033078cd7` |
| `development-s1-orig-base-1883209505` | 1009 | 857.195 | — | — | `1882649f38291c64f4d38e69556da2aaeb0ec6fa5e600c1f170c06a91b0dafd1` |
| `development-s1-orig-base-2195683955` | 1009 | 821.171 | — | — | `2550e100dcb607dafabce8f04d10ec23786bd30a69802bcf316e55dbec5265c1` |
| `development-s1-orig-base-3459030352` | 1009 | 885.954 | — | — | `95f0f50aca930576c9ed88d9cf45d5f3c7cc58f35ceef01f81e6f8918920c9ba` |
| `development-s2-orig-base-2195683955` | 1009 | 274.675 | — | — | `e3ad777446f35094dea14bfb45b7c8bfc24dab7948b41118342c2a843cbceb34` |
| `development-s2-orig-base-937154673` | 1009 | 656.879 | — | — | `1beff30f90aaf454a9ae3e6ce5696c2bfd5d3f890683ff32f80c6f9ba95ff1c1` |
| `development-s2-orig-canteen-restricted-2195683955` | 1009 | 236.553 | — | — | `c906d2d1dde348f8a4ae48a6e6c9d2720373bd82d417a5ec3848469b0e98300e` |
| `development-s2-orig-canteen-restricted-937154673` | 1009 | 248.362 | — | — | `738ad7a850f1cb1ed8ea062c80fe4594a7225d2721f9ba0b0434ae5898534be1` |
| `development-s2-orig-cue-ignored-2195683955` | 1009 | 271.116 | — | — | `9b3456974301cd27879ebe87ec916bac4e15cee6e2397230e96edb16b1e2fcfe` |
| `development-s2-orig-cue-ignored-937154673` | 1009 | 643.636 | — | — | `5be08907cb08370420a8727108405a91b5e3df34bb8debc422b426dbf9d35cb7` |
| `development-s3-orig-base-2195683955` | 1009 | 243.878 | — | — | `94ed5ad46d489a05ec7b71515aad3e2b109d4f2a9b4b38fc8a553ed5852291a6` |
| `development-s3-orig-base-937154673` | 1009 | 546.391 | — | — | `258bf8f90a7c06cb0fdc3bb7bdc70be8b99c82e69a5998ce6dc7846502734d2f` |
| `development-s4-orig-base-2195683955` | 1009 | 527.654 | — | — | `09573ed9ad07f781b5ff9d1baa8aca27442a2b551c2720a20886d930c35dfd89` |
| `development-s4-orig-base-937154673` | 1009 | 204.005 | — | — | `6ff8ce4f4d047229aa39e0e2a7a3ee76830d9a7724ab87a89e67aef7589e92b2` |
| `development-s4-orig-canteen-restricted-2195683955` | 1009 | 387.887 | — | — | `af8612a2e6dd1f8a18ddebd7694b07f004740bf783cbf02bb13d135a58a55bff` |
| `development-s4-orig-canteen-restricted-937154673` | 1009 | 149.208 | — | — | `b74487057093d8acfaebcd28d4d11820feedd0d449398fa8aa2776132fb53bb5` |

Matrix A recorded WAP-26 exception hits in 0 cases.

Matrix B recorded WAP-26 exception hits in 0 cases.

### Supplemental receipt

`development-s2-orig-base-1883209505` finished during the second scope change.
It matched 1,009 boundaries in 398.648 seconds.
The retained receipt is outside the final Matrix A totals.

### Dropped development cases

The second narrowing dropped the following 25 unfinished cases from
the earlier 62-case selection. The supplemental case is listed above.

```text
development-s1-orig-base-497199041
development-s1-orig-base-937154673
development-s2-orig-base-1452436788
development-s2-orig-base-3459030352
development-s2-orig-base-497199041
development-s2-orig-canteen-restricted-1452436788
development-s2-orig-canteen-restricted-1883209505
development-s2-orig-canteen-restricted-3459030352
development-s2-orig-canteen-restricted-497199041
development-s2-orig-cue-ignored-1452436788
development-s2-orig-cue-ignored-1883209505
development-s2-orig-cue-ignored-3459030352
development-s2-orig-cue-ignored-497199041
development-s3-orig-base-1452436788
development-s3-orig-base-1883209505
development-s3-orig-base-3459030352
development-s3-orig-base-497199041
development-s4-orig-base-1452436788
development-s4-orig-base-1883209505
development-s4-orig-base-3459030352
development-s4-orig-base-497199041
development-s4-orig-canteen-restricted-1452436788
development-s4-orig-canteen-restricted-1883209505
development-s4-orig-canteen-restricted-3459030352
development-s4-orig-canteen-restricted-497199041
```

The first narrowing dropped the following 98 cases.

```text
development-s1-orig-base-1011827743
development-s1-orig-base-1021125776
development-s1-orig-base-1263016932
development-s1-orig-base-1334592829
development-s1-orig-base-201486072
development-s1-orig-base-2104929825
development-s1-orig-base-2144999532
development-s1-orig-base-2344699806
development-s1-orig-base-2507182619
development-s1-orig-base-2520148199
development-s1-orig-base-3695162045
development-s1-orig-base-3698676642
development-s1-orig-base-3976177611
development-s1-orig-base-404876745
development-s2-orig-base-1011827743
development-s2-orig-base-1021125776
development-s2-orig-base-1263016932
development-s2-orig-base-1334592829
development-s2-orig-base-201486072
development-s2-orig-base-2104929825
development-s2-orig-base-2144999532
development-s2-orig-base-2344699806
development-s2-orig-base-2507182619
development-s2-orig-base-2520148199
development-s2-orig-base-3695162045
development-s2-orig-base-3698676642
development-s2-orig-base-3976177611
development-s2-orig-base-404876745
development-s2-orig-canteen-restricted-1011827743
development-s2-orig-canteen-restricted-1021125776
development-s2-orig-canteen-restricted-1263016932
development-s2-orig-canteen-restricted-1334592829
development-s2-orig-canteen-restricted-201486072
development-s2-orig-canteen-restricted-2104929825
development-s2-orig-canteen-restricted-2144999532
development-s2-orig-canteen-restricted-2344699806
development-s2-orig-canteen-restricted-2507182619
development-s2-orig-canteen-restricted-2520148199
development-s2-orig-canteen-restricted-3695162045
development-s2-orig-canteen-restricted-3698676642
development-s2-orig-canteen-restricted-3976177611
development-s2-orig-canteen-restricted-404876745
development-s2-orig-cue-ignored-1011827743
development-s2-orig-cue-ignored-1021125776
development-s2-orig-cue-ignored-1263016932
development-s2-orig-cue-ignored-1334592829
development-s2-orig-cue-ignored-201486072
development-s2-orig-cue-ignored-2104929825
development-s2-orig-cue-ignored-2144999532
development-s2-orig-cue-ignored-2344699806
development-s2-orig-cue-ignored-2507182619
development-s2-orig-cue-ignored-2520148199
development-s2-orig-cue-ignored-3695162045
development-s2-orig-cue-ignored-3698676642
development-s2-orig-cue-ignored-3976177611
development-s2-orig-cue-ignored-404876745
development-s3-orig-base-1011827743
development-s3-orig-base-1021125776
development-s3-orig-base-1263016932
development-s3-orig-base-1334592829
development-s3-orig-base-201486072
development-s3-orig-base-2104929825
development-s3-orig-base-2144999532
development-s3-orig-base-2344699806
development-s3-orig-base-2507182619
development-s3-orig-base-2520148199
development-s3-orig-base-3695162045
development-s3-orig-base-3698676642
development-s3-orig-base-3976177611
development-s3-orig-base-404876745
development-s4-orig-base-1011827743
development-s4-orig-base-1021125776
development-s4-orig-base-1263016932
development-s4-orig-base-1334592829
development-s4-orig-base-201486072
development-s4-orig-base-2104929825
development-s4-orig-base-2144999532
development-s4-orig-base-2344699806
development-s4-orig-base-2507182619
development-s4-orig-base-2520148199
development-s4-orig-base-3695162045
development-s4-orig-base-3698676642
development-s4-orig-base-3976177611
development-s4-orig-base-404876745
development-s4-orig-canteen-restricted-1011827743
development-s4-orig-canteen-restricted-1021125776
development-s4-orig-canteen-restricted-1263016932
development-s4-orig-canteen-restricted-1334592829
development-s4-orig-canteen-restricted-201486072
development-s4-orig-canteen-restricted-2104929825
development-s4-orig-canteen-restricted-2144999532
development-s4-orig-canteen-restricted-2344699806
development-s4-orig-canteen-restricted-2507182619
development-s4-orig-canteen-restricted-2520148199
development-s4-orig-canteen-restricted-3695162045
development-s4-orig-canteen-restricted-3698676642
development-s4-orig-canteen-restricted-3976177611
development-s4-orig-canteen-restricted-404876745
```

### Dropped determinism repeats

```text
acceptance-production-base-1007489817
acceptance-production-base-1557484054
acceptance-production-base-1569596598
acceptance-production-base-1802799976
acceptance-production-base-2122883013
acceptance-production-base-2170312666
acceptance-production-base-2560155364
acceptance-production-base-3178109895
acceptance-production-base-330361958
acceptance-production-base-3486741106
acceptance-production-base-3501343423
acceptance-production-base-4155892942
acceptance-production-base-598561891
acceptance-production-base-646834264
acceptance-production-base-857949281
acceptance-production-base-969717619
```

### Preliminary diagnostic runs

The six-seed diagnostic prefix matched all 121 checked boundaries per case.
It covered one acceptance seed and five development cases across the four
development configurations. Its log and result share stem
`pr07-prefix-4beaa0d7e449`.

The initial standalone acceptance probe for seed `2600456787` matched all
1,009 boundaries. It ran in 1,946.172 seconds alongside other workers.
That preliminary invocation retained the raw packet journal under
`C:/Temp/li-p35/pr07-probe-1` and measured the trajectory before the final
exception scanner and compact receipts were added.

## Declared exceptions

[CR-011 clause A](../../spec/open-questions.md#cr-011-compatibility-profiles-legacy-triggers-and-apparent-action-views-approved-2026-11-18)
preserved both WAP §11.3 scripted exception classes in the approved
compatibility domain. The WAP-26 checks drive the five exception cases and
one control through the real compatibility engine.
The matrix scanner uses v2 opening state and actual bound submissions.

| WAP-26 input | Required v2 code |
| --- | --- |
| Exhausted gather at a receipted tree outside reach | `OUT_OF_REACH` (CR-011 A, WAP §11.3 class 1) |
| Exhausted gather at a receipted tree that has disappeared | `INVALID_TARGET` (CR-011 A, WAP §11.3 class 1) |
| Full hydration with a canteen drink and no held canteen | `NO_ITEM` (CR-011 A, WAP §11.3 class 1) |
| Second reply after acceptance | `INVALID_REPLY` (CR-011 A, WAP §11.3 class 2) |
| Second reply after refusal | `INVALID_REPLY` (CR-011 A, WAP §11.3 class 2) |
| Unreceipted tree control | `INVALID_TARGET` in both engines |

## Owner rulings of 2026-11-23

| Decision | Approved scope |
| --- | --- |
| [CR-P3.5-EN-05](../../spec/open-questions.md#cr-p35-en-05-reachable-packets-for-wap-19-report-order) | WAP-19 uses separate reachable awake and wake packets. Each packet preserves the §5.3 report order and the final sleep tick suppresses hearing. |
| [CR-P3.5-PR-06](../../spec/open-questions.md#cr-p35-pr-06-a-private-trigger-for-an-externally-scheduled-fallback) | A native fallback turn may carry a private request-only `PLAN_FINISHED` when the legacy queue and deferred triggers are empty. Packet and boundary triggers retain their original provenance. |
| [CR-P3.5-PR-06-B3](../../spec/open-questions.md#cr-p35-pr-06-b3-private-typed-feedback-input-for-the-frozen-planner) | The adapter may give the frozen planner feedback through `request.context.perception.last_action_feedback` in an isolated typed v1 request for the duration of the synchronous call. Packet, journal, model and memory callbacks, day log and recall receive the clean input. |
| [OQ-P3.5-EN-05](../../spec/open-questions.md#oq-p35-en-05-visible-contents-and-progress-at-settlement) | Confirmed as written. Visible process workspaces expose contents at their captured location. Other containers show descriptors. Progress reports include a final word change at settlement. |
| [OQ-P3.5-EN-07](../../spec/open-questions.md#oq-p35-en-07-run-content-pins-and-packet-prefix-encoding) | Confirmed as written. Checkpoints bind the contiguous packet prefix and opaque sim state. Rule approvals retain admission order and the loader pins base-first composed ancestry. |
| [OQ-P3.5-PR-05](../../spec/open-questions.md#oq-p35-pr-05-read-access-to-the-frozen-boundary) | Confirmed as written. Scheduling uses detached pending packets and read-only access to turn ordinals. The world validates submissions and acknowledgement IDs. |
| [OQ-P3.5-PR-06](../../spec/open-questions.md#oq-p35-pr-06-mapping-speech-outside-the-v1-shapes) | Confirmed as written. The adapter uses `INVALID_SPEECH_ACT` for suppressed fallback talk, preserves native speech text in the private projection, and emits a reply trigger only for representable addressed requests. |

## Acceptance evidence

The combined `tests/v2 tests/p3/test_trial_registration.py` session passed
855 tests in 898.57 seconds on
`b412d912c0442b71277558c8f55cc3124abca6d6`. It included the compatibility,
synthetic-pack and ADR 0014 D3 tests. The four static checks passed on the rebased revision `c34da8d03f1b55f53bb528d184c8e600698ea54e`. The final focused equivalence session reported 82 passed in 27.56s (exit 0).

Under the owner's CI-only decision of 2026-11-23, the local full suite
was stopped. A green backend job in [GitHub CI](../../../.github/workflows/ci.yml)
on the draft PR's head revision supplies the full-suite evidence.

The focused equivalence suite passed all 43 tests on implementation and test
revision `d60acebb6915f8a14a527ffdec206f8aeb169d66`. The ADR 0014 D3 proof
passed in a separate process on that revision. Durable logs and exit receipts
are under `C:/Temp/li-p35`, with stems `pr07-focused-18d14d5407ff` and
`pr07-d3-98ef907e3779`.

| Acceptance | Test or evidence |
| --- | --- |
| WAP-15 and CT-02 | Every registered matrix trajectory through tick 1,008. |
| WAP-26 | `test_exceptions.py` and matrix scanner. |
| CT-15 | Three-tick give, capped two-fruit regrowth, registry refusals and bound config hashes. |
| CT-16, canteen | One serving fills to two. A full canteen returns the `already_full` phenomenon. |
| CT-17 | Pinned maps and configs, exact 0/1/2 servings, zero regrowth, one-tick gather. |
| EN-01 | Last-fruit gather settles before regrowth, and physiology sees completion. |
| EN-08 | Contested gather and pickup and the two talks competing for the last slot, with exact completion order and RNG. |
| EN-12, EN-13, CT-10 and CT-11, compatibility | Exact need values and ordinary and early wake at the archived boundaries. |
| WAP-32 | Sleep across dawn, final-tick hearing suppression, and corpse sight and receipts across restore. |
| WAP-33 and EN-23 | Exhaustion without a shuffle entry, phase-2 path blocking before death, and death winning when found with exhaustion. |
| ADR 0014 D3 | [EN-02 extension proof](P3.5-EN-02.md#what-changed). A content-only rule changes rest settlement. The validator refuses a nonconserving rule. The executable proof is `test_extension_pack_changes_settlement_and_refuses_nonconservation` in `backend/tests/v2/engine/settle/test_admission.py`. |

## Owner review at M12 Gate 3

The owner reviews this report and Claude Code's Gate 2 and acceptance
findings before signing [M12](../../plans/p3.5-implementation-plan-v0.1.md#4-milestones-and-gates).

1. Confirm that the real v2 engine, `compat-v1` and the frozen rule-based
   policy through its adapters match the v1 archive at all 1,009 boundaries
   of each of the 20 acceptance and 16 development cases. Verify that
   the four independent acceptance repeats match the corresponding
   Matrix A receipts.
2. Confirm that the scripted evidence covers the specified boundary cases
   and the five approved WAP-26 outcomes, with zero occurrences in the P2
   matrices. Check the approved change requests and any first differing
   boundaries before deciding whether the milestone can pass.
3. Verify the synthetic-pack engine tests and [ADR 0014 D3](../../adr/0014-evaluation.md#d3-extension-points-as-acceptance-tests)
   evidence. The engine settles a content-only extension rule and the
   validator rejects a rule that violates conservation.
