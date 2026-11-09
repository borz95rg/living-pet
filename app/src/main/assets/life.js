(() => {
  'use strict';

  const SAVE_KEY = 'livingPetSave';
  const SAVE_VERSION = 3;
  const MAX_OFFLINE_MS = 14 * 24 * 60 * 60 * 1000;
  const STEP_MS = 15 * 60 * 1000;
  const names = { fox: 'Искра', wolf: 'Туман', cat: 'Плюша', dog: 'Бублик' };
  const emoji = { fox: '🦊', wolf: '🐺', cat: '🐱', dog: '🐶' };
  const traits = { fox: 'любопытная лисица', wolf: 'верный волк', cat: 'независимая кошка', dog: 'весёлая собака' };
  const stages = ['Малыш', 'Детёныш', 'Подросток', 'Взрослый', 'Легенда'];
  const activityNames = {
    idle: 'Осматривает уголок', explore: 'Исследует поляну', forage: 'Ищет ягоды',
    drink: 'Пьёт воду', sleep: 'Сладко спит', play: 'Играет с хвостом',
    groom: 'Умывается', rest: 'Отдыхает', greet: 'Рада встрече',
  };
  const foods = {
    meat: { name: 'мясо', satiety: 42, mood: 2 },
    fish: { name: 'рыбу', satiety: 34, mood: 4 },
    berries: { name: 'ягоды', satiety: 17, mood: 6 },
    treat: { name: 'лакомство', satiety: 23, mood: 13 },
  };
  const discoveries = [
    { id: 'silver-feather', icon: '🪶', name: 'Серебряное перо', hint: 'Лёгкое, но не улетает даже на ветру.' },
    { id: 'old-button', icon: '🟡', name: 'Пуговица с янтарём', hint: 'Внутри будто застыл крошечный солнечный луч.' },
    { id: 'tiny-bell', icon: '🔔', name: 'Тихий колокольчик', hint: 'Звенит только тогда, когда рядом спокойно.' },
    { id: 'moon-stone', icon: '🌙', name: 'Лунный камешек', hint: 'Находится там, где вечером лежит светлая полоса.' },
    { id: 'marked-leaf', icon: '🍃', name: 'Лист с картой', hint: 'Прожилки складываются в знакомый узор долины.' },
  ];
  const $ = id => document.getElementById(id);
  const now = () => Date.now();
  let pet;
  let overlayEnabled = false;

  function clamp(value) { return Math.max(0, Math.min(100, Number(value) || 0)); }
  function freshPet(kind) {
    const time = now();
    return {
      version: SAVE_VERSION, kind, name: names[kind], bornAt: time, xp: 0,
      memories: [{ date: new Date(time).toLocaleDateString('ru-RU'), text: `Сегодня ты встретил ${traits[kind]}.` }],
      lastLine: '', bubble: 'М-м? Кто здесь?', weatherIndex: 0,
      needs: { satiety: 94, water: 88, energy: 92, mood: 86, health: 100, clean: 96, affection: 8 },
      inventory: { meat: 2, fish: 1, berries: 3, treat: 1, water: 2 },
      routine: { play: 0, talk: 0, explore: 0, feed: 0, autonomous: 0, sleep: 0 },
      discoveries: [], mysterySolved: false,
      activity: 'idle', lastActivityAt: time, lastInteractionAt: time,
      lastSimAt: time, nextActionAt: time + 25 * 60 * 1000,
    };
  }

  // Add new fields without discarding saves made by earlier app versions.
  function migrate(data) {
    if (!data || !names[data.kind]) return null;
    const defaults = freshPet(data.kind);
    data.version = SAVE_VERSION;
    data.name = typeof data.name === 'string' && data.name.trim() ? data.name : defaults.name;
    data.bornAt = Number(data.bornAt) || defaults.bornAt;
    data.xp = Math.max(0, Math.min(32, Number(data.xp) || 0));
    data.memories = Array.isArray(data.memories) ? data.memories.slice(0, 40) : defaults.memories;
    data.needs = { ...defaults.needs, ...(data.needs || {}) };
    Object.keys(data.needs).forEach(key => { data.needs[key] = clamp(data.needs[key]); });
    data.inventory = { ...defaults.inventory, ...(data.inventory || {}) };
    Object.keys(data.inventory).forEach(key => { data.inventory[key] = Math.max(0, Math.min(99, Number(data.inventory[key]) || 0)); });
    data.routine = { ...defaults.routine, ...(data.routine || {}) };
    Object.keys(data.routine).forEach(key => { data.routine[key] = Math.max(0, Number(data.routine[key]) || 0); });
    data.discoveries = Array.isArray(data.discoveries)
      ? [...new Set(data.discoveries.filter(id => discoveries.some(item => item.id === id)))].slice(0, discoveries.length)
      : [];
    data.mysterySolved = Boolean(data.mysterySolved) || data.discoveries.length === discoveries.length;
    data.activity = activityNames[data.activity] ? data.activity : 'idle';
    data.lastActivityAt = Number(data.lastActivityAt) || Number(data.updatedAt) || data.bornAt;
    data.lastInteractionAt = Number(data.lastInteractionAt) || data.bornAt;
    data.lastSimAt = Number(data.lastSimAt) || Number(data.updatedAt) || data.bornAt;
    data.nextActionAt = Number(data.nextActionAt) || data.lastSimAt + 30 * 60 * 1000;
    data.weatherIndex = Math.max(0, Math.min(3, Number(data.weatherIndex) || 0));
    return data;
  }

  function read() {
    try {
      let raw = window.PetSave?.load?.();
      if (!raw) raw = localStorage.getItem(SAVE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if ([1, 2, SAVE_VERSION].includes(data.version)) return migrate(data);
    } catch (_) { /* A damaged save never prevents starting a new game. */ }
    return null;
  }

  function write() {
    if (!pet) return;
    pet.version = SAVE_VERSION;
    pet.updatedAt = now();
    const raw = JSON.stringify(pet);
    try {
      if (window.PetSave?.save) window.PetSave.save(raw);
      else localStorage.setItem(SAVE_KEY, raw);
    } catch (_) {
      try { localStorage.setItem(SAVE_KEY, raw); } catch (__) { /* Private storage stays best-effort. */ }
    }
  }

  function remember(text, time = now()) {
    const date = new Date(time).toLocaleDateString('ru-RU');
    const previous = pet.memories[0];
    if (previous && previous.date === date && previous.text === text) return;
    pet.memories.unshift({ date, text });
    pet.memories = pet.memories.slice(0, 40);
  }

  function setActivity(activity, line, time, makeMemory = false) {
    pet.activity = activity;
    pet.lastActivityAt = time;
    pet.lastLine = line;
    if (makeMemory) remember(line, time);
  }

  function autonomousChoice(time) {
    const n = pet.needs;
    const hour = new Date(time).getHours();
    const night = hour >= 22 || hour < 7;
    if (n.water < 39) {
      if (pet.inventory.water > 0) pet.inventory.water--;
      n.water = clamp(n.water + 31);
      n.mood = clamp(n.mood + 2);
      setActivity('drink', pet.inventory.water > 0 ? 'Сама подошла к миске и напилась. Я теперь бодрее!' : 'Нашла в долине ручей и утолила жажду.', time, true);
      return;
    }
    if (n.satiety < 43) {
      pet.inventory.berries = Math.min(99, pet.inventory.berries + 1);
      n.satiety = clamp(n.satiety + 25);
      n.mood = clamp(n.mood + 3);
      setActivity('forage', 'Я нашла ягоды и перекусила. Всё хорошо, не волнуйся.', time, true);
      return;
    }
    if ((night && n.energy < 96) || n.energy < 29) {
      n.energy = clamp(n.energy + (night ? 26 : 19));
      n.mood = clamp(n.mood + 2);
      pet.routine.sleep++;
      setActivity('sleep', night ? 'Свернулась клубочком и поспала. Утром расскажу, что мне снилось.' : 'Немного вздремнула в уютном уголке.', time, true);
      return;
    }
    if (n.clean < 57) {
      n.clean = clamp(n.clean + 27);
      setActivity('groom', 'Умыла мордочку и почистила лапки. Вот теперь порядок!', time, true);
      return;
    }
    if (n.mood < 59) {
      n.mood = clamp(n.mood + 18);
      n.energy = clamp(n.energy - 4);
      setActivity('play', 'Поиграла с хвостом и развеселилась.', time, true);
      return;
    }

    pet.routine.autonomous++;
    const variation = Math.abs(Math.floor((time + pet.bornAt) / (45 * 60 * 1000))) % 4;
    if (variation === 0) {
      n.mood = clamp(n.mood + 4);
      n.energy = clamp(n.energy - 2);
      setActivity('play', 'Покружилась за хвостом — и сама над собой посмеялась.', time, true);
    } else if (variation === 1) {
      pet.inventory.berries = Math.min(99, pet.inventory.berries + 1);
      n.mood = clamp(n.mood + 3);
      setActivity('explore', 'Исследовала поляну и принесла одну ягодку домой.', time, true);
    } else if (variation === 2) {
      n.clean = clamp(n.clean + 12);
      setActivity('groom', 'Пригладила шерсть и послушала тихие звуки долины.', time, true);
    } else {
      n.energy = clamp(n.energy + 8);
      setActivity('rest', 'Отдохнула у окна и посмотрела на облака.', time, true);
    }
  }

  // A small event-driven simulation replaces a permanent background loop.
  // Needs never damage health; the fox finds berries and water on her own.
  function advanceTo(target) {
    if (!pet) return 0;
    const previous = Number(pet.lastSimAt) || pet.bornAt;
    const elapsed = Math.max(0, Math.min(MAX_OFFLINE_MS, target - previous));
    if (elapsed <= 0) return 0;
    const end = previous + elapsed;
    let time = previous;
    while (time < end) {
      const next = Math.min(end, time + STEP_MS);
      const hours = (next - time) / 3600000;
      const n = pet.needs;
      const hour = new Date(next).getHours();
      const night = hour >= 22 || hour < 7;
      n.satiety = clamp(n.satiety - 1.8 * hours);
      n.water = clamp(n.water - 2.2 * hours);
      n.energy = clamp(n.energy - (night ? 0.15 : 1.05) * hours);
      n.mood = clamp(n.mood - 0.35 * hours);
      n.clean = clamp(n.clean - 0.22 * hours);
      n.health = clamp(Math.max(85, n.health));

      if (next >= pet.nextActionAt) {
        autonomousChoice(next);
        pet.nextActionAt = next + (35 + Math.abs(Math.floor(next / 60000)) % 55) * 60 * 1000;
      }
      time = next;
    }
    pet.lastSimAt = target;
    return elapsed;
  }

  function ageStage() {
    const days = Math.floor((now() - pet.bornAt) / 86400000) + 1;
    return { days, stage: Math.min(4, Math.floor(pet.xp / 8)) };
  }

  function setBar(key, value) {
    const number = Math.round(clamp(value));
    $(`${key}Value`).textContent = `${number}%`;
    const bar = $(`${key}Bar`);
    bar.style.width = `${number}%`;
    bar.style.background = number < 35 ? '#dfa18b' : number < 60 ? '#d9bc78' : '#91bea0';
  }

  function applyWeather() {
    const weather = ['☀️ Ясно', '🌧️ Дождик', '❄️ Снежок', '🌬️ Ветер'];
    $('weather').textContent = weather[pet.weatherIndex];
    const backgrounds = [
      '',
      'linear-gradient(#b8cfce 0%,#d9e8df 68%,#bdcdb8 68%,#97b392 100%)',
      'linear-gradient(#d9e7ef 0%,#eff3f1 68%,#dbe7e2 68%,#b9d0cb 100%)',
      'linear-gradient(#bfd5d5 0%,#e2e9dd 68%,#c5d4bf 68%,#a3bf9b 100%)',
    ];
    $('scene').style.background = backgrounds[pet.weatherIndex];
  }

  function personality() {
    const counts = pet.routine;
    const list = [
      ['любопытство', counts.explore], ['игривость', counts.play],
      ['общительность', counts.talk], ['самостоятельность', counts.autonomous],
    ].sort((a, b) => b[1] - a[1]);
    return list[0][1] > 0 ? `Привычка: ${list[0][0]}` : 'Пока только знакомится с миром';
  }

  function chapterText() {
    const { days, stage } = ageStage();
    const counts = pet.routine;
    const habits = [
      ['исследовать новые места', counts.explore], ['играть вместе', counts.play],
      ['разговаривать', counts.talk], ['самостоятельно открывать мир', counts.autonomous],
      ['принимать ласку', counts.petting || 0],
    ].sort((a, b) => b[1] - a[1]);
    const bond = pet.needs.affection >= 70
      ? 'Вы уже привыкли друг к другу, и питомец смело делится своими открытиями.'
      : pet.needs.affection >= 30
        ? 'Питомец начинает узнавать твои привычки и всё смелее подходит поближе.'
        : 'Вы пока только знакомитесь, и каждое спокойное мгновение помогает ей освоиться.';
    const openings = {
      fox: `На ${days}-й день ${pet.name} заметила за окном едва различимый след и решила выяснить, куда он ведёт.`,
      wolf: `На ${days}-й день ${pet.name} обошёл свой уголок и убедился, что здесь всё спокойно.`,
      cat: `На ${days}-й день ${pet.name} выбрала самое уютное место и наблюдала, как меняется свет.`,
      dog: `На ${days}-й день ${pet.name} первым услышал знакомые шаги и радостно побежал навстречу.`,
    };
    const recent = pet.memories[0]?.text;
    const habit = habits[0][1] > 0 ? `Любимое занятие — ${habits[0][0]}.` : 'Пока питомец с любопытством пробует всё понемногу.';
    const lastMoment = recent ? `А в последней записи осталось: «${recent}»` : 'Впереди у вас ещё много маленьких открытий.';
    const stageLine = stage >= 4 ? 'Питомец стал легендой вашей долины.' : stage >= 3 ? 'Питомец уже вырос и увереннее выбирает свой путь.' : stage >= 2 ? 'Питомец подрос и всё чаще отправляется исследовать новое.' : stage >= 1 ? 'Питомец понемногу осваивается и становится смелее.' : 'Это только начало вашей общей истории.';
    const clue = pet.mysterySolved
      ? 'Пять странных находок сложились в карту тайного уголка долины.'
      : pet.discoveries.length > 0
        ? `В коллекции уже ${pet.discoveries.length} из ${discoveries.length} загадочных находок.`
        : 'На поляне ещё ждут загадочные находки.';
    return `${openings[pet.kind]} ${stageLine} ${habit} ${bond} ${clue} ${lastMoment}`;
  }

  function openJournal() {
    if (!pet) { toast('Сначала выбери питомца'); return; }
    const { days, stage } = ageStage();
    $('journalTitle').textContent = `История ${pet.name}`;
    $('chapterTitle').textContent = `Глава ${Math.max(1, Math.ceil(days / 3))} · ${stages[stage]}`;
    $('chapterText').textContent = chapterText();
    const list = $('journalList');
    list.replaceChildren();
    pet.memories.slice(0, 10).forEach(item => {
      const row = document.createElement('li');
      const date = document.createElement('time');
      const text = document.createElement('span');
      date.textContent = item.date;
      text.textContent = item.text;
      row.append(date, text);
      list.append(row);
    });
    const owned = new Set(pet.discoveries);
    const collection = $('discoveryList');
    collection.replaceChildren();
    discoveries.forEach((item, index) => {
      const row = document.createElement('li');
      const icon = document.createElement('span');
      const text = document.createElement('span');
      icon.textContent = owned.has(item.id) ? item.icon : '❔';
      text.textContent = owned.has(item.id) ? `${item.name} — ${item.hint}` : `Загадка ${index + 1} · не найдена`;
      row.append(icon, text);
      if (owned.has(item.id)) row.classList.add('found');
      collection.append(row);
    });
    $('discoveryProgress').textContent = pet.mysterySolved
      ? 'Все находки собраны · тайна долины раскрыта'
      : `Находки ${pet.discoveries.length} из ${discoveries.length}`;
    $('journalDialog').hidden = false;
  }

  function show() {
    if (!pet) return;
    const { days, stage } = ageStage();
    $('select').classList.add('hide');
    $('petName').textContent = pet.name;
    $('pet').dataset.kind = pet.kind;
    $('stage').textContent = `${stages[stage]} · ${traits[pet.kind]}`;
    $('age').textContent = `День ${days}`;
    $('memory').textContent = `✦ Воспоминания: ${pet.memories.length}`;
    $('prog').style.width = `${(pet.xp % 8) / 8 * 100}%`;
    $('chat').textContent = pet.lastLine || welcome();
    $('bubble').textContent = pet.bubble || 'М-м? Кто здесь?';
    $('behavior').textContent = activityNames[pet.activity] || activityNames.idle;
    setBar('satiety', pet.needs.satiety);
    setBar('water', pet.needs.water);
    setBar('energy', pet.needs.energy);
    setBar('mood', pet.needs.mood);
    setBar('clean', pet.needs.clean);
    setBar('health', pet.needs.health);
    setBar('affection', pet.needs.affection);
    $('inventory').textContent = `Запасы: мясо ${pet.inventory.meat} · рыба ${pet.inventory.fish} · ягоды ${pet.inventory.berries} · лакомства ${pet.inventory.treat} · вода в миске ${pet.inventory.water} · ${personality()}`;

    const hour = new Date().getHours();
    $('greeting').textContent = hour < 6 ? 'Тихая ночь' : hour < 11 ? 'Доброе утро' : hour < 18 ? 'Хороший день' : 'Тёплый вечер';
    const night = hour < 6 || hour >= 21;
    $('scene').classList.toggle('night', night);
    $('sky').textContent = night ? '🌙' : '☀️';
    applyWeather();
    write();
  }

  function welcome() {
    return ({
      fox: 'Я успела немного погулять, пока тебя не было. Хорошо, что ты вернулся!',
      wolf: 'Я здесь и всё спокойно. Рад, что ты заглянул.',
      cat: 'Я выбрала уютное место. Ты как раз вовремя.',
      dog: 'Ты пришёл! Я тут кое-что исследовал.',
    })[pet.kind];
  }

  function lineFor(action) {
    const lines = {
      fox: { play: 'О! Поймай эту солнечную пылинку!', talk: 'Как думаешь, куда исчезают сны? Я веду записи.', explore: 'Нашла на полянке кое-что интересное.', weather: 'Я выглянула в окно. Небо меняется, как настроение.' },
      wolf: { play: 'Поймаю игрушку. А потом просто побудем рядом?', talk: 'Не обязательно всё успевать. Я подожду.', explore: 'Я обошёл комнату. Всё спокойно, можно отдыхать.', weather: 'Смотрю на небо из окна.' },
      cat: { play: 'Ладно, одну минутку поиграю. Может быть, две.', talk: 'Я слышу тебя. Можешь рассказать ещё.', explore: 'Нашла полку повыше. Вид оттуда отличный.', weather: 'Солнце греет подоконник. Одобряю.' },
      dog: { play: 'Ура! Давай ещё раз! Теперь я за игрушкой!', talk: 'Мне нравится, когда ты со мной разговариваешь.', explore: 'Я всё обнюхал. Кажется, тут есть новый уголок!', weather: 'Давай посмотрим на небо вместе!' },
    };
    return lines[pet.kind][action];
  }

  function showFoodMenu() {
    if (!pet) return;
    $('foodTitle').textContent = `Чем угостить ${pet.name}?`;
    for (const item of Object.keys(foods)) {
      $(`${item}Count`).textContent = `Осталось: ${pet.inventory[item]}`;
      document.querySelector(`[data-food="${item}"]`).disabled = pet.inventory[item] <= 0;
    }
    $('foodMenu').hidden = false;
  }

  function feed(item) {
    if (!foods[item] || pet.inventory[item] <= 0) {
      toast('Такой еды пока нет. Искра сама поищет ягоды.');
      return;
    }
    pet.inventory[item]--;
    pet.needs.satiety = clamp(pet.needs.satiety + foods[item].satiety);
    pet.needs.mood = clamp(pet.needs.mood + foods[item].mood);
    pet.needs.affection = clamp(pet.needs.affection + 2);
    pet.routine.feed++;
    pet.lastInteractionAt = now();
    const line = `Спасибо за ${foods[item].name}! Теперь я сыта и довольна.`;
    setActivity('play', line, now(), true);
    pet.bubble = 'ням-ням, спасибо!';
    $('foodMenu').hidden = true;
    show();
    toast('Угощение сохранено в истории');
  }

  function act(type) {
    if (!pet) return;
    if (type === 'feed') { showFoodMenu(); return; }
    if (type === 'water') {
      pet.inventory.water = Math.min(4, pet.inventory.water + 2);
      pet.lastInteractionAt = now();
      setActivity('drink', 'Я наполнила миску свежей водой. Спасибо, что позаботился!', now(), true);
      pet.bubble = 'вода свежая 💧';
      show(); toast('В миске теперь есть вода'); return;
    }

    pet.lastInteractionAt = now();
    pet.routine[type] = (pet.routine[type] || 0) + 1;
    pet.needs.affection = clamp(pet.needs.affection + (type === 'talk' ? 3 : 1));
    let line = lineFor(type);
    if (type === 'play') {
      pet.needs.mood = clamp(pet.needs.mood + 13);
      pet.needs.energy = clamp(pet.needs.energy - 7);
      pet.needs.satiety = clamp(pet.needs.satiety - 2);
      pet.bubble = 'ха-ха! ещё раз!';
      setActivity('play', line, now());
    } else if (type === 'talk') {
      pet.needs.mood = clamp(pet.needs.mood + 6);
      pet.bubble = 'Я слушаю тебя.';
      setActivity('rest', line, now());
    } else if (type === 'explore') {
      pet.needs.energy = clamp(pet.needs.energy - 4);
      pet.needs.satiety = clamp(pet.needs.satiety - 1);
      pet.inventory.berries = Math.min(99, pet.inventory.berries + 1);
      const next = discoveries.find(item => !pet.discoveries.includes(item.id));
      if (next) {
        pet.discoveries.push(next.id);
        line = `${next.icon} Нашли «${next.name}». ${next.hint}`;
        if (pet.discoveries.length === discoveries.length && !pet.mysterySolved) {
          pet.mysterySolved = true;
          pet.xp = Math.min(32, pet.xp + 2);
          line += ' Все части карты сошлись — тайный уголок найден!';
        }
        remember(line);
        pet.bubble = pet.mysterySolved ? 'мы раскрыли тайну! ✨' : 'одна загадка разгадана!';
      } else {
        line = pet.mysterySolved
          ? 'Мы снова заглянули в тайный уголок. Теперь это наше особое место.'
          : 'Находок пока нет. Может быть, загадка откроется во время следующей прогулки?';
        pet.bubble = pet.mysterySolved ? 'наш секретный уголок 💛' : 'поищем ещё?';
      }
      setActivity('explore', line, now());
    } else if (type === 'weather') {
      pet.weatherIndex = (pet.weatherIndex + 1) % 4;
      const reactions = ['Какое спокойное небо.', 'Посмотрю на дождь из тёплой комнаты.', 'Снежинки! Поймаю одну лапкой.', 'Ветер щекочет уши. Пойду в укрытие.'];
      line = reactions[pet.weatherIndex];
      pet.bubble = pet.weatherIndex === 1 ? 'дождик шумит…' : pet.weatherIndex === 2 ? 'снежинка!' : pet.weatherIndex === 3 ? 'у-ух, ветрено' : 'солнечный день';
      setActivity('explore', line, now());
    }
    show();
    toast(type === 'explore' ? 'Найденная ягода добавлена в запасы' : 'Маленький момент вместе');
  }

  function tapPet() {
    if (!pet) return;
    pet.xp = Math.min(32, pet.xp + 1);
    pet.needs.mood = clamp(pet.needs.mood + 4);
    pet.needs.affection = clamp(pet.needs.affection + 4);
    pet.routine.petting = (pet.routine.petting || 0) + 1;
    pet.lastInteractionAt = now();
    pet.bubble = ['мур-р…', 'приятно!', 'я тут!', 'ещё немножко?'][Math.floor(Math.random() * 4)];
    const line = pet.kind === 'cat' ? 'Я заметила твою руку. Можно ещё погладить.' : pet.kind === 'dog' ? 'Ура, ты меня погладил!' : 'Я чувствую твоё прикосновение. Хорошо, что ты рядом.';
    setActivity('greet', line, now(), true);
    show(); toast(`${pet.name} запомнил этот момент`);
  }

  function toast(text) {
    const el = $('toast');
    el.textContent = text;
    el.classList.add('on');
    setTimeout(() => el.classList.remove('on'), 1800);
  }

  document.querySelectorAll('.choice').forEach(button => {
    button.onclick = () => {
      const kind = button.dataset.kind;
      if (overlayEnabled && kind !== 'fox' && window.PetSave) {
        window.PetSave.disableOverlay();
        window.overlayStateChanged(false);
      }
      pet = freshPet(kind);
      write(); show();
    };
  });
  document.querySelectorAll('.action').forEach(button => { button.onclick = () => act(button.dataset.act); });
  document.querySelectorAll('[data-food]').forEach(button => { button.onclick = () => feed(button.dataset.food); });
  $('foodClose').onclick = () => { $('foodMenu').hidden = true; };
  $('foodMenu').onclick = event => { if (event.target === $('foodMenu')) $('foodMenu').hidden = true; };
  $('petTap').onclick = tapPet;
  $('overlayBtn').onclick = () => {
    if (!pet) { toast('Сначала выбери питомца'); return; }
    if (pet.kind !== 'fox') { toast('Плавающий 3D-питомец сейчас доступен для лисицы'); return; }
    if (window.PetSave) {
      if (overlayEnabled && window.PetSave.disableOverlay) window.PetSave.disableOverlay();
      else if (window.PetSave.enableOverlay) window.PetSave.enableOverlay();
    } else toast('Плавающий питомец доступен в Android-приложении');
  };
  window.overlayStateChanged = enabled => {
    overlayEnabled = enabled;
    $('overlayBtn').textContent = enabled ? '🐾' : '＋';
    toast(enabled ? 'Питомец появился поверх экрана' : 'Плавающий режим выключен');
  };
  $('journalBtn').onclick = openJournal;
  $('journalClose').onclick = () => { $('journalDialog').hidden = true; };
  $('journalDialog').onclick = event => { if (event.target === $('journalDialog')) $('journalDialog').hidden = true; };

  pet = read();
  if (pet) {
    const awayFor = advanceTo(now());
    if (awayFor > 2 * 60 * 60 * 1000) {
      pet.bubble = 'Я погуляла и отдохнула, пока тебя не было.';
      if (pet.activity === 'sleep') pet.lastLine = 'Я выспалась, нашла воды и немного ягод. Рада тебя видеть!';
    }
    show();
  } else $('select').classList.remove('hide');

  if (window.PetSave?.overlayEnabled) {
    overlayEnabled = window.PetSave.overlayEnabled();
    $('overlayBtn').textContent = overlayEnabled ? '🐾' : '＋';
  }

  setInterval(() => {
    if (!pet || document.hidden) return;
    advanceTo(now());
    show();
  }, 60 * 1000);

  document.addEventListener('visibilitychange', () => {
    if (document.hidden || !pet) return;
    const previousSave = Number(pet.updatedAt) || 0;
    const current = read();
    if (current && Number(current.updatedAt) > previousSave) pet = current;
    advanceTo(now());
    show();
  });
})();
