/**
 * ============================================================================
 * CodeCoach • Dashboard, Roadmap, Links & Settings Controller (Gotham Edition)
 * ============================================================================
 */

document.addEventListener('DOMContentLoaded', () => {
  initSettingsForm();
});

// --- Dashboard & Telemetry ---
async function loadDashboardStats() {
  try {
    const res = await fetch('/api/dashboard/stats');
    const data = await res.json();

    const mastered = data.topics_mastered || 0;
    const reviewing = data.topics_reviewing || 0;
    const learning = data.topics_learning || 0;
    const total = data.topics_total || 31;
    const locked = Math.max(0, total - (mastered + reviewing + learning));

    const elMastered = document.getElementById('statMastered');
    if (elMastered) elMastered.textContent = mastered;
    const elReviewing = document.getElementById('statReviewing');
    if (elReviewing) elReviewing.textContent = reviewing;
    const elLearning = document.getElementById('statLearning');
    if (elLearning) elLearning.textContent = learning;
    const elLocked = document.getElementById('statLocked');
    if (elLocked) elLocked.textContent = locked;

    const elReviewsDue = document.getElementById('statReviewsDue');
    if (elReviewsDue) elReviewsDue.textContent = data.due_reviews_count;
    const elTokens = document.getElementById('statTokens');
    if (elTokens) elTokens.textContent = (data.total_tokens_used || 0).toLocaleString();

    // Sync streak across app header & badge
    if (window.CodeCoach && window.CodeCoach.updateStreak) {
      window.CodeCoach.updateStreak(data.current_streak || 0);
    }

    // Segmented Mastery Progress Bar
    const bar = document.getElementById('masterySegmentedBar');
    if (bar && total > 0) {
      const pMastered = (mastered / total) * 100;
      const pReviewing = (reviewing / total) * 100;
      const pLearning = (learning / total) * 100;
      const pLocked = (locked / total) * 100;

      const segs = bar.querySelectorAll('.segment');
      if (segs.length >= 4) {
        segs[0].style.width = `${pMastered.toFixed(1)}%`;
        segs[1].style.width = `${pReviewing.toFixed(1)}%`;
        segs[2].style.width = `${pLearning.toFixed(1)}%`;
        segs[3].style.width = `${pLocked.toFixed(1)}%`;
      }
    }

    // Render Score History Chart
    renderScoreHistoryChart(data.score_history);

    // Render Due Retention List
    renderDueRetentionList(data.due_retention_quizzes);

    // Render Links
    loadAllLinks();

    // Trigger Motion Telemetry Count-Ups
    if (window.GothamMotion) {
      window.GothamMotion.animateDashboardNumbers();
    }
  } catch (err) {
    console.error('Error loading dashboard stats:', err);
  }
}

function renderScoreHistoryChart(history) {
  const chart = document.getElementById('scoreHistoryChart');
  if (!chart) return;

  if (!history || !history.length) {
    chart.innerHTML = '<div style="color: var(--text-muted); font-size: 13.5px; width: 100%; text-align: center; padding-top: 40px; font-family: var(--font-mono);">[ No drill telemetry recorded yet. Complete your first 25-Q set to plot score history ]</div>';
    return;
  }

  chart.innerHTML = history.map(item => {
    const heightPercent = Math.max(12, Math.min(100, item.score));
    const isMastered = item.score >= 85;
    const isPassed = item.score >= 70;
    const color = isMastered ? 'var(--status-success)' : (isPassed ? 'var(--accent-yellow)' : 'var(--status-error)');

    return `
      <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; justify-content: flex-end;" title="${item.topic_title}: ${item.score}%">
        <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: ${color};">${item.score.toFixed(0)}%</span>
        <div style="width: 100%; max-width: 34px; height: ${heightPercent}%; background: ${color}; border-radius: 2px 2px 0 0; box-shadow: 0 0 8px ${color}33; transition: height 0.4s ease;"></div>
        <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 48px;">${item.date}</span>
      </div>
    `;
  }).join('');
}

function renderDueRetentionList(quizzes) {
  const container = document.getElementById('retentionHeroContent') || document.getElementById('retentionDueList');
  if (!container) return;

  if (!quizzes || !quizzes.length) {
    container.innerHTML = `
      <div style="padding: 16px 8px; text-align: left;">
        <div style="font-size: 14px; font-weight: 600; color: var(--accent-yellow); margin-bottom: 4px; font-family: var(--font-display); letter-spacing: 0.5px;">ALL GOTHAM GATES CLEAR</div>
        <p style="font-size: 13px; color: var(--text-muted); margin: 0; line-height: 1.5;">No 1-day, 3-day, or 7-day retests due. Complete a 25-question drill to activate a retention gate.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = quizzes.map(q => `
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-left: 3px solid var(--accent-yellow); border-radius: var(--radius-xs); margin-bottom: 8px;">
      <div>
        <div style="font-weight: 600; font-size: 14px; color: var(--text-primary); font-family: var(--font-body);">${q.topic_title}</div>
        <div style="font-size: 12px; color: var(--accent-yellow); font-family: var(--font-mono); margin-top: 2px;">Stage ${q.stage}/3 Retest Due • 5 Questions</div>
      </div>
      <button class="btn-primary" style="font-size: 12.5px; padding: 6px 14px; flex-shrink: 0;" onclick="takeRetentionQuiz(${q.id}, '${q.topic_id}')">Take Retest &rarr;</button>
    </div>
  `).join('');
}

async function takeRetentionQuiz(retentionId, topicId) {
  const scoreInput = prompt(`Gotham Spaced Retest for ${topicId}:\nEnter your score (0 to 100):`, "85");
  if (scoreInput !== null) {
    const score = parseFloat(scoreInput) || 0;
    try {
      const res = await fetch(`/api/retention/submit/${retentionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ score })
      });
      const data = await res.json();
      showToast(data.message);
      loadDashboardStats();
    } catch (e) {
      showToast('Error recording retention test: ' + e.message, 'error');
    }
  }
}

// --- Roadmap: "Gotham Map" Node Layout ---
async function loadRoadmap() {
  const container = document.getElementById('roadmapLevels');
  if (!container) return;
  container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 48px; font-family: var(--font-mono);">[ Surveying Gotham Curriculum Grid... ]</div>';

  try {
    const res = await fetch('/api/curriculum');
    const levels = await res.json();

    // Populate link topic select for custom link modal
    const topicSelect = document.getElementById('linkTopicSelect');
    if (topicSelect) {
      topicSelect.innerHTML = '';
      levels.forEach(lvl => {
        lvl.topics.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.id;
          opt.textContent = `${t.title} (${lvl.title})`;
          topicSelect.appendChild(opt);
        });
      });
    }

    container.innerHTML = levels.map((lvl, lIdx) => `
      <div class="level-block gotham-zone-block">
        <div class="level-title">
          <span>ZONE ${lIdx + 1} // ${lvl.title.toUpperCase()}</span>
          <span style="font-size: 12px; font-weight: 500; color: var(--text-dim); font-family: var(--font-body);">${lvl.description || ''}</span>
        </div>
        <div class="topic-list gotham-node-grid">
          ${lvl.topics.map(t => {
            const isLocked = !t.unlocked;
            const isMastered = t.status === 'Mastered';
            const statusClass = t.status.toLowerCase();

            let badgeHtml = '';
            if (isMastered) {
              badgeHtml = '<span class="status-badge mastered">🦇 MASTERED</span>';
            } else if (isLocked) {
              badgeHtml = '<span class="status-badge locked">🔒 LOCKED</span>';
            } else {
              badgeHtml = `<span class="status-badge ${statusClass}">⚡ ${t.status.toUpperCase()}</span>`;
            }

            return `
              <div class="topic-card gotham-map-node ${isLocked ? 'locked-node' : 'unlocked-node'} ${isMastered ? 'mastered-node' : ''}" 
                   onclick="${isLocked ? `showToast('Complete preceding verification gate to unlock this topic', 'error')` : `window.location.hash='#quiz/${t.id}'`}">
                <div class="topic-header">
                  <span class="node-order-tag">#${t.order}</span>
                  ${badgeHtml}
                </div>
                <div class="topic-title-text">${t.title}</div>
                <div class="topic-desc-text">${t.description || ''}</div>
                <div class="topic-node-footer">
                  <span>High Score: <strong>${t.highest_score.toFixed(0)}%</strong></span>
                  <span class="train-prompt-link">${isLocked ? 'Locked' : '▶ Launch Drill'}</span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = '<div style="color: var(--status-error); text-align: center; padding: 20px;">Failed to load curriculum roadmap.</div>';
  }
}

// --- Curated Links View ---
async function loadAllLinks() {
  const container = document.getElementById('linksContainer');
  if (!container) return;

  try {
    const res = await fetch('/api/links/variables-and-types');
    const links = await res.json();

    container.innerHTML = links.map(l => `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-radius: var(--radius-xs); margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <input type="checkbox" ${l.is_completed ? 'checked' : ''} onclick="toggleLinkCompleted(${l.id})" title="Mark read/completed" style="cursor: pointer; accent-color: var(--accent-yellow);">
          <div>
            <a href="${l.url}" target="_blank" style="color: var(--text-primary); font-weight: 600; text-decoration: none; font-size: 14px;">
              ${l.type === 'video' ? '📺' : '📄'} ${l.title}
            </a>
            <div style="font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono);">${l.level} • ${l.is_active ? 'Verified Link' : 'Unreachable'}</div>
          </div>
        </div>
        <a href="${l.url}" target="_blank" style="font-size: 12px; color: var(--accent-yellow); text-decoration: none; font-family: var(--font-mono);">&nearr; Open</a>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No resources loaded.</div>';
  }
}

async function toggleLinkCompleted(linkId) {
  try {
    await fetch(`/api/links/${linkId}/toggle`, { method: 'PUT' });
    showToast('Resource progress saved.');
  } catch (e) {
    console.error('Failed to toggle link:', e);
  }
}

function openAddLinkModal() {
  const modal = document.getElementById('addLinkModal');
  if (window.GothamMotion) window.GothamMotion.openModalAnimated(modal);
  else modal.classList.add('active');
}

function closeAddLinkModal() {
  const modal = document.getElementById('addLinkModal');
  if (window.GothamMotion) window.GothamMotion.closeModalAnimated(modal);
  else modal.classList.remove('active');
}

async function submitCustomLink(e) {
  e.preventDefault();
  const topicId = document.getElementById('linkTopicSelect').value;
  const title = document.getElementById('linkTitleInput').value.trim();
  const url = document.getElementById('linkUrlInput').value.trim();
  const type = document.getElementById('linkTypeSelect').value;

  try {
    const res = await fetch('/api/links', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic_id: topicId, title, url, type, level: 'intermediate' })
    });
    const link = await res.json();
    closeAddLinkModal();
    showToast('Resource registered to topic!');
    loadAllLinks();
  } catch (err) {
    showToast('Error saving resource: ' + err.message, 'error');
  }
}

// --- Settings View ---
async function loadSettingsView() {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();

    document.getElementById('settingReminderTimes').value = s.reminder_times || '08:00,20:00';
    document.getElementById('settingTimezone').textContent = s.timezone || 'UTC';
    document.getElementById('settingUserEmail').textContent = s.user_email || 'Not configured';
    document.getElementById('settingNtfyTopic').textContent = s.ntfy_topic || 'codecoach_demo';

    document.getElementById('settingPushEnabled').checked = s.push_enabled;
    document.getElementById('settingEmailEnabled').checked = s.email_enabled;
    document.getElementById('settingNtfyEnabled').checked = s.ntfy_enabled;
    document.getElementById('settingPauseReminders').checked = s.reminders_paused;
    document.getElementById('settingQuietHoursEnabled').checked = s.quiet_hours_enabled;
    document.getElementById('settingQuietStart').value = s.quiet_hours_start || '22:00';
    document.getElementById('settingQuietEnd').value = s.quiet_hours_end || '07:00';
  } catch (err) {
    console.error('Error loading settings:', err);
  }
}

function initSettingsForm() {
  const form = document.getElementById('settingsForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      reminder_times: document.getElementById('settingReminderTimes').value.trim(),
      push_enabled: document.getElementById('settingPushEnabled').checked,
      email_enabled: document.getElementById('settingEmailEnabled').checked,
      ntfy_enabled: document.getElementById('settingNtfyEnabled').checked,
      reminders_paused: document.getElementById('settingPauseReminders').checked,
      quiet_hours_enabled: document.getElementById('settingQuietHoursEnabled').checked,
      quiet_hours_start: document.getElementById('settingQuietStart').value.trim(),
      quiet_hours_end: document.getElementById('settingQuietEnd').value.trim()
    };

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      showToast(data.message || 'System preferences committed.');
    } catch (err) {
      showToast('Failed to commit preferences: ' + err.message, 'error');
    }
  });
}

async function sendTestPush() {
  try {
    const res = await fetch('/api/push/test', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
  } catch (e) {
    showToast('Failed to trigger test alert: ' + e.message, 'error');
  }
}

async function sendTestEmail() {
  try {
    const res = await fetch('/api/email/test', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
  } catch (e) {
    showToast('Failed to trigger test email: ' + e.message, 'error');
  }
}
