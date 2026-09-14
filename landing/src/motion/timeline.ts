import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { WebGLScene } from '../webgl/scene';

gsap.registerPlugin(ScrollTrigger);

// Prevent mobile address bar collapse/expand from jittering ScrollTrigger coordinates
ScrollTrigger.config({
  ignoreMobileResize: true,
});

export function initPinnedTimelines(scene: WebGLScene): void {
  const runway = document.querySelector<HTMLElement>('.runway-section');
  const panels = gsap.utils.toArray<HTMLElement>('.stage-panel');

  if (!runway || panels.length === 0) return;

  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;

  // Master pinned timeline across the runway
  const masterTl = gsap.timeline({
    scrollTrigger: {
      trigger: runway,
      start: 'top top',
      end: 'bottom bottom',
      pin: '.runway-sticky',
      scrub: isMobile ? 0.3 : 0.8,
      anticipatePin: 1,
      onUpdate: (self) => {
        scene.shield.updateScrub(self.progress, self.getVelocity());
      },
    },
  });

  // Stage 1 is initially visible
  gsap.set(panels[0], { opacity: 1, y: 0 });

  // Sequenced stage fade-ins and fade-outs
  panels.forEach((panel, i) => {
    if (i === 0) {
      // Stage 1 fades out as user progresses to Stage 2
      masterTl.to(panel, {
        opacity: 0,
        y: -30,
        duration: 0.8,
        ease: 'power1.inOut',
      }, '+=0.2');
    } else {
      // Current stage fades in
      masterTl.fromTo(
        panel,
        { opacity: 0, y: 30 },
        {
          opacity: 1,
          y: 0,
          duration: 0.8,
          ease: 'power1.out',
          onStart: () => panel.classList.add('active'),
          onReverseComplete: () => panel.classList.remove('active'),
        }
      );

      // If not the final panel, fade it out for the next
      if (i < panels.length - 1) {
        masterTl.to(panel, {
          opacity: 0,
          y: -30,
          duration: 0.8,
          ease: 'power1.inOut',
          onComplete: () => panel.classList.remove('active'),
        }, '+=0.4');
      }
    }
  });
}
