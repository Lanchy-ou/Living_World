import type { ReactNode } from "react";
import type { ReplayBundle } from "../replay/types.ts";
import { ExperienceList, GoalEvidence, PlainData, SourceFile } from "./CognitionSources.tsx";
import type { SourceNavigation } from "./CognitionSources.tsx";
import { decisionAt, reported } from "./cognitionView.ts";
import { deliveryId } from "./encoding.ts";
import type { AttemptDispatch, DecisionInspection as DecisionShard, LLMCallRecordP3 } from "./generated/decision.ts";
import type { InspectionDecisionRef } from "./generated/index.ts";
import { useShard } from "./useShard.ts";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

function Attempt({ call, dispatch }: { call: LLMCallRecordP3; dispatch: AttemptDispatch }) {
  const { result, debit } = call;
  return (
    <section className="p3-debug-card" aria-label={`Provider attempt ${call.attempt_index + 1}`}>
      <h4>Attempt {call.attempt_index + 1} · {result.outcome}</h4>
      <p><code>{call.call_id}</code></p>
      <dl className="p3-facts">
        <Fact label="Model">{dispatch.model_id}</Fact>
        <Fact label="Adapter">{dispatch.adapter_id} · {dispatch.adapter_version}</Fact>
        <Fact label="Prompt">{dispatch.prompt_version}</Fact>
        <Fact label="Action schema">{dispatch.action_schema_version}</Fact>
        <Fact label="Validation error">{call.validation_error ?? "None recorded"}</Fact>
        <Fact label="Detail code">{call.detail_code ?? "None recorded"}</Fact>
        <Fact label="Provider error code">{result.provider_error_code ?? "None recorded"}</Fact>
        <Fact label="Latency">{reported(result.latency_ms, " ms")}</Fact>
        <Fact label="Reported input tokens">{reported(result.token_input)}</Fact>
        <Fact label="Reported output tokens">{reported(result.token_output)}</Fact>
        <Fact label="Usage">{debit.usage_unknown ? "Unknown" : "Known"}</Fact>
        <Fact label="Reported cost">Unknown</Fact>
        <Fact label="Ledger ceiling charge">{debit.money_charged} micro-CNY</Fact>
        <Fact label="Ledger charged tokens">{debit.input_charged} input · {debit.output_charged} output</Fact>
        <Fact label="Provider request ID">{result.provider_request_id ?? "Unknown"}</Fact>
        <Fact label="Response body">{result.observed_body_bytes} bytes · {result.response_complete ? "complete" : "incomplete"}</Fact>
      </dl>
      <PlainData title="Proposed actions and cognitive delta" value={call.parsed_proposal ?? "No parsed proposal recorded"} />
      <details className="p3-source">
        <summary>Raw response</summary>
        <pre>{result.raw_response ?? "Unknown"}</pre>
      </details>
      <details className="p3-source">
        <summary>Extracted response text</summary>
        <pre>{result.response_text ?? "Unknown"}</pre>
      </details>
      <details className="p3-source">
        <summary>Captured response bytes (base64)</summary>
        <pre>{result.raw_body_base64 ?? "Unknown"}</pre>
      </details>
      <PlainData title="Dispatch, request and reservation" value={dispatch} />
      <PlainData title="Committed debit" value={debit} />
    </section>
  );
}

function DecisionDetails({
  shard, refInfo, ...navigation
}: SourceNavigation & { shard: DecisionShard; refInfo: InspectionDecisionRef }) {
  const { inspection, onShowEvent } = navigation;
  const { record, context, calls, dispatches } = shard;
  const { manifest, provider_projection: provider } = context.assembly;
  const { perception, goals, recalled_experience: recall } = context.request.context;
  const omittedExperience = manifest.experiences.filter((entry) => entry.omission !== null).length;
  const omittedTiles = manifest.static_tiles.filter((entry) => entry.omission !== null).length;
  return (
    <div className="p3-decision-content">
      <header className="p3-decision-head">
        <div>
          <h3>Committed decision</h3>
          <p><code>{record.decision_id}</code> · {record.actor_id} · decision tick {record.tick}</p>
        </div>
        <SourceFile refInfo={refInfo.shard} />
      </header>
      <dl className="p3-facts p3-decision-facts">
        <Fact label="Status">{record.status}</Fact>
        <Fact label="Primary policy">{record.policy_id}</Fact>
        <Fact label="Effective policy">{record.effective_policy_id}</Fact>
        <Fact label="Error">{record.error_kind ?? "None recorded"}</Fact>
        <Fact label="Detail code">{record.detail_code ?? "None recorded"}</Fact>
        <Fact label="Fallback error">{record.fallback_error ?? "None recorded"}</Fact>
        <Fact label="Decision triggers">{record.triggers.join(", ") || "None recorded"}</Fact>
      </dl>

      <div className="p3-split">
        <section className="p3-debug-card">
          <h4>Full delivered context</h4>
          <p>Delivery <code>{deliveryId(record.run_id, record.actor_id, record.tick)}</code></p>
          <p className="quiet">Before this decision · {recall.length} recalled experiences</p>
          <h5>Goal before this decision</h5>
          <GoalEvidence {...navigation} goals={goals} />
          <PlainData title="Full decision request" value={context.request} />
          <PlainData title="Delivered perception" value={perception} />
          <details className="p3-source">
            <summary>Recalled experience</summary>
            <ExperienceList {...navigation} experiences={recall} />
          </details>
        </section>
        <section className="p3-debug-card">
          <h4>Provider projection</h4>
          {provider === null ? <p>Unavailable · {context.assembly.error}</p> : (
            <>
              <p>{provider.recalled_experience.length} experiences · {provider.perception.explored_static_tiles.length} explored tiles</p>
              <PlainData title="Projected context" value={provider} />
            </>
          )}
          {context.provider_request === null ? <p className="quiet">No provider request was recorded.</p> : (
            <PlainData title="Recorded provider request" value={context.provider_request} />
          )}
          <h5>Inclusion and omission</h5>
          <dl className="p3-facts">
            <Fact label="Context profile"><code>{manifest.context_profile_id}</code></Fact>
            <Fact label="Retrieval strategy"><code>{manifest.retrieval_profile}</code></Fact>
            <Fact label="Projection profile"><code>{manifest.projection_profile}</code></Fact>
            <Fact label="Retained experience">{manifest.retained_record_count}</Fact>
            <Fact label="Evicted experience">{manifest.evicted_record_count}</Fact>
            <Fact label="Omitted">{omittedExperience} experience · {omittedTiles} tiles</Fact>
            <Fact label="Mandatory bytes">{manifest.mandatory_bytes}</Fact>
            <Fact label="Projection bytes">{reported(manifest.projection_bytes)}</Fact>
          </dl>
          <PlainData title="Full inclusion manifest and omission reasons" value={manifest} />
        </section>
      </div>

      <div className="p3-split">
        <section className="p3-debug-card">
          <h4>Accepted plan and delta</h4>
          <p><code>{record.plan.plan_id}</code> · goal change <strong>{record.accepted_delta.goal_change.operation}</strong></p>
          <ol className="p3-plan">
            {record.plan.intents.map((intent) => (
              <li key={intent.intent_id}><code>{intent.action_type}</code> · <code>{intent.intent_id}</code></li>
            ))}
          </ol>
          <PlainData title="Effective plan" value={record.plan} />
          <PlainData title="Accepted cognitive delta" value={record.accepted_delta} />
        </section>
        <section className="p3-debug-card">
          <h4>Recorded world outcomes</h4>
          {shard.outcome_event_ids.length === 0 ? <p>No outcome events for this plan.</p> : (
            <ul className="p3-plan">
              {shard.outcome_event_ids.map((id) => {
                const event = inspection.eventsById.get(id)!;
                return (
                  <li key={id}>
                    <span>{event.type} · tick {event.tick} </span>
                    <button className="p3-link" type="button" onClick={() => onShowEvent(event)}><code>{id}</code></button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <section className="p3-attempts">
        <h4>Provider attempts ({calls.length})</h4>
        {calls.length === 0 && <p>No provider attempts recorded for this decision.</p>}
        {calls.map((call, i) => <Attempt key={call.call_id} call={call} dispatch={dispatches[i]} />)}
      </section>
      <details className="p3-source">
        <summary>Index, trace and registration identities</summary>
        <dl className="p3-facts">
          <Fact label="Index SHA-256"><code>{inspection.indexSha256}</code></Fact>
          <Fact label="Trace SHA-256"><code>{inspection.index.trace_sha256}</code></Fact>
          <Fact label="Registration"><code>{inspection.registration.registration_id}</code></Fact>
          <Fact label="Registration SHA-256"><code>{inspection.index.registration_sha256}</code></Fact>
          <Fact label="Replay SHA-256"><code>{inspection.index.replay_sha256}</code></Fact>
          <Fact label="Request SHA-256"><code>{record.request_sha256}</code></Fact>
          <Fact label="Context SHA-256"><code>{record.context_sha256}</code></Fact>
          <Fact label="Projection SHA-256"><code>{record.projection_sha256 ?? "Unavailable"}</code></Fact>
        </dl>
      </details>
    </div>
  );
}

export function DecisionInspection({
  actor, tick, residents, onActor, ...navigation
}: SourceNavigation & {
  actor: string | null;
  tick: number;
  residents: ReplayBundle["residents"];
  onActor: (actor: string | null) => void;
}) {
  const { inspection, onDecision } = navigation;
  const refs = actor === null ? [] : inspection.decisionRefsByActor.get(actor) ?? [];
  const ref = decisionAt(refs, tick);
  const selected = useShard(ref, inspection.readDecision);
  return (
    <section className="p3-debug" aria-label="Decision debug">
      <div className="p3-selectors">
        <label>Resident{" "}
          <select value={actor ?? ""} onChange={(event) => onActor(event.target.value || null)}>
            <option value="">Select a resident</option>
            {residents.map((resident) => (
              <option key={resident.id} value={resident.id}>{resident.display_name} · {resident.id}</option>
            ))}
          </select>
        </label>
        {actor !== null && (
          <label>Decision tick{" "}
            <select value={ref?.decision_id ?? ""} onChange={(event) => onDecision(event.target.value)}>
              {ref === undefined && <option value="" disabled>No decision at tick {tick}</option>}
              {refs.map((row) => <option key={row.decision_id} value={row.decision_id}>Tick {row.tick} · decision {row.ordinal + 1}</option>)}
            </select>
          </label>
        )}
      </div>
      {actor === null ? <p>Select a resident to inspect its decisions.</p> : ref === undefined ? (
        <p>No committed decision for <code>{actor}</code> at replay tick {tick}.</p>
      ) : selected === null ? <p role="status">Reading the verified decision…</p> : "error" in selected ? (
        <p role="alert">{selected.error}</p>
      ) : <DecisionDetails {...navigation} shard={selected.value} refInfo={ref} />}
    </section>
  );
}
