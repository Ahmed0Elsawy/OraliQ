// Writes the home page's HTML into dist/index.html (served at "/") and keeps the plain shell as
// dist/app.html (served for every other route) after the two builds in `npm run build`:
//   vite build --manifest                                   -> dist/ (the app) + dist/.vite/manifest.json
//   vite build --ssr src/entry-prerender.tsx --outDir dist-ssr -> the same app, renderable in Node
// Only "/" is rendered. It is public and identical for every visitor; signed-in pages and
// exam links are never rendered here. index.html's head script and src/main.tsx decide per
// visit whether to adopt this HTML (hydrate) or hide it and draw from scratch.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const ssrDir = path.join(root, "dist-ssr");
const indexPath = path.join(dist, "index.html");
const manifestDir = path.join(dist, ".vite");

const fail = (msg) => { console.error(`prerender: ${msg}`); process.exit(1); };

const { render } = await import(pathToFileURL(path.join(ssrDir, "entry-prerender.js")).href);
// React puts image preload hints in front of a fragment render. They are not part of the tree the
// browser hydrates, and index.html already preloads the hero photos on "/", so they go.
const appHtml = (await render("/")).replace(/^(?:<link rel="preload" as="image"[^>]*\/>)+/, "");
if (appHtml.startsWith("<link")) fail("unexpected tags in front of the rendered app");

// Sanity: the real home page came out (headline, all six section anchors), not a loader or an error
for (const needle of ["أول منصة عربية", 'id="about"', 'id="video"', 'id="integrate"', 'id="contact"', 'id="main"']) {
    if (!appHtml.includes(needle)) fail(`rendered HTML is missing ${needle}`);
}

let html = fs.readFileSync(indexPath, "utf8");
if (!html.includes('<div id="root"></div>')) fail("dist/index.html has no empty #root (already pre-rendered?)");

// Every other route keeps the plain, light shell (vercel.json rewrites them to /app.html), so
// sign-in, dashboards and exam links do not download the home page's markup
fs.writeFileSync(path.join(dist, "app.html"), html);

// The home page's own chunks, so "/" can fetch them alongside the main bundle
const manifest = JSON.parse(fs.readFileSync(path.join(manifestDir, "manifest.json"), "utf8"));
const landingKey = Object.keys(manifest).find((k) => k.endsWith("src/pages/LandingPage.tsx"));
if (!landingKey) fail("LandingPage not found in the build manifest");
const chunks = new Set();
const walk = (key) => {
    const entry = manifest[key];
    if (!entry || entry.isEntry || chunks.has(`/${entry.file}`)) return;
    chunks.add(`/${entry.file}`);
    (entry.imports || []).forEach(walk);
};
walk(landingKey);

const head = `
  <style>
    /* Pre-rendered home page (scripts/prerender.mjs). A visit that cannot adopt it hides it before the first paint. */
    html[data-prerender="skip"] #root[data-prerendered] { display: none; }
    /* Until GSAP takes over, the hero's entrance pieces wait in their hidden starting state, as they do
       without pre-rendering. If the scripts never arrive they show anyway after a few seconds. */
    @media (prefers-reduced-motion: no-preference) {
      html[data-prerender="hydrate"] :is([data-hero-line], [data-hero-fade], [data-piece-enter]) {
        opacity: 0;
        animation: oiq-prerender-reveal 0s 6s forwards;
      }
    }
    @keyframes oiq-prerender-reveal { to { opacity: 1; } }
  </style>
  <script>
    // Home page: fetch its own code alongside the main bundle instead of after it
    if (location.pathname === "/") ${JSON.stringify([...chunks])}.forEach(function (href) {
      var link = document.createElement("link"); link.rel = "modulepreload"; link.href = href; document.head.appendChild(link);
    });
  </script>
</head>`;

html = html.replace("</head>", () => head).replace('<div id="root"></div>', () => `<div id="root" data-prerendered>${appHtml}</div>`);
fs.writeFileSync(indexPath, html);

// Build-only artefacts: the server bundle and the manifest are not part of the site
fs.rmSync(ssrDir, { recursive: true, force: true });
fs.rmSync(manifestDir, { recursive: true, force: true });

console.log(`prerender: "/" written into dist/index.html (${Math.round(appHtml.length / 1024)} KB of markup, ${chunks.size} home chunks preloaded)`);
