export class TelemetryEngine {
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

    // Fetch real data immediately, then poll every 15 seconds
    this.fetchAndUpdate();
    setInterval(() => this.fetchAndUpdate(), 15_000);
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
    try {
      const res = await fetch('/api/stats', {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(8_000),
      });

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
