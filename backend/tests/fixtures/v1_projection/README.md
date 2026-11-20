# v1 reference projections

The archive contains 20 acceptance runs and 140 development runs at the P2
horizon of 1,008 ticks, plus scripted M12 cases. The four TOML files under
`configs/` are exact, hash-checked substitutions from starter content §4.7.
The generator reads the original configs and maps from their pinned Git
revisions and checks their raw SHA-256 digests before applying a seed.

Regenerate fixtures from the annotated `v1-archive` tag only. Fetch the
tag and the full repository history, then run these commands from its checkout.

```sh
uv sync --directory backend --locked
uv run --directory backend python ../scripts/gen_v1_projections.py
uv run --directory backend python ../scripts/gen_v1_projections.py --check
```

The initial publication uses the pinned v1 source commit before the owner
creates the tag. Each fixture records that commit, the source and effective
config and map digests, the seed, and the generator version. The generator
checks the working tree against the pinned v1 source.

Each `.json.gz` file contains one `projection/0.1` object encoded as v1
canonical JSON. The gzip header has a zero timestamp and an empty filename.
Read fixtures through `living_island.sim.equivalence.projection.read_projection`.
Use `--jobs` to set the number of matrix workers.

A frame records committed world state and lists the utterances and outcomes
that ended at that boundary, in v1 emission order. Decisions at a boundary
are the actual plans selected after that packet is ingested. An outcome's
`next_decision_tick` links to the first recorded policy decision for its
actor. It is null when no later decision exists in the fixture, including
after death or when the run ended before the policy could decide again.
A queued intent can run without a new decision.

Scripted cases seed fixture state and submit selected plans through v1's
coordinator. The rule policy processes feedback and selects the next plan
at unscripted focal turns. The evidence includes packets, queues, receipts,
back-off and RNG state from v1. The daylight and regrowth cases use a late
starting boundary. Registry-negative inputs are checked in memory and
recorded with the profile refusal and two-serving controls. WAP-23's sleeping stamina case is
the owner-approved recovery and no-trigger control.
