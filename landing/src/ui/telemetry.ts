export class TelemetryEngine {
  private messagesScreened: number = 1489240;
  private threatsBlocked: number = 34912;
  private latencyMs: number = 18;
  private integrity: number = 99.98;

  private msgElem: HTMLElement | null;
  private threatElem: HTMLElement | null;
  private latencyElem: HTMLElement | null;
  private integrityElem: HTMLElement | null;

  constructor() {
    this.msgElem = document.querySelector('[data-telemetry="messages"]');
    this.threatElem = document.querySelector('[data-telemetry="threats"]');
    this.latencyElem = document.querySelector('[data-telemetry="latency"]');
    this.integrityElem = document.querySelector('[data-telemetry="integrity"]');

    this.render();
    this.startHeartbeat();
  }

  public incrementThreat(): void {
    this.threatsBlocked += 1;
    this.messagesScreened += 1;
    this.render();
  }

  private startHeartbeat(): void {
    // Subtle live tick simulating high-frequency group traffic
    setInterval(() => {
      this.messagesScreened += Math.floor(Math.random() * 8) + 3;
      if (Math.random() > 0.65) {
        this.threatsBlocked += 1;
      }
      this.latencyMs = 16 + Math.floor(Math.random() * 5);
      this.render();
    }, 2400);
  }

  private render(): void {
    if (this.msgElem) {
      this.msgElem.textContent = this.messagesScreened.toLocaleString();
    }
    if (this.threatElem) {
      this.threatElem.textContent = this.threatsBlocked.toLocaleString();
    }
    if (this.latencyElem) {
      this.latencyElem.textContent = `${this.latencyMs}ms`;
    }
    if (this.integrityElem) {
      this.integrityElem.textContent = `${this.integrity.toFixed(2)}%`;
    }
  }
}
