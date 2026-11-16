import { createReplayLoadCoordinator, readReplayFile } from "../replay/loadCoordinator.ts";
import type { LoadResult, ReplayBundle, ReplayError } from "../replay/types.ts";
import type { LocalInspectionFile, ReplayFileSource, VerifiedInspection } from "./inspection.ts";

export function createReplayWithSource(
  validateText: (text: string) => LoadResult,
  onLoad: (bundle: ReplayBundle, name: string, bytes: ArrayBuffer | null) => void,
  onError: (error: ReplayError, name: string) => void,
) {
  const bytesForBundle = new WeakMap<ReplayBundle, ArrayBuffer>();
  const request = createReplayLoadCoordinator({
    onLoad: (bundle, name) => onLoad(bundle, name, bytesForBundle.get(bundle) ?? null),
    onError,
  });
  return {
    file: (file: LocalInspectionFile) => request(file.name, async () => {
      let bytes: ArrayBuffer | null = null;
      const result = await readReplayFile({
        text: async () => {
          bytes = await file.arrayBuffer();
          return new TextDecoder().decode(bytes);
        },
      }, validateText);
      if (result.ok && bytes !== null) bytesForBundle.set(result.bundle, bytes);
      return result;
    }),
    example: request,
  };
}

export type InspectionState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; value: VerifiedInspection }
  | { status: "error"; message: string };

export function createInspectionImport(
  load: (files: readonly LocalInspectionFile[], replay: ReplayFileSource, signal: AbortSignal) => Promise<VerifiedInspection>,
  setState: (state: InspectionState) => void,
) {
  let active: AbortController | null = null;
  return {
    reset() {
      active?.abort();
      active = null;
      setState({ status: "idle" });
    },
    async select(files: readonly LocalInspectionFile[], replay: ReplayFileSource) {
      active?.abort();
      const request = new AbortController();
      active = request;
      setState({ status: "loading" });
      try {
        const value = await load(files, replay, request.signal);
        if (!request.signal.aborted) setState({ status: "ready", value });
      } catch (error) {
        if (!request.signal.aborted) {
          setState({ status: "error", message: error instanceof Error ? error.message : "Unable to verify these files." });
        }
      } finally {
        if (active === request) active = null;
      }
    },
  };
}
