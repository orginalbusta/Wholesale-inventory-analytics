// The per-SKU pages (../[sku].md) are rendered in the browser on demand instead of at build time:
// pre-rendering ~1,400 of them at medium scale would add minutes to every deploy. GitHub Pages
// serves the SPA fallback (404.html, see ../../../svelte.config.js) for these paths.
export const prerender = false;
