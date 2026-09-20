import { useState } from "react";
import type { CrossCheck, Provenance } from "./data/provenance";

/** A citation a reader can paste, dated to the extraction rather than to today. */
function citation(prov: Provenance): string {
  const gchd = prov.sources.find((s) => s.id === "gchd");
  const geo = prov.sources.find((s) => s.id === "georepo");
  const day = (stamp?: string | null) => (stamp ? stamp.slice(0, 10) : "undated");
  return [
    `UNICEF. Global Child Hazard Database (reference period ${gchd?.reference_period ?? "2025"}).`,
    `Extracted ${day(gchd?.extracted)}. ${gchd?.licence ?? ""}`,
    `Boundaries: UNICEF GeoRepo, ${geo?.licence ?? ""}, retrieved ${day(geo?.extracted)}.`,
    `Prepared with Child Hazard Explorer; provenance generated ${day(prov.generated)}.`,
  ].join(" ");
}

function Check({ check, scope }: { check: CrossCheck; scope?: string }) {
  const pct = check.total ? (check.agree / check.total) * 100 : 0;
  return (
    <div className="crosscheck">
      <div className="crosscheck-head">
        <span className={`tag ${check.passed ? "ok" : "warn"}`}>
          {check.passed ? "agrees" : "differs"}
        </span>
        <strong>{check.label}</strong>
      </div>
      <p className="note">{check.detail}</p>
      <p className="crosscheck-figure">
        {check.agree.toLocaleString()} of {check.total.toLocaleString()}
        {check.total ? ` (${pct.toFixed(pct > 99.9 && pct < 100 ? 3 : 1)}%)` : ""}
        {scope && <span className="crosscheck-scope"> · {scope}</span>}
      </p>
      {check.offenders.length > 0 && (
        <ul className="crosscheck-list">
          {check.offenders.map((o, i) => (
            <li key={i}>
              {o.iso3}
              {o.indicator ? ` · ${o.indicator}` : ""}
              {o.units !== undefined ? ` — ${o.units.toLocaleString()} units` : ""}
              {o.facet !== undefined && o.sum !== undefined
                ? ` — ${o.facet.toLocaleString()} vs ${o.sum.toLocaleString()}`
                : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Where the numbers come from, and where the sources disagree.
 *
 *  Everything rendered here is read from `provenance.json`, which the ETL
 *  computes from the artifacts -- so this panel cannot claim something the
 *  shipped data does not support. Collapsed by default: it is for the reader
 *  who wants to check a figure, not a permanent fixture. */
export default function SourcePanel({
  prov,
  iso3,
  countryName,
}: {
  prov: Provenance | null;
  iso3: string | null;
  countryName?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!prov) {
    return (
      <div className="panel">
        <div className="panel-head"><h2>Sources &amp; lineage</h2></div>
        <p className="empty">
          Provenance was not built — run <code>python3 etl/build_provenance.py</code>.
        </p>
      </div>
    );
  }

  const here = iso3 ? prov.crosschecks.per_country[iso3] : undefined;

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Sources &amp; lineage</h2>
        <button className="linkish" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </button>
      </div>

      <p className="note">
        {prov.counts.admin2_units.toLocaleString()} admin-2 units ·{" "}
        {prov.counts.admin1_areas.toLocaleString()} admin-1 areas ·{" "}
        {prov.counts.indicators} indicators · {prov.counts.countries} countries.{" "}
        {prov.sources.map((s) => s.name).join(" and ")}.
      </p>

      {here && (
        <p className="note">
          <strong>{countryName ?? iso3}:</strong> {here.adm2_units.toLocaleString()} admin-2
          units in {here.adm1_areas} admin-1 areas.{" "}
          {here.facet_agrees
            ? `Country totals match the sum of their records across all ${here.facet_cells} indicators.`
            : "Country totals do not match the sum of their records."}
          {here.version_mismatch > 0 &&
            ` ${here.version_mismatch} unit(s) cite a superseded boundary version.`}
          {here.unnamed > 0 && ` ${here.unnamed} unit(s) have no published name.`}
        </p>
      )}

      {open && (
        <div className="source-body">
          <h3>Sources</h3>
          <table className="table">
            <thead>
              <tr><th>Source</th><th>Provides</th><th>Access</th><th>Licence</th><th>Retrieved</th></tr>
            </thead>
            <tbody>
              {prov.sources.map((s) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td>{s.provides}</td>
                  <td>{s.access}</td>
                  <td>{s.licence}</td>
                  <td>{s.extracted?.slice(0, 10) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Which records were selected</h3>
          <ul className="crosscheck-list">
            {prov.query.meaning.map((m) => <li key={m}>{m}</li>)}
          </ul>

          <h3>Where each number comes from</h3>
          <table className="table">
            <thead><tr><th>Shown as</th><th>Field in the source</th></tr></thead>
            <tbody>
              {prov.fields.map((f) => (
                <tr key={f.shown}>
                  <td>{f.shown}</td>
                  <td><code>{f.field}</code></td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>What was done to it</h3>
          <ul className="crosscheck-list">
            {prov.transformations.map((t) => <li key={t}>{t}</li>)}
          </ul>

          <h3>Cross-checks</h3>
          <p className="note">
            Figures with two independent derivations, compared. These are computed
            when the data is built, not asserted here.
          </p>
          {prov.crosschecks.checks.map((c) => (
            <Check
              key={c.id}
              check={c}
              scope={
                c.id === "facet_vs_rows" && here
                  ? `${countryName ?? iso3}: ${here.facet_agrees ? "agrees" : "differs"}`
                  : undefined
              }
            />
          ))}

          <h3>Cite this</h3>
          <p className="citation">{citation(prov)}</p>
          <button
            className="linkish"
            onClick={() => {
              navigator.clipboard?.writeText(citation(prov)).then(
                () => { setCopied(true); setTimeout(() => setCopied(false), 2000); },
                () => setCopied(false),
              );
            }}
          >
            {copied ? "Copied" : "Copy citation"}
          </button>
        </div>
      )}
    </div>
  );
}
