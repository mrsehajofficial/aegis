export class TelemetryEngine {
  /** Absolute API origin — the Vite dev proxy only exists locally, so
      production (Wasmer static hosting) must call PythonAnywhere directly.
      Relative '/api/stats' 404s on Wasmer static_web_server (see deploy logs:
      every poll → WARN error_page status=404), then retries every 10s forever.
      Direct cross-origin fetch works — the endpoint sends CORS `*`. */
  private static readonly STATS_URL =
    'https://aegistelebot.pythonanywhere.com/api/stats';
  private messagesScreened: number = 0;
  private threatsBlocked: number = 0;
  private latencyMs: number = 0;
  private uptimePct: number = 0;

  private msgElem: HTMLElement | null;
  private threatElem: HTMLElement | null;
  private latencyElem: HTMLElement | null;
  private integrityElem: HTMLElement | null;

  // Whether we ever got a successful API response
  private apiReachable: boolean = false;
  // Fallback simulation baseline (used only if API never responds)
  private simMessages: number = 1489240;
  private simThreats: number = 34912;

  constructor() {
    this.msgElem = document.querySelector('[data-telemetry="messages"]');
    this.threatElem = document.querySelector('[data-telemetry="threats"]');
    this.latencyElem = document.querySelector('[data-telemetry="latency"]');
    this.integrityElem = document.querySelector('[data-telemetry="integrity"]');

    // Show dimmed state while loading
    this.setLoadingState();

    // Reduced interval: fetch real data immediately, then poll every 10 seconds
    this.fetchAndUpdate();
    setInterval(() => this.fetchAndUpdate(), 10_000);
  }

  /** Called from terminal when a command triggers an intercepted event. */
  public incrementThreat(): void {
    this.threatsBlocked += 1;
    this.messagesScreened += 1;
    this.render(this.messagesScreened, this.threatsBlocked, this.latencyMs, this.uptimePct);
  }

  // ── Private ────────────────────────────────────────────────────────────────

  private setLoadingState(): void {
    [this.msgElem, this.threatElem, this.latencyElem, this.integrityElem].forEach((el) => {
      if (el) el.style.opacity = '0.4';
    });
  }

  private clearLoadingState(): void {
    [this.msgElem, this.threatElem, this.latencyElem, this.integrityElem].forEach((el) => {
      if (el) el.style.opacity = '';
    });
  }

  private async fetchAndUpdate(): Promise<void> {
    // Fast path: the HUD already ships with credible static numbers in HTML.
    // Only hit the network when the telemetry strip is actually visible —
    // the constructor fires at page load (LCP window) but the HUD is
    // below the fold, so an immediate fetch just contends with LCP for
    // Slow-4G bandwidth (PSI: /api/stats 2.6s cold-start on critical path).
    // requestIdleCallback keeps it off the main thread even after visible.
    if (!this.isHudVisible()) {
      await new Promise<void>((resolve) => {
        if (!('IntersectionObserver' in window)) {
          setTimeout(() => resolve(), 5000);
          return;
        }
        const io = new IntersectionObserver(
          (entries) => {
            if (entries.some((e) => e.isIntersecting)) {
              io.disconnect();
              resolve();
            }
          },
          { rootMargin: '400px' },
        );
        const anchor = this.msgElem ?? document.body;
        io.observe(anchor);
        // Safety: never leave the HUD on stale numbers longer than 15s.
        setTimeout(() => {
          io.disconnect();
          resolve();
        }, 15000);
      });
    }
    const runFetch = async () => {
      await this.fetchOnce();
    };
    const w = window as Window & { requestIdleCallback?(c: () => void, o?: object): void };
    if (typeof w.requestIdleCallback === 'function') {
      await new Promise<void>((resolve) => {
        w.requestIdleCallback!(() => resolve(), { timeout: 8000 });
      });
    }
    await runFetch();
  }

  private isHudVisible(): boolean {
    const el = this.msgElem;
    if (!el || !('IntersectionObserver' in window)) return false;
    const r = el.getBoundingClientRect();
    return r.top < window.innerHeight * 1.5 && r.bottom > -400;
  }

  private async fetchOnce(): Promise<void> {
    try {
      // Absolute URL: the Vite dev proxy (/api → pythonanywhere) only runs
      // on localhost. Wasmer serves static files with no proxy, so a
      // relative '/api/stats' would hit aegis.wasmer.app/api/stats (404).
      // Direct cross-origin fetch works — the endpoint sends CORS `*`.
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 6000);
      let res: Response;
      try {
        res = await fetch(TelemetryEngine.STATS_URL, {
          method: 'GET',
          mode: 'cors',
          headers: { Accept: 'application/json' },
          cache: 'no-store',
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: {
        messages_screened: number;
        spam_intercepted: number;
        avg_latency_ms: number;
        uptime_pct: number;
      } = await res.json();

      this.apiReachable = true;
      this.clearLoadingState();

      // Animate from previous stored values → new real values
      this.animateTo(
        this.messagesScreened || data.messages_screened,
        data.messages_screened,
        this.threatsBlocked || data.spam_intercepted,
        data.spam_intercepted,
        data.avg_latency_ms,
        data.uptime_pct,
      );
    } catch {
      // API unreachable — subtle local simulation so numbers don't freeze on screen
      if (!this.apiReachable) {
        this.runFallbackTick();
      }
    }
  }

  /** Subtle local tick used only when /api/stats is unreachable (dev / offline). */
  private runFallbackTick(): void {
    this.simMessages += Math.floor(Math.random() * 7) + 2;
    if (Math.random() > 0.6) this.simThreats += 1;
    const lat = 16 + Math.floor(Math.random() * 6);
    this.render(this.simMessages, this.simThreats, lat, 99.98);
  }

  /** Smoothly tween all four counters simultaneously over ~800 ms using rAF. */
  private animateTo(
    fromMsg: number,
    toMsg: number,
    fromThreat: number,
    toThreat: number,
    toLatency: number,
    toUptime: number,
  ): void {
    const DURATION = 800;
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(elapsed / DURATION, 1);
      // Ease-out cubic
      const ease = 1 - Math.pow(1 - t, 3);

      const curMsg = Math.round(fromMsg + (toMsg - fromMsg) * ease);
      const curThreat = Math.round(fromThreat + (toThreat - fromThreat) * ease);

      this.render(curMsg, curThreat, toLatency, toUptime);

      if (t < 1) {
        requestAnimationFrame(tick);
      } else {
        // Lock in final authoritative values
        this.messagesScreened = toMsg;
        this.threatsBlocked = toThreat;
        this.latencyMs = toLatency;
        this.uptimePct = toUptime;
      }
    };

    requestAnimationFrame(tick);
  }

  private render(msgs: number, threats: number, latency: number, uptime: number): void {
    if (this.msgElem) {
      this.msgElem.textContent = msgs.toLocaleString();
    }
    if (this.threatElem) {
      this.threatElem.textContent = threats.toLocaleString();
    }
    if (this.latencyElem) {
      this.latencyElem.textContent = `${Math.round(latency)}ms`;
    }
    if (this.integrityElem) {
      this.integrityElem.textContent = `${uptime.toFixed(2)}%`;
    }
  }
}
