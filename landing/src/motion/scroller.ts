import Lenis from 'lenis';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

export class Scroller {
  public lenis: Lenis;

  constructor() {
    const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;

    this.lenis = new Lenis({
      duration: isMobile ? 0.7 : 1.1,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      orientation: 'vertical',
      smoothWheel: true,
      wheelMultiplier: 1.0,
      touchMultiplier: 1.0,
      syncTouch: true,
    });

    this.initSync();
  }

  private initSync(): void {
    // Notify ScrollTrigger on every Lenis scroll tick
    this.lenis.on('scroll', ScrollTrigger.update);

    // Bind Lenis animation frame directly to GSAP's ticker
    gsap.ticker.add((time: number) => {
      this.lenis.raf(time * 1000);
    });

    // Zero lag smoothing prevents micro-stutters during heavy computational frames
    gsap.ticker.lagSmoothing(0);
  }

  public scrollTo(target: string | HTMLElement): void {
    this.lenis.scrollTo(target, { offset: -60, duration: 1.2 });
  }
}
