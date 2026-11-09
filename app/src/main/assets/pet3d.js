// Glue between the game logic (life.js) and the 3D fox (fox3d.bundle.js).
// Behaviour layer: maps needs / activities / events to the 30 animation clips.
// Other pets (cat, dog, wolf) keep the SVG drawing until their 3D models exist.
(() => {
  'use strict';
  let fox = null, failed = false, loadingStage = -1, lastActivity = null, tempTimer = null, wanderTimer = null;
  let pet = null, greeted = false;
  const scene = () => document.getElementById('scene');
  const canvas = () => document.getElementById('pet3d');
  const pick = (list) => {
    const total = list.reduce((s, [, w]) => s + w, 0); let r = Math.random() * total;
    for (const [v, w] of list) { if ((r -= w) <= 0) return v; } return list[0][0];
  };

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
    document.addEventListener('visibilitychange', () => {
      fox.setPaused(document.hidden);
      if (!document.hidden) greetOwner();
    });
    scheduleWander();
    return fox;
  }

  // ---- what the fox does on her own, depending on how she feels ----------
  function baseState() {
    if (!pet) return 'sit';
    const n = pet.needs || {};
    switch (pet.activity) {
      case 'sleep': return 'sleep';
      case 'drink': return 'drink';
      case 'forage': return 'forage';
      case 'groom': return 'groom';
      case 'rest': return 'rest';
      case 'greet': return 'happy';
    }
    if ((n.mood ?? 80) < 35) return 'sad';
    if ((n.energy ?? 80) < 30) return 'rest';
    return 'sit';
  }

  function settle() { if (fox && fox.walkTarget == null) fox.setState(baseState()); }

  function temporary(state, ms) {
    if (!fox) return;
    clearTimeout(tempTimer);
    fox.setState(state, true);
    tempTimer = setTimeout(settle, ms);
  }

  function greetOwner() {
    if (!fox || !fox.model || !pet || pet.activity === 'sleep') return;
    fox.action('Greet', 3);
  }

  // Now and then she gets up and does something by herself: walks, sniffs,
  // looks around, chases her tail, scratches an ear, yawns in the evening…
  function scheduleWander() {
    clearTimeout(wanderTimer);
    wanderTimer = setTimeout(() => {
      if (fox && fox.model && !document.hidden && !fox.busy() && pet) {
        const st = fox.state, n = pet.needs || {};
        const hour = new Date().getHours(), evening = hour >= 20 || hour < 7;
        const energetic = (n.energy ?? 80) > 45, happy = (n.mood ?? 80) > 55;
        if (st === 'sit' || st === 'idle') {
          const what = pick([
            ['walk', energetic ? 5 : 2], ['LookAround', 4], ['Sniff', 3], ['Curious', 2], ['Lick', 2],
            ['ScratchEar', 2], ['Groom', 1.5], ['Stretch', 2], ['Yawn', evening ? 4 : 1],
            ['TailChase', energetic && happy ? 1.5 : 0], ['Spin', happy ? 1 : 0], ['Jump', energetic ? 1 : 0],
            ['Play', energetic && happy ? 1 : 0],
          ]);
          if (what === 'walk') {
            const x = (Math.random() * 2 - 1) * 1.3;
            if (Math.random() < 0.35) { fox.walkTo(x, 'sniff'); setTimeout(settle, 6000); }
            else fox.walkTo(x, Math.random() < 0.3 ? 'idle' : 'sit');
          } else if (what === 'Sniff') temporary('sniff', 2500);
          else fox.action(what, 1, ['TailChase', 'Groom', 'ScratchEar'].includes(what) ? 2 : 1);
        } else if (st === 'sad') fox.action(pick([['LookAround', 1], ['Yawn', 1], ['Lick', 1]]), 1);
        else if (st === 'rest') fox.action('Yawn', 1);
      }
      scheduleWander();
    }, 8000 + Math.random() * 12000);
  }

  const Pet3D = {
    /** called from show(): pet object, growth stage 0..4, night flag */
    update(p, stage, night) {
      pet = p;
      const sc = scene();
      if (!p || p.kind !== 'fox') { sc?.classList.remove('has3d'); return; }
      const f = ensure();
      if (!f) { sc?.classList.remove('has3d'); return; }
      f.setNight(!!night);
      f.setWind(p.weatherIndex === 3 ? 0.9 : 0.08);
      if (loadingStage !== stage) {
        const growing = loadingStage >= 0;
        loadingStage = stage;
        f.load(stage).then(() => {
          sc.classList.add('has3d');
          f.setState(baseState(), true);
          if (growing) f.action('Spin', 3);                 // a little celebration after growing up
          else if (!greeted) { greeted = true; setTimeout(greetOwner, 600); }
        }).catch(err => {
          console.error('fox model failed', err); failed = true; sc.classList.remove('has3d');
        });
      }
      if (p.activity !== lastActivity) {
        const wasSleeping = lastActivity === 'sleep';
        lastActivity = p.activity;
        if (wasSleeping && p.activity !== 'sleep' && f.model) { f.state = baseState(); f.action('WakeUp', 3); }
        else settle();
      } else if (f.model && !f.busy() && ['sit', 'sad', 'rest'].includes(f.state)) settle();
    },

    /** game events: play, talk, explore, weather, feed, water, tap */
    event(type) {
      if (!fox || !scene().classList.contains('has3d')) return;
      if (pet?.activity === 'sleep' && type !== 'tap') { fox.action('WakeUp', 3); return; }
      switch (type) {
        case 'play':
          fox.action(pick([['Play', 3], ['TailChase', 2], ['Spin', 2], ['Jump', 1]]), 3, 1);
          break;
        case 'talk': fox.action('Curious', 2); fox.talk(2.2); break;
        case 'explore': fox.walkTo(fox.root.position.x > 0 ? -1.2 : 1.2, 'sniff', Math.random() < 0.3); setTimeout(settle, 7000); break;
        case 'weather': {
          const w = ((pet?.weatherIndex ?? 0) + 1) % 4; // life.js switches weather right after this call
          if (w === 1) fox.action('Curious', 3);      // rain: watches the drops
          else if (w === 2) fox.action('Play', 3);    // snow: pounces on snowflakes
          else if (w === 3) { fox.setWind(0.9); fox.action('Scared', 3, 2); }
          else fox.action('Greet', 3);                // sunny again
          break;
        }
        case 'feed': fox.action('Sniff', 3); setTimeout(() => temporary('eat', 3800), 900); break;
        case 'water': temporary('drink', 3500); break;
        case 'stretch': fox.action('Stretch', 2); break;
      }
    },

    /** tap on the 3D canvas: react depending on what was touched */
    touch(x, y) {
      if (!fox) return null;
      fox.lookAt(x, y);
      const part = fox.hitTest(x, y);
      if (pet?.activity === 'sleep') { fox.action('WakeUp', 3); return part; }
      if (part === 'head') temporary('happy', 2600);
      else if (part === 'ears') fox.action('ScratchEar', 3);
      else if (part === 'tail') fox.action(Math.random() < 0.5 ? 'TailChase' : 'Spin', 3);
      else fox.action('React', 3);
      return part;
    },

    active() { return !!fox && scene().classList.contains('has3d'); },
    get fox() { return fox; },
  };
  window.Pet3D = Pet3D;
})();
