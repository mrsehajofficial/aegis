import * as THREE from 'three';

export class AegisShieldMesh {
  public group: THREE.Group;
  public baseScale: number = 1.0;
  private outerLattice: THREE.LineSegments;
  private innerCore: THREE.Mesh;
  private deflectionRings: THREE.Line[];
  private targetRotationX: number = 0;
  private targetRotationY: number = 0;
  private pulsePhase: number = 0;

  constructor() {
    this.group = new THREE.Group();

    // Outer Aegis Geometric Lattice (Icosahedron Wireframe)
    const outerGeo = new THREE.IcosahedronGeometry(2.0, 1);
    const wireframeGeo = new THREE.WireframeGeometry(outerGeo);
    const latticeMat = new THREE.LineBasicMaterial({
      color: 0x00ff88,
      transparent: true,
      opacity: 0.5,
      linewidth: 1,
    });
    this.outerLattice = new THREE.LineSegments(wireframeGeo, latticeMat);
    this.group.add(this.outerLattice);

    // Inner Kinetic Defense Core (Deep Obsidian & Cyan Facets)
    const coreGeo = new THREE.OctahedronGeometry(1.1, 0);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x0a0c10,
      metalness: 0.9,
      roughness: 0.2,
      wireframe: false,
    });
    this.innerCore = new THREE.Mesh(coreGeo, coreMat);
    this.group.add(this.innerCore);

    // Core Wireframe Outline
    const coreWireGeo = new THREE.WireframeGeometry(coreGeo);
    const coreWireMat = new THREE.LineBasicMaterial({
      color: 0x00f0ff,
      transparent: true,
      opacity: 0.7,
    });
    const coreWire = new THREE.LineSegments(coreWireGeo, coreWireMat);
    this.innerCore.add(coreWire);

    // Concentric Deflection Rings
    this.deflectionRings = [];
    const ringRadii = [2.6, 3.2];
    ringRadii.forEach((radius, i) => {
      const ringGeo = new THREE.BufferGeometry();
      const points = [];
      const segments = 64;
      for (let j = 0; j <= segments; j++) {
        const theta = (j / segments) * Math.PI * 2;
        points.push(new THREE.Vector3(Math.cos(theta) * radius, Math.sin(theta) * radius, 0));
      }
      ringGeo.setFromPoints(points);

      const ringMat = new THREE.LineDashedMaterial({
        color: i === 0 ? 0x00ff88 : 0x00f0ff,
        dashSize: 0.2,
        gapSize: 0.15,
        transparent: true,
        opacity: 0.3,
      });
      const ring = new THREE.Line(ringGeo, ringMat);
      ring.computeLineDistances();
      this.deflectionRings.push(ring);
      this.group.add(ring);
    });
  }

  public update(delta: number): void {
    this.pulsePhase += delta * 1.5;

    // Smooth lerp rotation toward pointer offsets
    this.group.rotation.x += (this.targetRotationX - this.group.rotation.x) * 0.05;
    this.group.rotation.y += (this.targetRotationY - this.group.rotation.y) * 0.05;

    // Internal kinetic rotations
    this.innerCore.rotation.y -= delta * 0.5;
    this.innerCore.rotation.z += delta * 0.3;

    // Subtle breath pulse
    const breathe = 1 + Math.sin(this.pulsePhase) * 0.02;
    this.innerCore.scale.set(breathe, breathe, breathe);

    // Rotate deflection rings in opposite directions
    if (this.deflectionRings[0]) this.deflectionRings[0].rotation.z += delta * 0.2;
    if (this.deflectionRings[1]) this.deflectionRings[1].rotation.z -= delta * 0.15;
  }

  public setPointerOffset(ndcX: number, ndcY: number): void {
    this.targetRotationY = ndcX * 0.5;
    this.targetRotationX = -ndcY * 0.4;
  }

  public updateScrub(progress: number, velocity: number): void {
    // 3D rotation scrub along pinned scroll progression
    this.group.rotation.y = progress * Math.PI * 3 + this.targetRotationY;
    this.group.rotation.z = Math.sin(progress * Math.PI * 2) * 0.35;

    // Dynamic scale morphing across stages respecting responsive device baseScale
    const scaleFactor = (1 + Math.sin(progress * Math.PI) * 0.3) * this.baseScale;
    this.group.scale.set(scaleFactor, scaleFactor, scaleFactor);

    // React to scroll velocity inertia
    this.outerLattice.rotation.x += velocity * 0.001;
  }

  public triggerDeflection(): void {
    // Flash effect on manual command deflection
    const mat = this.outerLattice.material as THREE.LineBasicMaterial;
    mat.opacity = 0.95;
    mat.color.setHex(0x00f0ff);

    setTimeout(() => {
      mat.opacity = 0.5;
      mat.color.setHex(0x00ff88);
    }, 300);
  }
}
