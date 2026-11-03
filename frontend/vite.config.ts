import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/** Public pages that should appear in search results (signed-in pages and exam links never do). */
const PUBLIC_ROUTES = [
    { loc: "/", priority: "1.0", changefreq: "weekly" },
    { loc: "/register", priority: "0.8", changefreq: "monthly" },
    { loc: "/login", priority: "0.5", changefreq: "monthly" },
];

/**
 * SEO: fills the site URL into index.html (canonical, Open Graph, JSON-LD) and writes
 * sitemap.xml + robots.txt at build time, all from one setting: VITE_SITE_URL.
 * Change it once when you move to your own domain.
 */
function seo(siteUrl: string, googleVerify: string): Plugin {
    const base = siteUrl.replace(/\/+$/, "");
    return {
        name: "oraliq-seo",
        transformIndexHtml: {
            order: "pre",
            handler: (html) =>
                html
                    .replaceAll("__SITE_URL__", base)
                    .replace(
                        "<!--__GOOGLE_VERIFY__-->",
                        googleVerify ? `<meta name="google-site-verification" content="${googleVerify}" />` : "",
                    ),
        },
        generateBundle(_opts, bundle) {
            if (this.environment?.config?.build?.ssr) return;
            if ("sitemap.xml" in bundle) return;
            const today = new Date().toISOString().slice(0, 10);
            const urls = PUBLIC_ROUTES.map(
                (r) => `  <url>\n    <loc>${base}${r.loc}</loc>\n    <lastmod>${today}</lastmod>\n    <changefreq>${r.changefreq}</changefreq>\n    <priority>${r.priority}</priority>\n  </url>`,
            ).join("\n");
            this.emitFile({
                type: "asset",
                fileName: "sitemap.xml",
                source: `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
            });
            this.emitFile({
                type: "asset",
                fileName: "robots.txt",
                source: [
                    "User-agent: *",
                    "Allow: /",
                    "# Signed-in pages hold nothing for search engines",
                    "Disallow: /dashboard",
                    "# Exam links carry their token in the URL. They are answered with \"X-Robots-Tag: noindex\"",
                    "# (vercel.json); they are not blocked here, because a blocked URL can still be indexed from",
                    "# a public link and a crawler that may not fetch it never sees the noindex.",
                    "",
                    `Sitemap: ${base}/sitemap.xml`,
                    "",
                ].join("\n"),
            });
        },
    };
}

// https://vitejs.dev/config/
export default defineConfig(({ isSsrBuild, mode }) => {
    const env = loadEnv(mode, __dirname, "VITE_");
    const siteUrl = env.VITE_SITE_URL || "https://oral-iq-vision-nlp-speech-based-sma.vercel.app";
    return {
        plugins: [react(), seo(siteUrl, env.VITE_GOOGLE_SITE_VERIFICATION || "")],
        resolve: {
            alias: {
                "@": path.resolve(__dirname, "./src"),
            },
        },
        build: {
            chunkSizeWarningLimit: 600,
            rollupOptions: isSsrBuild
                ? undefined
                : {
                      output: {
                          manualChunks(id: string) {
                              if (!id.includes("node_modules")) return undefined;
                              if (id.includes("@mediapipe")) return "vendor-vision";
                              if (id.includes("gsap") || id.includes("/motion/") || id.includes("framer-motion") || id.includes("lenis")) {
                                  return "vendor-motion";
                              }
                              if (id.includes("lucide-react")) return "vendor-icons";
                              if (id.includes("react-dom") || id.includes("react-router") || id.includes("/react/")) {
                                  return "vendor-react";
                              }
                              return undefined;
                          },
                      },
                  },
        },
        // Only for the build-time render of the home page (scripts/prerender.mjs): bundle the
        // dependencies into that one-off Node build so it runs without ESM/CommonJS mismatches
        ssr: {
            noExternal: true,
        },
    };
})
