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
function parseTimeList(raw) {
  const parts = (raw || '').split(',').map(s => s.trim()).filter(Boolean);
  if (!parts.length) return { ok: false, error: 'Add at least one reminder time (HH:MM).' };
  const re = /^([01]\d|2[0-3]):([0-5]\d)$/;
  for (const p of parts) {
    if (!re.test(p)) return { ok: false, error: `Invalid time "${p}". Use 24h HH:MM format (e.g. 08:00).` };
  }
  return { ok: true, value: parts.join(',') };
}

function parseSingleTime(raw, label) {
  const re = /^([01]\d|2[0-3]):([0-5]\d)$/;
  const v = (raw || '').trim();
  if (!re.test(v)) return { ok: false, error: `${label} must be HH:MM in 24h format (00:00–23:59).` };
  return { ok: true, value: v };
}

function syncQuietHoursInputs() {
  const checkbox = document.getElementById('settingQuietHoursEnabled');
  if (!checkbox) return;
  const enabled = checkbox.checked;
  const startInput = document.getElementById('settingQuietStart');
  const endInput = document.getElementById('settingQuietEnd');
  if (startInput) {
    startInput.disabled = !enabled;
    startInput.style.opacity = enabled ? '1' : '0.45';
    startInput.style.cursor = enabled ? 'text' : 'not-allowed';
  }
  if (endInput) {
    endInput.disabled = !enabled;
    endInput.style.opacity = enabled ? '1' : '0.45';
    endInput.style.cursor = enabled ? 'text' : 'not-allowed';
  }
}

async function loadSettingsView() {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();

    const remInput = document.getElementById('settingReminderTimes');
    if (remInput) remInput.value = s.reminder_times || '08:00,20:00';

    const tzEl = document.getElementById('settingTimezone');
    if (tzEl) tzEl.textContent = s.timezone || 'UTC';

    const emailEl = document.getElementById('settingUserEmail');
    if (emailEl) emailEl.textContent = s.user_email || 'Not configured';

    const emailInput = document.getElementById('settingUserEmailInput');
    if (emailInput) {
      emailInput.value = s.custom_email || '';
      emailInput.placeholder = s.default_email ? `Default: ${s.default_email}` : 'e.g. batman@wayne-enterprises.com';
    }

    const ntfyEl = document.getElementById('settingNtfyTopic');
    if (ntfyEl) ntfyEl.textContent = s.ntfy_topic || 'codecoach_demo';

    const ntfyInput = document.getElementById('settingNtfyTopicInput');
    if (ntfyInput) {
      ntfyInput.value = s.custom_ntfy_topic || '';
      ntfyInput.placeholder = s.default_ntfy_topic ? `Default: ${s.default_ntfy_topic}` : 'e.g. gotham_knight_csharp';
    }

    const pushBox = document.getElementById('settingPushEnabled');
    if (pushBox) pushBox.checked = s.push_enabled;

    const emailBox = document.getElementById('settingEmailEnabled');
    if (emailBox) emailBox.checked = s.email_enabled;

    const ntfyBox = document.getElementById('settingNtfyEnabled');
    if (ntfyBox) ntfyBox.checked = s.ntfy_enabled;

    const pauseBox = document.getElementById('settingPauseReminders');
    if (pauseBox) pauseBox.checked = s.reminders_paused;

    const quietBox = document.getElementById('settingQuietHoursEnabled');
    if (quietBox) quietBox.checked = s.quiet_hours_enabled;

    const qStart = document.getElementById('settingQuietStart');
    if (qStart) qStart.value = s.quiet_hours_start || '22:00';

    const qEnd = document.getElementById('settingQuietEnd');
    if (qEnd) qEnd.value = s.quiet_hours_end || '07:00';

    // Storage, Model, and App URL
    const storageEngineEl = document.getElementById('settingStorageEngine');
    if (storageEngineEl && s.storage_engine) {
      storageEngineEl.textContent = s.storage_engine;
    }
    const activeModelEl = document.getElementById('settingActiveModel');
    if (activeModelEl && s.model_name) {
      const isGroq = s.groq_configured || s.model_name.includes('qwen') || s.model_name.includes('gpt-oss');
      const isGrok = s.grok_configured || s.model_name.includes('grok');
      if (isGroq) {
        activeModelEl.textContent = `⚡ Groq (${s.model_name})`;
        activeModelEl.style.borderColor = 'rgba(245, 197, 24, 0.5)';
        activeModelEl.style.color = 'var(--accent-yellow)';
      } else if (isGrok) {
        activeModelEl.textContent = `🦇 xAI Grok (${s.model_name})`;
        activeModelEl.style.borderColor = 'rgba(245, 197, 24, 0.5)';
        activeModelEl.style.color = 'var(--accent-yellow)';
      } else {
        activeModelEl.textContent = s.model_name;
      }
    }
    const appUrlEl = document.getElementById('settingAppUrl');
    if (appUrlEl && s.app_url) {
      appUrlEl.textContent = s.app_url;
    }
    const storageHint = document.getElementById('settingStorageHint');
    if (storageHint && s.storage_engine) {
      storageHint.style.display = s.storage_engine.includes('Ephemeral') ? 'block' : 'none';
    }
    const sysFooterEl = document.getElementById('systemStorageStatus');
    if (sysFooterEl && s.storage_engine) {
      sysFooterEl.textContent = `SYSTEM::STATUS • ${s.storage_engine} Active`;
    }

    // Google OAuth & Gmail API State
    const googleBadge = document.getElementById('googleAuthBadge');
    const googleConnectedView = document.getElementById('googleConnectedView');
    const googleDisconnectedView = document.getElementById('googleDisconnectedView');
    const googleConnectedEmail = document.getElementById('googleConnectedEmail');
    const googleConfigNote = document.getElementById('googleConfigNote');

    if (s.google_connected && s.google_email) {
      if (googleBadge) {
        googleBadge.textContent = 'CONNECTED';
        googleBadge.className = 'badge badge-completed';
      }
      if (googleConnectedView) googleConnectedView.style.display = 'flex';
      if (googleDisconnectedView) googleDisconnectedView.style.display = 'none';
      if (googleConnectedEmail) googleConnectedEmail.textContent = s.google_email;
    } else {
      if (googleBadge) {
        googleBadge.textContent = s.google_oauth_configured ? 'NOT CONNECTED' : 'UNCONFIGURED';
        googleBadge.className = 'badge badge-topic';
      }
      if (googleConnectedView) googleConnectedView.style.display = 'none';
      if (googleDisconnectedView) googleDisconnectedView.style.display = 'block';
      if (googleConfigNote) {
        googleConfigNote.innerHTML = s.google_oauth_configured
          ? 'Ready to connect. Click "Sign in with Google" to grant <code class="inline-code">gmail.send</code> permissions.'
          : 'Requires <code class="inline-code">GOOGLE_OAUTH_CLIENT_ID</code> &amp; <code class="inline-code">GOOGLE_OAUTH_CLIENT_SECRET</code> in Vercel environment variables.';
      }
    }

    syncQuietHoursInputs();
  } catch (err) {
    console.error('Error loading settings:', err);
  }
}

function initSettingsForm() {
  const form = document.getElementById('settingsForm');
  if (!form) return;

  const quietBox = document.getElementById('settingQuietHoursEnabled');
  if (quietBox) {
    quietBox.addEventListener('change', syncQuietHoursInputs);
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Client-side 24h validation
    const timesVal = parseTimeList(document.getElementById('settingReminderTimes').value);
    if (!timesVal.ok) {
      return showToast(timesVal.error, 'error');
    }

    const quietOn = document.getElementById('settingQuietHoursEnabled').checked;
    let quietStart = document.getElementById('settingQuietStart').value.trim();
    let quietEnd = document.getElementById('settingQuietEnd').value.trim();
    if (quietOn) {
      const qs = parseSingleTime(quietStart, 'Quiet start');
      const qe = parseSingleTime(quietEnd, 'Quiet end');
      if (!qs.ok) return showToast(qs.error, 'error');
      if (!qe.ok) return showToast(qe.error, 'error');
      quietStart = qs.value;
      quietEnd = qe.value;
    }

    const customEmail = document.getElementById('settingUserEmailInput')?.value.trim() || '';
    if (customEmail && (!customEmail.includes('@') || !customEmail.includes('.'))) {
      return showToast('Invalid email address format.', 'error');
    }

    const customNtfy = document.getElementById('settingNtfyTopicInput')?.value.trim() || '';
    const pushEnabled = document.getElementById('settingPushEnabled').checked;

    // Issue 3: If user turns on Push notifications, prompt browser subscription if not already granted
    if (pushEnabled && 'Notification' in window && Notification.permission !== 'granted') {
      if (typeof window.requestAndSubscribePush === 'function') {
        showToast('Requesting browser notification permissions...');
        await window.requestAndSubscribePush();
      }
    }

    const payload = {
      reminder_times: timesVal.value,
      push_enabled: pushEnabled,
      email_enabled: document.getElementById('settingEmailEnabled').checked,
      ntfy_enabled: document.getElementById('settingNtfyEnabled').checked,
      reminders_paused: document.getElementById('settingPauseReminders').checked,
      quiet_hours_enabled: quietOn,
      quiet_hours_start: quietStart,
      quiet_hours_end: quietEnd,
      user_email: customEmail,
      ntfy_topic: customNtfy
    };

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Validation failed on server.');
      }
      // Re-fetch persisted values to confirm
      await loadSettingsView();
      if (typeof loadGlobalSettings === 'function') {
        await loadGlobalSettings();
      }
      showToast(data.message || 'System preferences committed and confirmed.');

      if (payload.push_enabled && typeof window.requestAndSubscribePush === 'function') {
        await window.requestAndSubscribePush(false);
      }
    } catch (err) {
      showToast('Failed to commit preferences: ' + err.message, 'error');
    }
  });
}

async function registerCurrentDevice() {
  if (typeof window.requestAndSubscribePush === 'function') {
    showToast('Registering this device with Gotham Signal service...', 'info');
    const ok = await window.requestAndSubscribePush(false);
    if (ok) {
      showToast('🦇 Device subscription confirmed! Ready for Web Push test.');
    }
  } else {
    showToast('Push notifications not supported in this browser.', 'error');
  }
}

async function sendTestPush() {
  try {
    if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      return showToast('This browser does not support Web Push. ntfy may still work.', 'error');
    }

    // Must be a user gesture path (button click) — good for iOS/Chrome
    if (Notification.permission === 'denied') {
      return showToast('Notifications are blocked. Allow them in the browser site settings.', 'error');
    }

    if (typeof window.requestAndSubscribePush === 'function') {
      const ok = await window.requestAndSubscribePush(Notification.permission === 'granted');
      if (!ok && Notification.permission !== 'granted') {
        return; // requestAndSubscribePush already toasted
      }
    }

    const res = await fetch('/api/push/test', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.message || 'Push test failed');

    if ((data.web_push_delivered || 0) === 0) {
      if (data.subscriptions_registered > 0) {
        showToast(
          (data.ntfy_delivered ? 'ntfy delivered. ' : '') +
            `Found ${data.subscriptions_registered} registered device(s), but Web Push failed: ${data.delivery_errors?.[0] || 'Invalid crypto keys or endpoint.'}`,
          'error'
        );
      } else {
        showToast(
          (data.ntfy_delivered ? 'ntfy delivered. ' : '') +
            'Web Push: 0 devices in DB. Click "Register This Device", Allow notifications in browser, then Test Push again.',
          'error'
        );
      }
    } else {
      showToast(data.message || `Web Push delivered to ${data.web_push_delivered} device(s)!`);
    }
  } catch (e) {
    showToast('Test push failed: ' + e.message, 'error');
  }
}

async function sendTestEmail() {
  try {
    showToast('Dispatching test transmission...', 'info');

    const customEmail =
      document.getElementById('settingUserEmailInput')?.value.trim() || '';

    const res = await fetch('/api/email/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(customEmail ? { to: customEmail } : {}),
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || data.message || 'Failed to send test email');
    }

    if (data.status === 'simulated' || data.delivered === false) {
      showToast(
        data.message ||
          'Could not dispatch live email. Showing preview.',
        'error'
      );
      if (data.html_preview && typeof openEmailPreviewModal === 'function') {
        openEmailPreviewModal(data);
      }
      return;
    }

    const providerLabel = data.provider === 'gmail_api' ? 'Gmail API' : 'SMTP';
    showToast(data.message || `Email sent via ${providerLabel} to ${data.target_email || 'your inbox'}!`);
  } catch (e) {
    showToast('Test email failed: ' + e.message, 'error');
  }
}

async function connectGoogleAccount() {
  try {
    showToast('Initializing Google Sign-in...', 'info');
    const res = await fetch('/api/auth/google/url');
    const data = await res.json();
    if (!data.configured || !data.url) {
      alert(
        'Google OAuth Credentials Missing!\n\n' +
        'To enable Sign in with Google & Gmail API in production:\n' +
        '1. Go to Google Cloud Console (console.cloud.google.com) -> APIs & Services -> Credentials\n' +
        '2. Create OAuth 2.0 Client ID (Web Application)\n' +
        '3. Add Authorized redirect URI:\n   ' + (data.redirect_uri || 'https://codecoach-blush.vercel.app/api/auth/google/callback') + '\n' +
        '4. Add to Vercel Project -> Settings -> Environment Variables:\n' +
        '   - GOOGLE_OAUTH_CLIENT_ID\n   - GOOGLE_OAUTH_CLIENT_SECRET\n' +
        '5. Redeploy.'
      );
      return;
    }
    window.location.href = data.url;
  } catch (err) {
    showToast('Google OAuth initialization error: ' + err.message, 'error');
  }
}

async function disconnectGoogleAccount() {
  if (!confirm('Disconnect your Google account? Real email transmissions via Gmail API will stop.')) {
    return;
  }
  try {
    const res = await fetch('/api/auth/google/disconnect', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || 'Google account disconnected.');
    await loadSettingsView();
  } catch (err) {
    showToast('Failed to disconnect Google account: ' + err.message, 'error');
  }
}

function checkGoogleOAuthReturnParams() {
  const fullUrl = window.location.href;
  if (fullUrl.includes('google=connected')) {
    const params = new URLSearchParams(window.location.search || window.location.hash.split('?')[1] || '');
    const email = params.get('email') || '';
    showToast(`🦇 Google Account connected successfully! Real Gmail transmissions enabled for ${email || 'your account'}.`);
    if (window.history && window.history.replaceState) {
      const cleanUrl = window.location.href.replace(/([?&])google=connected[^&]*/g, '').replace(/[?&]$/, '');
      window.history.replaceState(null, '', cleanUrl);
    }
  } else if (fullUrl.includes('google=error')) {
    const params = new URLSearchParams(window.location.search || window.location.hash.split('?')[1] || '');
    const detail = params.get('detail') || 'Authorization was cancelled or failed.';
    showToast('Google authorization failed: ' + decodeURIComponent(detail), 'error');
  }
}

// Check on load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', checkGoogleOAuthReturnParams);
} else {
  checkGoogleOAuthReturnParams();
}

function openEmailPreviewModal(data) {
  const modal = document.getElementById('emailPreviewModal');
  if (!modal) return;
  const frame = document.getElementById('emailPreviewFrame');
  if (frame && data.html_preview) {
    frame.srcdoc = data.html_preview;
  }
  const badge = document.getElementById('emailPreviewBadge');
  if (badge) {
    badge.textContent = data.delivered ? 'LIVE DISPATCHED' : 'PREVIEW MODE';
    badge.className = `badge ${data.delivered ? 'badge-completed' : 'badge-topic'}`;
  }
  const sub = document.getElementById('emailPreviewSubtitle');
  if (sub) {
    sub.textContent = `Destination: ${data.target_email || 'Configured address'}`;
  }
  const hint = document.getElementById('emailPreviewHint');
  if (hint && data.hint) {
    hint.innerHTML = `💡 <strong>Deployment Note:</strong> ${data.hint}`;
  }
  if (window.GothamMotion) window.GothamMotion.openModalAnimated(modal);
  else modal.classList.add('active');
}

function closeEmailPreviewModal() {
  const modal = document.getElementById('emailPreviewModal');
  if (!modal) return;
  if (window.GothamMotion) window.GothamMotion.closeModalAnimated(modal);
  else modal.classList.remove('active');
}

window.registerCurrentDevice = registerCurrentDevice;
window.connectGoogleAccount = connectGoogleAccount;
window.disconnectGoogleAccount = disconnectGoogleAccount;
window.openEmailPreviewModal = openEmailPreviewModal;
window.closeEmailPreviewModal = closeEmailPreviewModal;
