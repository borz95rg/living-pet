// Living Pet — 3D fox renderer (three.js). Bundled to assets/fox3d.bundle.js.
// Used by the game screen (index.html) and by the floating overlay (overlay.html).
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const STAGE_FILES = ['fox_stage_1_baby', 'fox_stage_2_cub', 'fox_stage_3_teen', 'fox_stage_4_adult', 'fox_stage_5_legendary'];
const STAGE_SIZE = [0.70, 0.80, 0.90, 1.0, 1.06];       // relative on-screen size per growth stage
const FUR_PARTS = /^(Body|Tail|Ear_)/;

// ---------------------------------------------------------------- fur texture
function makeFurTexture(size = 256) {
  const data = new Uint8Array(size * size * 4);
  const height = new Float32Array(size * size);
  const bright = new Float32Array(size * size).fill(1);
  let seed = 1337;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const cell = 3;
  for (let cy = 0; cy < size; cy += cell) {
    for (let cx = 0; cx < size; cx += cell) {
      const px = cx + rnd() * cell, py = cy + rnd() * cell;
      const h = 0.35 + 0.65 * Math.pow(rnd(), 0.6), r = 1.6 + rnd() * 1.4, b = 0.82 + rnd() * 0.3;
      for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) {
        const x = (Math.floor(px) + dx + size) % size, y = (Math.floor(py) + dy + size) % size;
        const d = Math.hypot(Math.floor(px) + dx + 0.5 - px, Math.floor(py) + dy + 0.5 - py) / r;
        if (d >= 1) continue;
        const v = h * (1 - d * d);
        const i = y * size + x;
        if (v > height[i]) { height[i] = v; bright[i] = b; }
      }
    }
  }
  for (let i = 0; i < size * size; i++) {
    const b = Math.min(255, bright[i] * 235);
    data[i * 4] = b; data[i * 4 + 1] = b; data[i * 4 + 2] = b;
    data[i * 4 + 3] = Math.round(height[i] * 255);
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.needsUpdate = true;
  return tex;
}

// ---------------------------------------------------------------- fur material
function furMaterial(furTex, shell, opts) {
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, metalness: 0 });
  if (opts.legendary) { m.emissive = new THREE.Color(0xff7a10); m.emissiveIntensity = 0.04 + shell * 0.30; }
  m.userData.shell = shell;
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uShell = { value: shell };
    sh.uniforms.uFurTex = { value: furTex };
    sh.uniforms.uFurScale = { value: opts.furScale };
    sh.uniforms.uDensity = { value: opts.density };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec2 furData; attribute vec2 furUv;
        uniform float uShell; uniform float uFurScale; uniform float uDensity;
        varying vec2 vFurUv; varying float vFurLen;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        float fl = furData.x * uFurScale;
        vFurLen = fl; vFurUv = furUv * uDensity;
        transformed += objectNormal * (uShell * fl);
        transformed.y -= uShell * uShell * fl * 0.45;`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D uFurTex; uniform float uShell; varying vec2 vFurUv; varying float vFurLen;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec4 fs = texture2D(uFurTex, vFurUv);
        if (uShell > 0.0) {
          if (vFurLen < 0.0015 || fs.a < uShell) discard;
        }
        float ao = mix(0.50, 1.10, uShell);
        diffuseColor.rgb *= ao * mix(1.0, fs.r / 0.92, 0.6);`);
  };
  m.customProgramCacheKey = () => 'fur-v1' + (opts.legendary ? 'L' : '');
  return m;
}

function remapFurAttributes(geo) {
  if (geo.userData.furReady) return;
  const uv = geo.getAttribute('uv');
  const fd = geo.getAttribute('uv1');
  geo.setAttribute('furUv', uv);
  geo.setAttribute('furData', fd || new THREE.BufferAttribute(new Float32Array(uv.count * 2), 2));
  geo.userData.furReady = true;
}

function blobShadowTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(64, 64, 4, 64, 64, 62);
  grd.addColorStop(0, 'rgba(40,30,25,0.55)'); grd.addColorStop(0.6, 'rgba(40,30,25,0.22)'); grd.addColorStop(1, 'rgba(40,30,25,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

// ---------------------------------------------------------------- Fox3D
export class Fox3D {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.opts = Object.assign({ base: 'models/', shells: 14, quality: 'high', facing: -0.42, view: 'room', pixelRatio: 2 }, opts);
    if (this.opts.quality === 'low') this.opts.shells = 8;
    const r = this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, premultipliedAlpha: true, powerPreference: 'low-power' });
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.opts.pixelRatio));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.05;
    r.setClearColor(0x000000, 0);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(26, 1, 0.05, 50);
    this._last = performance.now();
    this.furTex = makeFurTexture();
    this.pointer = null; this.pointerAt = 0;
    this.paused = false; this.state = 'sit'; this.facing = this.opts.facing; this.facingTarget = this.facing;
    this.listeners = {};
    this._lights();
    this.root = new THREE.Group(); this.scene.add(this.root);
    const sh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: blobShadowTexture(), transparent: true, depthWrite: false }));
    sh.rotation.x = -Math.PI / 2; sh.renderOrder = -1; this.shadow = sh; this.scene.add(sh);
    this._resize();
    this._loop = this._loop.bind(this);
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => this._resize()).observe(canvas);
    requestAnimationFrame(this._loop);
  }

  on(ev, fn) { (this.listeners[ev] ||= []).push(fn); }
  _emit(ev, a) { (this.listeners[ev] || []).forEach(f => f(a)); }

  _lights() {
    this.hemi = new THREE.HemisphereLight(0xfff1e0, 0x9a8a7a, 1.35); this.scene.add(this.hemi);
    const key = this.key = new THREE.DirectionalLight(0xfff0dc, 2.4); key.position.set(-1.6, 2.6, 2.6); this.scene.add(key);
    const fill = this.fill = new THREE.DirectionalLight(0xcfe3ff, 0.65); fill.position.set(2.2, 0.8, 1.5); this.scene.add(fill);
    const rim = this.rim = new THREE.DirectionalLight(0xffe2b8, 2.0); rim.position.set(0.6, 2.0, -2.8); this.scene.add(rim);
  }

  setNight(night) {
    this.hemi.color.set(night ? 0xd6dcf0 : 0xfff1e0); this.hemi.intensity = night ? 1.15 : 1.35;
    this.key.color.set(night ? 0xffe6cc : 0xfff0dc); this.key.intensity = night ? 2.0 : 2.4;
    this.rim.color.set(night ? 0x9fc0ff : 0xffe2b8);
  }

  async load(stage) {
    stage = Math.max(0, Math.min(4, stage | 0));
    if (this.stage === stage && this.model) return;
    this.stage = stage;
    const gltf = await new GLTFLoader().loadAsync(this.opts.base + STAGE_FILES[stage] + '.glb');
    if (this.model) { this.root.remove(this.model); this.model.traverse(o => { o.geometry?.dispose?.(); }); }
    const model = this.model = gltf.scene;
    const info = gltf.asset?.extras || {};
    const legendary = !!info.legendary;
    this.legendary = legendary;
    const shells = this.opts.shells;
    const furOpts = { furScale: 1.0, density: 0.045, legendary };
    const shellMats = [];
    for (let i = 0; i <= shells; i++) shellMats.push(furMaterial(this.furTex, i / shells, furOpts));
    const toAdd = [];
    model.traverse(o => {
      if (!o.isSkinnedMesh && !o.isMesh) return;
      o.frustumCulled = false;
      const n = o.name;
      if (FUR_PARTS.test(n)) {
        remapFurAttributes(o.geometry);
        o.material = shellMats[0];
        for (let i = 1; i <= shells; i++) {
          const s = new THREE.SkinnedMesh(o.geometry, shellMats[i]);
          s.bind(o.skeleton, o.bindMatrix); s.frustumCulled = false; s.renderOrder = i;
          toAdd.push([o.parent, s]);
        }
      } else if (n.startsWith('Eye')) {
        o.material = new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.03,
          emissive: legendary ? 0xffb030 : 0x000000, emissiveIntensity: legendary ? 0.15 : 0 });
      } else if (n.startsWith('Glint')) {
        o.material = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
      } else if (n.startsWith('Nose')) {
        o.material = new THREE.MeshPhysicalMaterial({ color: 0x1b1210, roughness: 0.28, clearcoat: 0.8, clearcoatRoughness: 0.15 });
      } else if (n.startsWith('Lid')) {
        o.material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 });
      } else {
        o.material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55 });
      }
    });
    toAdd.forEach(([p, s]) => p.add(s));
    this.root.add(model);
    // bones we steer procedurally
    this.bones = {};
    model.traverse(o => { if (o.isBone) this.bones[o.name] = o; });
    // frame the camera on the bind pose
    model.updateMatrixWorld(true);
    const box = new THREE.Box3();
    model.traverse(o => { if (o.isSkinnedMesh && o.name === 'Body') { o.geometry.computeBoundingBox(); box.union(o.geometry.boundingBox); } });
    this.bodyBox = box;
    this._frame();
    // animation
    this.mixer = new THREE.AnimationMixer(model);
    this.clips = {};
    gltf.animations.forEach(c => { const k = c.name.replace(/^Fox_[A-Za-z]+_/, ''); this.clips[k] = c; });
    this.actions = {};
    this.current = null;
    this.mixer.addEventListener('finished', e => this._onFinished(e));
    this._play(this.state === 'walk' ? 'Walk' : this._baseClip(), 0);
    this._scheduleBlink();
    this._emit('loaded', { stage, clips: Object.keys(this.clips) });
  }

  _frame() {
    const size = STAGE_SIZE[this.stage] ?? 1;
    const h = 1.75;                        // world height the adult fox occupies
    const b = this.bodyBox; const hgt = b.max.y - b.min.y;
    const s = (h / hgt) * size * (this.opts.view === 'overlay' ? 1.05 : 0.92) * (this.stage === 4 ? 0.94 : 1);
    this.root.scale.setScalar(s);
    this.baseScale = s;
    const cam = this.camera;
    const target = new THREE.Vector3(0, 0.78, 0);
    if (this.opts.view === 'overlay') cam.position.set(0, 1.1, 5.1); else cam.position.set(0, 1.25, 6.4);
    cam.lookAt(target);
    this.shadow.scale.set(1.5 * size, 1.1 * size, 1);
  }

  _resize() {
    const w = this.canvas.clientWidth || this.canvas.width, h = this.canvas.clientHeight || this.canvas.height;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    // keep the fox fully in view in narrow canvases
    this.camera.fov = w / h < 0.9 ? 30 / Math.max(0.55, w / h) * 0.9 : 26;
    this.camera.updateProjectionMatrix();
  }

  _baseClip() {
    return ({ sit: 'Sit', idle: 'Idle', walk: 'Walk', run: 'Run', sleep: 'Sleep', eat: 'Eat', happy: 'Happy', wag: 'Wag' })[this.state] || 'Sit';
  }

  _action(name) {
    if (!this.clips[name]) return null;
    if (!this.actions[name]) this.actions[name] = this.mixer.clipAction(this.clips[name]);
    return this.actions[name];
  }

  _play(name, fade = 0.35, once = false) {
    const a = this._action(name); if (!a) return;
    a.reset();
    a.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    a.clampWhenFinished = once;
    a.enabled = true; a.setEffectiveWeight(1); a.setEffectiveTimeScale(1);
    if (this.current && this.current !== a) {
      a.play(); if (fade > 0) this.current.crossFadeTo(a, fade, false); else this.current.stop();
    } else a.play();
    this.current = a; this.currentName = name;
  }

  _onFinished(e) {
    const name = e.action.getClip().name.replace(/^Fox_[A-Za-z]+_/, '');
    if (name === 'Blink' || name === 'Talk') { e.action.stop(); return; }
    if (e.action === this.current) this._play(this._baseClip(), 0.3);
  }

  /** sit | idle | walk | run | sleep | eat | happy | wag */
  setState(state) {
    if (state === this.state && this.currentName === this._baseClip()) return;
    this.state = state;
    if (this.mixer) this._play(this._baseClip(), state === 'sleep' ? 0.8 : 0.35);
  }

  /** one-shot actions: React, Jump, Stretch */
  action(name) { if (this.mixer && this.clips[name]) this._play(name, 0.2, true); }

  talk(seconds = 1.6) {
    const a = this._action('Talk'); if (!a) return;
    a.reset(); a.setLoop(THREE.LoopRepeat, Math.max(1, Math.round(seconds / this.clips.Talk.duration))); a.play();
  }

  blink() {
    if (this.state === 'sleep' || this.currentName === 'Happy') return;
    const a = this._action('Blink'); if (!a) return;
    a.reset(); a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = false; a.play();
  }

  _scheduleBlink() {
    clearTimeout(this._blinkT);
    this._blinkT = setTimeout(() => { if (!this.paused) this.blink(); this._scheduleBlink(); }, 1800 + Math.random() * 3800);
  }

  /** walk inside the room to x (world units, about -1.6..1.6), then return to `then` state */
  walkTo(x, then = 'sit', run = false) {
    this.walkTarget = x; this.walkThen = then; this.walkRun = run;
    this.setState(run ? 'run' : 'walk');
  }

  _walkUpdate(dt) {
    if (this.walkTarget == null) return;
    const p = this.root.position; const d = this.walkTarget - p.x;
    const speed = (this.walkRun ? 2.0 : 0.85) * (STAGE_SIZE[this.stage] ?? 1);
    if (Math.abs(d) < 0.03) {
      p.x = this.walkTarget; this.walkTarget = null; this.setFacing(0); this.setState(this.walkThen || 'sit');
      this._emit('arrived'); return;
    }
    this.setFacing(Math.sign(d));
    if (Math.abs(this.facing - this.facingTarget) < 0.5) p.x += Math.sign(d) * Math.min(Math.abs(d), speed * dt);
  }

  /** face direction: -1 left, 1 right, 0 towards viewer */
  setFacing(dir) { this.facingTarget = dir === 0 ? this.opts.facing : dir * 1.25; }

  /** pointer in canvas CSS pixels; the fox will look at it for a while */
  lookAt(x, y) { this.pointer = { x, y }; this.pointerAt = performance.now(); }

  /** returns which part was touched: head | ears | tail | body | null */
  hitTest(x, y) {
    if (!this.model) return null;
    const rect = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2((x / rect.width) * 2 - 1, -(y / rect.height) * 2 + 1);
    const pos = (n) => { const b = this.bones[n]; if (!b) return null; const v = new THREE.Vector3(); b.getWorldPosition(v); return v.project(this.camera); };
    const cand = [['head', 'Head'], ['ears', 'Ear_L'], ['ears', 'Ear_R'], ['tail', 'Tail_03'], ['tail', 'TailB_03'], ['body', 'Spine'], ['body', 'Chest']];
    let best = null, bd = 0.32;
    for (const [part, bn] of cand) { const p = pos(bn); if (!p) continue; const d = Math.hypot(p.x - ndc.x, (p.y - ndc.y) * 0.8); if (d < bd) { bd = d; best = part; } }
    return best;
  }

  setPaused(p) { this.paused = p; this._last = performance.now(); }

  _lookUpdate(dt) {
    const B = this.bones; if (!B.Head) return;
    const now = performance.now();
    const active = this.pointer && now - this.pointerAt < 4000 && !['sleep', 'happy'].includes(this.state) && this.currentName !== 'Happy';
    this._lookW = THREE.MathUtils.damp(this._lookW || 0, active ? 1 : 0, 4, dt);
    if (this._lookW < 0.01) return;
    const rect = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector3((this.pointer.x / rect.width) * 2 - 1, -(this.pointer.y / rect.height) * 2 + 1, 0.5);
    ndc.unproject(this.camera);
    const dir = ndc.sub(this.camera.position).normalize();
    const target = this.camera.position.clone().add(dir.multiplyScalar(this.camera.position.length() - 1.0));
    const turn = (bone, amount, maxAng, fwdLocalFn) => {
      const wp = new THREE.Vector3(); bone.getWorldPosition(wp);
      const want = target.clone().sub(wp).normalize();
      const fwd = fwdLocalFn();
      const q = new THREE.Quaternion().setFromUnitVectors(fwd, want);
      const ang = 2 * Math.acos(Math.min(1, Math.abs(q.w)));
      const lim = Math.min(1, maxAng / Math.max(ang, 1e-4));
      q.slerp(new THREE.Quaternion(), 1 - lim * amount * this._lookW);
      const wq = new THREE.Quaternion(); bone.getWorldQuaternion(wq);
      const pq = new THREE.Quaternion(); bone.parent.getWorldQuaternion(pq);
      bone.quaternion.copy(pq.invert().multiply(q).multiply(wq));
      bone.updateMatrixWorld(true);
    };
    const modelFwd = () => new THREE.Vector3(0, 0, 1).applyQuaternion(this.root.quaternion).normalize();
    turn(B.Head, 0.55, 0.45, modelFwd);
    for (const s of ['L', 'R']) {
      const e = B['Eye_' + s]; if (!e) continue;
      turn(e, 1.0, 0.32, () => { const q = new THREE.Quaternion(); e.getWorldQuaternion(q); return new THREE.Vector3(0, 1, 0).applyQuaternion(q).normalize(); });
    }
  }

  _loop() {
    requestAnimationFrame(this._loop);
    if (this.paused || !this.model) return;
    const tnow = performance.now(); const dt = Math.min(0.05, (tnow - this._last) / 1000); this._last = tnow;
    this.facing = THREE.MathUtils.damp(this.facing, this.facingTarget, 5, dt);
    this.root.rotation.y = this.facing;
    this._walkUpdate(dt);
    this.mixer.update(dt);
    this.root.updateMatrixWorld(true);
    this._lookUpdate(dt);
    const rp = new THREE.Vector3(); (this.bones.Root || this.root).getWorldPosition(rp);
    this.shadow.position.set(rp.x, 0.002, rp.z);
    const lift = Math.max(0, rp.y);
    this.shadow.material.opacity = 1 - Math.min(0.7, lift * 0.8);
    this.renderer.render(this.scene, this.camera);
  }

  /** testing helper: freeze a clip at time t (0..1) */
  debugPose(name, t) {
    this.paused = true;
    Object.values(this.actions).forEach(a => a.stop());
    const a = this._action(name); a.reset(); a.play(); a.paused = false;
    this.mixer.setTime(0); this.mixer.update(t * this.clips[name].duration);
    this.root.rotation.y = this.facing;
    this.root.updateMatrixWorld(true);
    const rp = new THREE.Vector3(); this.bones.Root.getWorldPosition(rp);
    this.shadow.position.set(rp.x, 0.002, rp.z);
    this.renderer.render(this.scene, this.camera);
  }
}

window.Fox3D = Fox3D;
window.THREE_REVISION = THREE.REVISION;
