// Project-level additions to Evidence's SvelteKit config (Evidence merges this file into its own).
//
// SKU drill-down pages (pages/sku/[sku].md) are not pre-rendered (pages/sku/[sku]/+page.js): at
// medium scale that would be ~1,400 pages and add minutes to every nightly deploy. Instead the build
// writes a single-page-app fallback, 404.html. GitHub Pages serves it for any path that has no
// file, and the app then renders /sku/<SKU> in the browser, querying the same DuckDB-WASM data as
// every other page.
// Clicking a SKU link inside the site never reaches the server at all (client-side navigation).
// See docs/DECISIONS.md.
import adapter from '@sveltejs/adapter-static';

export default {
	kit: {
		adapter: adapter({
			pages: process.env.EVIDENCE_BUILD_DIR ?? './build',
			fallback: '404.html',
			strict: false
		})
	}
};
