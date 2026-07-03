/**
 * Axiom AI - Single Page Application Core
 * Vanilla JS Client for Python backend API
 */

// Application State
const STATE = {
  // Localization dictionary
  tr: {},
  // Lists
  universes: [],
  selectedUniversePath: null,
  selectedSaveId: null,
  activeSession: null, // { db_path, save_id, difficulty, turn_id }
  
  // Settings
  config: null,
  models: [],
  personas: [], // { persona_id, name, description } -- Settings "Personas" tab + Setup picker

  // Creator Studio Data
  creatorData: null, // metadata, entities, rules, lore, setup questions, map, events, items
  creatorModified: false,
  creatorActiveEntityId: null,
  creatorActiveRuleId: null,
  
  // Timeline State
  checkpoints: [],
  maxTurnId: 0,

  // Map graphics view state
  mapNodes: [], // { id, name, scale, x, y }
  mapEdges: [], // { source, target, distance }
  selectedMapNodeId: null,
  selectedMapEdge: null,
  mapDragNode: null,
  mapCanvasOffset: { x: 0, y: 0 },
  mapConnectingSource: null,

  // Text playback state
  typewriterTimer: null,
  isGenerating: false,

  // Ambiance audio (crossfade, mirrors ui/ambiance_manager.py)
  ambianceTag: null,
  ambianceVolume: 0.5,
  ambianceFadeTimer: null,
};

// ── Application Initialization ──
document.addEventListener('DOMContentLoaded', async () => {
  await loadTranslations();
  await loadConfig();
  await loadPersonas();
  setupUIEventListeners();
  setupModalHandlers();
  setupTabHandlers();
  setupCanvasMapHandlers();
  setupSidebarMiniTabs();
  await refreshHub();
});

// ── i18n & Translation ──
async function loadTranslations() {
  try {
    const res = await fetch('/api/translations');
    STATE.tr = await res.json();
    localizeDocument();
  } catch (err) {
    console.error('Failed to load translations:', err);
  }
}

function tr(key, kwargs = {}) {
  let text = STATE.tr[key] || key;
  for (const [k, v] of Object.entries(kwargs)) {
    text = text.replace(`{${k}}`, v);
  }
  // Strip Qt mnemonics (e.g. "&Settings" -> "Settings", "Quick &Tour" -> "Quick Tour")
  // but preserve standard conjunction ampersands like "Session, Turn & Clock".
  return text.replace(/&([a-zA-Z])/g, '$1');
}

function localizeDocument() {
  document.querySelectorAll('[data-tr]').forEach(el => {
    const key = el.getAttribute('data-tr');
    el.textContent = tr(key);
  });
  document.querySelectorAll('[data-tr-placeholder]').forEach(el => {
    const key = el.getAttribute('data-tr-placeholder');
    el.placeholder = tr(key);
  });
}

// ── Config & Settings ──
async function loadConfig() {
  try {
    const res = await fetch('/api/settings');
    STATE.config = await res.json();
    // Inject values to general settings inputs
    document.getElementById('setting-language').innerHTML = '';
    const langs = {
      "en": "English", "fr": "Français", "es": "Español", "de": "Deutsch",
      "it": "Italiano", "pt": "Português", "ru": "Русский", "zh": "简体中文",
      "ja": "日本語", "ko": "한국어"
    };
    for (const [code, name] of Object.entries(langs)) {
      const opt = document.createElement('option');
      opt.value = code;
      opt.textContent = name;
      document.getElementById('setting-language').appendChild(opt);
    }
    document.getElementById('setting-language').value = STATE.config.language || 'en';
    document.getElementById('setting-font-size').value = STATE.config.ui_font_size || 14;
    document.getElementById('setting-rag-chunks').value = STATE.config.rag_chunk_count || 5;
    document.getElementById('setting-audio-enabled').checked = STATE.config.enable_audio;

    // LLM inputs
    document.getElementById('setting-llm-backend').value = STATE.config.llm_backend || 'universal';
    document.getElementById('setting-universal-url').value = STATE.config.universal_base_url || '';
    document.getElementById('setting-api-key').value = STATE.config.universal_api_key || STATE.config.gemini_api_key || '';
    document.getElementById('setting-model-name').value = STATE.config.universal_model || STATE.config.gemini_model || '';
    document.getElementById('setting-fallback-model').value = STATE.config.gemini_fallback_model || '';
    document.getElementById('setting-requests-limit').value = STATE.config.llm_requests_per_minute || 0;
    document.getElementById('setting-extraction-model').value = STATE.config.extraction_model || '';
    document.getElementById('setting-time-model').value = STATE.config.time_model || '';
    document.getElementById('setting-timekeeper-enabled').checked = STATE.config.timekeeper_enabled;

    // Image inputs
    document.getElementById('setting-image-enabled').checked = STATE.config.image_generation_enabled;
    document.getElementById('setting-image-backend').value = STATE.config.image_backend || 'gemini';
    document.getElementById('setting-image-url').value = STATE.config.image_api_url || '';
    document.getElementById('setting-image-width').value = STATE.config.image_width || 512;
    document.getElementById('setting-image-height').value = STATE.config.image_height || 512;
    document.getElementById('setting-image-steps').value = STATE.config.image_steps || 20;
    document.getElementById('setting-image-cfg').value = STATE.config.image_cfg_scale || 7.0;
    document.getElementById('setting-image-workflow').value = STATE.config.image_comfyui_workflow || '';

    // Adjust font size on document
    document.body.style.fontSize = `${STATE.config.ui_font_size}px`;
  } catch (err) {
    console.error('Failed to load settings:', err);
  }
}

async function saveConfig() {
  if (!STATE.config) return;
  const backend = document.getElementById('setting-llm-backend').value;
  const key = document.getElementById('setting-api-key').value;
  const model = document.getElementById('setting-model-name').value;

  STATE.config.language = document.getElementById('setting-language').value;
  STATE.config.ui_font_size = parseInt(document.getElementById('setting-font-size').value) || 14;
  STATE.config.rag_chunk_count = parseInt(document.getElementById('setting-rag-chunks').value) || 5;
  STATE.config.enable_audio = document.getElementById('setting-audio-enabled').checked;

  STATE.config.llm_backend = backend;
  if (backend === 'universal') {
    STATE.config.universal_base_url = document.getElementById('setting-universal-url').value;
    STATE.config.universal_api_key = key;
    STATE.config.universal_model = model;
  } else {
    STATE.config.gemini_api_key = key;
    STATE.config.gemini_model = model;
    STATE.config.gemini_fallback_model = document.getElementById('setting-fallback-model').value;
    STATE.config.llm_requests_per_minute = parseInt(document.getElementById('setting-requests-limit').value) || 0;
  }
  
  STATE.config.extraction_model = document.getElementById('setting-extraction-model').value;
  STATE.config.time_model = document.getElementById('setting-time-model').value;
  STATE.config.timekeeper_enabled = document.getElementById('setting-timekeeper-enabled').checked;

  STATE.config.image_generation_enabled = document.getElementById('setting-image-enabled').checked;
  STATE.config.image_backend = document.getElementById('setting-image-backend').value;
  STATE.config.image_api_url = document.getElementById('setting-image-url').value;
  STATE.config.image_width = parseInt(document.getElementById('setting-image-width').value) || 512;
  STATE.config.image_height = parseInt(document.getElementById('setting-image-height').value) || 512;
  STATE.config.image_steps = parseInt(document.getElementById('setting-image-steps').value) || 20;
  STATE.config.image_cfg_scale = parseFloat(document.getElementById('setting-image-cfg').value) || 7.0;
  STATE.config.image_comfyui_workflow = document.getElementById('setting-image-workflow').value;

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(STATE.config)
    });
    if (res.ok) {
      await savePersonas(); // Settings "Save" persists personas too, like ui/settings_dialog.py
      await loadTranslations();
      await loadConfig();
      if (!isAudioEnabled()) stopAmbiance();
      closeAllModals();
      showStatus('Settings saved successfully.');
    } else {
      alert('Error saving settings.');
    }
  } catch (err) {
    console.error(err);
  }
}

// ── Global Personas (Settings tab + Setup wizard picker) ──
async function loadPersonas() {
  try {
    const res = await fetch('/api/personas');
    STATE.personas = await res.json();
    fillPersonasTable();
  } catch (err) {
    console.error('Failed to load personas:', err);
  }
}

function fillPersonasTable() {
  const table = document.getElementById('table-personas');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  tbody.innerHTML = '';
  (STATE.personas || []).forEach((p, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" value="${p.name || ''}" data-key="name" data-idx="${idx}"></td>
      <td><input type="text" value="${p.description || ''}" data-key="description" data-idx="${idx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.personas.splice(idx, 1);
      fillPersonasTable();
    };
    tr.querySelectorAll('input').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const i = parseInt(e.target.getAttribute('data-idx'));
        STATE.personas[i][key] = e.target.value;
      };
    });
    tbody.appendChild(tr);
  });
}

async function savePersonas() {
  try {
    await fetch('/api/personas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ personas: STATE.personas || [] })
    });
  } catch (err) {
    console.error('Failed to save personas:', err);
  }
}

function generatePersonaId() {
  return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `persona_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

async function populateSetupPersonaPicker() {
  const select = document.getElementById('setup-persona-picker');
  if (!select) return;
  try {
    const res = await fetch('/api/personas');
    const personas = await res.json();
    personas.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.persona_id;
      opt.textContent = p.name;
      opt.dataset.description = p.description || '';
      select.appendChild(opt);
    });
    select.onchange = () => {
      const opt = select.selectedOptions[0];
      if (select.value && opt) {
        document.getElementById('setup-player-persona').value = opt.dataset.description || '';
      }
    };
  } catch (err) {
    console.error('Failed to load personas for setup picker:', err);
  }
}

// ── Screen Navigation Router ──
function showScreen(screenId) {
  document.querySelectorAll('.screen-view').forEach(view => {
    view.classList.remove('active');
  });
  document.getElementById(screenId).classList.add('active');
}

// ── Hub & Save Library ──
async function refreshHub() {
  try {
    const res = await fetch('/api/universes');
    STATE.universes = await res.json();
    renderUniverseGrid();
  } catch (err) {
    console.error('Failed to load universes:', err);
  }
}

function renderUniverseGrid() {
  const grid = document.getElementById('universe-grid');
  grid.innerHTML = '';

  STATE.universes.forEach(uni => {
    const card = document.createElement('div');
    card.className = 'universe-card';
    card.innerHTML = `
      <h3>${uni.name}</h3>
      <p class="desc">${uni.description || ''}</p>
      <div class="path">${uni.path}</div>
      <div class="card-saves-list">
        <!-- Saves listed here -->
      </div>
      <div class="card-footer">
        <button class="btn-primary play-new-btn" data-tr="play">Play New</button>
        <button class="btn-secondary edit-uni-btn" data-tr="edit">Edit Universe</button>
        <button class="btn-danger delete-uni-btn" data-tr="delete">Delete</button>
      </div>
    `;

    // Localize buttons in cards
    card.querySelectorAll('[data-tr]').forEach(el => {
      el.textContent = tr(el.getAttribute('data-tr'));
    });

    const savesList = card.querySelector('.card-saves-list');
    if (!uni.saves || uni.saves.length === 0) {
      savesList.innerHTML = `<div class="save-meta" style="padding: 4px;">No save files.</div>`;
    } else {
      uni.saves.forEach(save => {
        const item = document.createElement('div');
        item.className = 'save-item';
        item.innerHTML = `
          <div>
            <div class="save-name">${save.player_name}</div>
            <div class="save-meta">${save.difficulty} · Turn ${save.turn_id} · ${new Date(save.last_updated).toLocaleString()}</div>
          </div>
          <div class="save-actions">
            <button class="btn-primary btn-sm play-save-btn">▶</button>
            <button class="btn-secondary btn-sm edit-save-btn">Edit</button>
            <button class="btn-secondary btn-sm fork-save-btn">Fork</button>
            <button class="btn-danger btn-sm delete-save-btn">×</button>
          </div>
        `;

        item.querySelector('.play-save-btn').onclick = () => startSession(uni.path, save.save_id, save.difficulty);
        item.querySelector('.edit-save-btn').onclick = () => editSave(uni.path, save.save_id);
        item.querySelector('.fork-save-btn').onclick = () => forkSave(uni.path, save.save_id, save.turn_id);
        item.querySelector('.delete-save-btn').onclick = () => deleteSave(uni.path, save.save_id);
        savesList.appendChild(item);
      });
    }

    card.querySelector('.play-new-btn').onclick = () => loadSetupView(uni.path);
    card.querySelector('.edit-uni-btn').onclick = () => openCreatorStudio(uni.path);
    card.querySelector('.delete-uni-btn').onclick = () => deleteUniverse(uni.path);

    grid.appendChild(card);
  });
}

async function deleteUniverse(path) {
  if (!confirm('Are you sure you want to delete this universe? All source files and compile databases will be lost.')) return;
  try {
    const res = await fetch('/api/universes/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    if (res.ok) {
      refreshHub();
    } else {
      alert('Failed to delete universe.');
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteSave(universePath, saveId) {
  if (!confirm('Are you sure you want to delete this save? This action is permanent.')) return;
  try {
    const res = await fetch('/api/saves/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe_path: universePath, save_id: saveId })
    });
    if (res.ok) {
      refreshHub();
    } else {
      alert('Failed to delete save.');
    }
  } catch (err) {
    console.error(err);
  }
}

async function forkSave(universePath, saveId, maxTurnId) {
  const turnStr = prompt(`Enter turn number to fork from (0 to ${maxTurnId}):`, maxTurnId);
  if (turnStr === null) return;
  const turn = parseInt(turnStr);
  if (isNaN(turn) || turn < 0 || turn > maxTurnId) {
    alert('Invalid turn number.');
    return;
  }
  const newName = prompt('Enter new player name for forked timeline:', 'Timeline B');
  if (!newName) return;

  try {
    const res = await fetch('/api/saves/fork', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe_path: universePath, save_id: saveId, turn_id: turn, name: newName })
    });
    if (res.ok) {
      refreshHub();
      showStatus('Save forked successfully.');
    } else {
      alert('Failed to fork save.');
    }
  } catch (err) {
    console.error(err);
  }
}

// ── Setup View (New Save Questionnaire) ──
async function loadSetupView(universePath) {
  STATE.selectedUniversePath = universePath;
  try {
    const res = await fetch(`/api/setup/questions?universe=${encodeURIComponent(universePath)}`);
    const data = await res.json();
    
    const container = document.getElementById('setup-questions-container');
    container.innerHTML = '';

    // Add Player details block
    container.innerHTML = `
      <div class="setup-question-box">
        <label>Player Name</label>
        <input type="text" id="setup-player-name" value="Alice" required style="width:100%;">
      </div>
      <div class="setup-question-box">
        <label>Saved Persona (optional)</label>
        <select id="setup-persona-picker" style="width:100%;">
          <option value="">-- Write your own below --</option>
        </select>
      </div>
      <div class="setup-question-box">
        <label>Player Persona Description</label>
        <textarea id="setup-player-persona" placeholder="A reformed clockwork thief..." rows="2" style="width:100%;"></textarea>
      </div>
      <div class="setup-question-box">
        <label>Difficulty Mode</label>
        <select id="setup-difficulty" style="width:100%;">
          <option value="Normal">Normal</option>
          <option value="Companion">Companion Mode</option>
          <option value="Hardcore">Hardcore (Permadeath)</option>
        </select>
      </div>
    `;

    await populateSetupPersonaPicker();

    if (data.questions && data.questions.length > 0) {
      data.questions.forEach(q => {
        const box = document.createElement('div');
        box.className = 'setup-question-box';
        box.setAttribute('data-id', q.setup_id);

        const label = document.createElement('label');
        label.textContent = q.question;
        box.appendChild(label);

        if (q.type === 'choice' || q.type === 'single_choice' || q.type === 'multi_choice') {
          const selectType = q.type === 'multi_choice' ? 'checkbox' : 'radio';
          const choiceGrid = document.createElement('div');
          choiceGrid.className = 'choice-grid';

          const options = Array.isArray(q.options) ? q.options : JSON.parse(q.options || '[]');
          options.forEach((opt, oIdx) => {
            const optLabel = document.createElement('label');
            optLabel.className = 'choice-option';
            optLabel.innerHTML = `
              <input type="${selectType}" name="setup_q_${q.setup_id}" value="${opt}" ${oIdx === 0 ? 'checked' : ''}>
              <span>${opt}</span>
            `;
            choiceGrid.appendChild(optLabel);
          });
          box.appendChild(choiceGrid);
        } else {
          const input = document.createElement('input');
          input.type = 'text';
          input.name = `setup_q_${q.setup_id}`;
          input.style.width = '100%';
          input.placeholder = 'Type your answer...';
          box.appendChild(input);
        }
        container.appendChild(box);
      });
    }

    showScreen('view-setup');
  } catch (err) {
    console.error(err);
    alert('Failed to load questionnaire.');
  }
}

// ── Game Session Logic (Tabletop) ──
async function startSession(universePath, saveId, difficulty) {
  showStatus('Loading session...');
  try {
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe_path: universePath, save_id: saveId, difficulty })
    });
    if (res.ok) {
      STATE.activeSession = await res.json();
      document.getElementById('chat-save-title').textContent = `${STATE.activeSession.universe_name} - ${STATE.activeSession.player_name}`;
      document.getElementById('chat-mode-tag').textContent = STATE.activeSession.difficulty;
      rebuildChatFromHistory();
      updateAmbiance('exploration'); // default ambiance on session load, mirrors tabletop_view.py
      STATE.pendingIntents = {};
      updateMultiplayerLobby();

      await refreshTabletopState();
      showScreen('view-tabletop');
      showStatus('Ready.');
    } else {
      let errMsg = 'Failed to start session.';
      try {
        const errData = await res.json();
        if (errData && errData.error) {
          errMsg += `\nError: ${errData.error}`;
        }
      } catch (e) {}
      alert(errMsg);
    }
  } catch (err) {
    console.error(err);
    alert('Network error starting session.');
  }
}

async function refreshTabletopState() {
  if (!STATE.activeSession) return;
  // Stats Sidebar
  const statsList = document.getElementById('tabletop-entities-list');
  statsList.innerHTML = '';
  for (const [eid, stats] of Object.entries(STATE.activeSession.current_stats || {})) {
    const name = eid === 'player' ? STATE.activeSession.player_name : eid;
    const box = document.createElement('div');
    box.className = 'entity-box';
    box.innerHTML = `
      <div class="entity-box-header">
        <span>${name}</span>
        <span class="type">${eid === 'player' ? 'player' : 'npc'}</span>
      </div>
    `;
    for (const [k, v] of Object.entries(stats)) {
      const row = document.createElement('div');
      row.className = 'entity-stat-row';
      row.innerHTML = `<span>${k}</span><span class="val">${v}</span>`;
      box.appendChild(row);
    }
    statsList.appendChild(box);
  }

  // Current Location & Spatial nav
  const currentLoc = STATE.activeSession.current_location || '-';
  document.getElementById('tabletop-current-location').textContent = currentLoc;
  const travelOps = document.getElementById('tabletop-travel-options');
  travelOps.innerHTML = '';
  if (STATE.activeSession.spatial_neighbors && STATE.activeSession.spatial_neighbors.length > 0) {
    STATE.activeSession.spatial_neighbors.forEach(n => {
      const btn = document.createElement('button');
      btn.className = 'btn-secondary btn-sm w-100 m-b-8';
      btn.textContent = `${n.name} (${n.distance_km} km)`;
      btn.onclick = () => sendTravelIntent(n.location_id, n.name);
      travelOps.appendChild(btn);
    });
  } else {
    travelOps.innerHTML = `<span class="save-meta">No connection nodes.</span>`;
  }

  // Timeline
  document.getElementById('timeline-clock').textContent = STATE.activeSession.time_formatted;

  // Fetch timeline checkpoints
  try {
    const res = await fetch('/api/session/checkpoints');
    const checkpoints = await res.json();
    STATE.checkpoints = checkpoints;
    const maxTurn = STATE.activeSession.turn_id;
    const slider = document.getElementById('timeline-slider');
    slider.max = maxTurn;
    slider.value = maxTurn;
    document.getElementById('timeline-turn-label').textContent = `Turn ${maxTurn}`;
  } catch (err) {
    console.error(err);
  }

  await refreshInventory();
}

// ── Inventory (left sidebar tab) ──
const RARITY_COLORS = {
  common: '#cdd6f4',
  rare: '#4fa3ff',
  epic: '#a335ee',
  legendary: '#ff8000'
};

async function refreshInventory() {
  const container = document.getElementById('tabletop-inventory-list');
  if (!container) return;
  try {
    const res = await fetch('/api/session/inventory');
    const data = await res.json();
    container.innerHTML = '';

    const entityIds = Object.keys(data || {});
    if (entityIds.length === 0) {
      container.innerHTML = `<span class="save-meta" style="padding: 8px;">No items.</span>`;
      return;
    }

    entityIds.forEach(eid => {
      const items = data[eid] || [];
      if (items.length === 0) return;
      const displayName = eid === 'player' ? (STATE.activeSession ? STATE.activeSession.player_name : eid) : eid;

      const box = document.createElement('div');
      box.className = 'entity-box';
      box.innerHTML = `<div class="entity-box-header"><span>${displayName}</span><span class="type">inventory</span></div>`;

      items.forEach(item => {
        const color = RARITY_COLORS[(item.rarity || 'common').toLowerCase()] || RARITY_COLORS.common;
        const row = document.createElement('div');
        row.className = 'entity-stat-row';
        row.title = item.description || '';
        row.innerHTML = `<span style="color:${color}; font-weight:600;">${item.name}</span><span class="val">x${item.quantity}</span>`;
        box.appendChild(row);
      });

      container.appendChild(box);
    });
  } catch (err) {
    console.error('Failed to load inventory:', err);
  }
}

function setupSidebarMiniTabs() {
  document.querySelectorAll('.sidebar-mini-tabs .tab-btn').forEach(btn => {
    btn.onclick = (e) => {
      const nav = e.target.closest('.sidebar-mini-tabs');
      nav.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');

      const targetId = e.target.getAttribute('data-panel');
      nav.parentElement.querySelectorAll('.entities-list').forEach(panel => panel.classList.add('hidden'));
      document.getElementById(targetId).classList.remove('hidden');
    };
  });
}

// ── Ambiance audio (dual-<audio> crossfade, mirrors ui/ambiance_manager.py) ──
const AMBIANCE_FADE_DURATION_MS = 3000;
const AMBIANCE_FADE_STEP_MS = 50;

function getAmbiancePlayers() {
  // Created lazily so a fresh <audio> pair exists even if index.html doesn't
  // declare them; two elements alternate active/fading roles like Qt's dual QMediaPlayer.
  if (!STATE.ambiancePlayerA) {
    STATE.ambiancePlayerA = new Audio();
    STATE.ambiancePlayerA.loop = true;
    STATE.ambiancePlayerB = new Audio();
    STATE.ambiancePlayerB.loop = true;
    STATE.ambianceActive = STATE.ambiancePlayerA;
    STATE.ambianceFading = STATE.ambiancePlayerB;
  }
  return { active: STATE.ambianceActive, fading: STATE.ambianceFading };
}

function isAudioEnabled() {
  return !STATE.config || STATE.config.enable_audio !== false;
}

function setAmbianceVolume(vol) {
  STATE.ambianceVolume = Math.max(0, Math.min(1, vol));
  if (!STATE.ambianceFadeTimer) {
    const { active } = getAmbiancePlayers();
    active.volume = STATE.ambianceVolume;
  }
}

function stopAmbiance() {
  if (STATE.ambianceFadeTimer) {
    clearInterval(STATE.ambianceFadeTimer);
    STATE.ambianceFadeTimer = null;
  }
  if (STATE.ambiancePlayerA) STATE.ambiancePlayerA.pause();
  if (STATE.ambiancePlayerB) STATE.ambiancePlayerB.pause();
  STATE.ambianceTag = null;
  updateAmbianceLabel();
}

async function updateAmbiance(tag) {
  if (!isAudioEnabled() || !tag || tag === STATE.ambianceTag) return;
  STATE.ambianceTag = tag;

  let track = null;
  try {
    const res = await fetch(`/api/audio/track?tag=${encodeURIComponent(tag)}`);
    const data = await res.json();
    track = data.file;
  } catch (err) {
    console.error('Failed to fetch ambiance track:', err);
  }

  if (!track) {
    // No bundled tracks for this tag (the app ships with none by default) --
    // mirrors AmbianceManager.update_ambiance()'s stop_all() fallback.
    stopAmbiance();
    return;
  }

  const { active, fading } = getAmbiancePlayers();
  // Swap roles: the previously-active player now fades out.
  STATE.ambianceActive = fading;
  STATE.ambianceFading = active;
  const newActive = STATE.ambianceActive;
  const newFading = STATE.ambianceFading;

  newActive.src = `/audio/${encodeURIComponent(tag)}/${encodeURIComponent(track)}`;
  newActive.volume = 0;
  newActive.play().catch(() => {});

  if (STATE.ambianceFadeTimer) clearInterval(STATE.ambianceFadeTimer);
  let progress = 0;
  STATE.ambianceFadeTimer = setInterval(() => {
    progress += AMBIANCE_FADE_STEP_MS / AMBIANCE_FADE_DURATION_MS;
    if (progress >= 1) {
      progress = 1;
      clearInterval(STATE.ambianceFadeTimer);
      STATE.ambianceFadeTimer = null;
      newFading.pause();
    }
    newActive.volume = progress * STATE.ambianceVolume;
    newFading.volume = (1 - progress) * STATE.ambianceVolume;
  }, AMBIANCE_FADE_STEP_MS);

  updateAmbianceLabel(track);
}

function updateAmbianceLabel(track) {
  const label = document.getElementById('status-audio-label');
  if (!label) return;
  label.textContent = STATE.ambianceTag ? `Ambiance: ${STATE.ambianceTag}` : 'Ambiance: -';
}

function sendTravelIntent(locId, locName) {
  const promptText = `I travel to ${locName}.`;
  document.getElementById('chat-input').value = promptText;
  document.getElementById('chat-input').focus();
}

async function submitTurn() {
  const inputEl = document.getElementById('chat-input');
  const text = inputEl.value.trim();
  if (!text || STATE.isGenerating) return;

  const isMultiplayer = STATE.activeSession && STATE.activeSession.difficulty === 'Multiplayer';

  if (isMultiplayer) {
    const selEl = document.getElementById('mp-player-select');
    const playerId = selEl.value;
    if (!playerId) return;

    if (!STATE.pendingIntents) STATE.pendingIntents = {};
    STATE.pendingIntents[playerId] = text;

    const playerName = selEl.options[selEl.selectedIndex].text;
    appendBubble('system', `[Queued] ${playerName}: "${text}"`, { isPrep: true });

    inputEl.value = '';
    updateMultiplayerLobby();

    const roster = (STATE.activeSession.players || []).map(p => p.entity_id);
    if (roster.length === 0) return;

    const remaining = roster.filter(pid => !STATE.pendingIntents[pid]);
    if (remaining.length > 0) {
      return;
    }

    STATE.isGenerating = true;
    document.getElementById('status-cancel-btn').classList.remove('hidden');
    showStatus('Consulting Arbitrator (Multiplayer)...');

    const intentsPayload = Object.assign({}, STATE.pendingIntents);
    STATE.pendingIntents = {};

    try {
      const res = await fetch('/api/session/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intents: intentsPayload })
      });

      if (res.ok) {
        const result = await res.json();
        STATE.activeSession = Object.assign({}, STATE.activeSession, result);
        rebuildChatFromHistory({ animateLastNarrative: true });
        updateAmbiance(result.game_state_tag);
        await refreshTabletopState();
        updateMultiplayerLobby();
      } else {
        const err = await res.json();
        appendBubble('system', err.error || 'Failed to resolve turn.', {});
      }
    } catch (err) {
      console.error(err);
      appendBubble('system', 'Connection error resolving turn.', {});
    } finally {
      STATE.isGenerating = false;
      document.getElementById('status-cancel-btn').classList.add('hidden');
      showStatus('Ready.');
    }
  } else {
    inputEl.value = '';
    STATE.isGenerating = true;
    document.getElementById('status-cancel-btn').classList.remove('hidden');
    showStatus('Consulting Arbitrator...');

    appendBubble('player', text, {});

    try {
      const res = await fetch('/api/session/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_input: text })
      });

      if (res.ok) {
        const result = await res.json();
        STATE.activeSession = Object.assign({}, STATE.activeSession, result);
        rebuildChatFromHistory({ animateLastNarrative: true });
        updateAmbiance(result.game_state_tag);
        await refreshTabletopState();
        if (result.hardcore_death) {
          await handleHardcoreDeath();
          return;
        }
      } else {
        const err = await res.json();
        appendBubble('system', err.error || 'Failed to resolve turn.', {});
      }
    } catch (err) {
      console.error(err);
      appendBubble('system', 'Connection error resolving turn.', {});
    } finally {
      STATE.isGenerating = false;
      document.getElementById('status-cancel-btn').classList.add('hidden');
      showStatus('Ready.');
    }
  }
}

// ── Hardcore mode: permadeath confirm + irrevocable deletion ──
function stripHtml(html) {
  const tmp = document.createElement('div');
  tmp.innerHTML = html || '';
  return tmp.textContent || tmp.innerText || '';
}

async function handleHardcoreDeath() {
  alert(stripHtml(tr('death_text')) || 'You have fallen. This Hardcore save will now be permanently deleted.');
  stopAmbiance();
  showStatus(tr('releasing_connections') || 'Releasing connections...');
  try {
    const res = await fetch('/api/session/hardcore-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    if (res.ok) {
      alert(stripHtml(tr('save_deleted_text')) || 'Your Hardcore save has been permanently erased.');
    } else {
      const err = await res.json();
      alert(`${tr('deletion_failed_title') || 'Deletion Failed'}: ${err.error || ''}`);
    }
  } catch (err) {
    console.error(err);
  } finally {
    STATE.activeSession = null;
    showScreen('view-hub');
    await refreshHub();
    showStatus('Ready.');
  }
}

// ── Chat rendering: history events -> bubbles with edit/regenerate/variant-nav ──

function rebuildChatFromHistory(opts = {}) {
  const chatHistory = document.getElementById('chat-history');
  chatHistory.innerHTML = '';
  const history = (STATE.activeSession && STATE.activeSession.history) || [];
  history.forEach((ev, idx) => {
    const isLast = idx === history.length - 1;
    const animate = !!(opts.animateLastNarrative && isLast && ev.event_type === 'narrative_text');
    renderHistoryEvent(ev, animate);
  });
}

function renderHistoryEvent(ev, animate) {
  const p = ev.payload;
  if (ev.event_type === 'user_input' || ev.event_type === 'hero_intent') {
    const text = (p && typeof p === 'object') ? (p.text || '') : String(p || '');
    const role = ev.event_type === 'hero_intent' ? 'hero' : 'player';
    appendBubble(role, text, { turnId: ev.turn_id, eventType: ev.event_type });
  } else if (ev.event_type === 'narrative_text') {
    let text = '', activeIdx = 0, totalVariants = 1;
    if (p && typeof p === 'object') {
      if (Array.isArray(p.variants)) {
        activeIdx = p.active || 0;
        totalVariants = p.variants.length;
        text = p.variants[activeIdx] || '';
      } else {
        text = p.text || '';
      }
    } else {
      text = String(p || '');
    }
    appendBubble('narrator', text, {
      turnId: ev.turn_id, eventType: 'narrative_text', activeIdx, totalVariants, animate,
      // Images are keyed by turn number on disk (assets/<save_id>/turn_<n>.png);
      // not every turn has one, so the <img> just hides itself on 404.
      imgCandidate: true,
    });
  }
}

function appendBubble(role, text, opts = {}) {
  const chatHistory = document.getElementById('chat-history');
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}`;
  chatHistory.appendChild(bubble);

  const textDiv = document.createElement('div');
  textDiv.className = 'bubble-text';
  bubble.appendChild(textDiv);

  const cleanText = (text || '').replace(/~~~json[\s\S]*?~~~/g, '').replace(/```json[\s\S]*?```/g, '').trim();

  const finishBubble = () => {
    if (opts.imgCandidate && STATE.activeSession) {
      const img = document.createElement('img');
      img.className = 'chat-illustration';
      img.src = `/assets/${STATE.activeSession.save_id}/turn_${opts.turnId}.png`;
      img.onerror = () => img.remove();
      bubble.appendChild(img);
    }
    if (opts.turnId !== undefined && opts.turnId !== null) {
      appendBubbleControls(bubble, cleanText, opts);
    }
    chatHistory.scrollTop = chatHistory.scrollHeight;
  };

  if (!opts.animate) {
    textDiv.innerHTML = formatMarkdown(cleanText);
    finishBubble();
  } else {
    // Typewriter effect over the already-complete text (the backend has no
    // streaming endpoint; this just paces the reveal client-side).
    let currentText = '';
    let index = 0;
    if (STATE.typewriterTimer) clearInterval(STATE.typewriterTimer);
    STATE.typewriterTimer = setInterval(() => {
      if (index < cleanText.length) {
        currentText += cleanText[index++];
        textDiv.innerHTML = formatMarkdown(currentText);
        chatHistory.scrollTop = chatHistory.scrollHeight;
      } else {
        clearInterval(STATE.typewriterTimer);
        STATE.typewriterTimer = null;
        finishBubble();
      }
    }, 15);
  }
  return bubble;
}

function appendBubbleControls(bubble, currentText, opts) {
  const controls = document.createElement('div');
  controls.className = 'bubble-controls';

  const editBtn = document.createElement('button');
  editBtn.className = 'bubble-action-btn';
  editBtn.textContent = tr('edit') || 'Edit';
  editBtn.onclick = () => startEditMessage(opts.turnId, opts.eventType, currentText);
  controls.appendChild(editBtn);

  if (opts.eventType === 'narrative_text') {
    const regenBtn = document.createElement('button');
    regenBtn.className = 'bubble-action-btn';
    regenBtn.textContent = tr('regenerate') || 'Regenerate';
    regenBtn.onclick = () => regenerateMessage(opts.turnId);
    controls.appendChild(regenBtn);

    if (opts.totalVariants > 1) {
      const nav = document.createElement('span');
      nav.className = 'variant-nav';

      const prevBtn = document.createElement('button');
      prevBtn.className = 'bubble-action-btn';
      prevBtn.textContent = '<';
      prevBtn.disabled = opts.activeIdx <= 0;
      prevBtn.onclick = () => switchVariant(opts.turnId, opts.activeIdx - 1);

      const label = document.createElement('span');
      label.className = 'variant-label';
      label.textContent = `${opts.activeIdx + 1}/${opts.totalVariants}`;

      const nextBtn = document.createElement('button');
      nextBtn.className = 'bubble-action-btn';
      nextBtn.textContent = '>';
      nextBtn.disabled = opts.activeIdx >= opts.totalVariants - 1;
      nextBtn.onclick = () => switchVariant(opts.turnId, opts.activeIdx + 1);

      nav.appendChild(prevBtn);
      nav.appendChild(label);
      nav.appendChild(nextBtn);
      controls.appendChild(nav);
    }
  }

  bubble.appendChild(controls);
}

function applySessionUpdate(data) {
  STATE.activeSession = Object.assign({}, STATE.activeSession, data);
  rebuildChatFromHistory();
}

function startEditMessage(turnId, eventType, currentText) {
  STATE.editingMessageTurnId = turnId;
  STATE.editingMessageEventType = eventType;
  document.getElementById('edit-message-title').textContent =
    eventType === 'user_input' ? 'Edit your action' : 'Edit AI message';
  document.getElementById('edit-message-textarea').value = currentText;
  openModal('modal-edit-message');
}

async function submitMessageEdit() {
  const newText = document.getElementById('edit-message-textarea').value.trim();
  if (!newText) return;
  closeAllModals();
  showStatus(eventEditStatusLabel());
  try {
    const res = await fetch('/api/session/edit-message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: STATE.editingMessageEventType,
        turn_id: STATE.editingMessageTurnId,
        new_text: newText,
      })
    });
    if (res.ok) {
      applySessionUpdate(await res.json());
      await refreshTabletopState();
      showStatus('Message updated.');
    } else {
      const err = await res.json();
      alert(`Failed to edit message: ${err.error || ''}`);
      showStatus('Ready.');
    }
  } catch (err) {
    console.error(err);
    showStatus('Ready.');
  }
}

function eventEditStatusLabel() {
  return STATE.editingMessageEventType === 'user_input' ? 'Rewinding and resubmitting...' : 'Applying edit...';
}

async function regenerateMessage(turnId) {
  showStatus('Regenerating...');
  try {
    const res = await fetch('/api/session/regenerate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turn_id: turnId })
    });
    if (res.ok) {
      applySessionUpdate(await res.json());
      showStatus('Regenerated.');
    } else {
      const err = await res.json();
      alert(`Failed to regenerate: ${err.error || ''}`);
      showStatus('Ready.');
    }
  } catch (err) {
    console.error(err);
    showStatus('Ready.');
  }
}

async function switchVariant(turnId, variantIndex) {
  try {
    const res = await fetch('/api/session/variant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turn_id: turnId, variant_index: variantIndex })
    });
    if (res.ok) {
      applySessionUpdate(await res.json());
    } else {
      const err = await res.json();
      alert(`Failed to switch variant: ${err.error || ''}`);
    }
  } catch (err) {
    console.error(err);
  }
}

function formatMarkdown(text) {
  // Images: ![alt](url)
  let html = text.replace(/!\[(.*?)\]\((.*?)\)/g, '<img src="$2" alt="$1" style="max-width: 100%; max-height: 400px; border-radius: var(--border-radius); margin: 8px 0; display: block;">');
  // Links: [text](url)
  html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: var(--blue); text-decoration: underline;">$1</a>');
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
  // Italics
  html = html.replace(/\*(.*?)\*/g, '<i>$1</i>');
  // Newlines
  html = html.replace(/\n/g, '<br>');
  return html;
}

// ── Mini-Dico & RAG Lore Search ──
async function runLoreSearch(query) {
  if (!STATE.activeSession) return;
  const container = document.getElementById('minidico-results');
  container.innerHTML = `<span class="save-meta" style="display: block; text-align: center; margin-top: 12px; font-style: italic;">Consulting lore index...</span>`;
  try {
    const res = await fetch(`/api/session/lore?query=${encodeURIComponent(query)}`);
    if (!res.ok) {
      let errMsg = 'Error consulting lore.';
      try {
        const errData = await res.json();
        if (errData && errData.error) {
          errMsg += `<br>Error: ${errData.error}`;
        }
      } catch (e) {}
      container.innerHTML = `<span class="save-meta" style="color: var(--red); font-size: 13px;">${errMsg}</span>`;
      return;
    }
    const data = await res.json();
    container.innerHTML = '';
    if (data.answer) {
      const card = document.createElement('div');
      card.className = 'lore-hit-card';
      card.innerHTML = `
        <div class="title" style="margin-bottom: 8px;">
          <span>${query}</span>
          <span class="category">Mini-Dico</span>
        </div>
        <div class="content" style="line-height: 1.5; color: var(--text);">${formatMarkdown(data.answer)}</div>
      `;
      container.appendChild(card);
    } else {
      container.innerHTML = `<span class="save-meta">No matching lore.</span>`;
    }
  } catch (err) {
    console.error(err);
    container.innerHTML = `<span class="save-meta" style="color: var(--red);">Error consulting lore.</span>`;
  }
}

// ── Creator Studio ──
async function openCreatorStudio(universePath) {
  STATE.selectedUniversePath = universePath;
  showStatus('Loading Creator Studio...');
  try {
    const res = await fetch(`/api/creator/data?universe=${encodeURIComponent(universePath)}`);
    const data = await res.json();
    if (!res.ok) {
      // fetch() only rejects on network failure, not on 4xx/5xx -- without this
      // check a backend error silently became an "empty Creator Studio" (every
      // tab renders blank from undefined fields, with nothing telling the user why).
      throw new Error(data.error || `Server returned ${res.status}`);
    }
    STATE.creatorData = data;

    // Fill tabs UI
    fillCreatorMeta();
    fillCreatorStats();
    fillCreatorEntities();
    fillCreatorMap();
    fillCreatorRules();
    fillCreatorEvents();
    fillCreatorSetup();
    fillCreatorLore();
    fillCreatorFiles();

    showScreen('view-creator');
    showStatus('Creator Studio ready.');
  } catch (err) {
    console.error(err);
    alert(`Failed to load Creator Studio data: ${err.message || err}`);
  }
}

function fillCreatorMeta() {
  const meta = STATE.creatorData.metadata || {};
  document.getElementById('meta-name').value = meta.name || '';
  document.getElementById('meta-description').value = meta.description || '';
  document.getElementById('meta-system-prompt').value = meta.system_prompt || '';
  document.getElementById('meta-global-lore').value = meta.global_lore || '';
  document.getElementById('meta-first-message').value = meta.first_message || '';
  document.getElementById('meta-tension').value = meta.world_tension_level || 0.5;
  document.getElementById('meta-companion-enabled').checked = meta.companion_enabled || false;
  document.getElementById('meta-companion-hero-id').value = meta.companion_hero_id || 'hero';
}

function fillCreatorStats() {
  const table = document.getElementById('table-stats').querySelector('tbody');
  table.innerHTML = '';
  
  // Fill Presets Combo
  const presets = STATE.creatorData.stat_presets || {};
  const combo = document.getElementById('stats-preset-combo');
  combo.innerHTML = '';
  for (const key of Object.keys(presets)) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = key;
    combo.appendChild(opt);
  }

  const defs = STATE.creatorData.stats || [];
  defs.forEach((stat, rIdx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" value="${stat.stat_id}" readonly></td>
      <td><input type="text" value="${stat.name}" data-key="name" data-idx="${rIdx}"></td>
      <td>
        <select data-key="value_type" data-idx="${rIdx}">
          <option value="numeric" ${stat.value_type === 'numeric' ? 'selected' : ''}>Numeric</option>
          <option value="categorical" ${stat.value_type === 'categorical' ? 'selected' : ''}>Categorical</option>
        </select>
      </td>
      <td><input type="text" value="${stat.description || ''}" data-key="description" data-idx="${rIdx}"></td>
      <td><input type="text" value="${stat.parameters ? JSON.stringify(stat.parameters) : ''}" data-key="parameters" data-idx="${rIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.creatorData.stats.splice(rIdx, 1);
      fillCreatorStats();
    };
    tr.querySelectorAll('input, select').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        let val = e.target.value;
        if (key === 'parameters') {
          try { val = JSON.parse(val); } catch(ex) {}
        }
        STATE.creatorData.stats[idx][key] = val;
      };
    });
    table.appendChild(tr);
  });
}

function fillCreatorEntities() {
  const table = document.getElementById('table-entities').querySelector('tbody');
  table.innerHTML = '';
  const list = STATE.creatorData.entities || [];
  list.forEach((ent, rIdx) => {
    const tr = document.createElement('tr');
    if (ent.entity_id === STATE.creatorActiveEntityId) tr.className = 'selected';
    tr.innerHTML = `
      <td><input type="text" value="${ent.entity_id}" readonly></td>
      <td><input type="text" value="${ent.entity_type}" readonly></td>
      <td><input type="text" value="${ent.name}" data-key="name" data-idx="${rIdx}"></td>
      <td><input type="text" value="${ent.description || ''}" data-key="description" data-idx="${rIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.onclick = (e) => {
      if (e.target.className === 'btn-table-del') return;
      STATE.creatorActiveEntityId = ent.entity_id;
      fillCreatorEntities();
    };
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.creatorData.entities.splice(rIdx, 1);
      if (STATE.creatorActiveEntityId === ent.entity_id) STATE.creatorActiveEntityId = null;
      fillCreatorEntities();
    };
    tr.querySelectorAll('input').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        STATE.creatorData.entities[idx][key] = e.target.value;
      };
    });
    table.appendChild(tr);
  });

  // Load right panel initial stats for active entity
  const header = document.getElementById('entity-stats-header');
  const grid = document.getElementById('entity-stats-grid');
  grid.innerHTML = '';
  if (!STATE.creatorActiveEntityId) {
    header.textContent = 'Select an entity to configure initial stats.';
    return;
  }
  
  const ent = list.find(e => e.entity_id === STATE.creatorActiveEntityId);
  header.textContent = `Initial Stats for ${ent.name}`;
  
  const activeStats = ent.stats || {};
  const statDefs = STATE.creatorData.stats || [];
  
  statDefs.forEach(def => {
    const row = document.createElement('div');
    row.className = 'form-group';
    const val = activeStats[def.stat_id] || '';
    row.innerHTML = `
      <label>${def.name} (${def.stat_id}):</label>
      <input type="text" value="${val}" placeholder="E.g., 50 or friendly" data-stat="${def.stat_id}">
    `;
    row.querySelector('input').onchange = (e) => {
      const sId = e.target.getAttribute('data-stat');
      if (!ent.stats) ent.stats = {};
      ent.stats[sId] = e.target.value;
    };
    grid.appendChild(row);
  });
}

function fillCreatorMap() {
  const tree = document.getElementById('map-hierarchy-tree');
  tree.innerHTML = '';
  const locations = STATE.creatorData.locations || [];
  
  // Fill Add Scale Combo
  const scaleCombo = document.getElementById('map-new-scale');
  scaleCombo.innerHTML = '';
  const scales = ["universe", "galaxy", "world", "country", "zone", "city", "district", "building", "room", "poi"];
  scales.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    scaleCombo.appendChild(opt);
  });

  // Group by parent hierarchy
  const roots = locations.filter(l => !l.parent_id);
  roots.forEach(root => {
    tree.appendChild(renderMapTreeNode(root, locations));
  });

  // Load graph canvas arrays
  STATE.mapNodes = locations.map(l => ({
    id: l.location_id,
    name: l.name,
    scale: l.scale,
    x: typeof l.x === 'number' ? l.x * 20 + 200 : Math.random() * 400 + 50,
    y: typeof l.y === 'number' ? l.y * 20 + 200 : Math.random() * 250 + 50
  }));

  const connections = STATE.creatorData.connections || [];
  STATE.mapEdges = connections.map(c => ({
    source: c.source_id,
    target: c.target_id,
    distance: c.distance_km || 1
  }));

  drawCanvasMap();
}

function renderMapTreeNode(loc, allLocs) {
  const li = document.createElement('li');
  const children = allLocs.filter(l => l.parent_id === loc.location_id);
  li.innerHTML = `<span>${loc.name} (${loc.scale})</span>`;
  li.onclick = (e) => {
    e.stopPropagation();
    STATE.selectedMapNodeId = loc.location_id;
    // Highlight node in editor
    drawCanvasMap();
  };

  if (children.length > 0) {
    li.classList.add('has-children');
    const ul = document.createElement('ul');
    ul.className = 'tree-widget';
    children.forEach(c => {
      ul.appendChild(renderMapTreeNode(c, allLocs));
    });
    li.appendChild(ul);
  }
  return li;
}

function fillCreatorRules() {
  const table = document.getElementById('table-rules').querySelector('tbody');
  table.innerHTML = '';
  const rules = STATE.creatorData.rules || [];
  
  rules.forEach((rule, rIdx) => {
    const tr = document.createElement('tr');
    if (rule.rule_id === STATE.creatorActiveRuleId) tr.className = 'selected';
    tr.innerHTML = `
      <td><input type="text" value="${rule.rule_id}" readonly></td>
      <td><input type="number" value="${rule.priority || 0}" data-key="priority" data-idx="${rIdx}"></td>
      <td><input type="text" value="${rule.target_entity || '*'}" data-key="target_entity" data-idx="${rIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.onclick = (e) => {
      if (e.target.className === 'btn-table-del') return;
      STATE.creatorActiveRuleId = rule.rule_id;
      fillCreatorRules();
    };
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.creatorData.rules.splice(rIdx, 1);
      if (STATE.creatorActiveRuleId === rule.rule_id) STATE.creatorActiveRuleId = null;
      fillCreatorRules();
    };
    tr.querySelectorAll('input').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        let val = e.target.value;
        if (key === 'priority') val = parseInt(val) || 0;
        STATE.creatorData.rules[idx][key] = val;
      };
    });
    table.appendChild(tr);
  });

  // Conditions & Actions subgrids
  const condTable = document.getElementById('table-conditions').querySelector('tbody');
  const actionTable = document.getElementById('table-actions').querySelector('tbody');
  condTable.innerHTML = '';
  actionTable.innerHTML = '';

  if (!STATE.creatorActiveRuleId) return;

  const rule = rules.find(r => r.rule_id === STATE.creatorActiveRuleId);
  
  // Fill conditions
  const conditions = rule.conditions || [];
  conditions.forEach((cond, cIdx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" value="${cond.stat || ''}" data-key="stat" data-idx="${cIdx}"></td>
      <td>
        <select data-key="operator" data-idx="${cIdx}">
          <option value="==" ${cond.operator === '==' ? 'selected' : ''}>==</option>
          <option value="!=" ${cond.operator === '!=' ? 'selected' : ''}>!=</option>
          <option value="<=" ${cond.operator === '<=' ? 'selected' : ''}>&lt;=</option>
          <option value=">=" ${cond.operator === '>=' ? 'selected' : ''}>&gt;=</option>
          <option value="<" ${cond.operator === '<' ? 'selected' : ''}>&lt;</option>
          <option value=">" ${cond.operator === '>' ? 'selected' : ''}>&gt;</option>
        </select>
      </td>
      <td><input type="text" value="${cond.value || ''}" data-key="value" data-idx="${cIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      rule.conditions.splice(cIdx, 1);
      fillCreatorRules();
    };
    tr.querySelectorAll('input, select').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        rule.conditions[idx][key] = e.target.value;
      };
    });
    condTable.appendChild(tr);
  });

  // Fill actions
  const actions = rule.actions || [];
  actions.forEach((act, aIdx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <select data-key="type" data-idx="${aIdx}">
          <option value="stat_change" ${act.type === 'stat_change' ? 'selected' : ''}>stat_change</option>
          <option value="stat_set" ${act.type === 'stat_set' ? 'selected' : ''}>stat_set</option>
          <option value="trigger_event" ${act.type === 'trigger_event' ? 'selected' : ''}>trigger_event</option>
          <option value="set_status" ${act.type === 'set_status' ? 'selected' : ''}>set_status</option>
        </select>
      </td>
      <td><input type="text" value="${act.stat || ''}" data-key="stat" data-idx="${aIdx}"></td>
      <td><input type="text" value="${act.value || act.delta || ''}" data-key="value" data-idx="${aIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      rule.actions.splice(aIdx, 1);
      fillCreatorRules();
    };
    tr.querySelectorAll('input, select').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        const val = e.target.value;
        if (key === 'value') {
          if (rule.actions[idx].type === 'stat_change') {
            rule.actions[idx].delta = parseFloat(val) || 0;
            delete rule.actions[idx].value;
          } else {
            rule.actions[idx].value = val;
            delete rule.actions[idx].delta;
          }
        } else {
          rule.actions[idx][key] = val;
        }
      };
    });
    actionTable.appendChild(tr);
  });
}

function fillCreatorEvents() {
  const cal = STATE.creatorData.calendar || {};
  document.getElementById('cal-mph').value = cal.minutes_per_hour || 60;
  document.getElementById('cal-hpd').value = cal.hours_per_day || 24;
  document.getElementById('cal-start-day').value = cal.start_day || 1;
  document.getElementById('cal-start-hour').value = cal.start_hour || 8;
  document.getElementById('cal-start-minute').value = cal.start_minute || 0;
  document.getElementById('cal-months').value = (cal.month_names || []).join(', ');

  const events = STATE.creatorData.events || [];
  const table = document.getElementById('table-events').querySelector('tbody');
  table.innerHTML = '';
  events.forEach((ev, rIdx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" value="${ev.event_id}" readonly></td>
      <td><input type="number" value="${ev.trigger_minute}" data-key="trigger_minute" data-idx="${rIdx}"></td>
      <td><input type="text" value="${ev.title}" data-key="title" data-idx="${rIdx}"></td>
      <td><input type="text" value="${ev.description || ''}" data-key="description" data-idx="${rIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.creatorData.events.splice(rIdx, 1);
      fillCreatorEvents();
    };
    tr.querySelectorAll('input').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        let val = e.target.value;
        if (key === 'trigger_minute') val = parseInt(val) || 0;
        STATE.creatorData.events[idx][key] = val;
      };
    });
    table.appendChild(tr);
  });
  updateCalendarPreview();
}

function fillCreatorSetup() {
  const table = document.getElementById('table-setup').querySelector('tbody');
  table.innerHTML = '';
  const qs = STATE.creatorData.setup_questions || [];
  qs.forEach((q, rIdx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" value="${q.setup_id}" readonly></td>
      <td><input type="text" value="${q.question}" data-key="question" data-idx="${rIdx}"></td>
      <td>
        <select data-key="type" data-idx="${rIdx}">
          <option value="text" ${q.type === 'text' ? 'selected' : ''}>text</option>
          <option value="single_choice" ${q.type === 'single_choice' ? 'selected' : ''}>single_choice</option>
          <option value="multi_choice" ${q.type === 'multi_choice' ? 'selected' : ''}>multi_choice</option>
        </select>
      </td>
      <td><input type="text" value="${q.options ? JSON.stringify(q.options) : ''}" data-key="options" data-idx="${rIdx}"></td>
      <td><input type="number" value="${q.max_selections || 1}" data-key="max_selections" data-idx="${rIdx}"></td>
      <td><input type="number" value="${q.priority || 0}" data-key="priority" data-idx="${rIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.creatorData.setup_questions.splice(rIdx, 1);
      fillCreatorSetup();
    };
    tr.querySelectorAll('input, select').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        let val = e.target.value;
        if (key === 'options') {
          try { val = JSON.parse(val); } catch(ex) {}
        } else if (key === 'max_selections' || key === 'priority') {
          val = parseInt(val) || 0;
        }
        STATE.creatorData.setup_questions[idx][key] = val;
      };
    });
    table.appendChild(tr);
  });
}

function fillCreatorLore() {
  const table = document.getElementById('table-lore').querySelector('tbody');
  table.innerHTML = '';
  const lore = STATE.creatorData.lore || [];
  
  // Repopulate Categories combo
  const catCombo = document.getElementById('lore-new-category');
  catCombo.innerHTML = '';
  const cats = ["General", "Faction", "Location", "Character", "Magic"];
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    catCombo.appendChild(opt);
  });

  lore.forEach((entry, rIdx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="text" value="${entry.category || 'General'}" data-key="category" data-idx="${rIdx}"></td>
      <td><input type="text" value="${entry.name}" data-key="name" data-idx="${rIdx}"></td>
      <td><input type="text" value="${entry.text || ''}" data-key="text" data-idx="${rIdx}"></td>
      <td><button class="btn-table-del">&times;</button></td>
    `;
    tr.querySelector('.btn-table-del').onclick = () => {
      STATE.creatorData.lore.splice(rIdx, 1);
      fillCreatorLore();
    };
    tr.querySelectorAll('input').forEach(el => {
      el.onchange = (e) => {
        const key = e.target.getAttribute('data-key');
        const idx = parseInt(e.target.getAttribute('data-idx'));
        STATE.creatorData.lore[idx][key] = e.target.value;
      };
    });
    table.appendChild(tr);
  });
}

function fillCreatorFiles() {
  const isFolder = STATE.creatorData.is_folder;
  if (isFolder) {
    document.getElementById('files-panel-folder').classList.remove('hidden');
    document.getElementById('files-panel-flat').classList.add('hidden');
    renderFilesTree(STATE.creatorData.files || []);
  } else {
    document.getElementById('files-panel-folder').classList.add('hidden');
    document.getElementById('files-panel-flat').classList.remove('hidden');
  }
}

function renderFilesTree(files) {
  const tree = document.getElementById('files-tree');
  tree.innerHTML = '';
  
  // Standard list of text files
  files.forEach(f => {
    const li = document.createElement('li');
    li.textContent = f.rel_path;
    li.onclick = () => loadFileToEditor(f.rel_path);
    tree.appendChild(li);
  });
}

async function loadFileToEditor(relPath) {
  try {
    const res = await fetch(`/api/creator/file?universe=${encodeURIComponent(STATE.selectedUniversePath)}&rel_path=${encodeURIComponent(relPath)}`);
    const data = await res.json();
    const ed = document.getElementById('files-editor-textarea');
    ed.value = data.content;
    ed.removeAttribute('readonly');
    document.getElementById('files-current-path').textContent = relPath;
    const saveBtn = document.getElementById('files-save-btn');
    saveBtn.classList.remove('disabled');
    saveBtn.removeAttribute('disabled');
  } catch (err) {
    console.error(err);
  }
}

async function saveActiveFile() {
  const relPath = document.getElementById('files-current-path').textContent;
  const content = document.getElementById('files-editor-textarea').value;
  try {
    const res = await fetch(`/api/creator/file?universe=${encodeURIComponent(STATE.selectedUniversePath)}&rel_path=${encodeURIComponent(relPath)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    });
    if (res.ok) {
      showStatus(`Saved ${relPath} successfully.`);
      // Reload creator Studio to fetch compiled updates
      openCreatorStudio(STATE.selectedUniversePath);
    } else {
      alert('Failed to save file.');
    }
  } catch (err) {
    console.error(err);
  }
}

async function convertLegacyUniverse() {
  showStatus('Converting database structure...');
  try {
    const res = await fetch('/api/creator/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe_path: STATE.selectedUniversePath })
    });
    if (res.ok) {
      const data = await res.json();
      showStatus('Converted successfully.');
      openCreatorStudio(data.new_path);
    } else {
      alert('Failed to convert database.');
    }
  } catch (err) {
    console.error(err);
  }
}

async function saveCreatorChanges() {
  if (!STATE.creatorData) return;
  showStatus('Saving universe changes...');
  
  // Sync metadata edits
  const meta = STATE.creatorData.metadata || {};
  meta.name = document.getElementById('meta-name').value;
  meta.description = document.getElementById('meta-description').value;
  meta.system_prompt = document.getElementById('meta-system-prompt').value;
  meta.global_lore = document.getElementById('meta-global-lore').value;
  meta.first_message = document.getElementById('meta-first-message').value;
  meta.world_tension_level = parseFloat(document.getElementById('meta-tension').value) || 0.5;
  meta.companion_enabled = document.getElementById('meta-companion-enabled').checked;
  meta.companion_hero_id = document.getElementById('meta-companion-hero-id').value;

  // Sync Calendar
  const cal = STATE.creatorData.calendar || {};
  cal.minutes_per_hour = parseInt(document.getElementById('cal-mph').value) || 60;
  cal.hours_per_day = parseInt(document.getElementById('cal-hpd').value) || 24;
  cal.start_day = parseInt(document.getElementById('cal-start-day').value) || 1;
  cal.start_hour = parseInt(document.getElementById('cal-start-hour').value) || 8;
  cal.start_minute = parseInt(document.getElementById('cal-start-minute').value) || 0;
  cal.month_names = document.getElementById('cal-months').value.split(',').map(s => s.trim()).filter(Boolean);

  try {
    const res = await fetch(`/api/creator/save?universe=${encodeURIComponent(STATE.selectedUniversePath)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(STATE.creatorData)
    });
    if (res.ok) {
      showStatus('Saved and compiled successfully.');
      // Refresh Hub views
      await refreshHub();
    } else {
      alert('Failed to save universe changes.');
    }
  } catch (err) {
    console.error(err);
  }
}

// ── 2D Canvas Interactive Map Editor ──
function setupCanvasMapHandlers() {
  const canvas = document.getElementById('map-canvas');
  if (!canvas) return;

  canvas.addEventListener('mousedown', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Check hit node
    const hit = STATE.mapNodes.find(n => {
      const dist = Math.hypot(n.x - mouseX, n.y - mouseY);
      return dist <= 25; // Circle radius
    });

    if (hit) {
      if (e.shiftKey) {
        // Start connection
        STATE.mapConnectingSource = hit.id;
      } else {
        // Drag node
        STATE.mapDragNode = hit;
        STATE.selectedMapNodeId = hit.id;
      }
    } else {
      STATE.selectedMapNodeId = null;
    }
    drawCanvasMap();
  });

  canvas.addEventListener('mousemove', (e) => {
    if (!STATE.mapDragNode) return;
    const rect = canvas.getBoundingClientRect();
    STATE.mapDragNode.x = e.clientX - rect.left;
    STATE.mapDragNode.y = e.clientY - rect.top;
    
    // Update raw positions in creator data
    const rawNode = STATE.creatorData.locations.find(l => l.location_id === STATE.mapDragNode.id);
    if (rawNode) {
      rawNode.x = Math.round((STATE.mapDragNode.x - 200) / 20);
      rawNode.y = Math.round((STATE.mapDragNode.y - 200) / 20);
    }

    drawCanvasMap();
  });

  canvas.addEventListener('mouseup', (e) => {
    if (STATE.mapConnectingSource) {
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const hit = STATE.mapNodes.find(n => {
        const dist = Math.hypot(n.x - mouseX, n.y - mouseY);
        return dist <= 25;
      });
      if (hit && hit.id !== STATE.mapConnectingSource) {
        // Connect nodes
        const distStr = prompt('Enter travel distance (km):', '1');
        const dist = parseInt(distStr) || 1;
        
        STATE.mapEdges.push({ source: STATE.mapConnectingSource, target: hit.id, distance: dist });
        
        if (!STATE.creatorData.connections) STATE.creatorData.connections = [];
        STATE.creatorData.connections.push({
          source_id: STATE.mapConnectingSource,
          target_id: hit.id,
          distance_km: dist
        });
      }
      STATE.mapConnectingSource = null;
    }
    STATE.mapDragNode = null;
    drawCanvasMap();
  });

  canvas.addEventListener('dblclick', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const locId = prompt('Enter new Location ID (E.g., "tavern"):');
    if (!locId) return;
    const locName = prompt('Enter Location Display Name (E.g., "The Rusty Cog"):');
    if (!locName) return;

    const rawX = Math.round((x - 200) / 20);
    const rawY = Math.round((y - 200) / 20);

    STATE.mapNodes.push({ id: locId, name: locName, scale: 'room', x, y });
    
    if (!STATE.creatorData.locations) STATE.creatorData.locations = [];
    STATE.creatorData.locations.push({
      location_id: locId,
      name: locName,
      scale: 'room',
      x: rawX,
      y: rawY
    });

    fillCreatorMap();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Delete' && STATE.selectedMapNodeId) {
      // Delete selected location
      const idx = STATE.mapNodes.findIndex(n => n.id === STATE.selectedMapNodeId);
      if (idx !== -1) {
        STATE.mapNodes.splice(idx, 1);
        STATE.creatorData.locations.splice(idx, 1);
        
        // Remove connected edges
        STATE.mapEdges = STATE.mapEdges.filter(edge => edge.source !== STATE.selectedMapNodeId && edge.target !== STATE.selectedMapNodeId);
        STATE.creatorData.connections = STATE.creatorData.connections.filter(c => c.source_id !== STATE.selectedMapNodeId && c.target_id !== STATE.selectedMapNodeId);
        
        STATE.selectedMapNodeId = null;
        fillCreatorMap();
      }
    }
  });
}

function drawCanvasMap() {
  const canvas = document.getElementById('map-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  // Set dimensions based on bounding element
  const parent = canvas.parentElement;
  canvas.width = parent.clientWidth;
  canvas.height = parent.clientHeight;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Draw grid
  ctx.strokeStyle = '#1e1e2e';
  ctx.lineWidth = 1;
  const gridSize = 20;
  for (let x = 0; x < canvas.width; x += gridSize) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y < canvas.height; y += gridSize) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }

  // Draw Connections (Lines)
  STATE.mapEdges.forEach(edge => {
    const s = STATE.mapNodes.find(n => n.id === edge.source);
    const t = STATE.mapNodes.find(n => n.id === edge.target);
    if (!s || !t) return;

    ctx.beginPath();
    ctx.strokeStyle = '#585b70';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
    ctx.setLineDash([]); // Reset

    // Draw distance badge
    const midX = (s.x + t.x) / 2;
    const midY = (s.y + t.y) / 2;
    ctx.fillStyle = '#11111b';
    ctx.fillRect(midX - 25, midY - 10, 50, 20);
    ctx.strokeStyle = '#313244';
    ctx.strokeRect(midX - 25, midY - 10, 50, 20);
    
    ctx.fillStyle = '#a6adc8';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${edge.distance} km`, midX, midY + 4);
  });

  // Draw Locations (Nodes)
  STATE.mapNodes.forEach(node => {
    ctx.beginPath();
    ctx.arc(node.x, node.y, 25, 0, Math.PI * 2);
    ctx.fillStyle = node.id === STATE.selectedMapNodeId ? '#a6e3a1' : '#89b4fa';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#cdd6f4';
    ctx.stroke();

    // Node Label
    ctx.fillStyle = '#cdd6f4';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(node.name, node.x, node.y + 35);
  });
}

// ── Modal Handlers & UI Events ──
function setupModalHandlers() {
  document.querySelectorAll('.modal-close').forEach(btn => {
    btn.onclick = () => closeAllModals();
  });

  window.onclick = (e) => {
    if (e.target.classList.contains('modal-overlay')) {
      closeAllModals();
    }
  };
}

function closeAllModals() {
  document.querySelectorAll('.modal-overlay').forEach(modal => {
    modal.classList.remove('show');
  });
}

function openModal(id) {
  closeAllModals();
  document.getElementById(id).classList.add('show');
}

function setupTabHandlers() {
  // Studio tabs
  document.querySelectorAll('.studio-tabs .tab-btn').forEach(btn => {
    btn.onclick = (e) => {
      document.querySelectorAll('.studio-tabs .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.studio-tab-panel').forEach(p => p.classList.remove('active'));
      
      e.target.classList.add('active');
      const targetId = e.target.getAttribute('data-target');
      document.getElementById(targetId).classList.add('active');
      
      if (targetId === 'studio-tab-map') {
        // Redraw canvas
        setTimeout(drawCanvasMap, 50);
      }
    };
  });

  // Settings tabs
  document.querySelectorAll('.settings-tabs .settings-tab-btn').forEach(btn => {
    btn.onclick = (e) => {
      document.querySelectorAll('.settings-tabs .settings-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
      
      e.target.classList.add('active');
      const targetId = e.target.getAttribute('data-target');
      document.getElementById(targetId).classList.add('active');
    };
  });
}

function setupUIEventListeners() {
  // Menu Actions
  document.getElementById('btn-menu-settings').onclick = () => openModal('modal-settings');
  document.getElementById('btn-menu-diag').onclick = () => openModal('modal-diagnostics');
  document.getElementById('btn-menu-about').onclick = () => {
    document.getElementById('about-content').innerHTML = tr('about_text');
    openModal('modal-about');
  };
  document.getElementById('btn-menu-explain').onclick = explainCurrentPage;
  document.getElementById('btn-menu-help-directory').onclick = () => {
    document.getElementById('help-search-input').value = '';
    renderHelpDirectory('');
    openModal('modal-help-directory');
  };
  document.getElementById('help-search-input').oninput = (e) => {
    renderHelpDirectory(e.target.value);
  };
  document.getElementById('btn-menu-tour').onclick = () => openQuickTour(0);
  document.getElementById('tour-prev-btn').onclick = () => {
    if (STATE.tourStepIndex > 0) openQuickTour(STATE.tourStepIndex - 1);
  };
  document.getElementById('tour-next-btn').onclick = () => {
    if (STATE.tourStepIndex < TOUR_STEPS.length - 1) {
      openQuickTour(STATE.tourStepIndex + 1);
    } else {
      closeModal('modal-tour');
    }
  };
  document.getElementById('btn-menu-hub').onclick = () => showScreen('view-hub');
  document.getElementById('btn-menu-quit').onclick = () => {
    if (confirm('Quit Axiom AI?')) {
      window.close();
    }
  };
  document.getElementById('status-cancel-btn').onclick = () => {
    STATE.isGenerating = false;
    document.getElementById('status-cancel-btn').classList.add('hidden');
    showStatus('Generation cancelled.');
  };

  // Mini-Dico search triggers
  const minidicoSearch = document.getElementById('minidico-search');
  const minidicoAskBtn = document.getElementById('minidico-ask-btn');
  const triggerMinidico = () => {
    const val = minidicoSearch.value.trim();
    if (val) runLoreSearch(val);
  };
  if (minidicoSearch) {
    minidicoSearch.onkeypress = (e) => {
      if (e.key === 'Enter') triggerMinidico();
    };
  }
  if (minidicoAskBtn) {
    minidicoAskBtn.onclick = triggerMinidico;
  }

  // Settings Save
  document.getElementById('settings-save-btn').onclick = saveConfig;
  document.getElementById('edit-save-apply-btn').onclick = submitSaveEdit;
  document.getElementById('edit-message-apply-btn').onclick = submitMessageEdit;
  
  // Test connection settings
  document.getElementById('settings-test-btn').onclick = async () => {
    const statusEl = document.getElementById('settings-test-status');
    statusEl.textContent = 'Testing...';
    try {
      const res = await fetch('/api/settings/test-connection', { method: 'POST' });
      const data = await res.json();
      statusEl.textContent = data.message;
    } catch(err) {
      statusEl.textContent = 'Failed to request test.';
    }
  };

  // Run diagnostics
  document.getElementById('diag-run-btn').onclick = async () => {
    const out = document.getElementById('diag-output');
    out.textContent = 'Running diagnostics, please wait...';
    const runTests = document.getElementById('diag-tests-checkbox').checked;
    try {
      const res = await fetch(`/api/diagnostic?tests=${runTests}`);
      const data = await res.json();
      out.textContent = data.report;
    } catch(err) {
      out.textContent = 'Error running diagnostics.';
    }
  };

  // Setup Form Submit (Start New Save)
  document.getElementById('setup-form').onsubmit = async (e) => {
    e.preventDefault();
    const answers = {};
    document.querySelectorAll('.setup-question-box[data-id]').forEach(box => {
      const id = box.getAttribute('data-id');
      const textEl = box.querySelector(`input[name="setup_q_${id}"][type="text"]`);
      if (textEl) {
        answers[id] = textEl.value;
      } else {
        // Choice
        const selected = Array.from(box.querySelectorAll(`input[name="setup_q_${id}"]:checked`)).map(el => el.value);
        answers[id] = selected.join(', ');
      }
    });

    const playerName = document.getElementById('setup-player-name').value;
    const playerPersona = document.getElementById('setup-player-persona').value;
    const difficulty = document.getElementById('setup-difficulty').value;

    try {
      const res = await fetch('/api/saves/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe_path: STATE.selectedUniversePath,
          player_name: playerName,
          player_persona: playerPersona,
          difficulty: difficulty,
          setup_answers: answers
        })
      });
      if (res.ok) {
        const data = await res.json();
        await startSession(STATE.selectedUniversePath, data.save_id, difficulty);
      } else {
        alert('Failed to start new adventure.');
      }
    } catch (err) {
      console.error(err);
    }
  };

  document.getElementById('setup-back-btn').onclick = () => showScreen('view-hub');

  // Tabletop Controls
  document.getElementById('chat-send-btn').onclick = submitTurn;
  document.getElementById('chat-input').onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitTurn();
    }
  };

  // Timeline Rewind
  document.getElementById('timeline-rewind-btn').onclick = async () => {
    const slider = document.getElementById('timeline-slider');
    const turn = parseInt(slider.value);
    if (!confirm(`Rewind session back to turn ${turn}? This will permanently remove all actions taken after it.`)) return;

    showStatus('Rewinding...');
    try {
      const res = await fetch('/api/session/rewind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_turn_id: turn })
      });
      if (res.ok) {
        STATE.activeSession = await res.json();
        rebuildChatFromHistory();
        await refreshTabletopState();
        showStatus('Rewind completed.');
      } else {
        alert('Failed to rewind session.');
      }
    } catch (err) {
      console.error(err);
    }
  };

  document.getElementById('timeline-slider').oninput = (e) => {
    document.getElementById('timeline-turn-label').textContent = `Turn ${e.target.value}`;
  };

  // Creator back & Save changes
  document.getElementById('creator-back-btn').onclick = () => showScreen('view-hub');
  document.getElementById('creator-save-btn').onclick = saveCreatorChanges;

  // Add category lore btn
  document.getElementById('lore-add-category-btn').onclick = () => {
    const catName = prompt('Enter name of new Lore category:');
    if (!catName) return;
    const combo = document.getElementById('lore-new-category');
    const opt = document.createElement('option');
    opt.value = catName;
    opt.textContent = catName;
    combo.appendChild(opt);
    combo.value = catName;
  };

  // Add Persona (Settings tab)
  document.getElementById('personas-add-btn').onclick = () => {
    if (!STATE.personas) STATE.personas = [];
    STATE.personas.push({ persona_id: generatePersonaId(), name: 'New Persona', description: '' });
    fillPersonasTable();
  };

  // Add Stats Creator Studio
  document.getElementById('stats-add-btn').onclick = () => {
    const id = document.getElementById('stats-new-id').value.trim();
    const name = document.getElementById('stats-new-name').value.trim();
    const type = document.getElementById('stats-new-type').value;
    if (!id || !name) return;
    STATE.creatorData.stats.push({ stat_id: id, name, value_type: type, description: '', parameters: {} });
    fillCreatorStats();
    document.getElementById('stats-new-id').value = '';
    document.getElementById('stats-new-name').value = '';
  };

  // Apply Presets Creator Studio
  document.getElementById('stats-apply-preset-btn').onclick = () => {
    const key = document.getElementById('stats-preset-combo').value;
    const preset = STATE.creatorData.stat_presets[key] || [];
    preset.forEach(stat => {
      const sId = stat.name.toLowerCase().replace(/[^a-z0-9_]/g, '_');
      if (!STATE.creatorData.stats.some(s => s.stat_id === sId)) {
        STATE.creatorData.stats.push({
          stat_id: sId,
          name: stat.name,
          value_type: stat.value_type,
          description: stat.description || '',
          parameters: stat.parameters || {}
        });
      }
    });
    fillCreatorStats();
  };

  // Add Entities Creator Studio
  document.getElementById('entities-add-btn').onclick = () => {
    const id = document.getElementById('entities-new-id').value.trim();
    const type = document.getElementById('entities-new-type').value;
    const name = document.getElementById('entities-new-name').value.trim();
    if (!id || !name) return;
    STATE.creatorData.entities.push({ entity_id: id, entity_type: type, name, description: '', stats: {} });
    fillCreatorEntities();
    document.getElementById('entities-new-id').value = '';
    document.getElementById('entities-new-name').value = '';
  };

  // Add Rules Creator Studio
  document.getElementById('rules-add-btn').onclick = () => {
    const id = document.getElementById('rules-new-id').value.trim();
    const priority = parseInt(document.getElementById('rules-new-priority').value) || 0;
    const target = document.getElementById('rules-new-target').value.trim() || '*';
    if (!id) return;
    STATE.creatorData.rules.push({ rule_id: id, priority, target_entity: target, conditions: [], actions: [] });
    fillCreatorRules();
    document.getElementById('rules-new-id').value = '';
  };

  document.getElementById('cond-add-btn').onclick = () => {
    if (!STATE.creatorActiveRuleId) return;
    const rules = STATE.creatorData.rules || [];
    const rule = rules.find(r => r.rule_id === STATE.creatorActiveRuleId);
    if (!rule.conditions) rule.conditions = [];
    rule.conditions.push({ stat: '', operator: '==', value: '' });
    fillCreatorRules();
  };

  document.getElementById('action-add-btn').onclick = () => {
    if (!STATE.creatorActiveRuleId) return;
    const rules = STATE.creatorData.rules || [];
    const rule = rules.find(r => r.rule_id === STATE.creatorActiveRuleId);
    if (!rule.actions) rule.actions = [];
    rule.actions.push({ type: 'stat_change', stat: '', value: '' });
    fillCreatorRules();
  };

  // Add Map Locations Creator Studio
  document.getElementById('map-add-btn').onclick = () => {
    const id = document.getElementById('map-new-id').value.trim();
    const name = document.getElementById('map-new-name').value.trim();
    const scale = document.getElementById('map-new-scale').value;
    if (!id || !name) return;
    
    if (!STATE.creatorData.locations) STATE.creatorData.locations = [];
    STATE.creatorData.locations.push({
      location_id: id,
      name,
      scale,
      x: 10 + Math.random() * 5,
      y: 10 + Math.random() * 5
    });

    fillCreatorMap();
    document.getElementById('map-new-id').value = '';
    document.getElementById('map-new-name').value = '';
  };

  // Add Lore Book Creator Studio
  document.getElementById('lore-add-btn').onclick = () => {
    const cat = document.getElementById('lore-new-category').value;
    const name = document.getElementById('lore-new-name').value.trim();
    if (!name) return;
    
    if (!STATE.creatorData.lore) STATE.creatorData.lore = [];
    STATE.creatorData.lore.push({
      category: cat,
      name,
      text: ''
    });

    fillCreatorLore();
    document.getElementById('lore-new-name').value = '';
  };

  // Add setup questions Creator Studio
  document.getElementById('setup-add-btn').onclick = () => {
    const id = document.getElementById('setup-new-id').value.trim();
    const question = document.getElementById('setup-new-question').value.trim();
    const type = document.getElementById('setup-new-type').value;
    if (!id || !question) return;

    if (!STATE.creatorData.setup_questions) STATE.creatorData.setup_questions = [];
    STATE.creatorData.setup_questions.push({
      setup_id: id,
      question,
      type,
      options: [],
      max_selections: 1,
      priority: 0
    });

    fillCreatorSetup();
    document.getElementById('setup-new-id').value = '';
    document.getElementById('setup-new-question').value = '';
  };

  // Add Event Creator Studio
  document.getElementById('events-add-btn').onclick = () => {
    const id = document.getElementById('events-new-id').value.trim();
    const trigger = parseInt(document.getElementById('events-new-trigger').value) || 0;
    const title = document.getElementById('events-new-title').value.trim();
    if (!id || !title) return;
    
    if (!STATE.creatorData.events) STATE.creatorData.events = [];
    STATE.creatorData.events.push({
      event_id: id,
      trigger_minute: trigger,
      title: title,
      description: ""
    });

    fillCreatorEvents();
    document.getElementById('events-new-id').value = '';
    document.getElementById('events-new-title').value = '';
    document.getElementById('events-new-trigger').value = '0';
  };

  // Populate wizard direct generation
  document.getElementById('pop-run-btn').onclick = () => triggerPopulate(false);
  document.getElementById('pop-preview-btn').onclick = () => triggerPopulate(true);

  // Apply diff preview content
  document.getElementById('diff-apply-btn').onclick = async () => {
    showStatus('Applying generated changes...');
    try {
      const res = await fetch(`/api/creator/populate/apply?universe=${encodeURIComponent(STATE.selectedUniversePath)}`, {
        method: 'POST'
      });
      if (res.ok) {
        closeAllModals();
        openCreatorStudio(STATE.selectedUniversePath);
        showStatus('Populate applied successfully.');
      } else {
        alert('Failed to apply changes.');
      }
    } catch(err) {
      console.error(err);
    }
  };

  // Calendar config change
  const calInputs = ['cal-mph', 'cal-hpd', 'cal-start-day', 'cal-start-hour', 'cal-start-minute', 'cal-months'];
  calInputs.forEach(id => {
    document.getElementById(id).onchange = updateCalendarPreview;
  });

  // Files save button
  document.getElementById('files-save-btn').onclick = saveActiveFile;
  document.getElementById('files-convert-btn').onclick = convertLegacyUniverse;

  // New Universe creation
  document.getElementById('hub-create-btn').onclick = async () => {
    const name = prompt('Enter a name for the new Universe:');
    if (!name) return;
    try {
      const res = await fetch('/api/universes/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      if (res.ok) {
        refreshHub();
      } else {
        alert('Failed to create universe.');
      }
    } catch(err) {
      console.error(err);
    }
  };

  // Import .axiom
  document.getElementById('hub-import-btn').onclick = async () => {
    const fileUrl = prompt('Enter the absolute path of the .axiom file to import:');
    if (!fileUrl) return;
    try {
      const res = await fetch('/api/universes/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: fileUrl })
      });
      if (res.ok) {
        refreshHub();
        showStatus('.axiom universe imported successfully.');
      } else {
        const data = await res.json();
        alert(`Failed to import universe: ${data.error}`);
      }
    } catch(err) {
      console.error(err);
    }
  };

  // Import SillyTavern character card
  document.getElementById('hub-import-st-btn').onclick = async () => {
    const filePath = prompt('Enter the absolute path of the SillyTavern character PNG card to import:');
    if (!filePath) return;
    try {
      const res = await fetch('/api/universes/import-st', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath })
      });
      if (res.ok) {
        refreshHub();
        showStatus('SillyTavern character imported as a playable universe.');
      } else {
        const data = await res.json();
        alert(`Failed to import character card: ${data.error}`);
      }
    } catch(err) {
      console.error(err);
    }
  };

  // Audio volume slider
  document.getElementById('volume-slider').oninput = async (e) => {
    const vol = parseFloat(e.target.value) / 100;
    setAmbianceVolume(vol);
    try {
      await fetch('/api/audio/volume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume: vol })
      });
    } catch(err) {
      console.error(err);
    }
  };
}

function updateCalendarPreview() {
  const mph = parseInt(document.getElementById('cal-mph').value) || 60;
  const hpd = parseInt(document.getElementById('cal-hpd').value) || 24;
  const startDay = parseInt(document.getElementById('cal-start-day').value) || 1;
  const startHour = parseInt(document.getElementById('cal-start-hour').value) || 8;
  const startMinute = parseInt(document.getElementById('cal-start-minute').value) || 0;
  const monthsStr = document.getElementById('cal-months').value;
  const months = monthsStr.split(',').map(s => s.trim()).filter(Boolean);

  const monthName = months.length > 0 ? months[0] : 'Month 1';
  document.getElementById('cal-preview-text').textContent = `Year 1, ${monthName} Day ${startDay}, ${String(startHour).padStart(2,'0')}:${String(startMinute).padStart(2,'0')}`;
}

async function triggerPopulate(previewOnly) {
  const meta = document.getElementById('pop-target-meta').checked;
  const stats = document.getElementById('pop-target-stats').checked;
  const entities = document.getElementById('pop-target-entities').checked;
  const map = document.getElementById('pop-target-map').checked;
  const rules = document.getElementById('pop-target-rules').checked;
  const events = document.getElementById('pop-target-events').checked;
  const lore = document.getElementById('pop-target-lore').checked;

  const targets = [];
  if (meta) targets.push('meta');
  if (stats) targets.push('stats');
  if (entities) targets.push('entities');
  if (map) targets.push('map');
  if (rules) targets.push('rules');
  if (events) targets.push('events');
  if (lore) targets.push('lore');

  if (targets.length === 0) {
    alert('Please select at least one content target.');
    return;
  }

  const promptText = document.getElementById('pop-prompt').value.trim();
  const logContainer = document.getElementById('pop-log-container');
  const logBox = document.getElementById('pop-logs');
  logContainer.classList.remove('hidden');
  logBox.textContent = 'Generating content... calling LLM backend...\n';

  try {
    const res = await fetch(`/api/creator/populate?universe=${encodeURIComponent(STATE.selectedUniversePath)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets, prompt: promptText, preview: previewOnly })
    });
    
    if (res.ok) {
      const data = await res.json();
      logBox.textContent += 'Generation complete!\n';
      if (previewOnly) {
        document.getElementById('diff-content').textContent = data.diff || 'No changes proposed.';
        openModal('modal-diff');
      } else {
        logBox.textContent += 'Changes written directly to the database.\n';
        openCreatorStudio(STATE.selectedUniversePath);
      }
    } else {
      const err = await res.json();
      logBox.textContent += `Error: ${err.error || 'LLM generation failed.'}\n`;
    }
  } catch(err) {
    console.error(err);
    logBox.textContent += 'Connection error occurred.\n';
  }
}

// ── Status Bar Helpers ──
function showStatus(msg) {
  document.getElementById('status-text').textContent = msg;
}

// ── Save TOML Edit Flow ──
async function editSave(universePath, saveId) {
  showStatus('Exporting save state to TOML...');
  try {
    const res = await fetch(`/api/saves/export?universe=${encodeURIComponent(universePath)}&save_id=${encodeURIComponent(saveId)}`);
    if (res.ok) {
      const data = await res.json();
      STATE.editingSaveUniversePath = universePath;
      STATE.editingSaveId = saveId;
      STATE.editingSaveOriginalToml = data.toml;
      
      document.getElementById('edit-save-title').textContent = `Edit Save State (${saveId.substring(0, 8)}...)`;
      document.getElementById('edit-save-toml-textarea').value = data.toml;
      openModal('modal-edit-save');
      showStatus('Save state exported.');
    } else {
      alert('Failed to export save state.');
    }
  } catch (err) {
    console.error(err);
    alert('Error exporting save state.');
  }
}

async function submitSaveEdit() {
  const editedToml = document.getElementById('edit-save-toml-textarea').value;
  showStatus('Applying save state edits...');
  try {
    const res = await fetch('/api/saves/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        universe_path: STATE.editingSaveUniversePath,
        save_id: STATE.editingSaveId,
        original_toml: STATE.editingSaveOriginalToml,
        edited_toml: editedToml
      })
    });
    if (res.ok) {
      const data = await res.json();
      closeAllModals();
      await refreshHub();
      if (data.status === 'no_change') {
        showStatus('No changes were made.');
      } else {
        showStatus(`Save edited successfully (Turn correction: ${data.turn}).`);
      }
    } else {
      const err = await res.json();
      alert(`Failed to apply save edits: ${err.error}`);
    }
  } catch (err) {
    console.error(err);
    alert('Error applying save edits.');
  }
}

// ── Help System & Multiplayer Registries ──
const HELP_PAGES = {
  "hub": [
    "import_st",
    "import",
    "create",
    "card_play",
    "card_edit",
    "card_export",
    "card_delete"
  ],
  "setup": [
    "tab_saves",
    "saves_list",
    "sort_saves",
    "import_save",
    "export_save",
    "duplicate_save",
    "rename_save",
    "edit_save",
    "delete_save",
    "tab_persona",
    "persona_list",
    "add_persona",
    "player_name",
    "difficulty",
    "tab_story",
    "launch",
    "back"
  ],
  "tabletop": [
    "turn_time",
    "player_selector",
    "verbosity",
    "canon_auto",
    "canonize",
    "rewind",
    "back",
    "sidebar_stats",
    "sidebar_inventory",
    "sidebar_timeline",
    "chat_log",
    "chat_input",
    "send",
    "mini_dico"
  ],
  "creator": [
    "save",
    "back",
    "tab_meta",
    "tab_stats",
    "tab_entities",
    "tab_map",
    "tab_rules",
    "tab_events",
    "tab_setup",
    "tab_lore",
    "tab_populate",
    "tab_files"
  ],
  "creator_meta": [
    "world_lore",
    "description",
    "system_prompt",
    "first_message",
    "companion",
    "belief_missions",
    "tension",
    "llm_temp",
    "llm_top_p",
    "verbosity"
  ],
  "settings": [
    "tab_llm",
    "base_url",
    "api_key",
    "main_model",
    "extraction_model",
    "time_model",
    "test_connection",
    "tab_cloud",
    "cloud_provider",
    "cloud_key",
    "cloud_model",
    "browse_models",
    "gemini_fallback",
    "llm_rpm",
    "tab_params",
    "llm_temp",
    "llm_top_p",
    "tab_personas",
    "tab_image",
    "image_enable",
    "image_backend",
    "image_url",
    "image_gemini_model",
    "image_size",
    "image_steps",
    "image_cfg",
    "image_timeout",
    "image_workflow",
    "language",
    "chronicler",
    "font_size",
    "rag_chunks",
    "audio",
    "timekeeper",
    "doc_tooltips",
    "trim_sentences",
    "wallpaper",
    "basic_prompt",
    "negative_prompt",
    "tab_memory",
    "memory_mode",
    "memory_interval",
    "memory_model",
    "memory_reranker",
    "memory_beliefs",
    "memory_mental_models",
    "memory_prompt_cache",
    "extract_now",
    "memory_browser"
  ],
  "app": [
    "volume",
    "cancel_generation"
  ]
};

const HELP_DETAILS = new Set([
  "creator_meta.world_lore",
  "creator_meta.description",
  "creator_meta.system_prompt",
  "creator_meta.first_message",
  "creator_meta.companion",
  "creator_meta.tension",
  "creator_meta.llm_temp",
  "creator_meta.llm_top_p",
  "creator_meta.verbosity",
  "creator_meta.belief_missions",
  "settings.memory_mode",
  "settings.memory_interval",
  "settings.memory_reranker",
  "settings.memory_beliefs",
  "settings.memory_mental_models"
]);

const TOUR_STEPS = [
  "welcome",
  "hub",
  "create",
  "setup",
  "tabletop",
  "settings",
  "help"
];

function openQuickTour(stepIndex = 0) {
  STATE.tourStepIndex = stepIndex;
  const step = TOUR_STEPS[stepIndex];
  
  const titleKey = `doc_tour_${step}_t`;
  const bodyKey = `doc_tour_${step}`;
  
  document.getElementById('tour-step-title').textContent = tr(titleKey);
  document.getElementById('tour-step-body').innerHTML = tr(bodyKey);
  
  document.getElementById('tour-step-indicator').textContent = tr('tour_step_fmt', {
    current: stepIndex + 1,
    total: TOUR_STEPS.length
  });
  
  const prevBtn = document.getElementById('tour-prev-btn');
  const nextBtn = document.getElementById('tour-next-btn');
  
  prevBtn.disabled = stepIndex === 0;
  prevBtn.classList.toggle('disabled', stepIndex === 0);
  
  if (stepIndex === TOUR_STEPS.length - 1) {
    nextBtn.textContent = tr('close') || 'Close';
    nextBtn.setAttribute('data-tr', 'close');
  } else {
    nextBtn.textContent = tr('tour_next') || 'Next';
    nextBtn.setAttribute('data-tr', 'tour_next');
  }
  
  openModal('modal-tour');
}

function getCurrentHelpPage() {
  const visible = document.querySelector('.screen-view:not(.hidden)');
  if (!visible) return 'hub';
  const id = visible.id;
  if (id === 'view-hub') return 'hub';
  if (id === 'view-setup') return 'setup';
  if (id === 'view-tabletop') return 'tabletop';
  if (id === 'view-creator') {
    const activeTab = document.querySelector('.studio-tab-panel.active');
    if (activeTab) {
      const tabId = activeTab.id;
      if (tabId === 'studio-tab-meta') return 'creator_meta';
      const pageKey = tabId.replace('studio-tab-', 'creator_');
      if (HELP_PAGES[pageKey] && HELP_PAGES[pageKey].length > 0) {
        return pageKey;
      }
    }
    return 'creator';
  }
  return 'hub';
}

function explainCurrentPage() {
  const page = getCurrentHelpPage();
  const titleKey = `doc_page_${page}_t`;
  const introKey = `doc_page_${page}`;
  
  let html = `<p style="font-weight: 500; margin-bottom: 16px;">${tr(introKey) || ''}</p>`;
  
  const elements = HELP_PAGES[page] || [];
  if (elements.length > 0) {
    html += `<h3 style="color: var(--blue); margin-bottom: 12px; font-size: 15px;">Elements:</h3>`;
    html += `<div style="display: flex; flex-direction: column; gap: 12px;">`;
    elements.forEach(el => {
      const elTitleKey = `doc_${page}_${el}_t`;
      const elBodyKey = `doc_${page}_${el}`;
      const elDetailsKey = `doc_${page}_${el}_d`;
      
      html += `<div style="background-color: var(--crust); border: 1px solid var(--surface0); border-radius: var(--border-radius); padding: 12px;">`;
      html += `<strong style="color: var(--lavender); display: block; margin-bottom: 4px;">${tr(elTitleKey) || el}</strong>`;
      html += `<span style="display: block; color: var(--text);">${tr(elBodyKey) || ''}</span>`;
      
      const ref = `${page}.${el}`;
      if (HELP_DETAILS.has(ref)) {
        html += `<span style="display: block; margin-top: 8px; font-size: 13px; color: var(--subtext); border-top: 1px dashed var(--surface1); padding-top: 6px;">${tr(elDetailsKey) || ''}</span>`;
      }
      
      html += `</div>`;
    });
    html += `</div>`;
  }
  
  document.getElementById('explain-title').textContent = tr(titleKey) || 'Help';
  document.getElementById('explain-body').innerHTML = html;
  
  openModal('modal-explain');
}

function renderHelpDirectory(searchQuery = '') {
  const container = document.getElementById('help-directory-list');
  container.innerHTML = '';
  
  const query = searchQuery.toLowerCase().trim();
  
  for (const [page, elements] of Object.entries(HELP_PAGES)) {
    const pageTitle = tr(`doc_page_${page}_t`) || page;
    const pageIntro = tr(`doc_page_${page}`) || '';
    
    const matchedElements = elements.filter(el => {
      const elTitle = (tr(`doc_${page}_${el}_t`) || '').toLowerCase();
      const elBody = (tr(`doc_${page}_${el}`) || '').toLowerCase();
      return elTitle.includes(query) || elBody.includes(query);
    });
    
    const pageTitleMatched = pageTitle.toLowerCase().includes(query) || pageIntro.toLowerCase().includes(query);
    
    if (query && !pageTitleMatched && matchedElements.length === 0) {
      continue;
    }
    
    const section = document.createElement('div');
    section.style.marginBottom = '8px';
    section.innerHTML = `
      <h3 style="color: var(--blue); border-bottom: 1px solid var(--surface0); padding-bottom: 4px; margin-bottom: 8px; font-size: 16px;">${pageTitle}</h3>
      <p style="font-size: 13px; color: var(--subtext); margin-bottom: 12px; font-style: italic;">${pageIntro}</p>
    `;
    
    const elList = document.createElement('div');
    elList.style.display = 'flex';
    elList.style.flexDirection = 'column';
    elList.style.gap = '8px';
    elList.style.paddingLeft = '12px';
    
    const elementsToRender = query ? matchedElements : elements;
    elementsToRender.forEach(el => {
      const elTitle = tr(`doc_${page}_${el}_t`) || el;
      const elBody = tr(`doc_${page}_${el}`) || '';
      
      const elDiv = document.createElement('div');
      elDiv.style.backgroundColor = 'var(--crust)';
      elDiv.style.border = '1px solid var(--surface0)';
      elDiv.style.borderRadius = 'var(--border-radius-sm)';
      elDiv.style.padding = '8px 12px';
      
      let elHtml = `<strong style="color: var(--lavender); display: block; font-size: 13px;">${elTitle}</strong>`;
      elHtml += `<span style="font-size: 13px; color: var(--text);">${elBody}</span>`;
      
      const ref = `${page}.${el}`;
      if (HELP_DETAILS.has(ref)) {
        elHtml += `<span style="display: block; margin-top: 6px; font-size: 12px; color: var(--subtext); border-top: 1px dashed var(--surface1); padding-top: 4px;">${tr(`doc_${page}_${el}_d`) || ''}</span>`;
      }
      
      elDiv.innerHTML = elHtml;
      elList.appendChild(elDiv);
    });
    
    if (elementsToRender.length > 0 || pageTitleMatched) {
      section.appendChild(elList);
      container.appendChild(section);
    }
  }
  
  if (container.children.length === 0) {
    container.innerHTML = `<p style="color: var(--subtext); text-align: center; margin-top: 24px;">No documentation matches your search.</p>`;
  }
}

function updateMultiplayerLobby() {
  const lobby = document.getElementById('multiplayer-lobby');
  if (!lobby) return;

  const session = STATE.activeSession;
  if (!session || session.difficulty !== 'Multiplayer') {
    lobby.classList.add('hidden');
    return;
  }

  lobby.classList.remove('hidden');

  if (!session.players || session.players.length === 0) {
    const playersList = [];
    const statsKeys = Object.keys(session.current_stats || {});
    statsKeys.forEach(k => {
      if (k === 'player') {
        playersList.push({ entity_id: 'player', name: session.player_name });
      } else if (k.startsWith('player_')) {
        playersList.push({ entity_id: k, name: k });
      }
    });
    if (playersList.length === 0) {
      playersList.push({ entity_id: 'player', name: session.player_name || 'Player' });
    }
    session.players = playersList;
  }

  const select = document.getElementById('mp-player-select');
  const currentVal = select.value;
  select.innerHTML = '';
  session.players.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.entity_id;
    opt.textContent = p.name;
    select.appendChild(opt);
  });

  if (currentVal && Array.from(select.options).some(o => o.value === currentVal)) {
    select.value = currentVal;
  }

  if (!STATE.pendingIntents) STATE.pendingIntents = {};

  const roster = session.players.map(p => p.entity_id);
  const remaining = roster.filter(pid => !STATE.pendingIntents[pid]);

  const statusSpan = document.getElementById('mp-lobby-status');
  if (remaining.length > 0) {
    if (STATE.pendingIntents[select.value] && remaining.includes(remaining[0])) {
      select.value = remaining[0];
    }
    const remainingNames = remaining.map(pid => {
      const pObj = session.players.find(p => p.entity_id === pid);
      return pObj ? pObj.name : pid;
    });
    statusSpan.textContent = `Waiting for: ${remainingNames.join(', ')}`;
  } else {
    statusSpan.textContent = `All players ready! Resolving turn...`;
  }

  const queuedContainer = document.getElementById('mp-queued-container');
  const queuedList = document.getElementById('mp-queued-list');
  queuedList.innerHTML = '';

  const queuedPids = Object.keys(STATE.pendingIntents);
  if (queuedPids.length > 0) {
    queuedContainer.classList.remove('hidden');
    queuedPids.forEach(pid => {
      const pObj = session.players.find(p => p.entity_id === pid);
      const name = pObj ? pObj.name : pid;
      const text = STATE.pendingIntents[pid];

      const li = document.createElement('li');
      li.innerHTML = `<strong>${name}:</strong> "${text}" `;
      const delBtn = document.createElement('button');
      delBtn.className = 'btn-table-del';
      delBtn.innerHTML = '&times;';
      delBtn.style.marginLeft = '8px';
      delBtn.onclick = () => {
        delete STATE.pendingIntents[pid];
        updateMultiplayerLobby();
      };
      li.appendChild(delBtn);
      queuedList.appendChild(li);
    });
  } else {
    queuedContainer.classList.add('hidden');
  }
}
