import { Component, type ErrorInfo, type ReactNode } from "react";

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
          <div className="panel-head"><h2>Something went wrong</h2></div>
          <p className="note">
            This page hit an error it could not recover from. Reloading usually
            clears it; if it happens every time, the message below is the useful
            part of a bug report.
          </p>
          <p className="citation">{String(this.state.error?.message || this.state.error)}</p>
          <button className="linkish" onClick={() => location.reload()}>
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}
