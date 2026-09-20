import { useState } from "react";
import type { CrossCheck, Provenance } from "./data/provenance";
import { useT } from "./i18n";

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
  const { t, n } = useT();
  const pct = check.total ? (check.agree / check.total) * 100 : 0;
  return (
    <div className="crosscheck">
      <div className="crosscheck-head">
        <span className={`tag ${check.passed ? "ok" : "warn"}`}>
          {t(check.passed ? "sources.agrees" : "sources.differs")}
        </span>
        <strong>{check.label}</strong>
      </div>
      <p className="note">{check.detail}</p>
      <p className="crosscheck-figure">
        {t("sources.ofTotal", { agree: n(check.agree), total: n(check.total) })}
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
  const { t, n } = useT();

  if (!prov) {
    return (
      <div className="panel">
        <div className="panel-head"><h2>{t("sources.title")}</h2></div>
        <p className="empty">
          {t("sources.missing", { command: "python3 etl/build_provenance.py" })}
        </p>
      </div>
    );
  }

  const here = iso3 ? prov.crosschecks.per_country[iso3] : undefined;

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{t("sources.title")}</h2>
        <button className="linkish" onClick={() => setOpen(!open)}>
          {t(open ? "sources.hide" : "sources.show")}
        </button>
      </div>

      <p className="note">
        {t("sources.summary", {
          units: n(prov.counts.admin2_units),
          areas: n(prov.counts.admin1_areas),
          indicators: prov.counts.indicators,
          countries: prov.counts.countries,
        })}{" "}
        {prov.sources.map((s) => s.name).join(" · ")}
      </p>

      {here && (
        <p className="note">
          {t("sources.scoped", {
            country: countryName ?? iso3 ?? "",
            units: n(here.adm2_units),
            areas: here.adm1_areas,
          })}{" "}
          {here.facet_agrees
            ? t("sources.scopedAgree", { n: here.facet_cells })
            : t("sources.scopedDiffer")}
          {here.version_mismatch > 0 &&
            ` ${here.version_mismatch} unit(s) cite a superseded boundary version.`}
          {here.unnamed > 0 && ` ${here.unnamed} unit(s) have no published name.`}
        </p>
      )}

      {open && (
        <div className="source-body">
          <h3>{t("sources.heading")}</h3>
          <table className="table">
            <thead>
              <tr>
                <th>{t("sources.colSource")}</th><th>{t("sources.colProvides")}</th>
                <th>{t("sources.colAccess")}</th><th>{t("sources.colLicence")}</th>
                <th>{t("sources.colRetrieved")}</th>
              </tr>
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

          <h3>{t("sources.selected")}</h3>
          <ul className="crosscheck-list">
            {prov.query.meaning.map((m) => <li key={m}>{m}</li>)}
          </ul>

          <h3>{t("sources.fields")}</h3>
          <table className="table">
            <thead><tr><th>{t("sources.colShown")}</th><th>{t("sources.colField")}</th></tr></thead>
            <tbody>
              {prov.fields.map((f) => (
                <tr key={f.shown}>
                  <td>{f.shown}</td>
                  <td><code>{f.field}</code></td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>{t("sources.applied")}</h3>
          <ul className="crosscheck-list">
            {prov.transformations.map((t) => <li key={t}>{t}</li>)}
          </ul>

          <h3>{t("sources.checks")}</h3>
          <p className="note">{t("sources.checksNote")}</p>
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

          <p className="note">{t("sources.untranslated")}</p>

          <h3>{t("sources.cite")}</h3>
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
            {t(copied ? "sources.copied" : "sources.copy")}
          </button>
        </div>
      )}
    </div>
  );
}
