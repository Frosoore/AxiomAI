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
  setupSaves: [],
  setupSort: 'last_updated',
  setupSelectedSaveId: null,
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
  creatorEditingStatId: null,
  
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
  typewriterTimer: null,   // legacy interval id (cleared if set)
  typewriterRaf: null,     // requestAnimationFrame id for fast reveal
  isGenerating: false,
  streamAbort: null,       // AbortController for SSE turn
  pendingCheckpointTurn: null,
  canonPreview: null,
  cloudProvider: 'gemini',

  // Memory editor (facts / beliefs / mental models)
  memoryData: null,
  memoryTab: 'models',
  memorySelectedId: null,

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
  setupSetupLobby();
  await refreshHub();
  applyDocTooltips();
  if (!localStorage.getItem('axiom_tour_seen')) {
    localStorage.setItem('axiom_tour_seen', '1');
    openQuickTour(0);
  }
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
function stashCloudFieldsFromForm() {
  if (!STATE.config) return;
  const provider = (document.getElementById('setting-cloud-provider') || {}).value || STATE.cloudProvider;
  const fields = CLOUD_FIELDS[provider];
  if (!fields) return;
  const keyEl = document.getElementById('setting-cloud-key');
  const modelEl = document.getElementById('setting-cloud-model');
  if (keyEl) STATE.config[fields.key] = keyEl.value;
  if (modelEl) STATE.config[fields.model] = modelEl.value;
  STATE.cloudProvider = provider;
}

function fillCloudFieldsToForm() {
  if (!STATE.config) return;
  const provider = (document.getElementById('setting-cloud-provider') || {}).value || STATE.cloudProvider || 'gemini';
  const fields = CLOUD_FIELDS[provider] || CLOUD_FIELDS.gemini;
  const keyEl = document.getElementById('setting-cloud-key');
  const modelEl = document.getElementById('setting-cloud-model');
  if (keyEl) keyEl.value = STATE.config[fields.key] || '';
  if (modelEl) modelEl.value = STATE.config[fields.model] || '';
}

function applyWallpaper(path) {
  if (path) {
    const url = path.startsWith('data:') || path.startsWith('http') || path.startsWith('blob:')
      ? path
      : `file://${path}`;
    // Local file:// rarely loads in the browser; treat as CSS url anyway.
    document.body.style.backgroundImage = `linear-gradient(rgba(17,17,27,0.82), rgba(17,17,27,0.88)), url("${path.replace(/"/g, '\\"')}")`;
    document.body.style.backgroundSize = 'cover';
    document.body.style.backgroundPosition = 'center';
    document.body.style.backgroundAttachment = 'fixed';
  } else {
    document.body.style.backgroundImage = '';
  }
}

async function loadConfig() {
  try {
    const res = await fetch('/api/settings');
    STATE.config = await res.json();
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

    const chronicler = document.getElementById('setting-chronicler');
    if (chronicler) chronicler.value = STATE.config.chronicler_minutes_interval || 720;
    const docTips = document.getElementById('setting-doc-tooltips');
    if (docTips) docTips.checked = STATE.config.doc_tooltips_enabled !== false;
    const trim = document.getElementById('setting-trim-sentences');
    if (trim) trim.checked = STATE.config.trim_sentences !== false;
    const wallpaper = document.getElementById('setting-wallpaper');
    if (wallpaper) wallpaper.value = STATE.config.custom_wallpaper || '';
    const basic = document.getElementById('setting-basic-prompt');
    if (basic) basic.value = STATE.config.basic_prompt || '';
    const negative = document.getElementById('setting-negative-prompt');
    if (negative) negative.value = STATE.config.negative_prompt || '';

    document.getElementById('setting-llm-backend').value = STATE.config.llm_backend || 'universal';
    document.getElementById('setting-universal-url').value = STATE.config.universal_base_url || '';
    const univKey = document.getElementById('setting-universal-key');
    if (univKey) univKey.value = STATE.config.universal_api_key || '';
    const univModel = document.getElementById('setting-universal-model');
    if (univModel) univModel.value = STATE.config.universal_model || '';
    document.getElementById('setting-default-verbosity').value = STATE.config.default_verbosity || 'balanced';
    document.getElementById('setting-fallback-model').value = STATE.config.gemini_fallback_model || '';
    document.getElementById('setting-requests-limit').value = STATE.config.llm_requests_per_minute || 0;
    document.getElementById('setting-extraction-model').value = STATE.config.extraction_model || '';
    document.getElementById('setting-time-model').value = STATE.config.time_model || '';
    document.getElementById('setting-timekeeper-enabled').checked = STATE.config.timekeeper_enabled;

    const backend = STATE.config.llm_backend || 'universal';
    STATE.cloudProvider = CLOUD_FIELDS[backend] ? backend : 'gemini';
    const cloudSel = document.getElementById('setting-cloud-provider');
    if (cloudSel) cloudSel.value = STATE.cloudProvider;
    fillCloudFieldsToForm();

    document.getElementById('setting-image-enabled').checked = STATE.config.image_generation_enabled;
    document.getElementById('setting-image-backend').value = STATE.config.image_backend || 'gemini';
    document.getElementById('setting-image-url').value = STATE.config.image_api_url || '';
    document.getElementById('setting-image-width').value = STATE.config.image_width || 512;
    document.getElementById('setting-image-height').value = STATE.config.image_height || 512;
    document.getElementById('setting-image-steps').value = STATE.config.image_steps || 20;
    document.getElementById('setting-image-cfg').value = STATE.config.image_cfg_scale || 7.0;
    document.getElementById('setting-image-workflow').value = STATE.config.image_comfyui_workflow || '';
    const imgModel = document.getElementById('setting-image-gemini-model');
    if (imgModel) imgModel.value = STATE.config.image_gemini_model || '';
    const imgTimeout = document.getElementById('setting-image-timeout');
    if (imgTimeout) imgTimeout.value = STATE.config.image_timeout || 180;

    const memMode = document.getElementById('setting-memory-mode');
    if (memMode) {
      memMode.value = STATE.config.memory_mode || 'lite';
      document.getElementById('setting-memory-interval').value =
        STATE.config.memory_fact_interval != null ? STATE.config.memory_fact_interval : 5;
      document.getElementById('setting-memory-model').value = STATE.config.memory_fact_model || '';
      document.getElementById('setting-memory-beliefs').checked = !!STATE.config.memory_beliefs_enabled;
      document.getElementById('setting-memory-mental-models').checked = !!STATE.config.memory_mental_models_enabled;
      document.getElementById('setting-memory-reranker').checked = !!STATE.config.memory_reranker_enabled;
      const cache = document.getElementById('setting-memory-prompt-cache');
      if (cache) cache.checked = !!STATE.config.memory_prompt_cache_enabled;
      refreshMemorySettingsEnabled();
      memMode.onchange = refreshMemorySettingsEnabled;
      document.getElementById('setting-memory-beliefs').onchange = refreshMemorySettingsEnabled;
    }

    document.body.style.fontSize = `${STATE.config.ui_font_size}px`;
    applyWallpaper(STATE.config.custom_wallpaper || '');
    await refreshUniverseParamsPanel();
  } catch (err) {
    console.error('Failed to load settings:', err);
  }
}

function refreshMemorySettingsEnabled() {
  const living = (document.getElementById('setting-memory-mode') || {}).value === 'living';
  const beliefs = document.getElementById('setting-memory-beliefs');
  const models = document.getElementById('setting-memory-mental-models');
  const interval = document.getElementById('setting-memory-interval');
  const model = document.getElementById('setting-memory-model');
  if (interval) interval.disabled = !living;
  if (model) model.disabled = !living;
  if (beliefs) beliefs.disabled = !living;
  if (models) {
    models.disabled = !living || !(beliefs && beliefs.checked);
  }
}

async function saveConfig() {
  if (!STATE.config) return;
  const backend = document.getElementById('setting-llm-backend').value;

  STATE.config.language = document.getElementById('setting-language').value;
  STATE.config.ui_font_size = parseInt(document.getElementById('setting-font-size').value) || 14;
  STATE.config.rag_chunk_count = parseInt(document.getElementById('setting-rag-chunks').value) || 5;
  STATE.config.enable_audio = document.getElementById('setting-audio-enabled').checked;
  const chronicler = document.getElementById('setting-chronicler');
  if (chronicler) STATE.config.chronicler_minutes_interval = parseInt(chronicler.value, 10) || 720;
  const docTips = document.getElementById('setting-doc-tooltips');
  if (docTips) STATE.config.doc_tooltips_enabled = docTips.checked;
  const trim = document.getElementById('setting-trim-sentences');
  if (trim) STATE.config.trim_sentences = trim.checked;
  const wallpaper = document.getElementById('setting-wallpaper');
  if (wallpaper) STATE.config.custom_wallpaper = wallpaper.value || '';
  const basic = document.getElementById('setting-basic-prompt');
  if (basic) STATE.config.basic_prompt = basic.value || '';
  const negative = document.getElementById('setting-negative-prompt');
  if (negative) STATE.config.negative_prompt = negative.value || '';

  STATE.config.llm_backend = backend;
  STATE.config.universal_base_url = document.getElementById('setting-universal-url').value;
  const univKey = document.getElementById('setting-universal-key');
  if (univKey) STATE.config.universal_api_key = univKey.value;
  const univModel = document.getElementById('setting-universal-model');
  if (univModel) STATE.config.universal_model = univModel.value;
  stashCloudFieldsFromForm();
  STATE.config.gemini_fallback_model = document.getElementById('setting-fallback-model').value;
  STATE.config.llm_requests_per_minute = parseInt(document.getElementById('setting-requests-limit').value) || 0;
  STATE.config.default_verbosity = document.getElementById('setting-default-verbosity').value || 'talkative';

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
  const imgModel = document.getElementById('setting-image-gemini-model');
  if (imgModel) STATE.config.image_gemini_model = imgModel.value || '';
  const imgTimeout = document.getElementById('setting-image-timeout');
  if (imgTimeout) STATE.config.image_timeout = parseInt(imgTimeout.value, 10) || 180;

  if (document.getElementById('setting-memory-mode')) {
    STATE.config.memory_mode = document.getElementById('setting-memory-mode').value || 'lite';
    STATE.config.memory_fact_interval =
      parseInt(document.getElementById('setting-memory-interval').value, 10) || 0;
    STATE.config.memory_fact_model =
      (document.getElementById('setting-memory-model').value || '').trim();
    STATE.config.memory_beliefs_enabled =
      document.getElementById('setting-memory-beliefs').checked;
    STATE.config.memory_mental_models_enabled =
      document.getElementById('setting-memory-mental-models').checked;
    STATE.config.memory_reranker_enabled =
      document.getElementById('setting-memory-reranker').checked;
    const cache = document.getElementById('setting-memory-prompt-cache');
    if (cache) STATE.config.memory_prompt_cache_enabled = cache.checked;
  }

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
      applyDocTooltips();
      showStatus('Settings saved successfully.');
    } else {
      alert('Error saving settings.');
    }
  } catch (err) {
    console.error(err);
  }
}

async function refreshUniverseParamsPanel() {
  const hint = document.getElementById('settings-params-hint');
  const saveBtn = document.getElementById('settings-params-save-btn');
  const tempEl = document.getElementById('setting-univ-temp');
  const topEl = document.getElementById('setting-univ-top-p');
  if (!tempEl) return;
  const uni = STATE.selectedUniversePath || (STATE.activeSession && STATE.activeSession.universe_path);
  const qs = uni ? `?universe=${encodeURIComponent(uni)}` : '';
  try {
    const res = await fetch(`/api/universe/params${qs}`);
    if (!res.ok) {
      if (hint) hint.textContent = tr('no_universe_loaded') || 'Load a universe or start a session to edit sampling params.';
      if (saveBtn) saveBtn.disabled = true;
      return;
    }
    const data = await res.json();
    tempEl.value = data.llm_temperature;
    topEl.value = data.llm_top_p;
    if (hint) hint.textContent = tr('univ_params_info') || 'Temperature and top-p for the loaded universe.';
    if (saveBtn) saveBtn.disabled = false;
  } catch (err) {
    if (saveBtn) saveBtn.disabled = true;
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
      <td><input type="text" value="${escapeHtml(p.name || '')}" data-key="name" data-idx="${idx}"></td>
      <td><input type="text" value="${escapeHtml(p.description || '')}" data-key="description" data-idx="${idx}"></td>
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
    select.innerHTML = '<option value="">-- Write your own below --</option>';
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
      <h3>${escapeHtml(uni.name)}</h3>
      <p class="desc">${escapeHtml(uni.description || '')}</p>
      <div class="path">${escapeHtml(uni.path)}</div>
      <div class="card-saves-list">
        <!-- Saves listed here -->
      </div>
      <div class="card-footer">
        <button class="btn-primary play-new-btn" data-tr="play" data-doc="hub.card_play">Play New</button>
        <button class="btn-secondary export-uni-btn" data-tr="export" data-doc="hub.card_export">Export</button>
        <button class="btn-secondary edit-uni-btn" data-tr="edit" data-doc="hub.card_edit">Edit Universe</button>
        <button class="btn-danger delete-uni-btn" data-tr="delete" data-doc="hub.card_delete">Delete</button>
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
            <div class="save-name">${escapeHtml(save.player_name)}</div>
            <div class="save-meta">${escapeHtml(save.difficulty)} · Turn ${escapeHtml(save.turn_id)} · ${escapeHtml(new Date(save.last_updated).toLocaleString())}</div>
          </div>
          <div class="save-actions">
            <button class="btn-primary btn-sm play-save-btn">▶</button>
            <button class="btn-secondary btn-sm edit-save-btn">Edit</button>
            <button class="btn-secondary btn-sm fork-save-btn">Fork</button>
            <button class="btn-danger btn-sm delete-save-btn">×</button>
          </div>
        `;

        item.querySelector('.play-save-btn').onclick = () => startSession(uni.path, save.save_id, save.difficulty);
        item.querySelector('.edit-save-btn').onclick = () => editSave(uni.path, save.save_id, save.db_path);
        item.querySelector('.fork-save-btn').onclick = () => forkSave(uni.path, save.save_id, save.turn_id);
        item.querySelector('.delete-save-btn').onclick = () => deleteSave(uni.path, save.save_id);
        savesList.appendChild(item);
      });
    }

    card.querySelector('.play-new-btn').onclick = () => loadSetupView(uni.path, 'story');
    card.querySelector('.export-uni-btn').onclick = () => exportUniverse(uni.path, uni.name);
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

// ── Setup View (3-tab lobby) ──
function showSetupTab(tab) {
  document.querySelectorAll('#setup-tabs .tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-setup-tab') === tab);
  });
  ['saves', 'persona', 'story'].forEach(name => {
    const panel = document.getElementById(`setup-panel-${name}`);
    if (panel) panel.classList.toggle('hidden', name !== tab);
  });
  if (tab === 'saves') refreshSetupSavesList();
}

async function loadSetupView(universePath, tab = 'story') {
  STATE.selectedUniversePath = universePath;
  STATE.setupSelectedSaveId = null;
  try {
    const res = await fetch(`/api/setup/questions?universe=${encodeURIComponent(universePath)}`);
    const data = await res.json();

    const container = document.getElementById('setup-questions-container');
    container.innerHTML = '';

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
              <input type="${selectType}" name="setup_q_${escapeHtml(q.setup_id)}" value="${escapeHtml(opt)}" ${oIdx === 0 ? 'checked' : ''}>
              <span>${escapeHtml(opt)}</span>
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
    showSetupTab(tab);
    await loadSetupSaves();
  } catch (err) {
    console.error(err);
    alert('Failed to load questionnaire.');
  }
}

async function loadSetupSaves() {
  if (!STATE.selectedUniversePath) return;
  try {
    const res = await fetch('/api/universes');
    const all = await res.json();
    const uni = (all || []).find(u => u.path === STATE.selectedUniversePath);
    STATE.setupSaves = (uni && uni.saves) || [];
    refreshSetupSavesList();
  } catch (err) {
    console.error(err);
  }
}

function refreshSetupSavesList() {
  const list = document.getElementById('setup-saves-list');
  if (!list) return;
  const key = STATE.setupSort || 'last_updated';
  const saves = (STATE.setupSaves || []).slice().sort((a, b) => {
    const av = a[key] || '';
    const bv = b[key] || '';
    return String(bv).localeCompare(String(av));
  });
  list.innerHTML = '';
  if (!saves.length) {
    list.innerHTML = '<li class="checkpoint-item">No save files.</li>';
    return;
  }
  saves.forEach(save => {
    const li = document.createElement('li');
    li.className = 'checkpoint-item' + (save.save_id === STATE.setupSelectedSaveId ? ' selected' : '');
    li.textContent = `${save.player_name} · ${save.difficulty} · Turn ${save.turn_id} · ${save.last_updated || ''}`;
    li.onclick = () => {
      STATE.setupSelectedSaveId = save.save_id;
      refreshSetupSavesList();
    };
    li.ondblclick = () => startSession(STATE.selectedUniversePath, save.save_id, save.difficulty);
    list.appendChild(li);
  });
}

function selectedSetupSave() {
  return (STATE.setupSaves || []).find(s => s.save_id === STATE.setupSelectedSaveId) || null;
}

function setupSetupLobby() {
  document.querySelectorAll('#setup-tabs .tab-btn').forEach(btn => {
    btn.onclick = () => showSetupTab(btn.getAttribute('data-setup-tab'));
  });
  const sortEl = document.getElementById('setup-saves-sort');
  if (sortEl) sortEl.onchange = () => {
    STATE.setupSort = sortEl.value;
    refreshSetupSavesList();
  };
  const launchFromSaves = () => {
    const save = selectedSetupSave();
    if (!save) {
      alert('Select a save to launch.');
      return;
    }
    startSession(STATE.selectedUniversePath, save.save_id, save.difficulty);
  };
  const launchBtn = document.getElementById('setup-launch-save-btn');
  if (launchBtn) launchBtn.onclick = launchFromSaves;
  document.getElementById('setup-export-save-btn').onclick = () => {
    const save = selectedSetupSave();
    if (!save) return alert('Select a save first.');
    window.location.href = `/api/saves/pack?universe=${encodeURIComponent(STATE.selectedUniversePath)}&save_id=${encodeURIComponent(save.save_id)}`;
  };
  document.getElementById('setup-duplicate-save-btn').onclick = async () => {
    const save = selectedSetupSave();
    if (!save) return alert('Select a save first.');
    const name = prompt('Name for the copy:', `${save.player_name} (copy)`);
    if (!name) return;
    const res = await fetch('/api/saves/duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe_path: STATE.selectedUniversePath, save_id: save.save_id, name })
    });
    if (res.ok) { await loadSetupSaves(); await refreshHub(); showStatus('Save duplicated.'); }
    else alert('Failed to duplicate save.');
  };
  document.getElementById('setup-rename-save-btn').onclick = async () => {
    const save = selectedSetupSave();
    if (!save) return alert('Select a save first.');
    const name = prompt('New name:', save.player_name);
    if (!name) return;
    const res = await fetch('/api/saves/rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe_path: STATE.selectedUniversePath, save_id: save.save_id, name })
    });
    if (res.ok) { await loadSetupSaves(); await refreshHub(); showStatus('Save renamed.'); }
    else alert('Failed to rename save.');
  };
  document.getElementById('setup-edit-save-btn').onclick = () => {
    const save = selectedSetupSave();
    if (!save) return alert('Select a save first.');
    editSave(STATE.selectedUniversePath, save.save_id, save.db_path);
  };
  document.getElementById('setup-delete-save-btn').onclick = async () => {
    const save = selectedSetupSave();
    if (!save) return alert('Select a save first.');
    await deleteSave(STATE.selectedUniversePath, save.save_id);
    STATE.setupSelectedSaveId = null;
    await loadSetupSaves();
  };
  const importBtn = document.getElementById('setup-import-save-btn');
  const importFile = document.getElementById('setup-import-save-file');
  if (importBtn && importFile) {
    importBtn.onclick = () => importFile.click();
    importFile.onchange = () => unpackSaveUpload(importFile.files && importFile.files[0], false);
  }
  const createPersona = document.getElementById('setup-persona-create-btn');
  if (createPersona) createPersona.onclick = async () => {
    const name = prompt('Persona name:');
    if (!name) return;
    const description = prompt('Persona description:') || '';
    STATE.personas = STATE.personas || [];
    STATE.personas.push({ persona_id: generatePersonaId(), name, description });
    await savePersonas();
    fillPersonasTable();
    await populateSetupPersonaPicker();
    const picker = document.getElementById('setup-persona-picker');
    if (picker) picker.value = STATE.personas[STATE.personas.length - 1].persona_id;
    const desc = document.getElementById('setup-player-persona');
    if (desc) desc.value = description;
  };
}

async function unpackSaveUpload(file, force) {
  if (!file || !STATE.selectedUniversePath) return;
  const fd = new FormData();
  fd.append('file', file);
  fd.append('universe_path', STATE.selectedUniversePath);
  if (force) fd.append('force', 'true');
  try {
    const res = await fetch('/api/saves/unpack', { method: 'POST', body: fd });
    const data = await res.json().catch(() => ({}));
    if (res.status === 409 && data.needs_force) {
      if (confirm(data.error + '\n\nImport anyway?')) return unpackSaveUpload(file, true);
      return;
    }
    if (!res.ok) {
      alert(data.error || 'Failed to import save.');
      return;
    }
    await loadSetupSaves();
    await refreshHub();
    showStatus('Save imported.');
  } catch (err) {
    console.error(err);
    alert('Failed to import save.');
  }
}

function exportUniverse(path, name) {
  window.location.href = `/api/universes/export?universe=${encodeURIComponent(path)}`;
}

async function uploadUniverseFile(url, file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(url, { method: 'POST', body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Import failed');
  return data;
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
      STATE.selectedUniversePath = universePath;
      STATE.activeSession = await res.json();
      STATE.activeSession.universe_path = universePath;
      document.getElementById('chat-save-title').textContent = `${STATE.activeSession.universe_name} - ${STATE.activeSession.player_name}`;
      document.getElementById('chat-mode-tag').textContent = STATE.activeSession.difficulty;
      rebuildChatFromHistory();
      updateAmbiance('exploration'); // default ambiance on session load, mirrors tabletop_view.py
      STATE.pendingIntents = {};
      updateMultiplayerLobby();

      await refreshTabletopState();
      showScreen('view-tabletop');
      showStatus('Ready.');
      checkSessionIntegrity();
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
  const playerEid = STATE.activeSession.player_entity_id || 'player';
  const entityRows = Array.isArray(STATE.activeSession.entities) && STATE.activeSession.entities.length
    ? STATE.activeSession.entities
    : Object.entries(STATE.activeSession.current_stats || {}).map(([eid, estats]) => ({
        entity_id: eid,
        name: eid === playerEid ? (STATE.activeSession.player_name || eid) : eid,
        entity_type: (eid === playerEid || eid === 'player') ? 'player' : 'npc',
        stats: estats,
      }));
  entityRows.forEach(ent => {
    const eid = ent.entity_id;
    const name = ent.name || (eid === playerEid ? STATE.activeSession.player_name : eid);
    const etype = ent.entity_type || ((eid === playerEid || eid === 'player') ? 'player' : 'npc');
    const box = document.createElement('div');
    box.className = 'entity-box';
    box.innerHTML = `
      <div class="entity-box-header">
        <span>${escapeHtml(name)}</span>
        <span class="type">${escapeHtml(etype)}</span>
      </div>
    `;
    const stats = ent.stats || {};
    const keys = Object.keys(stats).filter(k => !String(k).startsWith('__')).sort((a, b) => a.localeCompare(b));
    const mods = (STATE.activeSession.modifiers || []).filter(m => m.entity_id === eid);
    if (!keys.length) {
      const empty = document.createElement('div');
      empty.className = 'entity-stat-row';
      empty.innerHTML = `<span class="save-meta">No stats yet.</span>`;
      box.appendChild(empty);
    } else {
      keys.forEach(k => {
        const row = document.createElement('div');
        row.className = 'entity-stat-row';
        const hint = mods
          .filter(m => String(m.stat_key || '').toLowerCase() === String(k).toLowerCase())
          .map(m => {
            const d = Number(m.delta);
            const sign = d >= 0 ? '+' : '';
            return `${sign}${d} · ${m.minutes_remaining}m`;
          })
          .join(', ');
        row.innerHTML = `<span>${escapeHtml(k)}${hint ? ` <span class="stat-mod-hint">${escapeHtml(hint)}</span>` : ''}</span><span class="val">${escapeHtml(stats[k])}</span>`;
        box.appendChild(row);
      });
    }
    statsList.appendChild(box);
  });

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

  // Header + rewind clock
  const clock = STATE.activeSession.time_formatted || '';
  const turnId = STATE.activeSession.turn_id || 0;
  const clockEl = document.getElementById('timeline-clock');
  if (clockEl) clockEl.textContent = clock;
  const headerClock = document.getElementById('chat-clock-label');
  if (headerClock) headerClock.textContent = clock;
  const headerTurn = document.getElementById('chat-turn-label');
  if (headerTurn) headerTurn.textContent = `Turn ${turnId}`;
  syncVerbositySlider(STATE.activeSession.verbosity);

  refreshChroniclerTimeline();

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
  renderLoreHits(STATE.activeSession.lore_hits);
}

function syncVerbositySlider(level) {
  const slider = document.getElementById('chat-verbosity');
  const label = document.getElementById('chat-verbosity-label');
  if (!slider) return;
  const idx = VERBOSITY_LEVELS.indexOf(level);
  slider.value = idx >= 0 ? idx : 2;
  if (label) label.textContent = tr(VERBOSITY_LEVELS[slider.value] || 'talkative');
}

async function refreshChroniclerTimeline() {
  const container = document.getElementById('tabletop-timeline-list');
  if (!container) return;
  try {
    const res = await fetch('/api/session/timeline');
    if (!res.ok) {
      container.innerHTML = `<span class="save-meta" style="padding:8px;">No timeline yet.</span>`;
      return;
    }
    const events = await res.json();
    container.innerHTML = '';
    if (!events.length) {
      container.innerHTML = `<span class="save-meta" style="padding:8px;">No world-news events yet.</span>`;
      return;
    }
    events.forEach(ev => {
      const box = document.createElement('div');
      box.className = 'entity-box';
      box.innerHTML = `
        <div class="entity-box-header">
          <span>Turn ${ev.turn_id}</span>
          <span class="type">${escapeHtml(ev.in_game_time)}</span>
        </div>
        <div class="entity-stat-row"><span>${escapeHtml(ev.description)}</span></div>
      `;
      container.appendChild(box);
    });
  } catch (err) {
    console.error(err);
  }
}

// ── Inventory (left sidebar tab) ──
const CLOUD_FIELDS = {
  gemini: { key: 'gemini_api_key', model: 'gemini_model' },
  claude: { key: 'anthropic_api_key', model: 'anthropic_model' },
  venice: { key: 'venice_api_key', model: 'venice_model' },
  fireworks: { key: 'fireworks_api_key', model: 'fireworks_model' },
  openai: { key: 'openai_api_key', model: 'openai_model' },
  openrouter: { key: 'openrouter_api_key', model: 'openrouter_model' },
};

const VERBOSITY_LEVELS = ['short', 'balanced', 'talkative'];

const RARITY_COLORS = {
  common: '#cdd6f4',
  rare: '#4fa3ff',
  epic: '#a335ee',
  legendary: '#ff8000'
};

function renderInvNodes(nodes, parent, names) {
  (nodes || []).forEach(n => {
    const color = RARITY_COLORS[(n.rarity || 'common').toLowerCase()] || RARITY_COLORS.common;
    const row = document.createElement('div');
    row.className = 'entity-stat-row inv-tree-item';
    row.title = n.description || '';
    const qty = n.quantity && n.quantity !== 1 ? `x${n.quantity}` : '';
    const bag = n.is_container ? ' ▸' : '';
    row.innerHTML = `<span style="color:${color}; font-weight:600;">${escapeHtml(n.name || n.item_id)}${bag}</span><span class="val">${escapeHtml(qty)}</span>`;
    if (n.instance_id) {
      row.style.cursor = 'pointer';
      row.onclick = async (e) => {
        e.stopPropagation();
        const dest = prompt('Move to holder (entity:id, location:id, or instance:id)', '');
        if (!dest) return;
        const parts = dest.split(':');
        await fetch('/api/session/inventory/move', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            instance_id: n.instance_id,
            dest_holder_kind: parts[0],
            dest_holder_id: parts.slice(1).join(':')
          })
        });
        refreshInventory();
      };
    }
    parent.appendChild(row);
    if (n.contents && n.contents.length) {
      const nest = document.createElement('div');
      nest.className = 'inv-nested';
      parent.appendChild(nest);
      renderInvNodes(n.contents, nest, names);
    }
  });
}

async function refreshInventory() {
  const container = document.getElementById('tabletop-inventory-list');
  if (!container) return;
  try {
    const res = await fetch('/api/session/inventory');
    const data = await res.json();
    container.innerHTML = '';
    const tree = data.tree || [];
    const names = data.names || {};
    if (!tree.length) {
      // Backward compat: old {entityId: [items]} shape
      const entityIds = Object.keys(data || {}).filter(k => k !== 'tree' && k !== 'names');
      if (!entityIds.length) {
        container.innerHTML = `<span class="save-meta" style="padding: 8px;">No items.</span>`;
        return;
      }
    }
    if (!tree.length) {
      container.innerHTML = `<span class="save-meta" style="padding: 8px;">No items.</span>`;
      return;
    }
    tree.forEach(root => {
      const title = names[root.holder_id] || root.holder_id;
      const kind = root.holder_kind === 'location' ? 'at' : (root.holder_kind === 'entity' ? 'on' : '');
      const box = document.createElement('div');
      box.className = 'entity-box';
      box.innerHTML = `<div class="entity-box-header"><span>${kind} ${escapeHtml(title)}</span><span class="type">inventory</span></div>`;
      renderInvNodes(root.contents || [], box, names);
      container.appendChild(box);
    });
  } catch (err) {
    console.error('Failed to load inventory:', err);
  }
}

function renderLoreHits(hits) {
  const box = document.getElementById('tabletop-lore-hits');
  if (!box) return;
  const list = hits || [];
  if (!list.length) {
    box.innerHTML = `<span class="save-meta" style="padding:8px;">None this turn.</span>`;
    return;
  }
  box.innerHTML = '';
  list.forEach(h => {
    const row = document.createElement('div');
    row.className = 'lore-hit';
    row.title = h.content || '';
    row.innerHTML = `<strong>${escapeHtml(h.name || '(untitled)')}</strong>
      <span class="save-meta">${escapeHtml(h.source || 'world')} · ${escapeHtml(h.why || 'match')}${h.category ? ' · ' + escapeHtml(h.category) : ''}</span>`;
    box.appendChild(row);
  });
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

function setGenerating(on, statusMsg) {
  STATE.isGenerating = !!on;
  const cancelBtn = document.getElementById('status-cancel-btn');
  const sendBtn = document.getElementById('chat-send-btn');
  if (cancelBtn) cancelBtn.classList.toggle('hidden', !on);
  if (sendBtn) sendBtn.disabled = !!on;
  if (statusMsg) showStatus(statusMsg);
  if (!on) {
    STATE.streamAbort = null;
    showStatus('Ready.');
  }
}

async function cancelActiveGeneration() {
  try {
    await fetch('/api/session/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
  } catch (err) {
    console.error(err);
  }
  if (STATE.streamAbort) {
    try { STATE.streamAbort.abort(); } catch (e) {}
  }
  setGenerating(false, 'Generation cancelled.');
}

function parseSseChunk(buffer, onEvent) {
  const parts = buffer.split('\n\n');
  const rest = parts.pop();
  for (const block of parts) {
    let event = 'message';
    const dataLines = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) continue;
    let payload = {};
    try { payload = JSON.parse(dataLines.join('\n')); } catch (e) { payload = { text: dataLines.join('\n') }; }
    onEvent(event, payload);
  }
  return rest;
}

async function streamSessionTurn(body) {
  const controller = new AbortController();
  STATE.streamAbort = controller;
  const res = await fetch('/api/session/turn/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  });
  if (!res.ok || !res.body) {
    let err = 'Failed to resolve turn.';
    try { err = (await res.json()).error || err; } catch (e) {}
    throw new Error(err);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let liveText = '';
  let liveBubble = null;
  let doneSnapshot = null;
  let streamError = null;

  const ensureLiveBubble = () => {
    if (liveBubble) return liveBubble;
    liveBubble = appendBubble('narrator', '', { streaming: true });
    return liveBubble;
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    buf = parseSseChunk(buf, (event, data) => {
      if (event === 'status' && data.message) showStatus(data.message);
      else if (event === 'token') {
        liveText += data.text || '';
        const bubble = ensureLiveBubble();
        const textDiv = bubble.querySelector('.bubble-text');
        if (textDiv) textDiv.textContent = liveText;
        const chatHistory = document.getElementById('chat-history');
        if (chatHistory) chatHistory.scrollTop = chatHistory.scrollHeight;
      } else if (event === 'done') {
        doneSnapshot = data;
      } else if (event === 'cancelled') {
        streamError = data.error || 'Generation cancelled.';
      } else if (event === 'error') {
        streamError = data.error || 'Turn failed.';
      }
    });
  }

  if (streamError) throw new Error(streamError);
  return doneSnapshot;
}

const CONTINUE_PROMPT =
  'Continue. The player does not take a new action. Advance the scene from here and narrate what happens next.';

async function continueNarration() {
  if (STATE.isGenerating) return;
  await submitTurn(CONTINUE_PROMPT, 'Continue');
}

async function submitTurn(overrideText, displayText) {
  const inputEl = document.getElementById('chat-input');
  const text = (overrideText != null ? String(overrideText) : inputEl.value).trim();
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

    const intentsPayload = Object.assign({}, STATE.pendingIntents);
    STATE.pendingIntents = {};
    setGenerating(true, 'Consulting Arbitrator (Multiplayer)...');
    try {
      const result = await streamSessionTurn({ intents: intentsPayload });
      if (result) {
        STATE.activeSession = Object.assign({}, STATE.activeSession, result);
        rebuildChatFromHistory({ animateLastNarrative: false });
        updateAmbiance(result.game_state_tag);
        await refreshTabletopState();
        updateMultiplayerLobby();
        reportRejectedChanges(result);
        if (result.hardcore_death) await handleHardcoreDeath();
        else maybeAutoCanonize();
      }
    } catch (err) {
      console.error(err);
      appendBubble('system', err.message || 'Connection error resolving turn.', {});
    } finally {
      setGenerating(false);
    }
    return;
  }

  inputEl.value = '';
  appendBubble('player', displayText || text, {});
  setGenerating(true, displayText === 'Continue' ? 'Continuing…' : 'Consulting Arbitrator...');
  if (STATE.config && STATE.config.image_generation_enabled) {
    showImagePlaceholder();
  }
  try {
    const result = await streamSessionTurn({ player_input: text });
    if (result) {
      STATE.activeSession = Object.assign({}, STATE.activeSession, result);
      rebuildChatFromHistory({ animateLastNarrative: false });
      updateAmbiance(result.game_state_tag);
      await refreshTabletopState();
      reportRejectedChanges(result);
      if (result.hardcore_death) await handleHardcoreDeath();
      else maybeAutoCanonize();
    }
  } catch (err) {
    console.error(err);
    appendBubble('system', err.message || 'Connection error resolving turn.', {});
  } finally {
    setGenerating(false);
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
    renderHistoryEvent(ev, animate, isLast);
  });
}

function renderHistoryEvent(ev, animate, isLast) {
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
      isLast: !!isLast,
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
      img.alt = 'Turn illustration';
      img.src = `/assets/${STATE.activeSession.save_id}/turn_${opts.turnId}.png`;
      img.onerror = () => img.remove();
      img.onclick = () => openLightbox(img.src);
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
    // Fast client-side reveal over already-complete text (backend is not
    // token-streaming). Target ~0.4s total so it feels animated but finishes
    // almost immediately; background tabs snap to full text (browsers throttle
    // timers/rAF when the window is unfocused).
    startFastTypewriter(cleanText, textDiv, chatHistory, finishBubble);
  }
  return bubble;
}

/** Cancel any in-flight typewriter (interval or rAF). */
function stopTypewriter() {
  if (STATE.typewriterTimer) {
    clearInterval(STATE.typewriterTimer);
    STATE.typewriterTimer = null;
  }
  if (STATE.typewriterRaf) {
    cancelAnimationFrame(STATE.typewriterRaf);
    STATE.typewriterRaf = null;
  }
}

/**
 * Reveal `fullText` into `textDiv` in a short animated burst.
 * Completes in roughly TYPEWRITER_TARGET_MS regardless of length (chunked).
 */
function startFastTypewriter(fullText, textDiv, chatHistory, onDone) {
  stopTypewriter();
  const len = fullText.length;
  if (len === 0) {
    textDiv.innerHTML = '';
    onDone();
    return;
  }

  // ~400ms full reveal; clamp so tiny messages still animate a beat and
  // huge ones don't crawl. ~10×+ faster than the old 1 char / 15ms path.
  const TYPEWRITER_TARGET_MS = 400;
  const MIN_CHUNK = 24;
  const start = performance.now();
  let index = 0;
  let lastFormatAt = 0;

  const finish = () => {
    stopTypewriter();
    textDiv.innerHTML = formatMarkdown(fullText);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    onDone();
  };

  // If the user tabs away mid-reveal, browsers freeze rAF/timers — snap done.
  const onVis = () => {
    if (document.hidden && STATE.typewriterRaf) finish();
  };
  document.addEventListener('visibilitychange', onVis);

  const tick = (now) => {
    if (document.hidden) {
      document.removeEventListener('visibilitychange', onVis);
      finish();
      return;
    }
    const elapsed = now - start;
    const progress = Math.min(1, elapsed / TYPEWRITER_TARGET_MS);
    // Time-based target index, but always advance by at least MIN_CHUNK.
    const timeTarget = Math.ceil(progress * len);
    index = Math.min(len, Math.max(timeTarget, index + MIN_CHUNK));

    // Avoid formatMarkdown every frame (expensive). Plain text mid-reveal;
    // reformat every ~80 chars and once at the end for *bold*/italics.
    if (index >= len || index - lastFormatAt >= 80) {
      textDiv.innerHTML = formatMarkdown(fullText.slice(0, index));
      lastFormatAt = index;
    } else {
      textDiv.textContent = fullText.slice(0, index);
    }
    chatHistory.scrollTop = chatHistory.scrollHeight;

    if (index < len) {
      STATE.typewriterRaf = requestAnimationFrame(tick);
    } else {
      document.removeEventListener('visibilitychange', onVis);
      finish();
    }
  };

  STATE.typewriterRaf = requestAnimationFrame(tick);
}

function appendBubbleControls(bubble, currentText, opts) {
  const controls = document.createElement('div');
  controls.className = 'bubble-controls';

  const editBtn = document.createElement('button');
  editBtn.className = 'bubble-action-btn';
  editBtn.type = 'button';
  editBtn.textContent = tr('edit') || 'Edit';
  editBtn.onclick = () => startEditMessage(opts.turnId, opts.eventType, currentText);
  controls.appendChild(editBtn);

  if (opts.eventType === 'narrative_text') {
    const regenBtn = document.createElement('button');
    regenBtn.className = 'bubble-action-btn';
    regenBtn.type = 'button';
    regenBtn.textContent = tr('regenerate') || 'Regenerate';
    regenBtn.onclick = () => regenerateMessage(opts.turnId);
    controls.appendChild(regenBtn);

    if (opts.isLast) {
      const contBtn = document.createElement('button');
      contBtn.className = 'bubble-action-btn';
      contBtn.type = 'button';
      contBtn.textContent = 'Continue';
      contBtn.title = 'Advance the scene without a new player action';
      contBtn.onclick = () => continueNarration();
      controls.appendChild(contBtn);
    }

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

function reportRejectedChanges(result) {
  const rejected = (result && result.rejected_changes) || [];
  const inv = (result && result.inventory_changes) || [];
  const parts = [];
  if (inv.length) {
    parts.push(inv.map(c => `${c.action || 'add'} ${c.quantity || 1}× ${c.item_id}`).join(', '));
  }
  if (rejected.length) {
    parts.push('skipped ' + rejected.slice(0, 3).map(r => {
      const key = r.stat_key || r.stat || '?';
      return `${r.entity_id || '?'}.${key}`;
    }).join(', '));
  }
  if (parts.length) showStatus(parts.join(' · '));
}

function renderColoredDiff(el, text) {
  if (!el) return;
  const src = text || '';
  if (!src.trim()) {
    el.textContent = '(no file-level diff — review the list above)';
    return;
  }
  el.innerHTML = '';
  src.split('\n').forEach(line => {
    const span = document.createElement('div');
    if (line.startsWith('+') && !line.startsWith('+++')) span.className = 'diff-added';
    else if (line.startsWith('-') && !line.startsWith('---')) span.className = 'diff-removed';
    else span.className = 'diff-meta';
    span.textContent = line || ' ';
    el.appendChild(span);
  });
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

// Only http(s), same-origin paths and inline images are allowed as markdown
// targets; anything else (javascript:, vbscript:, data:text/html...) becomes '#'.
// `url` is already HTML-escaped by formatMarkdown, so it is attribute-safe.
function safeUrl(url) {
  const u = String(url || '').trim();
  const decoded = u.replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"');
  if (/^(https?:\/\/|\/(?!\/)|data:image\/(png|jpe?g|gif|webp);)/i.test(decoded)) return u;
  return '#';
}

function formatMarkdown(text) {
  // Escape raw HTML first -- text comes from the LLM/DB and must not be able
  // to inject markup; the markdown-ish substitutions below then reintroduce
  // only the specific tags we intend (img/a/b/i/br).
  let html = escapeHtml(text == null ? '' : String(text));
  // Images: ![alt](url)
  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, (_m, alt, url) => `<img src="${safeUrl(url)}" alt="${alt}" style="max-width: 100%; max-height: 400px; border-radius: var(--border-radius); margin: 8px 0; display: block;">`);
  // Links: [text](url)
  html = html.replace(/\[(.*?)\]\((.*?)\)/g, (_m, label, url) => `<a href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer" style="color: var(--blue); text-decoration: underline;">${label}</a>`);
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
          errMsg += `<br>Error: ${escapeHtml(errData.error)}`;
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
          <span>${escapeHtml(query)}</span>
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
    if (stat.stat_id === STATE.creatorEditingStatId) tr.className = 'selected';
    const desc = stat.description || '';
    tr.innerHTML = `
      <td class="stat-id-cell">${escapeHtml(stat.stat_id)}</td>
      <td>${escapeHtml(stat.name || '')}</td>
      <td><span class="save-meta">${escapeHtml(stat.value_type || 'numeric')}</span></td>
      <td class="stat-desc-cell" title="${escapeHtml(desc)}">${escapeHtml(desc)}</td>
      <td>${creatorStatSummaryBadge(stat)}</td>
      <td class="col-actions">
        <button type="button" class="btn-secondary btn-sm" data-edit="1">Edit</button>
        <button type="button" class="btn-table-del">&times;</button>
      </td>
    `;
    tr.querySelector('[data-edit]').onclick = (e) => {
      e.stopPropagation();
      openCreatorStatEditor(stat.stat_id);
    };
    tr.querySelector('.btn-table-del').onclick = (e) => {
      e.stopPropagation();
      if (STATE.creatorEditingStatId === stat.stat_id) {
        STATE.creatorEditingStatId = null;
        closeAllModals();
      }
      STATE.creatorData.stats.splice(rIdx, 1);
      fillCreatorStats();
    };
    tr.onclick = () => openCreatorStatEditor(stat.stat_id);
    table.appendChild(tr);
  });
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function creatorStatSummaryBadge(stat) {
  const p = creatorStatParams(stat);
  if (!p.temporary) return `<span class="stat-badge lasting">Lasting</span>`;
  const dyn = (p.dynamics && typeof p.dynamics === 'object') ? p.dynamics : {};
  const kind = dyn.kind || 'heal';
  const pace = dyn.pace || 'medium';
  return `<span class="stat-badge temp">${escapeHtml(kind)} · ${escapeHtml(pace)}</span>`;
}

function creatorStatParams(stat) {
  if (!stat.parameters || typeof stat.parameters !== 'object' || Array.isArray(stat.parameters)) {
    stat.parameters = {};
  }
  return stat.parameters;
}

function creatorStatOptionsText(params) {
  if (params.options && Array.isArray(params.options)) return params.options.join(', ');
  const min = params.min;
  const max = params.max;
  if (min != null || max != null) return `min:${min != null ? min : 0}, max:${max != null ? max : 100}`;
  return '';
}

function minutesToScale(minutes) {
  const m = Number(minutes) || 0;
  if (m >= 1440 && m % 1440 === 0) return { n: m / 1440, unit: 'days' };
  if (m >= 60 && m % 60 === 0) return { n: m / 60, unit: 'hours' };
  return { n: m || 1, unit: 'minutes' };
}

function creatorPaceMinutes(kind, pace) {
  const table = {
    heal: { fast: 240, medium: 1440, slow: 20160 },
    buildup: { fast: 8, medium: 30, slow: 240 },
    duration: { fast: 90, medium: 480, slow: 1440 }
  };
  const row = table[kind] || table.heal;
  return row[pace] || row.medium;
}

function scaleToMinutes(n, unit) {
  const v = Math.max(1, Number(n) || 1);
  if (unit === 'days') return v * 1440;
  if (unit === 'hours') return v * 60;
  return v;
}

function creatorEditingStat() {
  if (!STATE.creatorData || !STATE.creatorEditingStatId) return null;
  return (STATE.creatorData.stats || []).find(s => s.stat_id === STATE.creatorEditingStatId) || null;
}

function openCreatorStatEditor(statId) {
  STATE.creatorEditingStatId = statId;
  fillCreatorStatEditor();
  openModal('modal-edit-stat');
  fillCreatorStats();
}

function fillCreatorStatEditor() {
  const stat = creatorEditingStat();
  const title = document.getElementById('edit-stat-title');
  if (!stat || !title) return;
  const p = creatorStatParams(stat);
  const dyn = (p.dynamics && typeof p.dynamics === 'object') ? p.dynamics : {};
  const kind = dyn.kind || 'heal';
  const minutes = Number(kind === 'buildup' ? (dyn.peak_hold_minutes || 8) : (dyn.heal_minutes || 10080));
  const scale = minutesToScale(minutes);
  title.textContent = `Edit ${stat.name || stat.stat_id}`;
  document.getElementById('edit-stat-name').value = stat.name || '';
  document.getElementById('edit-stat-type').value = stat.value_type || 'numeric';
  document.getElementById('edit-stat-desc').value = stat.description || '';
  document.getElementById('edit-stat-min').value = p.min != null ? p.min : '';
  document.getElementById('edit-stat-max').value = p.max != null ? p.max : '';
  document.getElementById('edit-stat-temporary').checked = !!p.temporary;
  document.getElementById('edit-stat-kind').value = kind;
  document.getElementById('edit-stat-pace').value = dyn.pace || 'medium';
  document.getElementById('edit-stat-resting').value = dyn.resting != null ? dyn.resting : '';
  document.getElementById('edit-stat-scale-n').value = scale.n;
  document.getElementById('edit-stat-scale-unit').value = scale.unit;
  document.getElementById('edit-stat-crash').value = [].concat(dyn.crash_on || []).join(', ');
  document.getElementById('edit-stat-extend').value = [].concat(dyn.extend_on || []).join(', ');
  const applies = document.getElementById('edit-stat-applies');
  const selected = new Set(stat.applies_to || []);
  applies.innerHTML = '';
  creatorTypeCatalog().forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.type_id;
    opt.textContent = t.name || t.type_id;
    opt.selected = selected.has(t.type_id);
    applies.appendChild(opt);
  });
  syncCreatorStatEditorChrome();
}

function syncCreatorStatEditorChrome() {
  const temp = document.getElementById('edit-stat-temporary').checked;
  const kind = document.getElementById('edit-stat-kind').value;
  document.getElementById('edit-stat-temp-fields').classList.toggle('hidden', !temp);
  document.getElementById('edit-stat-lasting-hint').classList.toggle('hidden', temp);
  document.getElementById('edit-stat-events-wrap').classList.toggle('hidden', !temp || kind !== 'buildup');
  const hints = {
    heal: tr('dyn_hint_heal') || 'Time pulls this toward resting (a wound closing, vitality returning). No crash tags — healing is not an orgasm switch.',
    buildup: tr('dyn_hint_buildup') || 'The scene raises it. Pace is how long it can sit at max. Crash tags snap it to resting; extend tags hold the peak.',
    duration: tr('dyn_hint_duration') || 'A short overlay that wears off on its own (a dose, a rush).'
  };
  document.getElementById('edit-stat-kind-hint').textContent = hints[kind] || '';
}

function applyCreatorStatEditor(remapPace) {
  const stat = creatorEditingStat();
  if (!stat) return;
  const p = creatorStatParams(stat);
  stat.name = document.getElementById('edit-stat-name').value.trim() || stat.name;
  stat.value_type = document.getElementById('edit-stat-type').value;
  stat.description = document.getElementById('edit-stat-desc').value;
  const minV = document.getElementById('edit-stat-min').value;
  const maxV = document.getElementById('edit-stat-max').value;
  if (minV !== '') p.min = Number(minV);
  if (maxV !== '') p.max = Number(maxV);
  const applies = document.getElementById('edit-stat-applies');
  stat.applies_to = Array.from(applies.selectedOptions).map(o => o.value);
  const temp = document.getElementById('edit-stat-temporary').checked;
  p.temporary = temp;
  if (!temp) {
    syncCreatorStatEditorChrome();
    return;
  }
  if (!p.dynamics || typeof p.dynamics !== 'object') p.dynamics = {};
  const kind = document.getElementById('edit-stat-kind').value || 'heal';
  const pace = document.getElementById('edit-stat-pace').value || 'medium';
  const kindChanged = remapPace || p.dynamics.kind !== kind || p.dynamics.pace !== pace;
  p.dynamics.kind = kind;
  p.dynamics.pace = pace;
  p.dynamics.inferred = false;
  const rest = document.getElementById('edit-stat-resting').value;
  if (rest !== '') p.dynamics.resting = Number(rest);
  let minutes = scaleToMinutes(
    document.getElementById('edit-stat-scale-n').value,
    document.getElementById('edit-stat-scale-unit').value
  );
  if (kindChanged) {
    minutes = creatorPaceMinutes(kind, pace);
    const scaled = minutesToScale(minutes);
    document.getElementById('edit-stat-scale-n').value = scaled.n;
    document.getElementById('edit-stat-scale-unit').value = scaled.unit;
  }
  if (kind === 'buildup') {
    p.dynamics.peak_hold_minutes = minutes;
    p.dynamics.crash_on = document.getElementById('edit-stat-crash').value.split(',').map(s => s.trim()).filter(Boolean);
    p.dynamics.extend_on = document.getElementById('edit-stat-extend').value.split(',').map(s => s.trim()).filter(Boolean);
  } else {
    p.dynamics.heal_minutes = minutes;
    p.dynamics.crash_on = [];
    p.dynamics.extend_on = [];
  }
  syncCreatorStatEditorChrome();
}

async function classifyCreatorStat(statId) {
  if (!STATE.creatorData) return;
  const stat = (STATE.creatorData.stats || []).find(s => s.stat_id === statId);
  if (!stat) return;
  showStatus(`Classifying ${stat.name || statId}…`);
  try {
    const hint = (STATE.creatorData.metadata && (STATE.creatorData.metadata.global_lore || STATE.creatorData.metadata.name)) || '';
    const res = await fetch('/api/creator/infer-stats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stats: [stat], world_hint: hint })
    });
    if (!res.ok) {
      showStatus('Could not classify that stat — set Temporary by hand if you want.');
      return;
    }
    const data = await res.json();
    const hit = (data.stats || [])[0];
    if (!hit) return;
    const live = (STATE.creatorData.stats || []).find(s => s.stat_id === statId);
    if (!live) return;
    if (hit.parameters) live.parameters = hit.parameters;
    if (hit.description && !(live.description || '').trim()) live.description = hit.description;
    fillCreatorStats();
    if (STATE.creatorEditingStatId === statId) fillCreatorStatEditor();
    const dyn = (live.parameters && live.parameters.dynamics) || {};
    if (live.parameters && live.parameters.temporary) {
      showStatus(`${live.name}: temporary · ${dyn.kind || '?'} · ${dyn.pace || 'medium'}`);
    } else {
      showStatus(`${live.name}: lasting (won’t tick on its own).`);
    }
  } catch (err) {
    console.error(err);
    showStatus('Could not classify that stat — set Temporary by hand if you want.');
  }
}

async function inferCreatorStatDynamics() {
  if (!STATE.creatorData || !STATE.selectedUniversePath) return;
  showStatus('Classifying temporary stats…');
  try {
    const hint = (STATE.creatorData.metadata && (STATE.creatorData.metadata.global_lore || STATE.creatorData.metadata.name)) || '';
    const res = await fetch('/api/creator/infer-stats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stats: STATE.creatorData.stats || [], world_hint: hint })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || 'Failed to infer temporary stats.');
      return;
    }
    const data = await res.json();
    const incoming = data.stats || [];
    const byId = {};
    incoming.forEach(s => { if (s.stat_id) byId[s.stat_id] = s; });
    (STATE.creatorData.stats || []).forEach(stat => {
      const hit = byId[stat.stat_id];
      if (!hit) return;
      if (hit.parameters) stat.parameters = hit.parameters;
      if (hit.description && !(stat.description || '').trim()) stat.description = hit.description;
    });
    fillCreatorStats();
    if (STATE.creatorEditingStatId) fillCreatorStatEditor();
    showStatus('Profiles updated — open Edit on a row to review.');
  } catch (err) {
    console.error(err);
    alert('Failed to infer temporary stats.');
  }
}

function creatorTypeCatalog() {
  const list = (STATE.creatorData && STATE.creatorData.entity_types) || [];
  if (list.length) return list;
  return [
    { type_id: 'player', name: 'Player', role: 'player', is_builtin: true },
    { type_id: 'npc', name: 'NPC', role: 'npc', is_builtin: true },
    { type_id: 'faction', name: 'Faction', role: 'faction', is_builtin: true },
    { type_id: 'world', name: 'World', role: 'world', is_builtin: true },
  ];
}

function creatorAppliesToCell(stat, rIdx) {
  const selected = new Set(stat.applies_to || []);
  const opts = creatorTypeCatalog().map(t =>
    `<option value="${escapeHtml(t.type_id)}" ${selected.has(t.type_id) ? 'selected' : ''}>${escapeHtml(t.name || t.type_id)}</option>`
  ).join('');
  return `<select multiple data-applies="1" data-idx="${rIdx}" title="Empty = all types">${opts}</select>`;
}

function statAppliesToType(def, typeId) {
  const links = def.applies_to || [];
  if (!links.length) return true;
  return links.includes(typeId);
}

function refreshCreatorTypeSelect() {
  const sel = document.getElementById('entities-new-type');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '';
  creatorTypeCatalog().forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.type_id;
    opt.textContent = `${t.name || t.type_id} (${t.role || t.type_id})`;
    sel.appendChild(opt);
  });
  if ([...sel.options].some(o => o.value === current)) sel.value = current;
}

function fillCreatorEntities() {
  refreshCreatorTypeSelect();
  const table = document.getElementById('table-entities').querySelector('tbody');
  table.innerHTML = '';
  const list = STATE.creatorData.entities || [];
  list.forEach((ent, rIdx) => {
    const tr = document.createElement('tr');
    if (ent.entity_id === STATE.creatorActiveEntityId) tr.className = 'selected';
    tr.innerHTML = `
      <td><input type="text" value="${escapeHtml(ent.entity_id)}" readonly></td>
      <td><input type="text" value="${escapeHtml(ent.entity_type)}" readonly></td>
      <td><input type="text" value="${escapeHtml(ent.name)}" data-key="name" data-idx="${rIdx}"></td>
      <td><input type="text" value="${escapeHtml(ent.description || '')}" data-key="description" data-idx="${rIdx}"></td>
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
  const statDefs = (STATE.creatorData.stats || []).filter(def => statAppliesToType(def, ent.entity_type));
  
  statDefs.forEach(def => {
    const row = document.createElement('div');
    row.className = 'form-group';
    const val = activeStats[def.stat_id] || '';
    row.innerHTML = `
      <label>${escapeHtml(def.name)} (${escapeHtml(def.stat_id)}):</label>
      <input type="text" value="${escapeHtml(val)}" placeholder="E.g., 50 or friendly" data-stat="${escapeHtml(def.stat_id)}">
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
  li.innerHTML = `<span>${escapeHtml(loc.name)} (${escapeHtml(loc.scale)})</span>`;
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
      <td><input type="text" value="${escapeHtml(rule.rule_id)}" readonly></td>
      <td><input type="number" value="${rule.priority || 0}" data-key="priority" data-idx="${rIdx}"></td>
      <td><input type="text" value="${escapeHtml(rule.target_entity || '*')}" data-key="target_entity" data-idx="${rIdx}"></td>
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
      <td>${statSelectHtml(cond.stat || '', cIdx)}</td>
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
      <td><input type="text" value="${escapeHtml(cond.value || '')}" data-key="value" data-idx="${cIdx}"></td>
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
      <td>${statSelectHtml(act.stat || '', aIdx)}</td>
      <td><input type="text" value="${escapeHtml(act.value || act.delta || '')}" data-key="value" data-idx="${aIdx}"></td>
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
  wireStudioFillDown(document.getElementById('table-rules'));
  wireStudioFillDown(document.getElementById('table-conditions'));
  wireStudioFillDown(document.getElementById('table-actions'));
}

function statSelectHtml(selected, idx) {
  const stats = (STATE.creatorData && STATE.creatorData.stats) || [];
  const opts = [`<option value="">—</option>`].concat(stats.map(s => {
    const id = s.stat_id || '';
    const sel = id === selected ? 'selected' : '';
    return `<option value="${escapeHtml(id)}" ${sel}>${escapeHtml(s.name || id)}</option>`;
  }));
  return `<select data-key="stat" data-idx="${idx}">${opts.join('')}</select>`;
}

function wireStudioFillDown(root) {
  if (!root) return;
  root.querySelectorAll('input, select').forEach(input => {
    if (input.dataset.fillDown) return;
    input.dataset.fillDown = '1';
    input.addEventListener('click', (e) => {
      if (!e.shiftKey) return;
      const td = input.closest('td');
      const tr = input.closest('tr');
      if (!td || !tr || !tr.previousElementSibling) return;
      const col = Array.from(tr.children).indexOf(td);
      const src = tr.previousElementSibling.children[col]
        && tr.previousElementSibling.children[col].querySelector('input, select');
      if (!src) return;
      input.value = src.value;
      input.dispatchEvent(new Event('change'));
    });
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
      <td><input type="text" value="${escapeHtml(ev.event_id)}" readonly></td>
      <td><input type="number" value="${ev.trigger_minute}" data-key="trigger_minute" data-idx="${rIdx}"></td>
      <td><input type="text" value="${escapeHtml(ev.title)}" data-key="title" data-idx="${rIdx}"></td>
      <td><input type="text" value="${escapeHtml(ev.description || '')}" data-key="description" data-idx="${rIdx}"></td>
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
      <td><input type="text" value="${escapeHtml(q.setup_id)}" readonly></td>
      <td><input type="text" value="${escapeHtml(q.question)}" data-key="question" data-idx="${rIdx}"></td>
      <td>
        <select data-key="type" data-idx="${rIdx}">
          <option value="text" ${q.type === 'text' ? 'selected' : ''}>text</option>
          <option value="single_choice" ${q.type === 'single_choice' ? 'selected' : ''}>single_choice</option>
          <option value="multi_choice" ${q.type === 'multi_choice' ? 'selected' : ''}>multi_choice</option>
        </select>
      </td>
      <td><input type="text" value="${escapeHtml(q.options ? JSON.stringify(q.options) : '')}" data-key="options" data-idx="${rIdx}"></td>
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
      <td><input type="text" value="${escapeHtml(entry.category || 'General')}" data-key="category" data-idx="${rIdx}"></td>
      <td><input type="text" value="${escapeHtml(entry.name)}" data-key="name" data-idx="${rIdx}"></td>
      <td><input type="text" value="${escapeHtml(entry.keywords || '')}" data-key="keywords" data-idx="${rIdx}" class="${entry.keywords ? '' : 'warn-empty'}" placeholder="keywords help recall"></td>
      <td><input type="text" value="${escapeHtml(entry.text || '')}" data-key="text" data-idx="${rIdx}"></td>
      <td>
        <button class="btn-secondary btn-sm lore-row-pop" type="button">AI</button>
        <button class="btn-table-del">&times;</button>
      </td>
    `;
    tr.querySelector('.lore-row-pop').onclick = (e) => {
      e.stopPropagation();
      triggerPopulateTargets(['lore'], false);
    };
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
  wireStudioFillDown(document.getElementById('table-lore'));
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
  // Creator Studio only — Setup / save-editor tabs reuse .studio-tabs but
  // use data-setup-tab / data-save-tab and have their own handlers.
  document.querySelectorAll('#view-creator .studio-tabs .tab-btn[data-target]').forEach(btn => {
    btn.onclick = (e) => {
      const targetId = e.currentTarget.getAttribute('data-target');
      const panel = targetId ? document.getElementById(targetId) : null;
      if (!panel) return;

      document.querySelectorAll('#view-creator .studio-tabs .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('#view-creator .studio-tab-panel').forEach(p => p.classList.remove('active'));

      e.currentTarget.classList.add('active');
      panel.classList.add('active');

      if (targetId === 'studio-tab-map') {
        setTimeout(drawCanvasMap, 50);
      }
    };
  });

  // Settings tabs only (do NOT match Memory modal tabs — those use
  // data-memory-tab and are wired in setupUIEventListeners).
  document.querySelectorAll('#modal-settings .settings-tabs .settings-tab-btn').forEach(btn => {
    btn.onclick = (e) => {
      document.querySelectorAll('#modal-settings .settings-tabs .settings-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('#modal-settings .settings-panel').forEach(p => p.classList.remove('active'));
      
      e.target.classList.add('active');
      const targetId = e.target.getAttribute('data-target');
      const panel = targetId ? document.getElementById(targetId) : null;
      if (panel) panel.classList.add('active');
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
  document.getElementById('status-cancel-btn').onclick = () => cancelActiveGeneration();

  const hubBtn = document.getElementById('btn-tabletop-hub');
  if (hubBtn) hubBtn.onclick = () => {
    stopAmbiance();
    showScreen('view-hub');
  };

  const rewindHdr = document.getElementById('btn-tabletop-rewind');
  if (rewindHdr) rewindHdr.onclick = () => openCheckpointDialog();

  const verbSlider = document.getElementById('chat-verbosity');
  if (verbSlider) {
    verbSlider.oninput = () => {
      const label = document.getElementById('chat-verbosity-label');
      const level = VERBOSITY_LEVELS[parseInt(verbSlider.value, 10)] || 'talkative';
      if (label) label.textContent = tr(level);
    };
    verbSlider.onchange = async () => {
      const level = VERBOSITY_LEVELS[parseInt(verbSlider.value, 10)] || 'talkative';
      try {
        await fetch('/api/session/verbosity', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ level })
        });
        if (STATE.activeSession) STATE.activeSession.verbosity = level;
      } catch (err) {
        console.error(err);
      }
    };
  }

  const canonBtn = document.getElementById('btn-canonize');
  if (canonBtn) canonBtn.onclick = () => runCanonize(true);

  const checkpointApply = document.getElementById('checkpoint-apply-btn');
  if (checkpointApply) checkpointApply.onclick = () => applyCheckpointRewind();

  const cloudSel = document.getElementById('setting-cloud-provider');
  if (cloudSel) {
    cloudSel.onchange = () => {
      const prev = STATE.cloudProvider;
      const fields = CLOUD_FIELDS[prev];
      if (fields && STATE.config) {
        const keyEl = document.getElementById('setting-cloud-key');
        const modelEl = document.getElementById('setting-cloud-model');
        if (keyEl) STATE.config[fields.key] = keyEl.value;
        if (modelEl) STATE.config[fields.model] = modelEl.value;
      }
      STATE.cloudProvider = cloudSel.value;
      fillCloudFieldsToForm();
    };
  }

  const browseModels = document.getElementById('settings-browse-models-btn');
  if (browseModels) browseModels.onclick = () => openModelBrowser();

  const paramsSave = document.getElementById('settings-params-save-btn');
  if (paramsSave) paramsSave.onclick = () => saveUniverseParams();

  const extractNow = document.getElementById('settings-extract-now-btn');
  if (extractNow) extractNow.onclick = () => {
    closeAllModals();
    memoryExtractNow();
  };
  const browseMem = document.getElementById('settings-browse-memory-btn');
  if (browseMem) browseMem.onclick = () => {
    closeAllModals();
    openMemoryEditor();
  };

  const wallpaperBrowse = document.getElementById('setting-wallpaper-browse');
  const wallpaperFile = document.getElementById('setting-wallpaper-file');
  if (wallpaperBrowse && wallpaperFile) {
    wallpaperBrowse.onclick = () => wallpaperFile.click();
    wallpaperFile.onchange = () => {
      const file = wallpaperFile.files && wallpaperFile.files[0];
      if (!file) return;
      const url = URL.createObjectURL(file);
      document.getElementById('setting-wallpaper').value = url;
      applyWallpaper(url);
    };
  }

  document.addEventListener('keydown', (e) => {
    if (!document.getElementById('view-tabletop').classList.contains('active')) return;
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'TEXTAREA' || tag === 'INPUT') return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'y')) {
      e.preventDefault();
      openCheckpointDialog();
    }
  });

  const memBtn = document.getElementById('btn-open-memory');
  if (memBtn) memBtn.onclick = () => openMemoryEditor();
  document.querySelectorAll('#memory-tabs .settings-tab-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('#memory-tabs .settings-tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.memoryTab = btn.getAttribute('data-memory-tab') || 'models';
      STATE.memorySelectedId = null;
      renderMemoryList();
    };
  });
  const memAdd = document.getElementById('memory-add-fact-btn');
  const memEdit = document.getElementById('memory-edit-btn');
  const memDel = document.getElementById('memory-delete-btn');
  const memExt = document.getElementById('memory-extract-btn');
  const memRef = document.getElementById('memory-refresh-btn');
  if (memAdd) memAdd.onclick = () => memoryAddFact();
  if (memEdit) memEdit.onclick = () => memoryEditSelected();
  if (memDel) memDel.onclick = () => memoryDeleteSelected();
  if (memExt) memExt.onclick = () => memoryExtractNow();
  if (memRef) memRef.onclick = () => loadMemoryData();

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
  document.querySelectorAll('#edit-save-tabs .tab-btn').forEach(btn => {
    btn.onclick = () => switchSaveEditTab(btn.getAttribute('data-save-tab'));
  });
  const modAdd = document.getElementById('edit-mod-add-btn');
  if (modAdd) modAdd.onclick = addSaveModifier;
  const modEnt = document.getElementById('edit-mod-entity');
  if (modEnt) modEnt.onchange = fillSaveModifierSelects;
  const invAdd = document.getElementById('edit-inv-add-btn');
  if (invAdd) invAdd.onclick = () => {
    if (!STATE.editingSaveState) return;
    const name = (document.getElementById('edit-inv-name').value || '').trim();
    if (!name) return;
    const qty = parseInt(document.getElementById('edit-inv-qty').value, 10) || 1;
    const holder = (document.getElementById('edit-inv-holder').value || 'entity:').split(':');
    const isC = document.getElementById('edit-inv-container').checked;
    if (!STATE.editingSaveState.inventory) STATE.editingSaveState.inventory = [];
    STATE.editingSaveState.inventory.push({
      instance_id: 'tmp-' + Date.now(),
      item_id: name.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
      name,
      quantity: qty,
      holder_kind: holder[0] || 'entity',
      holder_id: holder.slice(1).join(':'),
      is_container: isC
    });
    document.getElementById('edit-inv-name').value = '';
    renderSaveInventory();
  };
  const loreAdd = document.getElementById('edit-lore-add-btn');
  if (loreAdd) loreAdd.onclick = () => {
    if (!STATE.editingSaveState) return;
    if (!STATE.editingSaveState.session_lore) STATE.editingSaveState.session_lore = [];
    STATE.editingSaveState.session_lore.push({
      entry_id: '', name: 'New entry', category: 'General', keywords: '', content: ''
    });
    renderSaveLore();
  };
  const addTypeBtn = document.getElementById('entities-add-type-btn');
  if (addTypeBtn) addTypeBtn.onclick = () => {
    const typeId = prompt('New entity type id (e.g. robot, humanoid):');
    if (!typeId) return;
    const role = prompt('Engine role: player, npc, faction, or world', 'npc') || 'npc';
    if (!STATE.creatorData.entity_types) STATE.creatorData.entity_types = creatorTypeCatalog();
    const id = typeId.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_');
    if (STATE.creatorData.entity_types.some(t => t.type_id === id)) return;
    STATE.creatorData.entity_types.push({
      type_id: id,
      name: typeId.trim(),
      role: ['player', 'npc', 'faction', 'world'].includes(role) ? role : 'npc',
      is_builtin: false
    });
    refreshCreatorTypeSelect();
    fillCreatorStats();
  };
  
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
  const inferBtn = document.getElementById('stats-infer-btn');
  if (inferBtn) inferBtn.onclick = inferCreatorStatDynamics;
  const statDone = document.getElementById('edit-stat-done-btn');
  if (statDone) statDone.onclick = () => {
    applyCreatorStatEditor(false);
    fillCreatorStats();
    closeAllModals();
  };
  const statReclass = document.getElementById('edit-stat-reclassify-btn');
  if (statReclass) statReclass.onclick = () => {
    applyCreatorStatEditor(false);
    if (STATE.creatorEditingStatId) classifyCreatorStat(STATE.creatorEditingStatId);
  };
  ['edit-stat-name', 'edit-stat-type', 'edit-stat-desc', 'edit-stat-min', 'edit-stat-max',
   'edit-stat-resting', 'edit-stat-scale-n', 'edit-stat-scale-unit',
   'edit-stat-crash', 'edit-stat-extend', 'edit-stat-applies'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.onchange = () => applyCreatorStatEditor(false);
  });
  const tempEl = document.getElementById('edit-stat-temporary');
  if (tempEl) tempEl.onchange = () => applyCreatorStatEditor(false);
  ['edit-stat-kind', 'edit-stat-pace'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.onchange = () => applyCreatorStatEditor(true);
  });
  document.getElementById('stats-add-btn').onclick = () => {
    const id = document.getElementById('stats-new-id').value.trim();
    const name = document.getElementById('stats-new-name').value.trim();
    const note = (document.getElementById('stats-new-desc').value || '').trim();
    const type = document.getElementById('stats-new-type').value;
    if (!id || !name) return;
    STATE.creatorData.stats.push({ stat_id: id, name, value_type: type, description: note, parameters: {} });
    fillCreatorStats();
    document.getElementById('stats-new-id').value = '';
    document.getElementById('stats-new-name').value = '';
    document.getElementById('stats-new-desc').value = '';
    classifyCreatorStat(id);
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

  const lorePop = document.getElementById('lore-populate-btn');
  if (lorePop) lorePop.onclick = () => triggerPopulateTargets(['lore'], false);
  const mapPop = document.getElementById('map-populate-btn');
  if (mapPop) mapPop.onclick = () => triggerPopulateTargets(['map'], false);
  const assignStats = document.getElementById('entities-assign-stats-btn');
  if (assignStats) assignStats.onclick = () => {
    if (!STATE.creatorActiveEntityId || !STATE.creatorData) return;
    const ent = (STATE.creatorData.entities || []).find(e => e.entity_id === STATE.creatorActiveEntityId);
    if (!ent) return;
    if (!ent.stats) ent.stats = {};
    (STATE.creatorData.stats || []).filter(def => statAppliesToType(def, ent.entity_type)).forEach(def => {
      if (ent.stats[def.stat_id] == null || ent.stats[def.stat_id] === '') {
        ent.stats[def.stat_id] = def.value_type === 'numeric' ? '0' : '';
      }
    });
    fillCreatorEntities();
    showStatus('Assigned defined stats to the selected entity.');
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
      entry_id: generatePersonaId(),
      category: cat,
      name,
      keywords: '',
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

  const canonApply = document.getElementById('canonize-apply-btn');
  if (canonApply) canonApply.onclick = () => applyCanonizeSelection();

  // Apply populate preview (Creator Studio)
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
  const hubImportFile = document.getElementById('hub-import-file');
  document.getElementById('hub-import-btn').onclick = () => {
    if (hubImportFile) hubImportFile.click();
  };
  if (hubImportFile) {
    hubImportFile.onchange = async () => {
      const file = hubImportFile.files && hubImportFile.files[0];
      if (!file) return;
      showStatus('Importing universe...');
      try {
        await uploadUniverseFile('/api/universes/import', file);
        await refreshHub();
        showStatus('Universe imported.');
      } catch (err) {
        alert(err.message || 'Failed to import universe.');
      }
      hubImportFile.value = '';
    };
  }
  const hubImportStFile = document.getElementById('hub-import-st-file');
  document.getElementById('hub-import-st-btn').onclick = () => {
    if (hubImportStFile) hubImportStFile.click();
  };
  if (hubImportStFile) {
    hubImportStFile.onchange = async () => {
      const file = hubImportStFile.files && hubImportStFile.files[0];
      if (!file) return;
      showStatus('Importing SillyTavern card...');
      try {
        await uploadUniverseFile('/api/universes/import-st', file);
        await refreshHub();
        showStatus('SillyTavern card imported.');
      } catch (err) {
        alert(err.message || 'Failed to import card.');
      }
      hubImportStFile.value = '';
    };
  }
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
        renderColoredDiff(document.getElementById('diff-content'), data.diff || 'No changes proposed.');
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

async function triggerPopulateTargets(targets, previewOnly) {
  if (!STATE.selectedUniversePath) return;
  showStatus('Generating content…');
  try {
    const res = await fetch(`/api/creator/populate?universe=${encodeURIComponent(STATE.selectedUniversePath)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets, prompt: '', preview: !!previewOnly })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.error || 'Populate failed.');
      return;
    }
    if (previewOnly) {
      renderColoredDiff(document.getElementById('diff-content'), data.diff || 'No changes proposed.');
      openModal('modal-diff');
    } else {
      await openCreatorStudio(STATE.selectedUniversePath);
      showStatus('Populate applied.');
    }
  } catch (err) {
    console.error(err);
    alert('Populate failed.');
  }
}

function applyDocTooltips() {
  const on = STATE.config && STATE.config.doc_tooltips_enabled !== false;
  document.querySelectorAll('[data-doc]').forEach(el => {
    const ref = el.getAttribute('data-doc') || '';
    const parts = ref.split('.');
    if (parts.length < 2) return;
    if (!on) {
      el.removeAttribute('title');
      return;
    }
    const title = tr(`doc_${parts[0]}_${parts[1]}_t`);
    const body = tr(`doc_${parts[0]}_${parts[1]}`);
    const text = [title, body].filter(s => s && s !== `doc_${parts[0]}_${parts[1]}_t` && s !== `doc_${parts[0]}_${parts[1]}`).join(' — ');
    if (text) el.title = text;
  });
}

async function checkSessionIntegrity() {
  try {
    const res = await fetch('/api/session/integrity');
    if (!res.ok) return;
    const data = await res.json();
    if (data.ok === false) {
      const n = Object.keys(data.mismatches || {}).length;
      showStatus(tr('integrity_warning') || `State cache mismatch on ${n} entit${n === 1 ? 'y' : 'ies'}.`);
    }
  } catch (err) {
    console.error(err);
  }
}

// ── Status Bar Helpers ──
function showStatus(msg) {
  document.getElementById('status-text').textContent = msg;
}

// ── Story Memory editor (facts / beliefs / mental models) ──
async function openMemoryEditor() {
  if (!STATE.activeSession) {
    alert(tr('memory_browser_no_session') || 'Load a game to browse its memory.');
    return;
  }
  STATE.memoryTab = 'models';
  STATE.memorySelectedId = null;
  document.querySelectorAll('#memory-tabs .settings-tab-btn').forEach((b, i) => {
    b.classList.toggle('active', i === 0);
  });
  openModal('modal-memory');
  await loadMemoryData();
}

async function loadMemoryData() {
  try {
    const res = await fetch('/api/session/memory');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showStatus(err.error || 'Failed to load memory');
      return;
    }
    STATE.memoryData = await res.json();
    renderMemoryList();
  } catch (err) {
    console.error(err);
    showStatus('Failed to load memory');
  }
}

function renderMemoryList() {
  const root = document.getElementById('memory-list');
  if (!root) return;
  const data = STATE.memoryData || { facts: [], beliefs: [], mental_models: [] };
  const tab = STATE.memoryTab || 'models';
  const addBtn = document.getElementById('memory-add-fact-btn');
  if (addBtn) addBtn.style.display = tab === 'facts' ? '' : 'none';

  let rows = [];
  if (tab === 'facts') {
    rows = (data.facts || []).map(f => ({
      id: f.fact_id,
      title: f.statement,
      meta: `T${f.turn_id} · ${f.fact_type}${(f.entities && f.entities.length) ? ' · ' + f.entities.join(', ') : ''}`,
    }));
  } else if (tab === 'beliefs') {
    rows = (data.beliefs || []).map(b => ({
      id: b.observation_id,
      title: b.statement,
      meta: `${b.subject || tr('memory_browser_world') || '(world)'} · ${b.trend || ''} · T${b.updated_turn_id}`,
    }));
  } else {
    rows = (data.mental_models || []).map(m => ({
      id: m.model_id,
      title: m.summary,
      meta: `${m.subject || tr('memory_browser_world') || '(world)'} · T${m.updated_turn_id}`,
    }));
  }

  if (!rows.length) {
    const emptyKey = tab === 'facts'
      ? 'memory_browser_empty_facts'
      : (tab === 'beliefs' ? 'memory_browser_empty_beliefs' : 'memory_browser_empty_models');
    root.innerHTML = `<p class="hint">${tr(emptyKey) || 'Nothing here yet.'}</p>`;
    return;
  }

  root.innerHTML = rows.map(r => {
    const sel = STATE.memorySelectedId === r.id ? ' selected' : '';
    const title = escapeHtml(r.title);
    const meta = escapeHtml(r.meta);
    return `<div class="memory-row${sel}" data-id="${r.id}" role="button" tabindex="0">
      <div class="memory-row-title">${title}</div>
      <div class="memory-row-meta">${meta}</div>
    </div>`;
  }).join('');

  root.querySelectorAll('.memory-row').forEach(el => {
    el.onclick = () => {
      STATE.memorySelectedId = Number(el.getAttribute('data-id'));
      renderMemoryList();
    };
  });
}


async function memoryMutate(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || 'Memory update failed');
    return null;
  }
  if (data.memory) {
    STATE.memoryData = data.memory;
    STATE.memorySelectedId = null;
    renderMemoryList();
  }
  return data;
}

async function memoryAddFact() {
  const statement = prompt(tr('memory_browser_col_fact') || 'Fact', '');
  if (statement == null) return;
  const text = statement.trim();
  if (!text) return;
  await memoryMutate('/api/session/memory/fact', { action: 'create', statement: text });
}

async function memoryEditSelected() {
  if (STATE.memorySelectedId == null) {
    alert(tr('memory_browser_select_row') || 'Select a row first.');
    return;
  }
  const tab = STATE.memoryTab;
  const data = STATE.memoryData || {};
  if (tab === 'facts') {
    const f = (data.facts || []).find(x => x.fact_id === STATE.memorySelectedId);
    if (!f) return;
    const statement = prompt(tr('memory_browser_col_fact') || 'Fact', f.statement);
    if (statement == null) return;
    await memoryMutate('/api/session/memory/fact', {
      action: 'update', fact_id: f.fact_id, statement: statement.trim(),
    });
  } else if (tab === 'beliefs') {
    const b = (data.beliefs || []).find(x => x.observation_id === STATE.memorySelectedId);
    if (!b) return;
    const statement = prompt(tr('memory_browser_col_belief') || 'Belief', b.statement);
    if (statement == null) return;
    const subject = prompt(tr('memory_browser_col_subject') || 'Subject', b.subject || '');
    if (subject == null) return;
    await memoryMutate('/api/session/memory/belief', {
      action: 'update',
      observation_id: b.observation_id,
      statement: statement.trim(),
      subject: subject.trim(),
    });
  } else {
    const m = (data.mental_models || []).find(x => x.model_id === STATE.memorySelectedId);
    if (!m) return;
    const summary = prompt(tr('memory_browser_col_profile') || 'Profile', m.summary);
    if (summary == null) return;
    const subject = prompt(tr('memory_browser_col_subject') || 'Subject', m.subject || '');
    if (subject == null) return;
    await memoryMutate('/api/session/memory/model', {
      action: 'update',
      model_id: m.model_id,
      summary: summary.trim(),
      subject: subject.trim(),
    });
  }
}

async function memoryDeleteSelected() {
  if (STATE.memorySelectedId == null) {
    alert(tr('memory_browser_select_row') || 'Select a row first.');
    return;
  }
  if (!confirm(tr('memory_browser_delete_confirm') || 'Delete this memory entry?')) return;
  const tab = STATE.memoryTab;
  if (tab === 'facts') {
    await memoryMutate('/api/session/memory/fact', {
      action: 'delete', fact_id: STATE.memorySelectedId,
    });
  } else if (tab === 'beliefs') {
    await memoryMutate('/api/session/memory/belief', {
      action: 'delete', observation_id: STATE.memorySelectedId,
    });
  } else {
    await memoryMutate('/api/session/memory/model', {
      action: 'delete', model_id: STATE.memorySelectedId,
    });
  }
}

async function memoryExtractNow() {
  showStatus(tr('memory_extracting') || 'Distilling memory from recent story…');
  try {
    // Relative URL — must be same origin as the page (127.0.0.1 vs localhost).
    const res = await fetch('/api/session/memory/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const errMsg = data.error || `Extract failed (HTTP ${res.status})`;
      alert(errMsg);
      showStatus(errMsg);
      return;
    }
    if (data.memory) {
      STATE.memoryData = data.memory;
      STATE.memorySelectedId = null;
      // Jump to Facts so a successful extract is visible (Profiles is default tab).
      STATE.memoryTab = 'facts';
      document.querySelectorAll('#memory-tabs .settings-tab-btn').forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-memory-tab') === 'facts');
      });
      renderMemoryList();
    }
    const msg = data.message || data.error || `Stored ${data.facts_stored || 0} fact(s).`;
    showStatus(msg);
    if (data.status === 'skipped' || data.status === 'error') {
      alert(msg);
    } else if ((data.facts_stored || 0) > 0) {
      showStatus(msg);
    }
  } catch (err) {
    console.error(err);
    // Browser "Could not connect" / Failed to fetch — network or server process gone.
    const detail = (err && err.message) ? err.message : String(err);
    const hint =
      `Could not reach the web server for memory extract (${detail}).\n\n` +
      `Check: (1) terminal still running python main_web.py, ` +
      `(2) open the app at the same host as the server (use http://127.0.0.1:8000 not file://), ` +
      `(3) if you restarted the server, re-open the save so a session is loaded.`;
    alert(hint);
    showStatus('Extract failed — server not reachable');
  }
}

function openLightbox(src) {
  const img = document.getElementById('lightbox-image');
  if (!img) return;
  img.src = src;
  openModal('modal-lightbox');
}

function showImagePlaceholder() {
  const existing = document.getElementById('image-placeholder-bubble');
  if (existing) existing.remove();
  const chatHistory = document.getElementById('chat-history');
  if (!chatHistory) return;
  const bubble = document.createElement('div');
  bubble.id = 'image-placeholder-bubble';
  bubble.className = 'chat-bubble system';
  bubble.textContent = tr('generating_image') || 'Generating illustration…';
  chatHistory.appendChild(bubble);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

async function openCheckpointDialog() {
  if (!STATE.activeSession) return;
  try {
    const res = await fetch('/api/session/checkpoints');
    const checkpoints = res.ok ? await res.json() : [];
    const list = document.getElementById('checkpoint-list');
    if (!list) return;
    list.innerHTML = '';
    const turns = Array.isArray(checkpoints) ? checkpoints.slice().reverse() : [];
    if (!turns.length && STATE.activeSession.turn_id != null) {
      for (let t = STATE.activeSession.turn_id; t >= 0; t--) turns.push(t);
    }
    turns.forEach((turn, i) => {
      const li = document.createElement('li');
      li.className = 'checkpoint-item' + (i === 0 ? ' selected' : '');
      li.dataset.turn = turn;
      li.textContent = tr('turn_fmt', { count: turn }) || `Turn ${turn}`;
      li.onclick = () => {
        list.querySelectorAll('.checkpoint-item').forEach(el => el.classList.remove('selected'));
        li.classList.add('selected');
        STATE.pendingCheckpointTurn = parseInt(turn, 10);
      };
      list.appendChild(li);
    });
    STATE.pendingCheckpointTurn = turns.length ? parseInt(turns[0], 10) : 0;
    openModal('modal-checkpoints');
  } catch (err) {
    console.error(err);
    alert('Could not load checkpoints.');
  }
}

async function applyCheckpointRewind() {
  const turn = STATE.pendingCheckpointTurn;
  if (turn == null) return;
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
      closeAllModals();
      showStatus('Rewind completed.');
    } else {
      alert('Failed to rewind session.');
    }
  } catch (err) {
    console.error(err);
  }
}

async function runCanonize(preview) {
  if (!STATE.activeSession) {
    alert('Start a session first.');
    return;
  }
  showStatus(tr('canonize_running') || 'Canonizing recent story…');
  try {
    const res = await fetch('/api/session/canonize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preview: !!preview })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.error || 'Canonize failed.';
      showStatus(msg);
      if (preview) alert(msg);
      return;
    }
    if (data.applied) {
      const counts = data.counts || {};
      showStatus(tr('canon_applied_msg') || `Canon applied (${counts.entities || 0} entities, ${counts.lore || 0} lore).`);
      return;
    }
    if (!data.diff && !(data.diffs && data.diffs.length)) {
      showStatus(tr('canon_none_msg') || 'Nothing new to canonize.');
      return;
    }
    STATE.canonPreview = data;
    renderCanonizePicker(data);
    openModal('modal-canonize');
    showStatus('Review the canonize preview.');
  } catch (err) {
    console.error(err);
    showStatus('Canonize failed.');
    if (preview) alert('Canonize failed.');
  }
}

function renderCanonizePicker(data) {
  const box = document.getElementById('canonize-picks');
  if (!box) return;
  box.innerHTML = '';
  const lore = data.lore_entries || [];
  const ents = data.entities || [];
  if (!lore.length && !ents.length) {
    box.innerHTML = '<p class="hint">Nothing new to pick.</p>';
  }
  lore.forEach((entry, i) => {
    const id = `canon-lore-${i}`;
    const wrap = document.createElement('label');
    wrap.className = 'canon-pick';
    wrap.innerHTML = `
      <input type="checkbox" id="${id}" data-kind="lore" data-idx="${i}" checked>
      <div>
        <strong>${escapeHtml(entry.name || 'Untitled')}</strong>
        <span class="save-meta"> ${escapeHtml(entry.category || 'General')}${entry.keywords ? ' · ' + escapeHtml(entry.keywords) : ''}</span>
        <div class="canon-pick-body">${escapeHtml(entry.content || '')}</div>
      </div>
    `;
    box.appendChild(wrap);
  });
  ents.forEach((ent, i) => {
    const id = `canon-ent-${i}`;
    const wrap = document.createElement('label');
    wrap.className = 'canon-pick';
    wrap.innerHTML = `
      <input type="checkbox" id="${id}" data-kind="entity" data-idx="${i}" checked>
      <div>
        <strong>${escapeHtml(ent.name || 'Unnamed')}</strong>
        <span class="save-meta"> ${escapeHtml(ent.entity_type || 'npc')}</span>
        <div class="canon-pick-body">${escapeHtml(ent.description || '')}</div>
      </div>
    `;
    box.appendChild(wrap);
  });
  const raw = data.diff || (data.diffs || []).map(d => d.diff || '').join('\n\n');
  renderColoredDiff(document.getElementById('canonize-diff'), raw);
}

async function applyCanonizeSelection() {
  if (!STATE.canonPreview) return;
  const lore = [];
  const entities = [];
  document.querySelectorAll('#canonize-picks input[type="checkbox"]:checked').forEach(cb => {
    const idx = parseInt(cb.getAttribute('data-idx'), 10);
    const kind = cb.getAttribute('data-kind');
    if (kind === 'lore' && STATE.canonPreview.lore_entries[idx]) {
      lore.push(STATE.canonPreview.lore_entries[idx]);
    }
    if (kind === 'entity' && STATE.canonPreview.entities[idx]) {
      entities.push(STATE.canonPreview.entities[idx]);
    }
  });
  if (!lore.length && !entities.length) {
    alert('Tick at least one entry, or cancel.');
    return;
  }
  const scopeEl = document.querySelector('input[name="canon-scope"]:checked');
  const scope = (scopeEl && scopeEl.value) || 'save';
  showStatus('Applying selected canon…');
  try {
    const res = await fetch('/api/session/canonize/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lore_entries: lore, entities, scope })
    });
    const data = await res.json().catch(() => ({}));
    STATE.canonPreview = null;
    if (!res.ok) {
      alert(data.error || 'Failed to apply canonize.');
      return;
    }
    closeAllModals();
    const n = (data.counts && data.counts.lore) || lore.length;
    const where = data.scope === 'world' ? 'world lorebook' : 'this save only';
    showStatus(`Canon applied (${n} lore) — ${where}.`);
  } catch (err) {
    console.error(err);
    alert('Failed to apply canonize.');
  }
}

function maybeAutoCanonize() {
  const box = document.getElementById('chat-canon-auto');
  if (!box || !box.checked || STATE.isGenerating) return;
  runCanonize(false);
}

async function openModelBrowser() {
  const list = document.getElementById('model-list');
  if (!list) return;
  list.innerHTML = '<li class="checkpoint-item">Loading…</li>';
  openModal('modal-models');
  try {
    const res = await fetch('/api/models');
    const data = res.ok ? await res.json() : { models: [] };
    const models = data.models || [];
    list.innerHTML = '';
    if (!models.length) {
      list.innerHTML = '<li class="checkpoint-item">No models returned.</li>';
      return;
    }
    models.forEach(mid => {
      const li = document.createElement('li');
      li.className = 'checkpoint-item';
      li.textContent = mid;
      li.onclick = () => {
        const field = document.getElementById('setting-universal-model');
        if (field) field.value = mid;
        closeAllModals();
        openModal('modal-settings');
      };
      list.appendChild(li);
    });
  } catch (err) {
    list.innerHTML = '<li class="checkpoint-item">Failed to list models.</li>';
  }
}

async function saveUniverseParams() {
  const uni = STATE.selectedUniversePath || null;
  const temp = parseFloat(document.getElementById('setting-univ-temp').value);
  const topP = parseFloat(document.getElementById('setting-univ-top-p').value);
  try {
    const res = await fetch('/api/universe/params', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        universe_path: uni,
        llm_temperature: temp,
        llm_top_p: topP,
      })
    });
    if (res.ok) showStatus('Universe params saved.');
    else alert('Failed to save universe params.');
  } catch (err) {
    console.error(err);
  }
}

// ── Structured save editor ──
function switchSaveEditTab(tab) {
  document.querySelectorAll('#edit-save-tabs .tab-btn').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-save-tab') === tab);
  });
  ['entities', 'inventory', 'lore', 'modifiers', 'toml'].forEach(name => {
    const panel = document.getElementById(`edit-save-panel-${name}`);
    if (panel) panel.classList.toggle('hidden', name !== tab);
  });
}

function lookupEntityStat(stats, def) {
  const empty = { key: (def && def.stat_id) || '', value: '' };
  if (!stats || !def) return empty;
  if (stats[def.stat_id] != null) return { key: def.stat_id, value: stats[def.stat_id] };
  if (def.name && stats[def.name] != null) return { key: def.name, value: stats[def.name] };
  const wantId = String(def.stat_id || '').toLowerCase();
  const wantName = String(def.name || '').toLowerCase();
  for (const k of Object.keys(stats)) {
    const lk = String(k).toLowerCase();
    if (lk === wantId || (wantName && lk === wantName)) return { key: k, value: stats[k] };
  }
  return empty;
}

function statAppliesToSaveEntity(def, typeId) {
  const links = def.applies_to || [];
  if (!links.length) return true;
  return links.includes(typeId);
}

function renderSaveEntityList() {
  const box = document.getElementById('edit-save-entity-list');
  if (!box || !STATE.editingSaveState) return;
  box.innerHTML = '';
  (STATE.editingSaveState.entities || []).forEach(ent => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'edit-save-entity-btn' + (STATE.editingSaveEntityId === ent.entity_id ? ' active' : '');
    row.innerHTML = `<strong>${escapeHtml(ent.name || ent.entity_id)}</strong><span class="save-meta">${escapeHtml(ent.entity_type)} · ${escapeHtml(ent.entity_role)}</span>`;
    row.onclick = () => {
      STATE.editingSaveEntityId = ent.entity_id;
      renderSaveEntityList();
      renderSaveEntityStats();
    };
    box.appendChild(row);
  });
}

function renderSaveEntityStats() {
  const grid = document.getElementById('edit-save-entity-stats');
  const header = document.getElementById('edit-save-entity-header');
  const st = STATE.editingSaveState;
  if (!grid || !st) return;
  const ent = (st.entities || []).find(e => e.entity_id === STATE.editingSaveEntityId);
  if (!ent) {
    header.textContent = 'Select an entity';
    grid.innerHTML = '';
    return;
  }
  header.textContent = `${ent.name} (${ent.entity_type})`;
  grid.innerHTML = '';
  const defs = st.stat_definitions || [];
  const shown = defs.filter(d => statAppliesToSaveEntity(d, ent.entity_type));
  const keys = new Set(shown.map(d => d.stat_id));
  Object.keys(ent.stats || {}).forEach(k => { if (!String(k).startsWith('__')) keys.add(k); });
  const rows = shown.length ? shown : Object.keys(ent.stats || {}).map(k => ({ stat_id: k, name: k, value_type: 'categorical' }));
  rows.forEach(def => {
    if (shown.length && !statAppliesToSaveEntity(def, ent.entity_type) && !(def.stat_id in (ent.stats || {}))) return;
    const wrap = document.createElement('div');
    wrap.className = 'form-group';
    const found = lookupEntityStat(ent.stats, def);
    const val = found.value != null ? found.value : '';
    wrap.innerHTML = `<label>${escapeHtml(def.name || def.stat_id)}</label><input type="text" value="${escapeHtml(val)}">`;
    wrap.querySelector('input').onchange = (e) => {
      if (!ent.stats) ent.stats = {};
      const writeKey = found.key || def.stat_id;
      if (writeKey !== def.stat_id && def.stat_id in ent.stats) delete ent.stats[def.stat_id];
      ent.stats[writeKey] = e.target.value;
    };
    grid.appendChild(wrap);
  });
  if (!rows.length) {
    grid.innerHTML = `<span class="save-meta">No stats linked to type ${escapeHtml(ent.entity_type)}.</span>`;
  }
}

function fillSaveModifierSelects() {
  const entSel = document.getElementById('edit-mod-entity');
  const statSel = document.getElementById('edit-mod-stat');
  if (!entSel || !statSel || !STATE.editingSaveState) return;
  const st = STATE.editingSaveState;
  const prevEnt = entSel.value;
  const prevStat = statSel.value;
  entSel.innerHTML = '';
  (st.entities || []).forEach(e => {
    const opt = document.createElement('option');
    opt.value = e.entity_id;
    opt.textContent = e.name || e.entity_id;
    entSel.appendChild(opt);
  });
  if ([...entSel.options].some(o => o.value === prevEnt)) entSel.value = prevEnt;
  const ent = (st.entities || []).find(e => e.entity_id === entSel.value);
  statSel.innerHTML = '';
  const defs = st.stat_definitions || [];
  const shown = defs.filter(d => !ent || statAppliesToSaveEntity(d, ent.entity_type));
  (shown.length ? shown : defs).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.name || d.stat_id;
    opt.textContent = d.name || d.stat_id;
    statSel.appendChild(opt);
  });
  if ([...statSel.options].some(o => o.value === prevStat)) statSel.value = prevStat;
}

function renderSaveModifiers() {
  const box = document.getElementById('edit-save-modifiers-list');
  if (!box || !STATE.editingSaveState) return;
  fillSaveModifierSelects();
  const items = STATE.editingSaveState.modifiers || [];
  box.innerHTML = '';
  if (!items.length) {
    box.innerHTML = `<span class="save-meta">No temporary effects. Add one for arousal, a drug, adrenaline…</span>`;
    return;
  }
  items.forEach((m, idx) => {
    const row = document.createElement('div');
    row.className = 'inv-row';
    const name = (STATE.editingSaveNames || {})[m.entity_id] || m.entity_id;
    const sign = Number(m.delta) >= 0 ? '+' : '';
    row.innerHTML = `<span>${escapeHtml(name)} · ${escapeHtml(m.stat_key)} ${sign}${m.delta}</span><span class="save-meta">${m.minutes_remaining} min</span>`;
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn-table-del';
    del.textContent = '×';
    del.onclick = () => {
      STATE.editingSaveState.modifiers.splice(idx, 1);
      renderSaveModifiers();
    };
    row.appendChild(del);
    box.appendChild(row);
  });
}

function addSaveModifier() {
  if (!STATE.editingSaveState) return;
  const entityId = document.getElementById('edit-mod-entity').value;
  const statKey = document.getElementById('edit-mod-stat').value;
  const delta = parseFloat(document.getElementById('edit-mod-delta').value);
  const minutes = parseInt(document.getElementById('edit-mod-minutes').value, 10);
  if (!entityId || !statKey || Number.isNaN(delta) || !minutes || minutes < 1) return;
  if (!STATE.editingSaveState.modifiers) STATE.editingSaveState.modifiers = [];
  STATE.editingSaveState.modifiers.push({
    entity_id: entityId,
    stat_key: statKey,
    delta,
    minutes_remaining: minutes,
  });
  renderSaveModifiers();
}

function saveInvHolderLabel(it) {
  const names = STATE.editingSaveNames || {};
  if (it.holder_kind === 'instance') {
    const parent = (STATE.editingSaveState.inventory || []).find(x => x.instance_id === it.holder_id);
    return parent ? `in ${escapeHtml(parent.name || parent.item_id)}` : `in ${escapeHtml(it.holder_id)}`;
  }
  if (it.holder_kind === 'location') return `at ${escapeHtml(names[it.holder_id] || it.holder_id)}`;
  return `on ${escapeHtml(names[it.holder_id] || it.holder_id)}`;
}

function renderSaveInventory() {
  const box = document.getElementById('edit-save-inventory-tree');
  const holderSel = document.getElementById('edit-inv-holder');
  if (!box || !STATE.editingSaveState) return;
  const items = STATE.editingSaveState.inventory || [];
  box.innerHTML = '';
  if (!items.length) {
    box.innerHTML = `<span class="save-meta">No items yet. Add a purse, a toy, cash — whatever this run created.</span>`;
  }
  items.forEach((it, idx) => {
    const row = document.createElement('div');
    row.className = 'inv-row';
    const label = `${escapeHtml(it.name || it.item_id)}${it.is_container ? ' [bag]' : ''}`;
    row.innerHTML = `<span>${label}</span><span class="save-meta">${saveInvHolderLabel(it)}</span>
      <input type="number" min="1" value="${it.quantity || 1}" style="width:64px;">
      <button type="button" class="btn-table-del">&times;</button>`;
    row.querySelector('input').onchange = (e) => { it.quantity = parseInt(e.target.value, 10) || 1; };
    row.querySelector('button').onclick = () => {
      STATE.editingSaveState.inventory.splice(idx, 1);
      renderSaveInventory();
    };
    box.appendChild(row);
  });
  if (holderSel) {
    holderSel.innerHTML = '';
    (STATE.editingSaveState.entities || []).forEach(e => {
      const o = document.createElement('option');
      o.value = `entity:${e.entity_id}`;
      o.textContent = `On ${e.name}`;
      holderSel.appendChild(o);
    });
    items.filter(i => i.is_container).forEach(i => {
      const o = document.createElement('option');
      o.value = `instance:${i.instance_id}`;
      o.textContent = `In ${i.name || i.item_id}`;
      holderSel.appendChild(o);
    });
  }
}

function renderSaveLore() {
  const box = document.getElementById('edit-save-lore-list');
  if (!box || !STATE.editingSaveState) return;
  box.innerHTML = '';
  (STATE.editingSaveState.session_lore || []).forEach((entry, idx) => {
    const card = document.createElement('div');
    card.className = 'lore-edit-card';
    const emptyKw = !(entry.keywords || '').trim();
    card.innerHTML = `
      <div class="form-group"><label>Name</label><input data-k="name" value="${escapeHtml(entry.name || '')}"></div>
      <div class="form-group"><label>Category</label><input data-k="category" value="${escapeHtml(entry.category || '')}"></div>
      <div class="form-group"><label>Keywords ${emptyKw ? '<span class="warn-empty-label">(empty — weaker recall)</span>' : ''}</label>
        <input data-k="keywords" value="${escapeHtml(entry.keywords || '')}" class="${emptyKw ? 'warn-empty' : ''}"></div>
      <div class="form-group"><label>Content</label><textarea data-k="content" rows="3">${escapeHtml(entry.content || '')}</textarea></div>
      <button type="button" class="btn-table-del">Remove</button>`;
    card.querySelectorAll('input, textarea').forEach(el => {
      el.onchange = () => { entry[el.getAttribute('data-k')] = el.value; };
    });
    card.querySelector('button').onclick = () => {
      STATE.editingSaveState.session_lore.splice(idx, 1);
      renderSaveLore();
    };
    box.appendChild(card);
  });
}

async function editSave(universePath, saveId, dbPath) {
  showStatus('Loading save state...');
  try {
    const q = new URLSearchParams({ save_id: saveId || '' });
    if (universePath) q.set('universe', universePath);
    if (dbPath) q.set('db', dbPath);
    const res = await fetch(`/api/saves/state?${q.toString()}`);
    if (!res.ok) {
      let msg = 'Failed to load save state.';
      try {
        const err = await res.json();
        if (err && err.error) msg += '\n' + err.error;
      } catch (e) {}
      alert(msg);
      return;
    }
    const data = await res.json();
    STATE.editingSaveUniversePath = universePath;
    STATE.editingSaveId = saveId;
    STATE.editingSaveDbPath = dbPath || data.db_path || '';
    STATE.editingSaveState = data;
    STATE.editingSaveEntityId = (data.entities && data.entities[0] && data.entities[0].entity_id) || null;
    STATE.editingSaveNames = {};
    (data.entities || []).forEach(e => { STATE.editingSaveNames[e.entity_id] = e.name; });

    const tomlRes = await fetch(`/api/saves/export?universe=${encodeURIComponent(universePath)}&save_id=${encodeURIComponent(saveId)}`);
    if (tomlRes.ok) {
      const t = await tomlRes.json();
      STATE.editingSaveOriginalToml = t.toml;
      document.getElementById('edit-save-toml-textarea').value = t.toml || '';
    }

    document.getElementById('edit-save-title').textContent = `Edit Game State (${saveId.substring(0, 8)}…)`;
    switchSaveEditTab('entities');
    renderSaveEntityList();
    renderSaveEntityStats();
    renderSaveInventory();
    renderSaveLore();
    renderSaveModifiers();
    openModal('modal-edit-save');
    showStatus('Save state loaded.');
  } catch (err) {
    console.error(err);
    alert('Error loading save state.');
  }
}

async function submitSaveEdit() {
  showStatus('Applying save state edits...');
  try {
    const st = STATE.editingSaveState || {};
    const entities = {};
    (st.entities || []).forEach(e => { entities[e.entity_id] = e.stats || {}; });
    const res = await fetch('/api/saves/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        universe_path: STATE.editingSaveUniversePath,
        save_id: STATE.editingSaveId,
        db_path: STATE.editingSaveDbPath || '',
        entities,
        inventory: st.inventory || [],
        session_lore: st.session_lore || [],
        modifiers: st.modifiers || []
      })
    });
    if (res.ok) {
      const data = await res.json();
      closeAllModals();
      await refreshHub();
      showStatus(`Save edited (turn ${data.turn}).`);
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
      li.innerHTML = `<strong>${escapeHtml(name)}:</strong> "${escapeHtml(text)}" `;
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
