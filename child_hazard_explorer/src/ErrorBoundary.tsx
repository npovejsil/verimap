import { Component, type ErrorInfo, type ReactNode } from "react";
import { en } from "./i18n/strings";

interface State {
  error: Error | null;
}

/** Last line of defence against a blank page.
 *
 *  React's answer to a throw during render or in an effect is to unmount the
 *  whole tree, so one failure anywhere takes the header, the indicator list and
 *  every panel with it -- and the reader sees nothing at all, with no hint that
 *  something broke rather than loaded. The map guards WebGL itself; this is for
 *  everything unforeseen. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the detail reachable for whoever is asked "what happened?".
    console.error("Unhandled error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="boundary">
        <div className="panel">
          {/* English only: a hook cannot run here, and if the store is what
              broke, reading the chosen language from it would fail too. */}
          <div className="panel-head"><h2>{en["error.title"]}</h2></div>
          <p className="note">{en["error.body"]}</p>
          <p className="citation">{String(this.state.error?.message || this.state.error)}</p>
          <button className="linkish" onClick={() => location.reload()}>
            {en["error.reload"]}
          </button>
        </div>
      </div>
    );
  }
}
