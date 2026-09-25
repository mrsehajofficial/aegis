import './styles/index.css';

/**
 * Performance-first bootstrap.
 * Only the stylesheet + this tiny shell (~2 KiB) run before first paint.
 * Heavy motion libs (Lenis + GSAP + ScrollTrigger) and the demo terminal
 * load when near their sections — NEVER on idle timers that compete with
 * LCP on Slow-4G (see PSI critical path: every lazy chunk was racing LCP).
 *
 * Every deferred loader runs EXACTLY ONCE.
 */
class AegisLandingApp {
  private scroller: { scrollTo(t: string | HTMLElement): void } | null = null;
  private telemetry: { incrementThreat(): void } | null = null;
  private motionStarted = false;
  private terminalStarted = false;
  private telemetryStarted = false;

  constructor() {
    this.initNavigation();
    this.initMobileMenu();
    this.initCodeCopy();
    this.deferHeavyModules();
  }

  private deferHeavyModules(): void {
    const reduceMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Load fn the FIRST time `sel` comes within `margin` of the viewport.
    // No idle-timer fallback: firing chunk downloads during the LCP window
    // is what put scroller/ScrollTrigger/timeline/terminal/telemetry on the
    // PSI critical path (2.6s chain) and delayed LCP element render by 2.5s.
    // If the user never scrolls, the chunks never load — by design.
    const whenNear = (
      sel: string,
      margin: string,
      flag: 'motion' | 'terminal' | 'telemetry',
      fn: () => void,
    ) => {
      const run = () => {
        if (flag === 'motion' && this.motionStarted) return;
        if (flag === 'terminal' && this.terminalStarted) return;
        if (flag === 'telemetry' && this.telemetryStarted) return;
        if (flag === 'motion') this.motionStarted = true;
        if (flag === 'terminal') this.terminalStarted = true;
        if (flag === 'telemetry') this.telemetryStarted = true;
        fn();
      };
      const el = document.querySelector(sel);
      // No IntersectionObserver (ancient browser): load immediately —
      // functionality wins over perf there.
      if (!el || !('IntersectionObserver' in window)) { run(); return; }
      const io = new IntersectionObserver(
        (entries) => { if (entries.some((e) => e.isIntersecting)) { io.disconnect(); run(); } },
        { rootMargin: margin },
      );
      io.observe(el);
    };

    whenNear('.runway-section', '800px', 'motion', async () => {
      try {
        const [{ Scroller }, { initPinnedTimelines }] = await Promise.all([
          import('./motion/scroller'),
          import('./motion/timeline'),
        ]);
        if (!this.scroller) this.scroller = new Scroller();
        if (!reduceMotion) initPinnedTimelines();
      } catch { /* motion is progressive enhancement */ }
    });

    whenNear('.sandbox-section', '600px', 'terminal', async () => {
      try {
        const [{ TacticalTerminal }] = await Promise.all([import('./ui/terminal')]);
        const termContainer = document.querySelector<HTMLElement>('.terminal-window');
        if (termContainer && !termContainer.dataset.ready) {
          termContainer.dataset.ready = '1';
          new TacticalTerminal(termContainer, () => { this.telemetry?.incrementThreat(); });
        }
      } catch { /* ignore chunk failure */ }
    });

    whenNear('[data-telemetry="messages"]', '400px', 'telemetry', async () => {
      try {
        const { TelemetryEngine } = await import('./ui/telemetry');
        if (!this.telemetry) this.telemetry = new TelemetryEngine();
      } catch { /* offline — HUD keeps static fallback numbers */ }
    });
  }

  private scrollToEl(targetEl: HTMLElement): void {
    if (this.scroller) {
      try { this.scroller.scrollTo(targetEl); return; } catch { /* native fallback */ }
    }
    targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  private initMobileMenu(): void {
    const toggleBtn = document.querySelector<HTMLButtonElement>('.mobile-toggle-btn');
    const closeBtn = document.querySelector<HTMLButtonElement>('.mobile-close-btn');
    const drawer = document.querySelector<HTMLElement>('.mobile-drawer');
    const overlay = document.querySelector<HTMLElement>('.mobile-drawer-overlay');
    if (!toggleBtn || !drawer || !overlay) return;
    const openMenu = () => { drawer.classList.add('open'); overlay.classList.add('open'); };
    const closeMenu = () => { drawer.classList.remove('open'); overlay.classList.remove('open'); };
    toggleBtn.addEventListener('click', openMenu);
    if (closeBtn) closeBtn.addEventListener('click', closeMenu);
    overlay.addEventListener('click', closeMenu);
    document.querySelectorAll<HTMLAnchorElement>('.mobile-drawer-link').forEach((link) => {
      link.addEventListener('click', (e: MouseEvent) => {
        e.preventDefault();
        closeMenu();
        const targetId = link.getAttribute('href');
        if (targetId && targetId !== '#') {
          const targetEl = document.querySelector<HTMLElement>(targetId);
          if (targetEl) setTimeout(() => this.scrollToEl(targetEl), 220);
        }
      });
    });
  }

  private initNavigation(): void {
    document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener('click', (e: MouseEvent) => {
        e.preventDefault();
        const targetId = anchor.getAttribute('href');
        if (targetId && targetId !== '#') {
          const targetEl = document.querySelector<HTMLElement>(targetId);
          if (targetEl) this.scrollToEl(targetEl);
        }
      });
    });
  }

  private initCodeCopy(): void {
    document.querySelectorAll<HTMLButtonElement>('.copy-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-target');
        const codeElem = targetId ? document.getElementById(targetId) : null;
        if (codeElem) {
          navigator.clipboard.writeText(codeElem.textContent?.trim() || '');
          const originalText = btn.textContent;
          btn.textContent = 'COPIED';
          btn.style.color = 'var(--signal-accent)';
          setTimeout(() => { btn.textContent = originalText; btn.style.color = ''; }, 1800);
        }
      });
    });
  }
}

window.addEventListener('DOMContentLoaded', () => { new AegisLandingApp(); });
