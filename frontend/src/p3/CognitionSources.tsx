import type { WorldEvent } from "../replay/types.ts";
import type { ShardRef } from "./generated/index.ts";
import type { ExperienceRecord, GoalState } from "./generated/sample.ts";
import type { VerifiedInspection } from "./inspection.ts";
import { decisionAt, experienceLabels, prettyValue } from "./cognitionView.ts";

export interface SourceNavigation {
  inspection: VerifiedInspection;
  onDecision: (id: string) => void;
  onShowEvent: (event: WorldEvent) => void;
}

export function SourceFile({ refInfo }: { refInfo: ShardRef }) {
  return (
    <details className="p3-source">
      <summary>Source file and SHA-256</summary>
      <dl className="p3-facts">
        <div><dt>File</dt><dd><code>{refInfo.file}</code></dd></div>
        <div><dt>SHA-256</dt><dd><code>{refInfo.sha256}</code></dd></div>
      </dl>
    </details>
  );
}

export function PlainData({ title, value }: { title: string; value: unknown }) {
  return <details className="p3-source"><summary>{title}</summary><pre>{prettyValue(value)}</pre></details>;
}

function DecisionLink({ id, onDecision }: { id: string; onDecision: SourceNavigation["onDecision"] }) {
  return <button className="p3-link" type="button" onClick={() => onDecision(id)}><code>{id}</code></button>;
}

export function GoalEvidence({
  goals, inspection, onDecision, onShowEvent,
}: SourceNavigation & { goals: GoalState }) {
  const goal = goals.current;
  if (goal === null) return <p className="quiet">No current goal recorded.</p>;
  const evidence = goal.evidence;
  const status = { intended: "Intended", attempted: "Attempted", observed_complete: "Observed complete" }[goal.status];
  const outcome = evidence === null ? undefined : inspection.eventsByIntent.get(evidence.feedback.intent_id)
    ?.find((event) => event.tick === evidence.observed_tick && event.type === "action_succeeded");
  return (
    <div className="p3-goal">
      <p><strong>{goal.text}</strong></p>
      <p><span className="p3-status">{status}</span><span className="quiet"> · created tick {goal.created_at_tick} · <code>{goal.goal_id}</code></span></p>
      {evidence === null ? (
        <p className="quiet">No delivered feedback recorded for this goal.</p>
      ) : (
        <div className="p3-evidence">
          <p>Feedback at tick {evidence.observed_tick} · <strong>{evidence.feedback.status}</strong> · <code>{evidence.feedback.intent_id}</code></p>
          <details className="p3-source">
            <summary>Delivery <code>{evidence.delivery_id}</code></summary>
            <pre>{prettyValue(evidence)}</pre>
          </details>
          <p>Accepted decision <DecisionLink id={evidence.owned_intent.decision_id} onDecision={onDecision} /></p>
          {outcome !== undefined && (
            <p>World event <button type="button" className="p3-link" onClick={() => onShowEvent(outcome)}><code>{outcome.event_id}</code></button></p>
          )}
        </div>
      )}
      <PlainData title="Completion condition" value={goal.completion} />
    </div>
  );
}

function ExperienceValue({ experience }: { experience: ExperienceRecord }) {
  const { data } = experience.payload;
  if ("text" in data) return <q>{data.text}</q>;
  if ("physical_description" in data) return <p>{data.physical_description}</p>;
  if ("entity_id" in data) return <p><code>{data.entity_id}</code> · {data.entity_type} · ({data.position.x}, {data.position.y})</p>;
  if ("plan" in data) return <p>{data.plan.intents.map((intent) => intent.action_type).join(", ")}</p>;
  if ("feedback" in data) return <p>{data.feedback.status} · <code>{data.feedback.intent_id}</code></p>;
  return <p>({data.position.x}, {data.position.y}) · health {data.condition.health} · {data.inventory.fruit_count} fruit</p>;
}

export function ExperienceList({
  experiences, inspection, onDecision, onShowEvent,
}: SourceNavigation & { experiences: readonly ExperienceRecord[] }) {
  if (experiences.length === 0) return <p className="quiet">No experience records in this view.</p>;
  return (
    <ol className="p3-experience">
      {experiences.map((experience) => {
        const source = experience.source;
        const context = decisionAt(inspection.decisionRefsByActor.get(experience.owner_id) ?? [], experience.observed_tick);
        const utterance = "utterance_id" in experience.payload.data
          ? inspection.eventsById.get(experience.payload.data.utterance_id) : undefined;
        return (
          <li key={experience.experience_id}>
            <p><strong>{experienceLabels[experience.kind]}</strong> <span className="quiet">· tick {experience.observed_tick} · {experience.payload.information_kind}</span></p>
            <ExperienceValue experience={experience} />
            <details className="p3-source">
              <summary>Source record <code>{experience.experience_id}</code></summary>
              {source.source_kind === "decision" ? (
                <p>Accepted decision <DecisionLink id={source.decision_id} onDecision={onDecision} /></p>
              ) : (
                <>
                  <p>Delivery <code>{source.delivery_id}</code> · <code>{source.field}{source.index === null ? "" : `[${source.index}]`}</code></p>
                  {context !== undefined && (
                    <p>Delivered context <DecisionLink id={context.decision_id} onDecision={onDecision} /></p>
                  )}
                  {utterance !== undefined && (
                    <p>World event <button type="button" className="p3-link" onClick={() => onShowEvent(utterance)}><code>{utterance.event_id}</code></button></p>
                  )}
                </>
              )}
              <pre>{prettyValue(experience)}</pre>
            </details>
          </li>
        );
      })}
    </ol>
  );
}
