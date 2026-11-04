/**
 * ============================================================================
 * CodeCoach • Smart Learning Controller (Phase 2 - Gotham Noir Edition)
 * ============================================================================
 * Features:
 * 1. Adaptive Difficulty Metrics & Visual Badge
 * 2. Weak-Spot Drill Launcher (1-Click 10-Question Targeted Sets)
 * 3. Multi-Perspective "Explain It Differently" (Analogy, Simplified, Code-First)
 * 4. Interactive Concept Map (SVG Node-Link Dependency Graph)
 * 5. Personal Notes & SM-2 Spaced Repetition Flashcards Deck
 * 6. Dynamic Study Plan Generator with Progress Sync
 * ============================================================================
 */

let dueFlashcards = [];
let currentCardIndex = 0;
let isCardFlipped = false;
let currentConceptMapData = null;
let activeStudyPlanData = null;

// Expose on window.CodeCoach
window.CodeCoach.startWeakSpotDrill = startWeakSpotDrill;
window.CodeCoach.loadConceptMap = loadConceptMap;
window.CodeCoach.loadFlashcardsView = loadFlashcardsView;
window.CodeCoach.loadStudyPlanView = loadStudyPlanView;
window.CodeCoach.explainConceptDifferently = explainConceptDifferently;
window.CodeCoach.saveCurrentExplanationAsNote = saveCurrentExplanationAsNote;

// ============================================================================
// 1. WEAK-SPOT DRILL LAUNCHER
// ============================================================================

async function startWeakSpotDrill() {
  showToast('🦇 Generating 10-Question Weak-Spot Drill from missed questions...', 'info');
  try {
    const res = await fetch('/api/smart-learning/weak-spot-drill', { method: 'POST' });
    if (!res.ok) throw new Error('Could not generate drill set');
    const data = await res.json();

    // Switch to active drill tab
    switchTab('quiz');

    // Load first question of the weak-spot set
    const container = document.getElementById('quizContent');
    container.innerHTML = `
      <div class="quiz-card" style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 36px; margin-bottom: 10px;">⚡</div>
        <h3 style="font-family: var(--font-display); font-size: 26px; color: var(--accent-yellow); margin-bottom: 6px;">WEAK-SPOT DRILL ACTIVE</h3>
        <p style="color: var(--text-secondary); font-size: 14px; max-width: 500px; margin: 0 auto 16px;">
          ${data.message}
        </p>
        <button class="btn-primary" onclick="loadNextDrillQuestion(${data.set_id})">Launch Question 1 of 10 &rarr;</button>
      </div>
    `;
  } catch (err) {
    showToast('Failed to start Weak-Spot Drill: ' + err.message, 'error');
  }
}

async function loadNextDrillQuestion(setId) {
  try {
    const res = await fetch(`/api/quiz/next/${setId}`);
    const qData = await res.json();
    if (qData) {
      currentSetId = setId;
      renderQuestion(qData, 10);
    } else {
      loadLearningReport(setId);
    }
  } catch (err) {
    showToast('Error loading drill question: ' + err.message, 'error');
  }
}

// ============================================================================
// 2. "EXPLAIN IT DIFFERENTLY" & NOTES CAPTURE
// ============================================================================

function toggleExplainMenu(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('explainDropdownMenu');
  if (menu) {
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  }
}

// Close dropdown on outside click
document.addEventListener('click', () => {
  const menu = document.getElementById('explainDropdownMenu');
  if (menu) menu.style.display = 'none';
});

async function requestExplanationPerspective(perspective) {
  toggleExplainMenu();
  const box = document.getElementById('alternateExplanationContainer');
  if (!box || !activeQuestion) return;

  box.style.display = 'block';
  box.innerHTML = `
    <div style="padding: 12px; font-family: var(--font-mono); font-size: 12px; color: var(--accent-yellow);">
      🦇 Transcribing perspective (${perspective.toUpperCase()}) through Gotham tutor...
    </div>
  `;

  try {
    const res = await fetch('/api/smart-learning/explain-differently', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        concept: activeQuestion.subtopic || activeQuestion.prompt.slice(0, 80),
        current_explanation: activeQuestion.explanation,
        perspective: perspective,
        context_code: activeQuestion.code_snippet
      })
    });
    const data = await res.json();

    const perspectiveBadges = {
      analogy: '🦇 GOTHAM ANALOGY',
      simplified: '👶 SIMPLIFIED (ELI5)',
      code_first: '💻 CODE-FIRST C# 13'
    };

    box.innerHTML = `
      <div class="alternate-explain-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span class="badge badge-topic">${perspectiveBadges[perspective] || perspective.toUpperCase()}</span>
          <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">${data.is_cached ? '⚡ INSTANT CACHE' : '✨ VERIFIED'}</span>
        </div>
        <div style="font-size: 13.5px; line-height: 1.5; color: var(--text-primary); margin-bottom: 10px;">
          ${escapeHtml(data.explanation).replace(/```csharp([\s\S]*?)```/g, '<pre><code class="language-csharp">$1</code></pre>')}
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <button class="btn-secondary" style="font-size: 11px; padding: 4px 10px;" onclick="copyAltExplanation('${escapeHtml(data.explanation).replace(/'/g, "\\'")}')">📋 Copy</button>
          <button class="btn-primary" style="font-size: 11px; padding: 4px 10px;" onclick="saveNoteDirectly('${escapeHtml(activeQuestion.subtopic || 'C# Concept')}', '${escapeHtml(data.explanation).replace(/'/g, "\\'")}')">💾 Save Note</button>
        </div>
      </div>
    `;

    box.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  } catch (err) {
    box.innerHTML = `<div style="color: var(--status-error); padding: 8px;">Failed to generate alternate perspective: ${err.message}</div>`;
  }
}

function copyAltExplanation(text) {
  navigator.clipboard.writeText(text);
  showToast('Copied alternate explanation to clipboard!');
}

async function saveCurrentExplanationAsNote() {
  if (!activeQuestion) return;
  const title = `Insight: ${activeQuestion.subtopic || activeQuestion.topic_id}`;
  const content = `Question: ${activeQuestion.prompt}\n\nCorrect Answer: ${activeQuestion.correct_answer}\n\nExplanation:\n${activeQuestion.explanation}`;
  await saveNoteDirectly(title, content, activeQuestion.topic_id);
}

async function saveNoteDirectly(title, content, topicId = 'csharp-basics') {
  try {
    const res = await fetch('/api/smart-learning/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        content: content,
        topic_id: topicId,
        tags: ['C# .NET 9', topicId]
      })
    });
    if (!res.ok) throw new Error('Could not save note');
    showToast('💾 Saved to Personal Notes!', 'success');
  } catch (err) {
    showToast('Failed to save note: ' + err.message, 'error');
  }
}

// ============================================================================
// 3. INTERACTIVE CONCEPT MAP (SVG Dependency Graph)
// ============================================================================

async function loadConceptMap() {
  const container = document.getElementById('conceptMapContainer');
  if (!container) return;

  container.innerHTML = `
    <div style="text-align: center; padding: 60px 20px;">
      <div class="loading-bat-spinner">🦇</div>
      <p style="font-family: var(--font-mono); font-size: 13px; color: var(--accent-yellow); margin-top: 12px;">Tracing Gotham C# Knowledge Dependencies...</p>
    </div>
  `;

  try {
    const res = await fetch('/api/smart-learning/concept-map');
    const data = await res.json();
    currentConceptMapData = data;
    renderConceptMap(data);
  } catch (err) {
    container.innerHTML = `<div style="color: var(--status-error); padding: 24px;">Failed to load Concept Map: ${err.message}</div>`;
  }
}

function renderConceptMap(data) {
  const container = document.getElementById('conceptMapContainer');
  if (!container) return;

  // Layout parameters for SVG node columns (4 Levels)
  const colWidth = 240;
  const rowHeight = 76;
  const startX = 40;
  const startY = 40;

  // Group nodes by level_id
  const levels = {};
  data.nodes.forEach(n => {
    levels[n.level_id] = levels[n.level_id] || [];
    levels[n.level_id].push(n);
  });

  const levelKeys = Object.keys(levels);
  const nodeCoords = {};

  levelKeys.forEach((lvlKey, colIdx) => {
    const colNodes = levels[lvlKey];
    colNodes.forEach((node, rowIdx) => {
      nodeCoords[node.id] = {
        x: startX + colIdx * colWidth,
        y: startY + rowIdx * rowHeight,
        w: 190,
        h: 56,
        node: node
      };
    });
  });

  const svgWidth = Math.max(1000, startX + levelKeys.length * colWidth + 60);
  const maxRows = Math.max(...Object.values(levels).map(l => l.length));
  const svgHeight = Math.max(540, startY + maxRows * rowHeight + 40);

  // Build SVG Paths for edges
  let pathsHtml = '';
  data.edges.forEach(e => {
    const src = nodeCoords[e.source];
    const tgt = nodeCoords[e.target];
    if (src && tgt) {
      const x1 = src.x + src.w;
      const y1 = src.y + src.h / 2;
      const x2 = tgt.x;
      const y2 = tgt.y + tgt.h / 2;
      const dx = (x2 - x1) / 2;
      const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
      const isActive = src.node.status === 'Mastered' || tgt.node.status !== 'Locked';
      pathsHtml += `<path class="concept-edge-path ${isActive ? 'active' : ''}" id="edge-${e.source}-${e.target}" d="${d}" />`;
    }
  });

  // Build SVG Nodes
  let nodesHtml = '';
  Object.values(nodeCoords).forEach(({ x, y, w, h, node }) => {
    const statusClass = `status-${node.status.toLowerCase()}`;
    const badgeText = node.status === 'Mastered' ? '🦇 MASTERED' : (node.status === 'Locked' ? '🔒 LOCKED' : `${node.status.toUpperCase()}`);

    nodesHtml += `
      <g class="concept-node-group ${statusClass}" data-id="${node.id}" transform="translate(${x}, ${y})" onclick="inspectConceptNode('${node.id}')">
        <rect class="concept-node-rect" width="${w}" height="${h}"></rect>
        <text class="concept-node-text-title" x="12" y="24">${escapeHtml(node.title.slice(0, 22))}</text>
        <text class="concept-node-text-meta" x="12" y="42">${badgeText} • ${Math.round(node.mastery_score)}%</text>
      </g>
    `;
  });

  container.innerHTML = `
    <div class="concept-map-wrapper">
      <div class="concept-map-toolbar">
        <div>
          <span class="mono-step">[ KNOWLEDGE GRAPH // 22 CORE TOPICS ]</span>
          <span style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); margin-left: 10px;">
            ${data.mastered_nodes} Mastered • ${data.learning_nodes} Active • ${data.locked_nodes} Locked
          </span>
        </div>
        <div class="concept-map-legend">
          <span style="color: var(--status-success);">● Mastered</span>
          <span style="color: var(--accent-yellow);">● Active</span>
          <span style="color: var(--text-muted);">● Locked</span>
          <button class="btn-primary" style="font-size: 11px; padding: 4px 10px;" onclick="startWeakSpotDrill()">⚡ Weak-Spot Drill</button>
        </div>
      </div>

      <div style="overflow-x: auto; overflow-y: hidden;">
        <svg class="concept-map-svg-canvas" viewBox="0 0 ${svgWidth} ${svgHeight}" preserveAspectRatio="xMinYMin meet" style="width: ${svgWidth}px; height: ${svgHeight}px;">
          ${pathsHtml}
          ${nodesHtml}
        </svg>
      </div>

      <!-- Node Inspection Drawer -->
      <div class="concept-drawer" id="conceptDrawer">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <span class="mono-step">[ NODE TELEMETRY ]</span>
          <button class="modal-close" style="position: static;" onclick="closeConceptDrawer()">&times;</button>
        </div>
        <div id="conceptDrawerContent"></div>
      </div>
    </div>
  `;
}

function inspectConceptNode(topicId) {
  if (!currentConceptMapData) return;
  const node = currentConceptMapData.nodes.find(n => n.id === topicId);
  if (!node) return;

  const drawer = document.getElementById('conceptDrawer');
  const content = document.getElementById('conceptDrawerContent');
  if (!drawer || !content) return;

  content.innerHTML = `
    <div style="margin-bottom: 14px;">
      <span class="badge badge-topic">LEVEL ${node.order} // ${node.level_title || 'C#'}</span>
      <h3 style="font-family: var(--font-display); font-size: 26px; color: var(--accent-yellow); margin: 8px 0 4px;">${escapeHtml(node.title)}</h3>
      <span style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">Status: <strong>${node.status}</strong> (${Math.round(node.mastery_score)}% verified)</span>
    </div>

    <div style="margin-bottom: 18px;">
      <label style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 6px;">SUBTOPICS COVERED:</label>
      <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px;">
        ${node.subtopics.map(s => `<li style="font-size: 12.5px; color: var(--text-secondary); background: var(--bg-canvas); padding: 4px 8px; border-radius: 2px;">• ${escapeHtml(s)}</li>`).join('')}
      </ul>
    </div>

    ${node.prerequisites && node.prerequisites.length > 0 ? `
      <div style="margin-bottom: 18px;">
        <label style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">PREREQUISITE KNOWLEDGE:</label>
        <span style="font-size: 12px; color: var(--accent-yellow); font-family: var(--font-mono);">${node.prerequisites.join(' &rarr; ')}</span>
      </div>
    ` : ''}

    <div style="margin-top: auto; display: flex; flex-direction: column; gap: 10px; padding-top: 16px; border-top: 1px solid var(--border-steel);">
      <button class="btn-primary" onclick="launchTopicFromMap('${node.id}')">🎯 Start 25-Question Active Drill</button>
      <button class="btn-secondary" onclick="openPlaygroundForTopic('${node.id}')">🥋 Open in Code Playground</button>
      <button class="btn-secondary" onclick="startWeakSpotDrill()">⚡ Target in Weak-Spot Drill</button>
    </div>
  `;

  drawer.classList.add('open');
}

function closeConceptDrawer() {
  const drawer = document.getElementById('conceptDrawer');
  if (drawer) drawer.classList.remove('open');
}

function launchTopicFromMap(topicId) {
  closeConceptDrawer();
  switchTab('quiz');
  startTopicTraining(topicId);
}

function openPlaygroundForTopic(topicId) {
  closeConceptDrawer();
  switchTab('practice');
  const sel = document.getElementById('playgroundChallengeSelect');
  if (sel) {
    const opt = Array.from(sel.options).find(o => o.value.includes(topicId) || o.value.includes('basic'));
    if (opt) {
      sel.value = opt.value;
      sel.dispatchEvent(new Event('change'));
    }
  }
}

// ============================================================================
// 4. PERSONAL NOTES & SM-2 SPACED REPETITION FLASHCARDS
// ============================================================================

async function loadFlashcardsView() {
  await Promise.all([loadDueFlashcards(), loadPersonalNotes()]);
}

async function loadDueFlashcards() {
  const deckContainer = document.getElementById('flashcardDeckContainer');
  if (!deckContainer) return;

  try {
    const res = await fetch('/api/smart-learning/flashcards/due');
    dueFlashcards = await res.json();
    currentCardIndex = 0;
    isCardFlipped = false;
    renderCurrentFlashcard();
  } catch (err) {
    deckContainer.innerHTML = `<div style="color: var(--status-error);">Failed to load review deck: ${err.message}</div>`;
  }
}

function renderCurrentFlashcard() {
  const deckContainer = document.getElementById('flashcardDeckContainer');
  const countBadge = document.getElementById('flashcardDueCount');
  if (countBadge) countBadge.textContent = dueFlashcards.length;

  if (!dueFlashcards || dueFlashcards.length === 0) {
    deckContainer.innerHTML = `
      <div style="text-align: center; padding: 48px 20px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-radius: var(--radius-sm);">
        <div style="font-size: 40px; margin-bottom: 12px;">🦇</div>
        <h3 style="font-family: var(--font-display); font-size: 26px; color: var(--accent-yellow); margin-bottom: 8px;">ZERO CARDS DUE FOR REVIEW</h3>
        <p style="color: var(--text-secondary); font-size: 14px; max-width: 480px; margin: 0 auto 20px;">
          All SM-2 spaced repetition schedules are current. You can generate new flashcards from your missed quiz questions with one click.
        </p>
        <button class="btn-primary" onclick="autoGenerateCardsFromMissed()">⚡ Generate Cards from Missed Questions (0-LLM)</button>
      </div>
    `;
    return;
  }

  const card = dueFlashcards[currentCardIndex];
  deckContainer.innerHTML = `
    <div class="flashcard-stage" onclick="flipActiveFlashcard()">
      <div class="flashcard-card ${isCardFlipped ? 'flipped' : ''}" id="activeFlashcardElement">
        <!-- Front Face -->
        <div class="flashcard-face">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <span class="badge badge-topic">CARD ${currentCardIndex + 1} OF ${dueFlashcards.length}</span>
              <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${card.subtopic || card.topic_id || 'C#'}</span>
            </div>
            <div style="font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 14px; line-height: 1.4;">
              ${escapeHtml(card.front)}
            </div>
            ${card.code_snippet ? `
              <pre class="terminal-well" style="margin-bottom: 14px;"><code class="language-csharp">${escapeHtml(card.code_snippet)}</code></pre>
            ` : ''}
          </div>
          <div style="text-align: center; font-family: var(--font-mono); font-size: 12px; color: var(--accent-yellow);">
            [ Click card or press SPACEBAR to flip ]
          </div>
        </div>

        <!-- Back Face -->
        <div class="flashcard-face flashcard-back" onclick="event.stopPropagation()">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
              <span class="badge badge-type" style="color: var(--status-success); border-color: var(--status-success);">SOLUTION VERIFICATION</span>
              <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">Ease: ${card.ease_factor.toFixed(2)}x • Rep: ${card.repetitions}</span>
            </div>
            <div style="font-size: 14.5px; color: var(--text-primary); line-height: 1.5; white-space: pre-wrap;">
              ${escapeHtml(card.back)}
            </div>
          </div>
          <div>
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin-bottom: 6px; text-align: center;">
              RATE YOUR RECALL (SM-2 INTERVAL ADJUSTMENT):
            </div>
            <div class="flashcard-rating-bar">
              <button class="btn-sm2-again" onclick="rateFlashcard(${card.id}, 1)">[1] Again (1d)</button>
              <button class="btn-sm2-hard" onclick="rateFlashcard(${card.id}, 2)">[2] Hard (1.2x)</button>
              <button class="btn-sm2-good" onclick="rateFlashcard(${card.id}, 3)">[3] Good (${card.interval_days * 2 || 3}d)</button>
              <button class="btn-sm2-easy" onclick="rateFlashcard(${card.id}, 4)">[4] Easy (${Math.round(card.interval_days * card.ease_factor * 1.3) || 7}d)</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  deckContainer.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
}

function flipActiveFlashcard() {
  const el = document.getElementById('activeFlashcardElement');
  if (el) {
    isCardFlipped = !isCardFlipped;
    el.classList.toggle('flipped', isCardFlipped);
  }
}

async function rateFlashcard(cardId, rating) {
  try {
    const res = await fetch(`/api/smart-learning/flashcards/${cardId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating: rating })
    });
    if (!res.ok) throw new Error('Rating evaluation failed');

    // Remove rated card and advance
    dueFlashcards.splice(currentCardIndex, 1);
    if (currentCardIndex >= dueFlashcards.length) currentCardIndex = 0;
    isCardFlipped = false;
    renderCurrentFlashcard();
    showToast(`Card scheduled for next interval (${rating >= 3 ? 'Retained' : 'Reviewing'})`, 'info');
  } catch (err) {
    showToast('Failed to record rating: ' + err.message, 'error');
  }
}

async function autoGenerateCardsFromMissed() {
  try {
    const res = await fetch('/api/smart-learning/flashcards/from-missed', { method: 'POST' });
    const data = await res.json();
    showToast(`🦇 Created ${data.generated_count} flashcards from missed questions!`, 'success');
    await loadDueFlashcards();
  } catch (err) {
    showToast('Error generating cards: ' + err.message, 'error');
  }
}

// Keyboard shortcuts for flashcard flipping and rating
document.addEventListener('keydown', (e) => {
  if (window.CodeCoach.activeTab !== 'flashcards') return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  if (e.code === 'Space') {
    e.preventDefault();
    flipActiveFlashcard();
  } else if (isCardFlipped && dueFlashcards.length > 0) {
    const card = dueFlashcards[currentCardIndex];
    if (e.key === '1') rateFlashcard(card.id, 1);
    else if (e.key === '2') rateFlashcard(card.id, 2);
    else if (e.key === '3') rateFlashcard(card.id, 3);
    else if (e.key === '4') rateFlashcard(card.id, 4);
  }
});

// Personal Notes Library
async function loadPersonalNotes() {
  const listContainer = document.getElementById('notesListContainer');
  if (!listContainer) return;

  try {
    const res = await fetch('/api/smart-learning/notes');
    const notes = await res.json();

    if (!notes || notes.length === 0) {
      listContainer.innerHTML = `
        <div style="text-align: center; padding: 24px; color: var(--text-muted); font-family: var(--font-mono); font-size: 13px;">
          No personal notes yet. Click "+ Create Note" or use "💾 Save to Notes" on any chat answer.
        </div>
      `;
      return;
    }

    listContainer.innerHTML = `
      <div class="notes-grid">
        ${notes.map(n => `
          <div class="note-card">
            <div>
              <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <h4 style="font-family: var(--font-body); font-size: 15px; font-weight: 600; color: var(--accent-yellow); margin: 0;">${escapeHtml(n.title)}</h4>
                <button class="icon-btn" style="color: var(--status-error); padding: 2px;" onclick="deleteNote(${n.id})" title="Delete Note">✕</button>
              </div>
              <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 12px; white-space: pre-wrap;">
                ${escapeHtml(n.content.slice(0, 160))}${n.content.length > 160 ? '...' : ''}
              </p>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-subtle); padding-top: 8px;">
              <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">${n.topic_id || 'General'}</span>
              <button class="btn-secondary" style="font-size: 11px; padding: 3px 8px;" onclick="generateCardsFromNote(${n.id})">🎴 Make Cards</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (err) {
    listContainer.innerHTML = `<div style="color: var(--status-error);">Failed to load notes: ${err.message}</div>`;
  }
}

async function deleteNote(noteId) {
  if (!confirm('Delete this personal note?')) return;
  try {
    await fetch(`/api/smart-learning/notes/${noteId}`, { method: 'DELETE' });
    showToast('Note deleted');
    await loadPersonalNotes();
  } catch (err) {
    showToast('Failed to delete note: ' + err.message, 'error');
  }
}

async function generateCardsFromNote(noteId) {
  try {
    const res = await fetch(`/api/smart-learning/notes/${noteId}/flashcards`, { method: 'POST' });
    const cards = await res.json();
    showToast(`Generated ${cards.length} flashcards from note!`, 'success');
    await loadDueFlashcards();
  } catch (err) {
    showToast('Failed to generate cards: ' + err.message, 'error');
  }
}

function openCreateNoteModal() {
  const modal = document.getElementById('createNoteModal');
  if (modal) modal.classList.add('open');
}

function closeCreateNoteModal() {
  const modal = document.getElementById('createNoteModal');
  if (modal) modal.classList.remove('open');
}

async function submitCreateNote(e) {
  e.preventDefault();
  const title = document.getElementById('newNoteTitle').value.trim();
  const content = document.getElementById('newNoteContent').value.trim();
  const topicId = document.getElementById('newNoteTopic').value;

  if (!title || !content) return;

  try {
    await fetch('/api/smart-learning/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        content: content,
        topic_id: topicId,
        tags: [topicId]
      })
    });
    closeCreateNoteModal();
    document.getElementById('newNoteForm').reset();
    showToast('Note saved!', 'success');
    await loadPersonalNotes();
  } catch (err) {
    showToast('Error saving note: ' + err.message, 'error');
  }
}

// ============================================================================
// 5. STUDY PLAN GENERATOR & PROGRESS TRACKER
// ============================================================================

async function loadStudyPlanView() {
  const container = document.getElementById('studyPlanContainer');
  if (!container) return;

  container.innerHTML = `
    <div style="text-align: center; padding: 40px 20px;">
      <div class="loading-bat-spinner">🦇</div>
      <p style="font-family: var(--font-mono); font-size: 13px; color: var(--accent-yellow); margin-top: 10px;">Syncing Study Milestones & Progress...</p>
    </div>
  `;

  try {
    const res = await fetch('/api/smart-learning/study-plan/active');
    const plan = await res.json();
    activeStudyPlanData = plan;

    if (!plan) {
      renderStudyPlanCreator();
    } else {
      renderActiveStudyPlan(plan);
    }
  } catch (err) {
    container.innerHTML = `<div style="color: var(--status-error);">Failed to load study plan: ${err.message}</div>`;
  }
}

function renderStudyPlanCreator() {
  const container = document.getElementById('studyPlanContainer');
  container.innerHTML = `
    <div class="telemetry-card" style="max-width: 680px; margin: 0 auto; padding: 32px 24px;">
      <div style="text-align: center; margin-bottom: 24px;">
        <span class="mono-step">[ SYLLABUS ARCHITECT ]</span>
        <h3 style="font-family: var(--font-display); font-size: 32px; color: var(--accent-yellow); margin: 6px 0;">CREATE YOUR GOTHAM STUDY PLAN</h3>
        <p style="color: var(--text-secondary); font-size: 14px;">Select a goal and daily time commitment to generate a structured week-by-week timeline.</p>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px;">
        <button class="option-btn" onclick="selectPresetPlan('Junior .NET Developer', 8, 30)">
          <strong style="color: var(--accent-yellow); display: block;">Junior .NET Developer</strong>
          <span style="font-size: 12px; color: var(--text-muted);">8 Weeks • 30 mins/day</span>
        </button>
        <button class="option-btn" onclick="selectPresetPlan('Mid-Level C# Backend Specialist', 6, 45)">
          <strong style="color: var(--accent-yellow); display: block;">Mid-Level C# Specialist</strong>
          <span style="font-size: 12px; color: var(--text-muted);">6 Weeks • 45 mins/day</span>
        </button>
      </div>

      <form id="customStudyPlanForm" onsubmit="submitCustomPlan(event)" style="display: flex; flex-direction: column; gap: 14px;">
        <div>
          <label style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Target Role or Goal</label>
          <input type="text" id="planGoalTitle" class="chat-input" placeholder="e.g. Junior .NET Core Developer in 8 Weeks" required>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
          <div>
            <label style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Duration (Weeks)</label>
            <input type="number" id="planWeeks" class="chat-input" value="8" min="2" max="16" required>
          </div>
          <div>
            <label style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px;">Daily Minutes Budget</label>
            <select id="planDailyMins" class="chat-input" style="width: 100%;">
              <option value="15">15 mins / day</option>
              <option value="30" selected>30 mins / day</option>
              <option value="45">45 mins / day</option>
              <option value="60">60 mins / day</option>
            </select>
          </div>
        </div>
        <button type="submit" class="btn-primary" style="margin-top: 10px;">Generate Structured Study Plan &rarr;</button>
      </form>
    </div>
  `;
}

function selectPresetPlan(role, weeks, mins) {
  document.getElementById('planGoalTitle').value = `${role} in ${weeks} Weeks`;
  document.getElementById('planWeeks').value = weeks;
  document.getElementById('planDailyMins').value = mins;
}

async function submitCustomPlan(e) {
  e.preventDefault();
  const goal = document.getElementById('planGoalTitle').value.trim();
  const weeks = parseInt(document.getElementById('planWeeks').value, 10);
  const mins = parseInt(document.getElementById('planDailyMins').value, 10);

  try {
    const res = await fetch('/api/smart-learning/study-plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        goal_title: goal,
        target_role: goal,
        duration_weeks: weeks,
        daily_minutes: mins
      })
    });
    if (!res.ok) throw new Error('Could not create plan');
    showToast('🦇 Study Plan generated successfully!', 'success');
    await loadStudyPlanView();
  } catch (err) {
    showToast('Failed to create plan: ' + err.message, 'error');
  }
}

function renderActiveStudyPlan(plan) {
  const container = document.getElementById('studyPlanContainer');
  container.innerHTML = `
    <div>
      <!-- Hero Telemetry Card -->
      <div class="telemetry-card" style="margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 14px;">
          <div>
            <span class="mono-step">[ ACTIVE GOAL // WEEK ${plan.current_week} OF ${plan.duration_weeks} ]</span>
            <h3 style="font-family: var(--font-display); font-size: 28px; color: var(--accent-yellow); margin: 6px 0 2px;">
              ${escapeHtml(plan.goal_title)}
            </h3>
            <span style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">
              Daily Target: <strong>${plan.daily_minutes} mins</strong> • Overall Progress: <strong>${plan.overall_progress_pct}%</strong>
            </span>
          </div>
          <button class="btn-secondary" style="font-size: 12px;" onclick="resetStudyPlan(${plan.id})">🔄 Reset Plan</button>
        </div>

        <div class="studyplan-progress-track">
          <div class="studyplan-progress-fill" style="width: ${plan.overall_progress_pct}%;"></div>
        </div>
      </div>

      <!-- Week-by-Week Milestones -->
      <div class="studyplan-timeline">
        ${plan.weeks.map(w => {
          const isCurrent = w.week_number === plan.current_week;
          const isDone = w.completed;
          return `
            <div class="studyplan-week-card ${isCurrent ? 'current-active-week' : ''} ${isDone ? 'completed-week' : ''}">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="badge ${isDone ? 'badge-diff' : (isCurrent ? 'badge-topic' : 'badge-type')}">
                    WEEK ${w.week_number} ${isDone ? '✅ COMPLETED' : (isCurrent ? '⚡ CURRENT FOCUS' : '')}
                  </span>
                  <h4 style="font-family: var(--font-display); font-size: 20px; color: var(--text-primary); margin: 0;">${escapeHtml(w.title)}</h4>
                </div>
                <span style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-yellow);">${Math.round(w.progress_pct)}%</span>
              </div>

              <p style="font-size: 13.5px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.4;">
                ${escapeHtml(w.goal_description)}
              </p>

              <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px;">
                ${w.topic_titles.map((tTitle, idx) => `
                  <button class="badge badge-topic" style="cursor: pointer;" onclick="launchTopicFromMap('${w.topic_ids[idx]}')">
                    ${escapeHtml(tTitle)} &rarr;
                  </button>
                `).join('')}
              </div>

              <div class="studyplan-progress-track" style="margin: 0;">
                <div class="studyplan-progress-fill" style="width: ${w.progress_pct}%;"></div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

async function resetStudyPlan(planId) {
  if (!confirm('Archive this study plan and create a new one?')) return;
  try {
    await fetch(`/api/smart-learning/study-plan/${planId}`, { method: 'DELETE' });
    showToast('Study plan archived');
    await loadStudyPlanView();
  } catch (err) {
    showToast('Error resetting plan: ' + err.message, 'error');
  }
}

