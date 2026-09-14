import * as THREE from 'three';
import { AegisShieldMesh } from './shield';
import { MessagePacketField } from './particles';

export class WebGLScene {
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  public shield: AegisShieldMesh;
  private packets: MessagePacketField;
  private clock: THREE.Clock;

  constructor(canvas: HTMLCanvasElement) {
    this.scene = new THREE.Scene();
    this.clock = new THREE.Clock();

    this.camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
    this.camera.position.z = 7;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });

    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Ambient & Directional Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    this.scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0x00f0ff, 1.5);
    dirLight.position.set(5, 5, 5);
    this.scene.add(dirLight);

    const emeraldLight = new THREE.PointLight(0x00ff88, 2, 10);
    emeraldLight.position.set(-3, -2, 2);
    this.scene.add(emeraldLight);

    // Add Shield and Message Flow
    this.shield = new AegisShieldMesh();
    this.scene.add(this.shield.group);

    this.packets = new MessagePacketField();
    this.scene.add(this.packets.points);

    this.onResize();
    this.initEventListeners();
  }

  private initEventListeners(): void {
    window.addEventListener('resize', this.onResize.bind(this));
    window.addEventListener('pointermove', (e: MouseEvent) => {
      const ndcX = (e.clientX / window.innerWidth) * 2 - 1;
      const ndcY = -(e.clientY / window.innerHeight) * 2 + 1;
      this.shield.setPointerOffset(ndcX, ndcY);
    });

    // Touch support for mobile inertia
    window.addEventListener('touchmove', (e: TouchEvent) => {
      if (e.touches.length > 0) {
        const touch = e.touches[0];
        const ndcX = (touch.clientX / window.innerWidth) * 2 - 1;
        const ndcY = -(touch.clientY / window.innerHeight) * 2 + 1;
        this.shield.setPointerOffset(ndcX * 0.7, ndcY * 0.7);
      }
    }, { passive: true });
  }

  private onResize(): void {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const aspect = width / height;

    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);

    // Responsive 3D layout framing
    if (aspect < 0.8) {
      // Small mobile portrait (e.g., iPhone)
      this.camera.position.z = 8.5;
      this.shield.baseScale = 0.50;
      this.shield.group.position.y = 1.6;
    } else if (aspect < 1.2) {
      // Tablet / medium screens
      this.camera.position.z = 8.0;
      this.shield.baseScale = 0.70;
      this.shield.group.position.y = 0.8;
    } else {
      // Desktop
      this.camera.position.z = 7.0;
      this.shield.baseScale = 1.0;
      this.shield.group.position.y = 0.0;
    }

    const s = this.shield.baseScale;
    this.shield.group.scale.set(s, s, s);
  }

  public render(): void {
    const delta = this.clock.getDelta();
    this.shield.update(delta);
    this.packets.update();
    this.renderer.render(this.scene, this.camera);
  }
}
