/**
 * Entry for the error page (404.html).
 *
 * Mirrors src/pages/legal.ts: the page is complete without JavaScript — the
 * header, the copy, the full route list and every link are in the HTML, which
 * keeps the page readable for people (and review bots) that never run scripts.
 *
 * This module adds exactly one enhancement: it echoes the path that 404'd back
 * into the request line of the terminal panel and onto the retry link. That is
 * the detail a visitor actually wants when a deep link breaks, and it is the
 * only thing on the page that cannot be known at build time.
 *
 * Security note: the echoed value is attacker-controlled (anyone can link to
 * /anything). It is written with `textContent`, never `innerHTML`, so markup in
 * a crafted URL cannot execute — turning the page into a reflected-XSS sink is
 * the classic way a 404 page becomes a vulnerability.
 */
import '../styles/error.css';

/** Longest path echoed back, so a pathological URL cannot flood the card. */
const MAX_ECHOED_PATH = 120;

/**
 * The path to echo, restricted to something safe to put in `textContent` and in
 * an `href`. Only same-origin absolute paths qualify: a protocol-relative value
 * ("//evil.example") also starts with "/" but would send the visitor off-site,
 * and browsers read a backslash the same way, so both are rejected.
 */
function requestedPath(): string {
  const { pathname, search } = window.location;
  const full = `${pathname}${search}`;

  if (!full.startsWith('/') || full.startsWith('//') || full.startsWith('/\\')) {
    return '/';
  }
  return full.length > MAX_ECHOED_PATH ? `${full.slice(0, MAX_ECHOED_PATH)}…` : full;
}

const path = requestedPath();

// Reveal the request line only once it carries a real value (the element ships
// with the `hidden` attribute), and make the retry link re-request what failed.
for (const line of document.querySelectorAll<HTMLElement>('[data-error-request]')) {
  const slot = line.querySelector<HTMLElement>('[data-error-path]');
  if (slot) slot.textContent = path;
  line.hidden = false;
}

const retry = document.querySelector<HTMLAnchorElement>('[data-error-retry]');
if (retry) retry.href = path;
