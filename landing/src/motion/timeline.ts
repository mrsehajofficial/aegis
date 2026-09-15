import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

// Prevent mobile address bar collapse/expand from jittering ScrollTrigger coordinates
ScrollTrigger.config({
  ignoreMobileResize: true,
});

/**
 * Mirror-move the stage video so it slides to the empty side of the runway:
 * - content on the RIGHT → the video glides to the LEFT
 * - content on the LEFT  → the video glides to the RIGHT
 * - content in the CENTER (space in the middle) → the video rests CENTER
 */
function positionFromPanel(panel: HTMLElement): string {
  if (panel.classList.contains('panel-right')) return 'video-left';
  if (panel.classList.contains('panel-left')) return 'video-right';
  return 'video-center';
}

export function initPinnedTimelines(): void {
  const runway = document.querySelector<HTMLElement>('.runway-section');
  const panels = gsap.utils.toArray<HTMLElement>('.stage-panel');

  if (!runway || panels.length === 0) return;

  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;

  // Stage video: starts paused and is scrubbed by the pinned scroll progress below,
  // so it only "plays" while the user is scrolling the runway.
  const stageVideo = runway.querySelector<HTMLVideoElement>('.stage-video video');
  if (stageVideo) {
    stageVideo.pause();
  }

  // Keep track of which stage is currently being presented
  let currentIndex = 0;

  const moveVideo = (panel: HTMLElement) => {
    const video = runway.querySelector<HTMLElement>('.stage-video');
    if (video) {
      video.dataset.pos = positionFromPanel(panel);
    }
  };

  // Master pinned timeline across the runway
  const masterTl = gsap.timeline({
    scrollTrigger: {
      trigger: runway,
      start: 'top top',
      end: 'bottom bottom',
      pin: '.runway-sticky',
      scrub: isMobile ? 0.3 : 0.8,
      anticipatePin: 1,
    },
  });

  const st = masterTl.scrollTrigger as ScrollTrigger | undefined;

  // Scroll-scrubbed playback: video frame follows the pinned progress 1:1.
  if (st && stageVideo) {
    gsap.ticker.add(() => {
      if (st.isActive && stageVideo.readyState >= 2 && stageVideo.duration > 0) {
        const target = stageVideo.duration * gsap.utils.clamp(0, 1, st.progress);
        if (Math.abs(stageVideo.currentTime - target) > 0.02) {
          stageVideo.currentTime = target;
        }
      }
    });
  }

  // Stage 1 is initially visible
  gsap.set(panels[0], { opacity: 1, y: 0 });
  moveVideo(panels[0]);

  // Sequenced stage fade-ins and fade-outs
  panels.forEach((panel, i) => {
    if (i === 0) {
      // Stage 1 fades out as user progresses to Stage 2
      masterTl.to(panel, {
        opacity: 0,
        y: -30,
        duration: 0.8,
        ease: 'power1.inOut',
        onReverseComplete: () => {
          currentIndex = 0;
          moveVideo(panels[0]);
        },
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
          onStart: () => {
            currentIndex = i;
            panel.classList.add('active');
            moveVideo(panel);
          },
          onReverseComplete: () => {
            panel.classList.remove('active');
            if (i > 0) {
              currentIndex = i - 1;
              moveVideo(panels[currentIndex]);
            }
          },
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

  // Re-evaluate the video position when the window resizes
  window.addEventListener('resize', () => {
    if (currentIndex < panels.length) {
      moveVideo(panels[currentIndex]);
    }
  });
}
