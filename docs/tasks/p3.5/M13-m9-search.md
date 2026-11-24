# M13 D4 record: original M9 source artifacts

Claude Code searched once, read-only, on 2026-11-25 as custodian under
[M13 plan](M13-plan.md) D4. No earlier completed search receipt existed in
`docs/tasks`. This is the single D4 record that CT-10 cites. It is
independent of milestone acceptance. [P3 closeout](../p3/P3-closeout.md)

## Scope

The search took the 22 distinct `runs/` paths named in
[M9 evidence](../p3/M9-evidence.md). It checked each path, verbatim and
below a `runs/` prefix, in these places:

- the main checkout `E:\桌面\Living_World`;
- all 17 retained Codex worktrees under `D:\Codex\.codex\worktrees\*\Living_World`;
- the two worktree folders that M9 recorded, `p3-05-launcher` and
  `p3-05-integration`;
- the retained `.p3ext-*` and `g2-*` folders in the main checkout;
- the only backup found, `runs/_cleanup-backup-2026-11-14`.

The owner has named no other backup.

## Result

| Status | Paths |
| --- | --- |
| **Present, receipts only** | `runs/p3/p3-smoke-u3-r1`, `runs/p3/p3-smoke-u3-r1/receipts`, `runs/p3/p3-smoke-u4-r1` |
| **Lost** (absent from every accessible location) | the remaining 19 paths: the `first`, `recorded` and `continued` run trees and the tick-8 checkpoint of `p3-smoke-r1`; the `first` and `recorded` trees of `p3-05-fake-r1`; `runs/p3/verification/backend-ab4a3f6.xml`; and all eleven `runs/p305-*` files and folders |
| **Unresolved** (inaccessible) | `.p3ext-a37` through `.p3ext-a48` and `g2-3213a65596`. Their access control denies listing, so they were not searched. Reading them needs the owner's approval of a read-only access grant on retained evidence. |

The two recorded worktree folders still exist. `p3-05-launcher` holds only
pytest temporary folders and a `.codex-worktree-name` marker.
`p3-05-integration` holds only the marker. Neither has a `Living_World`
checkout or a `runs/` tree. The cleanup backup holds `p2-f1-frontend`,
`p3-01-spec-review` and `p3-03-runtime-audit`, which are not M9 sources.

## Surviving receipts

`E:\桌面\Living_World\runs\p3` keeps receipt folders, not run data, for four
M9 runs. There are 130 files in total. The SHA-256 of the sorted
`sha256sum` listing of all 130 files is
`7ffcc5e9505c0fcb02f9201e998ff671fc14e1237a005eaf5ccf13d8e136c158`.

| Run | Files | Top-level receipt | SHA-256 |
| --- | ---: | --- | --- |
| `p3-05-fake-r1` | 5 | `receipts/p3-05-fake-r1.s1292387875.json` | `6bbd50e54bf16d4d402e5a4e6b92dd50f19cdb2962d19628f98b677c054645bf` |
| `p3-smoke-r1` | 17 | `receipts/p3-smoke-r1.s1292387875.json` | `8da11781d524b4056cb045b8f3c795029ea2d5cc6e89681b6635fb0f2058a025` |
| `p3-smoke-u3-r1` | 10 | `receipts/p3-smoke-u3-r1.s1292387875.json` | `b052b39344162bab5d0fe054c8ed5887df11518ad34dd75c946be277520c28f6` |
| `p3-smoke-u4-r1` | 98 | `receipts/p3-smoke-u4-r1.s1292387875.json` | `7c66af94d52808ed6420f55e981942a462046e44a22eca46d984b39481925c5d` |

The surviving files are receipts, lineage records and finalization records.
They cannot replay or re-verify a run. The original source runs are
therefore **lost** at every accessible location, with the 13 inaccessible
folders left **unresolved**. Nothing was moved, recreated or modified. The
historical P3 V-04 stays stopped at 132.
