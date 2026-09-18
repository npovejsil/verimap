import { useState } from "react";
import { GOAL_COLORS, GOAL_SHORT } from "./sdg";
import { useStore, type CatalogNode } from "./store";

function Branch({
  node,
  depth,
  names,
}: {
  node: CatalogNode;
  depth: number;
  names: Record<string, string>;
}) {
  const [open, setOpen] = useState(depth < 1);
  const setVariable = useStore((s) => s.setVariable);
  const active = useStore((s) => s.variable);
  const children = node.c ?? [];
  const variables = node.v ?? [];
  const expandable = children.length > 0 || variables.length > 0;

  return (
    <div className="branch" style={{ marginLeft: depth ? 10 : 0 }}>
      {expandable ? (
        <button className="branch-toggle" onClick={() => setOpen(!open)}>
          <span className="caret">{open ? "−" : "+"}</span>
          {node.n}
        </button>
      ) : (
        <span className="branch-leaf">{node.n}</span>
      )}
      {open && (
        <>
          {variables.map((dcid) => (
            <button
              key={dcid}
              className={`variable ${active === dcid ? "active" : ""}`}
              onClick={() => setVariable(dcid, names[dcid] ?? dcid)}
              title={dcid}
            >
              {names[dcid] ?? dcid}
            </button>
          ))}
          {children.map((child) => (
            <Branch key={child.d} node={child} depth={depth + 1} names={names} />
          ))}
        </>
      )}
    </div>
  );
}

export default function GoalNav() {
  const catalog = useStore((s) => s.catalog);
  const openGoal = useStore((s) => s.openGoal);
  const setOpenGoal = useStore((s) => s.setOpenGoal);
  if (!catalog) return <p className="empty">Loading catalog…</p>;

  return (
    <div className="goals">
      {catalog.goals.map((goal) => {
        const n = goal.g!;
        const on = openGoal === n;
        return (
          <div key={goal.d} className="goal">
            <button
              className={`goal-chip ${on ? "open" : ""}`}
              style={{ borderLeftColor: GOAL_COLORS[n] }}
              onClick={() => setOpenGoal(on ? null : n)}
            >
              <span className="goal-num" style={{ background: GOAL_COLORS[n] }}>
                {n}
              </span>
              <span className="goal-name">{GOAL_SHORT[n]}</span>
            </button>
            {on && (
              <div className="goal-body">
                {(goal.c ?? []).map((child) => (
                  <Branch key={child.d} node={child} depth={0} names={catalog.names} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
