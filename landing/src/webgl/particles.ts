import * as THREE from 'three';

export class MessagePacketField {
  public points: THREE.Points;
  private particleCount: number = 650;
  private positions: Float32Array;
  private velocities: Float32Array;
  private colors: Float32Array;
  private shieldRadiusSq: number = 2.4 * 2.4;

  constructor() {
    this.positions = new Float32Array(this.particleCount * 3);
    this.velocities = new Float32Array(this.particleCount * 3);
    this.colors = new Float32Array(this.particleCount * 3);

    const normalColor = new THREE.Color(0x9da0b0);
    const spamColor = new THREE.Color(0xff385c);
    const verifiedColor = new THREE.Color(0x00ff88);

    for (let i = 0; i < this.particleCount; i++) {
      const idx = i * 3;
      // Spread across wide 3D corridor
      this.positions[idx] = (Math.random() - 0.5) * 16;
      this.positions[idx + 1] = (Math.random() - 0.5) * 12;
      this.positions[idx + 2] = (Math.random() - 0.5) * 14;

      this.velocities[idx] = (Math.random() - 0.5) * 0.02;
      this.velocities[idx + 1] = (Math.random() - 0.5) * 0.02;
      this.velocities[idx + 2] = -0.04 - Math.random() * 0.06;

      // Color coding: 15% rogue spam, 20% verified, remainder standard traffic
      const rand = Math.random();
      const col = rand < 0.15 ? spamColor : (rand < 0.35 ? verifiedColor : normalColor);
      this.colors[idx] = col.r;
      this.colors[idx + 1] = col.g;
      this.colors[idx + 2] = col.b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(this.colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.065,
      vertexColors: true,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending,
    });

    this.points = new THREE.Points(geometry, material);
  }

  public update(): void {
    const pos = this.positions;
    const vel = this.velocities;

    for (let i = 0; i < this.particleCount; i++) {
      const idx = i * 3;

      pos[idx] += vel[idx];
      pos[idx + 1] += vel[idx + 1];
      pos[idx + 2] += vel[idx + 2];

      // Shield collision deflection
      const distSq = pos[idx] * pos[idx] + pos[idx + 1] * pos[idx + 1] + pos[idx + 2] * pos[idx + 2];
      if (distSq < this.shieldRadiusSq) {
        // Bounce outward radially
        const dist = Math.sqrt(distSq) || 1;
        vel[idx] += (pos[idx] / dist) * 0.03;
        vel[idx + 1] += (pos[idx + 1] / dist) * 0.03;
        vel[idx + 2] += (pos[idx + 2] / dist) * 0.03;
      }

      // Recycle particles that travel behind camera
      if (pos[idx + 2] < -8) {
        pos[idx] = (Math.random() - 0.5) * 14;
        pos[idx + 1] = (Math.random() - 0.5) * 10;
        pos[idx + 2] = 8;
        vel[idx] = (Math.random() - 0.5) * 0.02;
        vel[idx + 1] = (Math.random() - 0.5) * 0.02;
        vel[idx + 2] = -0.04 - Math.random() * 0.06;
      }
    }

    this.points.geometry.attributes.position.needsUpdate = true;
  }
}
