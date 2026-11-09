// Living Pet — 3D fox renderer (three.js). Bundled to assets/fox3d.bundle.js.
// Used by the game screen (index.html) and by the floating overlay (overlay.html).
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const STAGE_FILES = ['fox_stage_1_baby', 'fox_stage_2_cub', 'fox_stage_3_teen', 'fox_stage_4_adult', 'fox_stage_5_legendary'];
const STAGE_SIZE = [0.70, 0.80, 0.90, 1.0, 1.06];       // relative on-screen size per growth stage
const FUR_PARTS = /^(Body|Tail|Ear_)/;

// ---------------------------------------------------------------- fur texture
function makeFurTexture(size = 512) {
  // Fur in tufts: each clump is a cone of strands that share a height,
  // so the shells read as soft locks of fur rather than velvet.
  const data = new Uint8Array(size * size * 4);
  const height = new Float32Array(size * size);
  const bright = new Float32Array(size * size).fill(1);
  let seed = 1337;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stamp = (px, py, r, h, b, sharp) => {
    const R = Math.ceil(r);
    for (let dy = -R; dy <= R; dy++) for (let dx = -R; dx <= R; dx++) {
      const x = (Math.floor(px) + dx + size) % size, y = (Math.floor(py) + dy + size) % size;
      const d = Math.hypot(Math.floor(px) + dx + 0.5 - px, Math.floor(py) + dy + 0.5 - py) / r;
      if (d >= 1) continue;
      const v = h * Math.pow(1 - d, sharp);
      const i = y * size + x;
      if (v > height[i]) { height[i] = v; bright[i] = b; }
    }
  };
  // big soft clumps
  for (let n = 0; n < 900; n++) stamp(rnd() * size, rnd() * size, 5 + rnd() * 5, 0.55 + 0.45 * rnd(), 0.88 + rnd() * 0.22, 0.75);
  // fine strands on top so the surface never looks bald
  for (let cy = 0; cy < size; cy += 3) for (let cx = 0; cx < size; cx += 3)
    stamp(cx + rnd() * 3, cy + rnd() * 3, 1.4 + rnd(), 0.25 + 0.4 * rnd(), 0.8 + rnd() * 0.3, 1.0);
  for (let i = 0; i < size * size; i++) {
    const b = Math.min(255, bright[i] * 232);
    data[i * 4] = b; data[i * 4 + 1] = b; data[i * 4 + 2] = b;
    data[i * 4 + 3] = Math.round(Math.min(1, height[i]) * 255);
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
    sh.uniforms.uWind = opts.uniforms.uWind;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec2 furData; attribute vec2 furUv;
        uniform float uShell; uniform float uFurScale; uniform float uDensity; uniform vec3 uWind;
        varying vec2 vFurUv; varying float vFurLen;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        float fl = furData.x * uFurScale;
        vFurLen = fl; vFurUv = furUv * uDensity;
        transformed += objectNormal * (uShell * fl);
        transformed.y -= uShell * uShell * fl * 0.55;
        transformed.z -= uShell * uShell * fl * 0.35;   // combed back towards the tail
        transformed += uWind * (uShell * uShell * fl * 1.6);`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D uFurTex; uniform float uShell; varying vec2 vFurUv; varying float vFurLen;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        vec4 fs = texture2D(uFurTex, vFurUv);
        if (uShell > 0.0) {
          if (vFurLen < 0.0015 || fs.a < uShell) discard;
        }
        float ao = mix(0.48, 1.28, pow(uShell, 0.72));   // darker roots, softly lit fur tips
        float strand = smoothstep(0.18, 0.92, fs.r);
        float fineShade = mix(0.84, 1.12, strand);
        diffuseColor.rgb *= ao * fineShade * mix(1.0, fs.r / 0.92, 0.42);`);
  };
  m.customProgramCacheKey = () => 'fur-v2' + (opts.legendary ? 'L' : '');
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
    this.opts = Object.assign({ base: 'models/', shells: 28, quality: 'high', facing: -0.42, view: 'room', pixelRatio: 2 }, opts);
    if (this.opts.quality === 'low') this.opts.shells = 12;
    else if (this.opts.quality === 'medium') this.opts.shells = 20;
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
    this.hemi = new THREE.HemisphereLight(0xfff0e0, 0xa08870, 1.45); this.scene.add(this.hemi);
    const key = this.key = new THREE.DirectionalLight(0xfff0dc, 2.4); key.position.set(-1.6, 2.6, 2.6); this.scene.add(key);
    const fill = this.fill = new THREE.DirectionalLight(0xcfe3ff, 0.65); fill.position.set(2.2, 0.8, 1.5); this.scene.add(fill);
    const rim = this.rim = new THREE.DirectionalLight(0xffd7a0, 3.2); rim.position.set(1.2, 2.2, -2.6); this.scene.add(rim);
  }

  setNight(night) {
    this.hemi.color.set(night ? 0xd6dcf0 : 0xfff0e0); this.hemi.intensity = night ? 1.2 : 1.45;
    this.key.color.set(night ? 0xffe6cc : 0xfff0dc); this.key.intensity = night ? 2.0 : 2.4;
    this.rim.color.set(night ? 0xb8ccff : 0xffd7a0);
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
    this.furUniforms = this.furUniforms || { uWind: { value: new THREE.Vector3() } };
    const furOpts = { furScale: 1.0, density: 0.030, legendary, uniforms: this.furUniforms };
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
    this.oneShot = null;
    this._play(this.state === 'walk' ? 'Walk' : this._baseClip(), 0);
    this._setupPhysics();
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
    return ({ sit: 'Sit', idle: 'Idle', walk: 'Walk', run: 'Run', sleep: 'Sleep', eat: 'Eat', drink: 'Drink',
      happy: 'Happy', wag: 'Wag', sad: 'Sad', rest: 'Rest', groom: 'Groom', forage: 'Forage', scared: 'Scared',
      sniff: 'Sniff' })[this.state] || 'Sit';
  }

  _action(name) {
    if (!this.clips[name]) return null;
    if (!this.actions[name]) this.actions[name] = this.mixer.clipAction(this.clips[name]);
    return this.actions[name];
  }

  _play(name, fade = 0.35, once = false, reps = 1) {
    const a = this._action(name); if (!a) return false;
    a.reset();
    a.setLoop(once ? (reps > 1 ? THREE.LoopRepeat : THREE.LoopOnce) : THREE.LoopRepeat, once ? reps : Infinity);
    a.clampWhenFinished = once;
    a.enabled = true; a.setEffectiveWeight(1); a.setEffectiveTimeScale(1);
    if (this.current && this.current !== a) {
      a.play(); if (fade > 0) this.current.crossFadeTo(a, fade, false); else this.current.stop();
    } else a.play();
    this.current = a; this.currentName = name;
    return true;
  }

  _onFinished(e) {
    const name = e.action.getClip().name.replace(/^Fox_[A-Za-z]+_/, '');
    if (name === 'Blink' || name === 'Talk') { e.action.stop(); return; }
    if (e.action === this.current) {
      this.oneShot = null;
      this._play(this._baseClip(), 0.35);
      this._emit('actionEnd', name);
    }
  }

  /** Base (looping) states: sit idle walk run sleep eat drink happy wag sad rest groom forage scared sniff.
   *  A running one-shot action is not interrupted unless `force` is set. */
  setState(state, force = false) {
    const changed = state !== this.state;
    this.state = state;
    if (!this.mixer) return;
    if (this.oneShot && !force) return;            // the action returns to the new base state when it ends
    if (!changed && this.currentName === this._baseClip()) return;
    this.oneShot = null;
    this._play(this._baseClip(), state === 'sleep' ? 0.8 : 0.35);
  }

  /** One-shot action with priority (1 flourish, 2 play, 3 reaction). Lower priority never cuts a higher one.
   *  Looping clips (TailChase, Groom, ScratchEar…) can be repeated `reps` times. Returns true if it started. */
  action(name, priority = 2, reps = 1) {
    if (!this.mixer || !this.clips[name]) return false;
    if (this.oneShot && this.oneShot.priority > priority) return false;
    if (this.walkTarget != null && priority < 3) return false;
    this.oneShot = { name, priority };
    return this._play(name, 0.25, true, reps);
  }

  busy() { return !!this.oneShot || this.walkTarget != null; }

  talk(seconds = 1.6) {
    const a = this._action('Talk'); if (!a) return;
    a.reset(); a.setLoop(THREE.LoopRepeat, Math.max(1, Math.round(seconds / this.clips.Talk.duration))); a.play();
  }

  blink() {
    const closedEyes = ['Sleep', 'Happy', 'Sad', 'Groom', 'ScratchEar', 'Yawn', 'WakeUp', 'Lick'];
    if (closedEyes.includes(this.currentName)) return;
    const a = this._action('Blink'); if (!a) return;
    a.reset(); a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = false; a.play();
  }

  // ---------------------------------------------------------- secondary motion
  /** Spring chains for tails and ears: they lag behind, overshoot and settle. */
  _setupPhysics() {
    const B = this.bones; this.chains = [];
    const chainOf = (prefix) => { const out = []; for (let i = 1; i <= 4; i++) { const b = B[prefix + String(i).padStart(2, '0')]; if (b) out.push(b); } return out; };
    for (const pre of ['Tail_', 'TailA_', 'TailB_', 'TailC_']) {
      const bones = chainOf(pre); if (!bones.length) continue;
      this.chains.push({ bones, k: 90, damp: 7, gravity: 0.6, maxAng: 0.75, nodes: [] });
    }
    for (const s of ['L', 'R']) if (B['Ear_' + s]) this.chains.push({ bones: [B['Ear_' + s]], k: 260, damp: 9, gravity: 0, maxAng: 0.35, nodes: [] });
    this.model.updateMatrixWorld(true);
    const wp = new THREE.Vector3(), wq = new THREE.Vector3();
    for (const c of this.chains) {
      c.len = c.bones.map((b, i) => {
        const nxt = c.bones[i + 1];
        if (nxt) { b.getWorldPosition(wp); nxt.getWorldPosition(wq); return wp.distanceTo(wq); }
        return null;
      });
      const known = c.len.filter(x => x); const avg = known.length ? known.reduce((a, b) => a + b) / known.length : 0.25 * this.root.scale.x;
      c.len = c.len.map(x => x || (c.bones.length === 1 ? 0.3 * this.root.scale.x : avg));
    }
    this._physReset = true;
  }

  /** push tails and ears, e.g. when the overlay window is dragged (screen px) */
  nudge(dx, dy = 0) {
    if (!this.chains) return;
    const v = new THREE.Vector3(-dx, dy, 0).multiplyScalar(0.02);
    for (const c of this.chains) for (const n of c.nodes) n.v.add(v);
    this._windKick = Math.min(1.5, (this._windKick || 0) + Math.abs(dx) * 0.01);
  }

  _physicsUpdate(dt) {
    if (!this.chains) return;
    const p0 = new THREE.Vector3(), dir = new THREE.Vector3(), tgt = new THREE.Vector3();
    const q = new THREE.Quaternion(), wq = new THREE.Quaternion(), pq = new THREE.Quaternion();
    const yAxis = new THREE.Vector3(0, 1, 0);
    const steps = 2, h = dt / steps;
    for (const c of this.chains) {
      for (let i = 0; i < c.bones.length; i++) {
        const b = c.bones[i];
        b.getWorldPosition(p0); b.getWorldQuaternion(wq);
        dir.copy(yAxis).applyQuaternion(wq).normalize();          // bone points along local +Y
        tgt.copy(p0).addScaledVector(dir, c.len[i]);
        let n = c.nodes[i];
        if (!n || this._physReset || n.x.distanceTo(tgt) > c.len[i] * 3) { n = c.nodes[i] = { x: tgt.clone(), v: new THREE.Vector3() }; continue; }
        for (let s = 0; s < steps; s++) {
          const acc = tgt.clone().sub(n.x).multiplyScalar(c.k).addScaledVector(n.v, -c.damp);
          acc.y -= c.gravity;
          n.v.addScaledVector(acc, h); n.x.addScaledVector(n.v, h);
        }
        const nd = n.x.clone().sub(p0); if (nd.lengthSq() < 1e-10) continue;
        nd.normalize(); n.x.copy(p0).addScaledVector(nd, c.len[i]);
        q.setFromUnitVectors(dir, nd);
        const ang = 2 * Math.acos(Math.min(1, Math.abs(q.w)));
        if (ang > c.maxAng) q.slerp(new THREE.Quaternion(), 1 - c.maxAng / ang);
        b.parent.getWorldQuaternion(pq);
        b.quaternion.copy(pq.clone().invert().multiply(q).multiply(wq));
        b.updateMatrixWorld(true);
      }
    }
    this._physReset = false;
  }

  /** wind in the fur: 0 calm … 1 strong (weather), plus a kick from movement */
  setWind(strength) { this.windStrength = strength; }

  _windUpdate(dt) {
    if (!this.furUniforms) return;
    const t = performance.now() / 1000;
    const base = this.windStrength || 0;
    this._windKick = Math.max(0, (this._windKick || 0) - dt * 1.5);
    const gust = base * (0.55 + 0.45 * Math.sin(t * 1.7) * Math.sin(t * 0.63 + 1.3)) + this._windKick * 0.4;
    // wind blows from screen-left to right in world space; convert into the model's bind space
    const w = new THREE.Vector3(1, 0.1, 0.35).normalize().multiplyScalar(gust * 0.9);
    if (this.walkTarget != null) w.x -= Math.sign(this.walkTarget - this.root.position.x) * 0.5;
    w.applyQuaternion(this.root.quaternion.clone().invert());
    this.furUniforms.uWind.value.lerp(w, Math.min(1, dt * 4));
    if (base > 0.05 && this.chains) {
      const push = new THREE.Vector3(gust * 0.9 * dt * 6, 0, 0);
      for (const c of this.chains) for (const n of c.nodes) n.v.add(push);
    }
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
    this._physicsUpdate(dt);
    this._windUpdate(dt);
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
