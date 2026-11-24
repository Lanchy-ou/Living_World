"""Exercise the existing frontend import router with the retained replay and directories."""

import json
import subprocess

from v2.fake_workload.island import ROOT


def open_exports(directory, actors):
    # Node 24 supplies the browser byte APIs. Read files lazily as the operator's
    # File objects do; a week export is too large to preload all parts into memory.
    program = """
import assert from "node:assert/strict";
import { openAsBlob } from "node:fs";
import { readFile, readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { inspectionRouter, makeLoader } from "./src/features/v2-inspection/import.ts";
const [root, ...actors] = process.argv.slice(2);
const schema = async name => JSON.parse(await readFile(
    './src/features/v2-inspection/generated/' + name + '.schema.json', 'utf8'));
const load = makeLoader(await schema("index"), await schema("shard"));
const blob = await openAsBlob(join(root, "replay.json"));
const replay = {bundle: JSON.parse(await blob.text()), bytes: await blob.arrayBuffer()};
const opened = {};
for (const actor of actors) {
    const folder = join(root, "inspection-" + actor);
    const files = [];
    for (const name of await readdir(folder)) {
        const path = join(folder, name);
        files.push({name, size: (await stat(path)).size,
                    arrayBuffer: async () => (await openAsBlob(path)).arrayBuffer()});
    }
    let state;
    const router = inspectionRouter({reset() {}, select() {assert.fail("unexpected v1 route")}},
                                    load, s => {state = s});
    await router.select(files, replay);
    assert.equal(state.status, "ready", state.message);
    const archive = state.value;
    const {shard} = archive.index.decisions.find(r => r.resident_id === actor);
    const turn = await archive.read(shard);
    opened[actor] = turn.record.turn_id;
}
console.log(JSON.stringify(opened));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-", str(directory), *actors],
        input=program,
        text=True,
        cwd=ROOT / "frontend",
        stdout=subprocess.PIPE,
        check=True,
    )
    return json.loads(result.stdout)
