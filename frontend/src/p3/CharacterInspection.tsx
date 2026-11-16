import { ExperienceList, GoalEvidence, SourceFile } from "./CognitionSources.tsx";
import type { SourceNavigation } from "./CognitionSources.tsx";
import { useShard } from "./useShard.ts";

export function CharacterInspection({
  actor, tick, alive, ...navigation
}: SourceNavigation & { actor: string; tick: number; alive: boolean }) {
  const { inspection } = navigation;
  const ref = inspection.sample(actor, tick);
  const sample = useShard(ref, inspection.readSample);
  return (
    <section className="p3-character" aria-label="Character cognition">
      <h3>Character cognition</h3>
      <p className="quiet"><code>{actor}</code> · replay tick {tick}</p>
      {ref === undefined ? <p>No sample for this actor and tick.</p> : sample === null ? (
        <p role="status">Reading the verified sample…</p>
      ) : "error" in sample ? <p role="alert">{sample.error}</p> : (
        <>
          <p className="p3-cursor">
            {sample.value.latest_perception_tick < 0
              ? "Cognition observed through tick −1 · no observations received"
              : `Cognition observed through tick ${sample.value.latest_perception_tick}`}
          </p>
          {!alive && <p className="quiet">Cognition stopped after death.</p>}
          <dl className="p3-facts">
            <div><dt>Identity profile</dt><dd><code>{sample.value.identity.profile_id}</code></dd></div>
            <div><dt>Values</dt><dd>
              {sample.value.identity.values.length === 0 ? "None recorded" :
                <ul>{sample.value.identity.values.map((value, index) => <li key={index}>{value}</li>)}</ul>}
            </dd></div>
            <div><dt>Initial direction</dt><dd>{sample.value.identity.initial_direction}</dd></div>
          </dl>
          <h4>Current goal</h4>
          <GoalEvidence {...navigation} goals={sample.value.goals} />
          <h4>Recent experience</h4>
          <p className="quiet">{sample.value.recent_experience.length} shown · {sample.value.retained_record_count} retained</p>
          <ExperienceList {...navigation} experiences={sample.value.recent_experience} />
          {sample.value.latest_decision_id !== null && (
            <p>Latest committed decision <button type="button" className="p3-link" onClick={() => navigation.onDecision(sample.value.latest_decision_id!)}><code>{sample.value.latest_decision_id}</code></button></p>
          )}
          <SourceFile refInfo={ref.shard} />
        </>
      )}
    </section>
  );
}
