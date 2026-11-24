import { useEffect, useState } from "react";
import { ResidentCost, ResidentMetrics } from "../v2-analysis/ResidentAnalysis.tsx";
import type { Inspection } from "./import.ts";
import type { ShardRef } from "./generated/index.ts";
import type { CallInspection, InspectionShard } from "./generated/shard.ts";

type Seek = (resident: string, tick: number) => void;

function Details({ title, value }: { title: string; value: unknown }) {
  return <details className="p3-source"><summary>{title}</summary>
    <pre>{JSON.stringify(value, null, 2)}</pre></details>;
}

function CallDetails({ call }: { call: CallInspection }) {
  return <section className="p3-debug-card"><h4>{call.call_kind} · {call.outcome}</h4>
    {call.prepared?.candidates.map((candidate, i) => <details key={i} className="p3-source">
      <summary>{i === 0 ? "Full request" : "Candidate " + i}
        {i === call.prepared?.floor_candidate && " · floor"}
        {call.attempts.some(a => a.dispatch.request_sha256 === candidate.wire_sha256) && " · sent"}
        {" · "}{candidate.manifest.tokens_total} tokens</summary>
      {candidate.manifest.sections.map((section, n) => <section key={n}><h5>{section.section}</h5>
        <ol>{section.entries.map((entry, k) => <li key={k}>{entry.source.id} · {entry.tokens} tokens
          <Details title="Source and rendered text" value={{source: entry.source, sha256: entry.sha256,
            text: call.parts.find(p => p.sha256 === entry.sha256)?.text}} /></li>)}</ol></section>)}
      <details><summary>Rebuilt request</summary><pre>{call.requests[i].text}</pre></details>
    </details>)}
    {call.prepared === null && <Details title="Authorized parts" value={call.authorized_parts} />}
    {call.attempts.map(a => <details key={a.dispatch.n} className="p3-source">
      <summary>Attempt {a.dispatch.n + 1} · {a.terminal?.error_class ?? (a.terminal ? "returned" : "interrupted")}</summary>
      <Details title="Usage and latency" value={{tokens: a.terminal?.tokens ?? null,
        latency_ms: a.terminal?.latency_ms ?? null, missing_usage_reason: a.missing_usage_reason}} />
      <Details title="Parsed output" value={a.parsed_output} />
      {a.raw_output_base64 !== null && <pre>{new TextDecoder().decode(Uint8Array.from(atob(a.raw_output_base64), c => c.charCodeAt(0)))}</pre>}
    </details>)}
  </section>;
}

export function MetricRows({ rows }: { rows: Extract<InspectionShard, { instances: unknown }>["instances"] }) {
  return <table><thead><tr><th>Metric</th><th>Recorded value</th><th>Evidence</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.instance_id}><td>{row.metric}</td>
      <td>{row.value ?? row.reason}</td><td><Details title={row.instance_id} value={row.trace} /></td></tr>)}</tbody></table>;
}

function Detail({ inspection, source, seek, follow }: { inspection: Inspection; source: ShardRef; seek: Seek; follow: (ref: ShardRef) => void }) {
  const [value, setValue] = useState<InspectionShard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    inspection.read(source).then(row => { if (live) setValue(row); }, e => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [inspection, source]);
  if (error) return <p role="alert">{error}</p>;
  if (value === null) return <p role="status">Loading evidence…</p>;
  return <InspectionDetail value={value} inspection={inspection} source={source} seek={seek} follow={follow} />;
}

export function InspectionDetail({ value, inspection, source, seek, follow }: {
  value: InspectionShard; inspection: Inspection; source: ShardRef; seek: Seek; follow: (ref: ShardRef) => void;
}) {
  const jump = (actor: string, tick: number) => <button className="p3-link" onClick={() => seek(actor, tick)}>Show {actor} at tick {tick}</button>;
  const revision = (actor: string, version: number) => {
    const ref = inspection.index.revisions.find(r => r.id === actor + ":" + version);
    return ref && <button className="p3-link" onClick={() => follow(ref)}>Open version {version}</button>;
  };
  const packetLink = (id: string) => {
    const ref = inspection.index.deliveries.find(r => r.id === id);
    return ref && <button className="p3-link" onClick={() => follow(ref)}>{id}</button>;
  };
  switch (value.family) {
    case "cost": return <ResidentCost data={value} inspection={inspection} follow={follow}/>;
    case "metrics": return <><ResidentMetrics data={value.resident_analysis} inspection={inspection} follow={follow}/>
      <MetricRows rows={value.instances} />
      {value.content_checks.map(check => <section key={check.instance_id}><Details title={check.check + " · " + check.verdict} value={check} />
        {check.check === "choice_link" && check.sent_fragment_sha256.map(hash =>
          <pre key={hash}>{value.checked_parts.find(part => part.sha256 === hash)?.text}</pre>)}</section>)}</>;
    case "decisions": {
      const delivery = inspection.index.deliveries.find(r => r.id === value.record.telemetry.delivery_id);
      return <>{jump(value.record.resident_id, value.record.tick)}
        {delivery && <button className="p3-link" onClick={() => follow(delivery)}>Open source packet</button>}
        <Details title="Decision, citations and telemetry" value={value.record}/>
        {value.calls.flatMap(c => c.adopted_citations.flatMap(binding => binding.valid.map(cite =>
          <section key={binding.call_id + cite.id}><h4>Cited · {cite.id}</h4>
            {cite.fragments.map((f, i) => <div key={i}>
              <pre>{c.parts.find(p => p.sha256 === f.sha256)?.text}</pre>
              {f.memory_revision && revision(value.record.resident_id, f.memory_revision.store_version)}
            </div>)}</section>)))}
        {value.calls.map(c => <CallDetails key={c.call.call_id} call={c} />)}
        <Details title="Day entries" value={value.entries} />
        {value.outcomes.map(e => <section key={e.event_id}><Details title={e.type + " · " + e.event_id} value={e}/>
          {jump(value.record.resident_id, e.tick)}</section>)}</>;
    }
    case "calls": return <>{jump(value.call.resident_id, value.call.tick)}<CallDetails call={value}/></>;
    case "stores": return <>{inspection.index.stores.filter(r => r.shard === source).map(r =>
      <span key={r.shard.id}>{jump(r.resident_id, r.boundary_tick)}</span>)}<h4>Memory index · {value.period_id}</h4><pre>{value.index_lines.join("\n")}</pre>
      {value.records.map(r => <Details key={r.id} title={r.kind + " · " + r.id + " · " + r.gist} value={r} />)}
      {value.relabel_flags.map(f => <section key={f.flagged.id + ":" + f.store_version}><h4>Possible relabel · {f.flagged.id}</h4>
        <p>Overlapping told records · {f.overlaps.map(r => r.id).join(", ")}</p>{revision(value.resident_id, f.store_version)}</section>)}</>;
    case "revisions": return <>{value.records.map(r => <Details key={r.ref.id + r.ref.content_hash} title={r.ref.id + " · " + r.record.gist} value={r} />)}</>;
    case "deliveries": return <>{jump(value.packet.actor_id, value.packet.observed_tick)}
      {value.entries.map(e => <Details key={e.entry.id} title={e.entry.text} value={e}/>)}
      <Details title="Exact delivered packet" value={value.packet}/></>;
    case "consolidations": return <>{jump(value.record.resident_id, value.record.boundary_tick)}
      <Details title={value.record.period_id + " · " + value.record.outcome} value={value.record}/>
      {value.record.effects.map(op => <section key={op.op_id}><h4>{op.op_id} · {op.produced_id}</h4>
        {op.bindings.map((b, i) => <div key={i}>
          {b.delivery_id && packetLink(b.delivery_id)}
          {b.revisions?.map(ref => <span key={ref.id}>{revision(value.record.resident_id, ref.store_version)}</span>)}
        </div>)}</section>)}
      {value.calls.map(c => <CallDetails key={c.call.call_id} call={c}/>)}</>;
    case "evidence_writes": return <>{value.skill && revision(value.write.owner_id, value.skill.hypothesis.store_version)}
      {value.members.map(m => <div key={m.delivery_id + m.path}>{packetLink(m.delivery_id)} · {m.path}</div>)}
      <Details title="Evidence write and source members" value={value}/></>;
    case "attempts": return <>{value.events.map(e => <section key={e.event_id}><Details title={e.type + " · " + e.event_id} value={e}/>
      {e.actor_id && jump(e.actor_id, e.tick)}</section>)}</>;
    default: return <Details title={source.family} value={value}/>;
  }
}

export default function Viewer({ inspection, seek }: { inspection: Inspection; seek: Seek }) {
  const { index } = inspection;
  const groups = [
    ["Decisions", index.decisions.map(v => v.shard)], ["Calls", index.calls.map(v => v.shard)],
    ["Period boundaries", index.consolidations.map(v => v.shard)], ["Memory browser", index.stores.map(v => v.shard)],
    ["Memory revisions", index.revisions], ["Packet deliveries", index.deliveries], ["Evidence writes", index.evidence_writes],
    ["Analysis", [index.metrics, index.cost, index.time_use, index.attempts]],
  ] as const;
  const [ref, setRef] = useState<ShardRef>(index.decisions[0]?.shard ?? index.metrics);
  const key = (r: ShardRef) => r.parts[0].name;
  return <section className="p3-debug"><div className="p3-selectors"><label>Inspection record
    <select value={key(ref)} onChange={e => {
      const next = groups.flatMap(([, refs]) => refs).find(r => key(r) === e.target.value);
      if (next) setRef(next);
    }}>{groups.map(([label, refs]) => <optgroup key={label} label={label}>{refs.map(r =>
      <option key={key(r)} value={key(r)}>{r.id}</option>)}</optgroup>)}</select></label></div>
    <Detail key={key(ref)} source={ref} inspection={inspection} seek={seek} follow={setRef}/></section>;
}
