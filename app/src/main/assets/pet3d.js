// Glue between the game logic (life.js) and the 3D fox (fox3d.bundle.js).
// Other pets (cat, dog, wolf) keep the SVG drawing until their 3D models exist.
(() => {
  'use strict';
  let fox = null, failed = false, loadingStage = -1, lastActivity = null, tempTimer = null, wanderTimer = null;
  const scene = () => document.getElementById('scene');
  const canvas = () => document.getElementById('pet3d');

  function webglOk() {
    try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); }
    catch (_) { return false; }
  }

  function lowEnd() {
    const mem = navigator.deviceMemory || 4, cores = navigator.hardwareConcurrency || 4;
    return mem <= 2 || cores <= 4;
  }

  function ensure() {
    if (fox || failed) return fox;
    if (!window.Fox3D || !webglOk() || !canvas()) { failed = true; return null; }
    try {
      fox = new window.Fox3D(canvas(), { base: 'models/', quality: lowEnd() ? 'low' : 'high' });
    } catch (e) { console.error('3D init failed', e); failed = true; return null; }
    const c = canvas();
    c.addEventListener('pointermove', e => fox.lookAt(e.offsetX, e.offsetY));
    c.addEventListener('pointerdown', e => fox.lookAt(e.offsetX, e.offsetY));
    document.addEventListener('visibilitychange', () => fox.setPaused(document.hidden));
    scheduleWander();
    return fox;
  }

  function stateFor(activity) {
    return ({ sleep: 'sleep', drink: 'eat', forage: 'eat', greet: 'happy' })[activity] || 'sit';
  }

  function temporary(state, ms, after = 'sit') {
    if (!fox) return;
    clearTimeout(tempTimer);
    fox.setState(state);
    tempTimer = setTimeout(() => fox.setState(lastActivity === 'sleep' ? 'sleep' : after), ms);
  }

  // Now and then the fox gets up and walks to another spot of the room on her own.
  function scheduleWander() {
    clearTimeout(wanderTimer);
    wanderTimer = setTimeout(() => {
      if (fox && !document.hidden && lastActivity !== 'sleep' && fox.walkTarget == null && fox.state === 'sit') {
        const r = Math.random();
        if (r < 0.55) fox.walkTo((Math.random() * 2 - 1) * 1.3, Math.random() < 0.3 ? 'idle' : 'sit');
        else if (r < 0.7) fox.action('Stretch');
        else if (r < 0.85) temporary('wag', 2500);
        else fox.action('Jump');
      }
      scheduleWander();
    }, 9000 + Math.random() * 14000);
  }

  const Pet3D = {
    /** called from show(): pet object, growth stage 0..4, night flag */
    update(pet, stage, night) {
      const sc = scene();
      if (!pet || pet.kind !== 'fox') { sc?.classList.remove('has3d'); return; }
      const f = ensure();
      if (!f) { sc?.classList.remove('has3d'); return; }
      f.setNight(!!night);
      if (loadingStage !== stage) {
        loadingStage = stage;
        f.load(stage).then(() => sc.classList.add('has3d')).catch(err => {
          console.error('fox model failed', err); failed = true; sc.classList.remove('has3d');
        });
      }
      if (pet.activity !== lastActivity) {
        lastActivity = pet.activity;
        if (f.walkTarget == null) f.setState(stateFor(pet.activity));
      }
    },

    /** game events: play, talk, explore, weather, feed, water, tap */
    event(type) {
      if (!fox || !document.getElementById('scene').classList.contains('has3d')) return;
      switch (type) {
        case 'play': fox.action(Math.random() < 0.5 ? 'Jump' : 'React'); setTimeout(() => temporary('wag', 2600), 1100); break;
        case 'talk': fox.setState('sit'); fox.talk(2.2); break;
        case 'explore': fox.walkTo(fox.root.position.x > 0 ? -1.2 : 1.2, 'idle', Math.random() < 0.3); break;
        case 'weather': fox.action('React'); break;
        case 'feed': case 'water': temporary('eat', 3800); break;
        case 'stretch': fox.action('Stretch'); break;
      }
    },

    /** tap on the 3D canvas: react depending on what was touched */
    touch(x, y) {
      if (!fox) return null;
      fox.lookAt(x, y);
      const part = fox.hitTest(x, y);
      if (lastActivity === 'sleep') { fox.action('React'); return part; }
      if (part === 'head') temporary('happy', 2600);
      else if (part === 'ears') fox.action('React');
      else if (part === 'tail') temporary('wag', 2200);
      else fox.action('React');
      return part;
    },

    active() { return !!fox && document.getElementById('scene').classList.contains('has3d'); },
  };
  window.Pet3D = Pet3D;
})();
