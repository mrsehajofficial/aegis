import './styles/index.css';
import { Scroller } from './motion/scroller';
import { WebGLScene } from './webgl/scene';
import { initPinnedTimelines } from './motion/timeline';
import { TacticalTerminal } from './ui/terminal';
import { TelemetryEngine } from './ui/telemetry';

class AegisLandingApp {
  private scroller: Scroller;
  private scene: WebGLScene;
  private terminal: TacticalTerminal | null = null;
  private telemetry: TelemetryEngine;

  constructor() {
    this.scroller = new Scroller();

    const canvas = document.querySelector<HTMLCanvasElement>('#webgl-canvas')!;
    this.scene = new WebGLScene(canvas);

    this.telemetry = new TelemetryEngine();

    // Initialize pinned scroll animations
    initPinnedTimelines(this.scene);

    // Initialize tactical terminal
    const termContainer = document.querySelector<HTMLElement>('.terminal-window');
    if (termContainer) {
      this.terminal = new TacticalTerminal(termContainer, this.scene, (_cmd: string) => {
        this.telemetry.incrementThreat();
      });
    }

    this.initNavigation();
    this.initMobileMenu();
    this.initCodeCopy();
    this.startRenderLoop();
  }

  private initMobileMenu(): void {
    const toggleBtn = document.querySelector<HTMLButtonElement>('.mobile-toggle-btn');
    const closeBtn = document.querySelector<HTMLButtonElement>('.mobile-close-btn');
    const drawer = document.querySelector<HTMLElement>('.mobile-drawer');
    const overlay = document.querySelector<HTMLElement>('.mobile-drawer-overlay');

    if (!toggleBtn || !drawer || !overlay) return;

    const openMenu = () => {
      drawer.classList.add('open');
      overlay.classList.add('open');
    };

    const closeMenu = () => {
      drawer.classList.remove('open');
      overlay.classList.remove('open');
    };

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
          if (targetEl) {
            setTimeout(() => {
              this.scroller.scrollTo(targetEl);
            }, 220);
          }
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
          if (targetEl) {
            this.scroller.scrollTo(targetEl);
          }
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
          btn.style.color = 'var(--signal-emerald)';
          setTimeout(() => {
            btn.textContent = originalText;
            btn.style.color = '';
          }, 1800);
        }
      });
    });
  }

  private startRenderLoop(): void {
    const tick = () => {
      this.scene.render();
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
}

// Mount application once DOM is ready
window.addEventListener('DOMContentLoaded', () => {
  new AegisLandingApp();
});
