import decisionSchema from "./generated/decision.schema.json?raw";
import indexSchema from "./generated/index.schema.json?raw";
import registrationSchema from "./generated/registration.schema.json?raw";
import sampleSchema from "./generated/sample.schema.json?raw";
import traceSchema from "./generated/trace.schema.json?raw";
import { createInspectionLoader } from "./inspection.ts";
import type { LocalInspectionFile, ReplayFileSource } from "./inspection.ts";

let loader: ReturnType<typeof createInspectionLoader> | undefined;

export function loadInspection(files: readonly LocalInspectionFile[], replay: ReplayFileSource, signal: AbortSignal) {
  signal.throwIfAborted();
  loader ??= createInspectionLoader({
    index: JSON.parse(indexSchema),
    decision: JSON.parse(decisionSchema),
    sample: JSON.parse(sampleSchema),
    registration: JSON.parse(registrationSchema),
    trace: JSON.parse(traceSchema),
  });
  return loader(files, replay, signal);
}
