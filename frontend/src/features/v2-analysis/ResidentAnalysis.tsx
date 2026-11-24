import { useState } from "react";
import type { Inspection } from "../v2-inspection/import.ts";
import type { ShardRef } from "../v2-inspection/generated/index.ts";
import type { AnalysisLink, Cost, ExposureCall, ResidentAnalysis } from "../v2-inspection/generated/shard.ts";

type Navigation = { inspection: Inspection; follow: (ref: ShardRef) => void };

function Source({ item, nav }: { item: AnalysisLink; nav: Navigation }) {
  const [evidence, showEvidence] = useState<string | null>(null);
  const family = nav.inspection.index[item.family];
  const refs = Array.isArray(family) ? family : [family];
  const entry = refs.find(r => ("shard" in r ? r.shard : r).id === item.id);
  if (!entry) return <span>{item.label} (source unavailable)</span>;
  const ref = "shard" in entry ? entry.shard : entry;
  if (item.member) {
    async function openMember() {
      try {
        const shard = await nav.inspection.read(ref);
        const source = shard.family === "attempts" ? shard.events.find(e => e.event_id === item.member) :
          shard.family === "revisions" ? shard.records.find(r => r.ref.content_hash === item.member) : null;
        showEvidence(source ? JSON.stringify(source, null, 2) : "Source member unavailable.");
      } catch (error) { showEvidence(String(error)); }
    }
    return <div><button className="p3-link" onClick={() => void openMember()}>{item.label}</button>
      {evidence !== null && <><pre>{evidence}</pre><button onClick={() => nav.follow(ref)}>Open full record</button></>}</div>;
  }
  return <button className="p3-link" onClick={() => nav.follow(ref)}>{item.label}</button>;
}

function CallLink({ id, nav }: { id: string; nav: Navigation }) {
  return <Source item={{ family: "calls", id, label: id }} nav={nav} />;
}

function Evidence({ row, nav }: { row: { instance_id: string; trace: string[]; links: AnalysisLink[] }; nav: Navigation }) {
  return <div>{row.links.map(l => <Source key={l.family + l.id + l.label} item={l} nav={nav} />)}
    <details><summary>Evidence IDs · {row.instance_id}</summary><ul>{row.trace.map(id => <li key={id}>{id}</li>)}</ul></details></div>;
}

function Stages({ stages, nav }: { stages: ExposureCall[]; nav: Navigation }) {
  return <ul>{stages.map(c => <li key={c.call_id}>{c.call_kind} · {c.outcome} · <CallLink id={c.call_id} nav={nav}/>
    {c.retrieved.length > 0 && <div>Retrieved · {c.retrieved.join(", ")}</div>}
    {c.omitted.map((r, i) => <div key={i}>Guard omitted {r.kind} · {r.id} · {r.version}</div>)}</li>)}</ul>;
}

export function ResidentMetrics({ data, ...nav }: Navigation & { data: ResidentAnalysis }) {
  const [actor, select] = useState(data.uses[0]?.resident_id ?? data.skills[0]?.resident_id ?? data.residents[0]?.resident_id ?? "");
  const resident = data.residents.find(r => r.resident_id === actor);
  if (!resident) return <p>No recorded residents.</p>;
  return <section aria-label="Resident analysis">
    <h3>Resident analysis · {data.packs.join(", ")}</h3>
    <label>Resident <select value={actor} onChange={e => select(e.target.value)}>
      {data.residents.map(r => <option key={r.resident_id}>{r.resident_id}</option>)}</select></label>
    <h4>Skill hypotheses · {data.packs.join(", ")}</h4>
    <p>Self-found skills · {resident.self_found_skills}. Accuracy distribution · {resident.accuracy_distribution.join(", ") || "no scored hypotheses"}.</p>
    {data.skills.filter(r => r.resident_id === actor).map(s => <details key={s.instance_id}>
      <summary>{s.revision.id} · {s.origin} · accuracy {s.accuracy ?? "unavailable"}</summary>
      <p>Creator · {s.creator_call ?? "supplied hypothesis"}</p><pre>{s.prediction}</pre>
      <p>Sources · {s.sources.join(", ")}</p>
      <p>Attempts · {s.attempts ?? "unknown"}. Matched expected · {s.matched_expected ?? "unknown"}.
        Watched · {s.watched}. Supplied attempts · {s.supplied_attempts}. Fallback attempts · {s.fallback_attempts}.</p>
      {s.reason && <p>{s.reason}</p>}<Evidence row={s} nav={nav}/></details>)}
    <h4>First successful choices</h4>
    {data.learning.filter(r => r.resident_id === actor).map(r => <details key={r.instance_id}>
      <summary>{r.rule_id} · {r.flags.join(", ") || r.reason}</summary><p>{r.turn_id} · {r.period_id}</p>
      {r.unchecked_utterances.length > 0 && <p>Unchecked speech · {r.unchecked_utterances.join(", ")}</p>}
      {r.reason && <p>{r.reason}</p>}<Evidence row={r} nav={nav}/></details>)}
    <h4>Memory at decision dispatch</h4>
    <p>Later-period uses · {resident.later_period_uses}. Prior-day dispatches · {resident.prior_day_uses}.
      Unknown creation periods · {resident.unknown_use_origins}.</p>
    {data.uses.filter(r => r.resident_id === actor).map(r => <details key={r.instance_id}>
      <summary>{r.revision.id} · {r.kind} · day {r.created_day ?? "unknown"} → {r.day}</summary>
      <p>{r.created_period ?? "Unknown waking period"} → {r.period_id}. Store v{r.before_version} → v{r.after_version}.</p>
      <p>{r.cited ? "Cited by the adopted decision" : "Dispatched without an adopted citation"}</p>
      <Evidence row={r} nav={nav}/></details>)}
    <h4>Guard exposure</h4>
    {data.periods.filter(r => r.resident_id === actor).map(r => <details key={r.period_id}>
      <summary>{r.period_id} · {r.exposed ? "guard exposed" : "no recorded guard exposure"}</summary>
      <p>Exposed turns · {r.exposed_turns.join(", ") || "none"}.</p>
      {r.inherited_from.map(id => <Source key={id} item={{family:"consolidations",id,label:"Supplier " + id}} nav={nav}/>)}
      <Stages stages={r.calls} nav={nav}/></details>)}
    {data.consolidations.filter(r => r.resident_id === actor).map(r => <details key={r.attempt_id}>
      <summary>Consolidation · {r.period_id} · {r.outcome}</summary>
      <Source item={{family:"consolidations",id:r.attempt_id,label:r.attempt_id}} nav={nav}/>
      <p>Supplies · {r.supplies_period ?? "no recorded supplier relationship"}</p><Stages stages={r.calls} nav={nav}/></details>)}
  </section>;
}

const show = (n: number | null | undefined) => n ?? "unknown";

export function ResidentCost({ data, ...nav }: Navigation & { data: Cost }) {
  return <section aria-label="Context cost"><h3>Context and cost</h3>
    <p>Ledger · {data.ledger_mode ?? "unavailable"} {data.ledger_sha256}</p>
    {data.days?.map(d => <section key={d.resident_id + d.day}><h4>{d.resident_id} · day {d.day}</h4>
      <p>{d.calls} calls · {d.attempts} dispatches · {d.fallback_turns} fallback turns of {d.turns} (rate {d.fallback_rate ?? "undefined"}).</p>
      <p>Input / output · {show(d.input_tokens)} / {show(d.output_tokens)} tokens.
        Cache hit / miss · {show(d.cache_hit)} / {show(d.cache_miss)}. Latency · {show(d.latency_ms)} ms.
        Paid · {show(d.paid_pico_cny)} pico-CNY.</p>
      <p>Input · {show(d.input_pico_cny)}. Output · {show(d.output_pico_cny)}. Unassignable · {show(d.unassignable_pico_cny)} pico-CNY.</p>
      {data.turns?.filter(t => t.resident_id === d.resident_id && t.day === d.day).map(t => <div key={t.turn_id}>
        <Source item={{family:"decisions",id:t.turn_id,label:"Decision " + t.turn_id}} nav={nav}/>
        {t.awake_ticks} awake ticks · fatigue {t.fatigue_band ?? "unknown"} · {t.fallback.used ? "fallback · " + t.fallback.reason : "no fallback"}
      </div>)}
    </section>)}
    <p>Section estimates allocate the input charge in proportion to measured tokens. The framing row includes the difference between standalone section counts and the framed request.</p>
    {data.contexts?.map(r => {
      const usage = data.attempts.find(a => a.call_id === r.call_id && a.n === r.n);
      return <details key={r.call_id + "/" + r.n}><summary>{r.resident_id} · day {r.day} · tick {r.tick} · {r.call_kind}
        {" · "}{r.n === null ? "no dispatch" : "attempt " + r.n} · {r.attempt_outcome}</summary>
        <CallLink id={r.call_id} nav={nav}/><p>{r.period_id} · {r.turn_id} · {r.outcome}</p>
        <p>Full / sent · {show(r.full_tokens)} / {show(r.sent_tokens)} tokens. Pressure · {r.pressure_band ?? "unavailable"}.
          Day log · {show(r.full_log_tokens)} tokens. Growth · {show(r.log_growth_tokens)}.</p>
        <p>Input / output · {show(usage?.input)} / {show(usage?.output)} tokens. Cache hit / miss · {show(usage?.cache_hit)} / {show(usage?.cache_miss)}.
          Latency · {show(usage?.latency_ms)} ms. {usage?.missing_usage_reason}</p>
        {r.omitted.map((o, i) => <div key={i}>Guard omitted {o.kind} · {o.id} · {o.version}</div>)}
        <table><thead><tr><th>Sent section</th><th>Measured tokens</th><th>Share</th><th>Estimated input (pico-CNY)</th></tr></thead>
          <tbody>{r.sections.map(s => <tr key={s.section}><td>{s.section}</td><td>{s.tokens}</td><td>{s.share}</td><td>{show(s.estimated_input_pico_cny)}</td></tr>)}</tbody></table>
        <p>Input · {show(r.input_pico_cny)}. Output · {show(r.output_pico_cny)}. Unassignable · {show(r.unassignable_pico_cny)}.
          Total paid · {show(r.paid_pico_cny)} pico-CNY. {r.cost_reason}</p>
      </details>;
    })}
    {!data.contexts && <pre>{JSON.stringify(data.attempts, null, 2)}</pre>}
  </section>;
}
