import type { LoadResult, ReplayBundle, ReplayError } from "./types.ts";

interface ReplayLoadHandlers {
  onLoad: (bundle: ReplayBundle, name: string) => void;
  onError: (error: ReplayError, name: string) => void;
}

export function createReplayLoadCoordinator({ onLoad, onError }: ReplayLoadHandlers) {
  let latestRequest = 0;

  return async (name: string, load: () => LoadResult | Promise<LoadResult>): Promise<void> => {
    const request = ++latestRequest;
    const result = await load();
    if (request !== latestRequest) return;

    if (result.ok) onLoad(result.bundle, name);
    else onError(result.error, name);
  };
}

export async function readReplayFile(
  file: { text(): Promise<string> },
  validateText: (text: string) => LoadResult,
): Promise<LoadResult> {
  let text: string;
  try {
    text = await file.text();
  } catch {
    return {
      ok: false,
      error: {
        kind: "file_read",
        message: "The browser could not read the selected replay file.",
        details: [],
      },
    };
  }
  return validateText(text);
}
