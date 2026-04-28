// Renderer — Three.js with PBR-friendly defaults. Lighting + background
// are owned by the Lighting module; this file only configures the WebGL
// renderer + a default scene/camera.
import * as THREE from 'three';

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.three = null;
    this.scene = null;
    this.camera = null;
  }

  async init() {
    const renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      powerPreference: 'high-performance',
      stencil: false,
      logarithmicDepthBuffer: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.shadowMap.autoUpdate = true;

    // Wide-gamut output if the display supports it (Apple silicon, recent
    // Windows HDR-aware browsers). Fall back to sRGB if not.
    if (THREE.ColorManagement) THREE.ColorManagement.enabled = true;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x050507);  // overwritten by Lighting

    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 5, 10);
    camera.lookAt(0, 0, 0);

    this.three = renderer;
    this.scene = scene;
    this.camera = camera;

    addEventListener('resize', this.onResize, { passive: true });
  }

  onResize = () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.three.setSize(w, h, false);
    if (this.camera.isPerspectiveCamera) {
      this.camera.aspect = w / h;
    } else if (this.camera.isOrthographicCamera) {
      // Caller should adjust ortho frustum. We just refresh the projection.
    }
    this.camera.updateProjectionMatrix?.();
  };

  setBackground(colorOrTexture) {
    this.scene.background = colorOrTexture;
  }

  setExposure(v) {
    this.three.toneMappingExposure = v;
  }

  setShadowQuality(level = 'high') {
    const r = this.three;
    r.shadowMap.type = ({
      'off':    THREE.BasicShadowMap,
      'low':    THREE.BasicShadowMap,
      'medium': THREE.PCFShadowMap,
      'high':   THREE.PCFSoftShadowMap,
      'vsm':    THREE.VSMShadowMap,
    })[level] ?? THREE.PCFSoftShadowMap;
    r.shadowMap.enabled = level !== 'off';
    r.shadowMap.needsUpdate = true;
  }

  render() {
    this.three.render(this.scene, this.camera);
  }
}
