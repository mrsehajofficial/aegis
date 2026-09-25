import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import type { Connect, Plugin, ViteDevServer } from "vite";
import { compression } from "vite-plugin-compression2";

/** Multi-page build: the landing, the two generated legal documents and the
    static error page. Output paths mirror the inputs, so a host that serves
    dist/404.html for unmatched routes gets the page as built. */
const entry = (name: string) => fileURLToPath(new URL(name, import.meta.url));

/** Name of the error page, at the site root in both source and dist. */
const ERROR_PAGE = "404.html";

/**
 * Serve 404.html — with a genuine 404 status — for unmatched routes in dev and
 * in `vite preview`.
 *
 * Without this, the error page is only ever visible in production, because two
 * Vite defaults hide the 404 path locally:
 *   1. `appType: "spa"` rewrites every unmatched URL to /index.html, answering
 *      200 with the landing page. A typo therefore looks fine locally (and that
 *      soft-404 is exactly what crawlers treat as a duplicate of the homepage).
 *   2. Even in `mpa` mode Vite's own notFoundMiddleware replies with an empty
 *      body, so the page still would not be previewable.
 *
 * Placement: a `configureServer` / `configurePreviewServer` hook that returns a
 * function runs after htmlFallbackMiddleware (which already rewrote /privacy to
 * /privacy.html) and before indexHtmlMiddleware / notFoundMiddleware. Static
 * files, public/ assets and proxied /api requests have all been answered by
 * then, so a request that is still in flight is a genuine miss.
 *
 * The page is read, transformed and sent here rather than by rewriting req.url
 * to /404.html: Vite's indexHtmlMiddleware serves HTML through a helper whose
 * last two lines are `res.statusCode = 200; res.end(content)`, which would turn
 * every miss into a soft 404 (200 status, error content) — the one thing a 404
 * page must not do, since crawlers and uptime checks read the status first.
 *
 * Only navigations (Accept: text/html) are intercepted: answering a missing
 * module or asset fetch with an HTML page would make a broken import look like
 * a parse error instead of a clean 404.
 */
function errorPage(): Plugin {
  const middleware = (
    root: string,
    // Present in dev (injects /@vite/client and transforms module URLs in the
    // HTML); null under `vite preview`, matching how Vite serves .html there.
    transform: ViteDevServer["transformIndexHtml"] | null,
    log: (message: string) => void,
  ): Connect.NextHandleFunction =>
    async function aegisErrorPageMiddleware(req, res, next) {
      if (req.method !== "GET" && req.method !== "HEAD") return next();
      if (!(req.headers.accept ?? "").includes("text/html")) return next();

      const url = (req.url ?? "/").split("?")[0].split("#")[0];
      const candidate = url.endsWith(".html")
        ? join(root, url)
        : join(root, url.endsWith("/") ? join(url, "index.html") : `${url}.html`);
      if (existsSync(candidate)) return next();

      const target = join(root, ERROR_PAGE);
      if (!existsSync(target)) return next();

      try {
        let html = await readFile(target, "utf-8");
        if (transform) html = await transform(`/${ERROR_PAGE}`, html, req.originalUrl ?? url);
        res.statusCode = 404;
        res.setHeader("Content-Type", "text/html; charset=utf-8");
        res.setHeader("Cache-Control", "no-cache");
        log(`404  ${url} -> /${ERROR_PAGE}`);
        res.end(html);
      } catch (error) {
        // Fall through to Vite's own handling rather than masking the failure.
        log(`404  ${url} -> /${ERROR_PAGE} failed: ${String(error)}`);
        next();
      }
    };

  return {
    name: "aegis:error-page",
    configureServer(server) {
      // Post hook: runs once the internal middleware stack exists.
      return () => {
        server.middlewares.use(
          middleware(server.config.root, server.transformIndexHtml, server.config.logger.info),
        );
      };
    },
    configurePreviewServer(server) {
      return () => {
        const dist = resolve(server.config.root, server.config.build.outDir);
        server.middlewares.use(middleware(dist, null, server.config.logger.info));
      };
    },
  };
}

export default defineConfig({
  // This site is a real multi-page app (index, privacy, terms, 404) whose links
  // are all hash anchors, so there is no client-side router to fall back to.
  // Claiming "spa" made the dev server answer any unmatched URL with a 200 copy
  // of index.html; "mpa" mirrors what the static host does and lets the error
  // page plugin below own the miss.
  appType: "mpa",
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: "https://aegistelebot.pythonanywhere.com",
        changeOrigin: true,
        secure: true,
        // Don't let the proxy time out — PythonAnywhere free tier can be slow.
        timeout: 15_000,
        // Prevent Vite's dev-server from caching stale responses.
        headers: { "Cache-Control": "no-cache" },
      },
    },
  },
  build: {
    target: "esnext",
    outDir: "dist",
    // No sourcemaps in production: keeps dist lean (no 668 KiB .map payloads)
    // and avoids shipping source content to clients.
    sourcemap: false,
    rollupOptions: {
      input: {
        main: entry("index.html"),
        privacy: entry("privacy.html"),
        terms: entry("terms.html"),
        // Static error page. Every mainstream host serves a root 404.html for
        // unmatched routes, so this ships beside the other pages rather than in
        // public/ (where it would be copied verbatim, without asset hashing and
        // without the .br/.gz siblings the compression plugins produce).
        error: entry("404.html"),
      },
    },
  },
  plugins: [
    // Serve 404.html for unmatched routes during dev and preview, so the error
    // page is testable before it ships.
    errorPage(),
    // Pre-compress text assets at build time. Wasmer Edge currently serves
    // dist/ bytes verbatim (proven: identical Content-Length for br/gzip
    // requests, no Content-Encoding), so committed .br/.gz siblings are what
    // let capable CDNs/servers negotiate Brotli instead of identity.
    // Brotli-11 (~zopfli-grade for gzip fallback) — best ratio for text.
    compression({ algorithms: ["brotliCompress"], exclude: [/\.(png|jpe?g|webp|avif|mp4|webm|ico|woff2?)$/i], threshold: 1024, deleteOriginalAssets: false }),
    compression({ algorithms: ["gzip"], exclude: [/\.(png|jpe?g|webp|avif|mp4|webm|ico|woff2?)$/i], threshold: 1024, deleteOriginalAssets: false }),
  ],
});

