/**
 * Dashboard, Roadmap, Links & Settings Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  initSettingsForm();
});

// --- Dashboard ---
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
    const elStreak = document.getElementById('streakCount');
    if (elStreak) elStreak.textContent = data.current_streak;

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
  } catch (err) {
    console.error('Error loading dashboard stats:', err);
  }
}

function renderScoreHistoryChart(history) {
  const chart = document.getElementById('scoreHistoryChart');
  if (!chart) return;

  if (!history || !history.length) {
    chart.innerHTML = '<div style="color: var(--text-muted); font-size: 13.5px; width: 100%; text-align: center; padding-top: 40px; font-family: var(--font-mono);">[ No completed sets yet. Complete your first 25-Q drill to visualize score telemetry ]</div>';
    return;
  }

  chart.innerHTML = history.map(item => {
    const heightPercent = Math.max(12, Math.min(100, item.score));
    const isMastered = item.score >= 85;
    const isPassed = item.score >= 70;
    const color = isMastered ? 'var(--status-success)' : (isPassed ? 'var(--accent-cyan)' : 'var(--status-error)');

    return `
      <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; justify-content: flex-end;" title="${item.topic_title}: ${item.score}%">
        <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: ${color};">${item.score.toFixed(0)}%</span>
        <div style="width: 100%; max-width: 32px; height: ${heightPercent}%; background: ${color}; border-radius: 2px 2px 0 0; transition: height 0.4s ease;"></div>
        <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 46px;">${item.date}</span>
      </div>
    `;
  }).join('');
}

function renderDueRetentionList(quizzes) {
  const container = document.getElementById('retentionHeroContent') || document.getElementById('retentionDueList');
  if (!container) return;

  if (!quizzes || !quizzes.length) {
    container.innerHTML = `
      <div style="padding: 18px 12px; text-align: left;">
        <div style="font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">All Spaced Repetition Gates Clear</div>
        <p style="font-size: 13px; color: var(--text-muted); margin: 0; line-height: 1.5;">No 1-day, 3-day, or 7-day retests currently scheduled. Complete a 25-question drill to activate a retention gate.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = quizzes.map(q => `
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); margin-bottom: 8px;">
      <div>
        <div style="font-weight: 600; font-size: 14px; color: var(--text-primary); font-family: var(--font-ui);">${q.topic_title}</div>
        <div style="font-size: 12px; color: var(--status-warning); font-family: var(--font-mono); margin-top: 2px;">Stage ${q.stage}/3 Gate Due • 5 Questions</div>
      </div>
      <button class="btn-primary" style="font-size: 12.5px; padding: 6px 14px; flex-shrink: 0;" onclick="takeRetentionQuiz(${q.id}, '${q.topic_id}')">Take 5-Q Quiz &rarr;</button>
    </div>
  `).join('');
}

async function takeRetentionQuiz(retentionId, topicId) {
  // Simple prompt-based or inline 5-question quick check
  const scoreInput = prompt(`Retention Quiz for ${topicId} (Stage Check):\nEnter your score (0 to 100):`, "85");
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
      showToast('Error recording retention quiz: ' + e.message, 'error');
    }
  }
}

// --- Roadmap View ---
async function loadRoadmap() {
  const container = document.getElementById('roadmapLevels');
  container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 40px;">Loading curriculum roadmap...</div>';

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

    container.innerHTML = levels.map(lvl => `
      <div class="level-block">
        <div class="level-title">
          <span>📚 ${lvl.title}</span>
          <span style="font-size: 12px; font-weight: 500; color: var(--text-dim);">${lvl.description || ''}</span>
        </div>
        <div class="topic-list">
          ${lvl.topics.map(t => {
            const isLocked = !t.unlocked;
            return `
              <div class="topic-card ${isLocked ? 'locked' : ''}" onclick="${isLocked ? `showToast('Complete previous topics to unlock')` : `window.location.hash='#quiz/${t.id}'`}">
                <div class="topic-header">
                  <span style="font-size: 12px; font-weight: 700; color: var(--text-muted);">#${t.order}</span>
                  <span class="status-badge ${t.status}">${t.status}</span>
                </div>
                <div style="font-weight: 700; font-size: 15px; margin-bottom: 6px; color: var(--text-main);">${t.title}</div>
                <div style="font-size: 12.5px; color: var(--text-muted); line-height: 1.4; margin-bottom: 12px;">${t.description || ''}</div>
                <div style="display: flex; justify-content: space-between; font-size: 11.5px; color: var(--text-dim); border-top: 1px solid var(--border-color); padding-top: 8px;">
                  <span>Best: <strong>${t.highest_score.toFixed(0)}%</strong></span>
                  <span>${isLocked ? '🔒 Locked' : '▶ Train'}</span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = '<div style="color: #ef4444;">Failed to load roadmap.</div>';
  }
}

// --- Links View ---
async function loadAllLinks() {
  const container = document.getElementById('linksContainer');
  try {
    const res = await fetch('/api/links/variables-and-types');
    const links = await res.json();

    container.innerHTML = links.map(l => `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-app); border: 1px solid var(--border-color); border-radius: 6px; margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <input type="checkbox" ${l.is_completed ? 'checked' : ''} onclick="toggleLinkCompleted(${l.id})" title="Mark read/watched" style="cursor: pointer;">
          <div>
            <a href="${l.url}" target="_blank" style="color: var(--text-main); font-weight: 600; text-decoration: none; font-size: 14px;">
              ${l.type === 'video' ? '📺' : '📄'} ${l.title}
            </a>
            <div style="font-size: 11.5px; color: var(--text-muted);">${l.level} • ${l.is_active ? '✅ Link verified' : '⚠️ Unreachable'}</div>
          </div>
        </div>
        <a href="${l.url}" target="_blank" style="font-size: 12px; color: var(--accent-cyan); text-decoration: none;">&nearr; Visit</a>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No links loaded.</div>';
  }
}

async function toggleLinkCompleted(linkId) {
  try {
    await fetch(`/api/links/${linkId}/toggle`, { method: 'PUT' });
    showToast('Link progress saved.');
  } catch (e) {
    console.error('Failed to toggle link:', e);
  }
}

function openAddLinkModal() {
  document.getElementById('addLinkModal').classList.add('active');
}

function closeAddLinkModal() {
  document.getElementById('addLinkModal').classList.remove('active');
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
    showToast('Custom link saved successfully!');
    loadAllLinks();
  } catch (err) {
    showToast('Error saving link: ' + err.message, 'error');
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
      showToast(data.message || 'Settings saved successfully!');
    } catch (err) {
      showToast('Failed to save settings: ' + err.message, 'error');
    }
  });
}

async function sendTestPush() {
  try {
    const res = await fetch('/api/push/test', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
  } catch (e) {
    showToast('Failed to send test push: ' + e.message, 'error');
  }
}

async function sendTestEmail() {
  try {
    const res = await fetch('/api/email/test', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
  } catch (e) {
    showToast('Failed to send test email: ' + e.message, 'error');
  }
}

