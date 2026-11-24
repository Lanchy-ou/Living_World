import indexText from "./generated/index.schema.json?raw";
import shardText from "./generated/shard.schema.json?raw";
import { makeLoader } from "./import.ts";

export const load = makeLoader(JSON.parse(indexText), JSON.parse(shardText));
