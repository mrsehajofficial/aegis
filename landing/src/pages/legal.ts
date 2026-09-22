/**
 * Entry for the legal pages (privacy.html / terms.html).
 *
 * The documents themselves are rendered at build time by scripts/build-legal.mjs
 * from PRIVACY.md and TERMS.md, so this module only pulls in the site's
 * stylesheets. Deliberately no runtime JavaScript and no fetch: the text is in
 * the HTML, which keeps the pages readable for crawlers and for people (or
 * review bots) with JS disabled.
 */
import '../styles/legal.css';
