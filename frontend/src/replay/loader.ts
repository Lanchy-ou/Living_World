// Loading: file picker, drag-and-drop and the bundled example all end in validateText.
// The text is parsed and checked as-is; it is never repaired or written back.
import exampleText from "../../tests/fixtures/handmade/move-and-gather.json?raw";
import schemaText from "../api/generated/replay.schema.json?raw";
import { readReplayFile } from "./loadCoordinator.ts";
import type { LoadResult } from "./types.ts";
import type { ReplayValidator } from "./validate.ts";
import { createReplayValidator } from "./validate.ts";

let validator: ReplayValidator | null = null;

export function getValidator(): ReplayValidator {
  validator ??= createReplayValidator(JSON.parse(schemaText) as object);
  return validator;
}

export function loadFromFile(file: File): Promise<LoadResult> {
  return readReplayFile(file, (text) => getValidator().validateText(text));
}

export const EXAMPLE_NAME = "move-and-gather.json (hand-made example)";

export function loadExample(): LoadResult {
  return getValidator().validateText(exampleText);
}
