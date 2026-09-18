/// <reference types="vite/client" />

/** The CSP build is the same library with the worker kept out of a blob URL,
 *  so it loads where `worker-src blob:` is disallowed -- which is the case in
 *  a published artifact. It ships no types of its own. */
declare module "maplibre-gl/dist/maplibre-gl-csp" {
  import maplibregl from "maplibre-gl";
  export default maplibregl;
}
