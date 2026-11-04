/**
 * ============================================================================
 * CodeCoach • Core Application Controller (Gotham Noir Edition)
 * ============================================================================
 */

// Global State
window.CodeCoach = {
  theme: localStorage.getItem('cc_theme') || 'dark',
  activeTab: 'chat',
  userSettings: null,
  activeTopicId: 'variables-and-types',
  activeSetId: null,
  currentQuestion: null,
  updateStreak: updateStreakDisplay
};

document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initTabs();
  initRailToggle();
  initServiceWorker();
  initNotificationButton();
  handleHashNavigation();

  // Load global config & populate curriculum rail
  await loadGlobalSettings();
  await loadCurriculumRail();
});

// Theme Management: Gotham Dark (Default) & Gotham Day (Light)
function initTheme() {
  const html = document.documentElement;
  html.setAttribute('data-theme', window.CodeCoach.theme);
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.textContent = window.CodeCoach.theme === 'dark' ? '☀️' : '🌙';

  if (btn) {
    btn.addEventListener('click', () => {
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      window.CodeCoach.theme = next;
      localStorage.setItem('cc_theme', next);
      btn.textContent = next === 'dark' ? '☀️' : '🌙';

      const hljsTheme = document.getElementById('hljs-theme');
      if (hljsTheme) {
        hljsTheme.href = next === 'dark'
          ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css'
          : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
      }
    });
  }
}

// Navigation Tabs & Mobile Bottom Bar Synchronization
function initTabs() {
  const desktopTabs = document.querySelectorAll('.nav-tab-btn');
  const mobileTabs = document.querySelectorAll('.bottom-nav-btn');

  const bindTabs = (elements) => {
    elements.forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.tab;
        switchTab(target);
      });
    });
  };

  bindTabs(desktopTabs);
  bindTabs(mobileTabs);

  window.addEventListener('hashchange', handleHashNavigation);
}

function switchTab(tabName) {
  window.CodeCoach.activeTab = tabName;

  // Sync Desktop Nav
  document.querySelectorAll('.nav-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabName);
  });

  // Sync Mobile Bottom Nav
  document.querySelectorAll('.bottom-nav-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabName);
  });

  // Target View Section
  const targetSection = document.getElementById(`view-${tabName}`);

  // Auto-close rail on mobile when navigating
  const rail = document.getElementById('curriculumRail');
  if (rail && rail.classList.contains('open')) {
    rail.classList.remove('open');
  }

  // Trigger angular slash wipe transition
  if (window.GothamMotion && targetSection) {
    window.GothamMotion.transitionToView(targetSection);
  } else if (targetSection) {
    document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
    targetSection.classList.add('active');
  }

  if (tabName === 'dashboard') {
    loadDashboardStats();
  } else if (tabName === 'roadmap') {
    loadRoadmap();
  } else if (tabName === 'settings') {
    loadSettingsView();
  }
}

function initRailToggle() {
  const btn = document.getElementById('railToggleBtn');
  const rail = document.getElementById('curriculumRail');
  if (btn && rail) {
    btn.addEventListener('click', () => {
      rail.classList.toggle('open');
    });
  }
}

// Left Curriculum Rail
async function loadCurriculumRail() {
  const container = document.getElementById('railTopicList');
  if (!container) return;

  try {
    const res = await fetch('/api/curriculum');
    const levels = await res.json();

    container.innerHTML = levels.map((lvl, lIdx) => `
      <div class="rail-level-group">
        <div class="rail-level-title">
          <span>L${lIdx + 1} // ${lvl.title}</span>
        </div>
        <div>
          ${lvl.topics.map(t => {
            const statusClass = `status-${t.status.toLowerCase()}`;
            const isActive = t.id === window.CodeCoach.activeTopicId;
            const isMastered = t.status === 'Mastered';
            return `
              <div class="rail-topic-item ${isActive ? 'active' : ''}" onclick="selectRailTopic('${t.id}')">
                <span class="rail-topic-title">${isMastered ? '🦇 ' : ''}${t.title}</span>
                <span class="rail-topic-status-pill ${statusClass}">${t.status}</span>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="rail-loading-state" style="color: var(--status-error);">Could not load curriculum rail.</div>`;
  }
}

function selectRailTopic(topicId) {
  window.CodeCoach.activeTopicId = topicId;
  document.querySelectorAll('.rail-topic-item').forEach(item => {
    item.classList.remove('active');
  });

  switchTab('quiz');
  if (window.CodeCoach.startTopicTraining) {
    window.CodeCoach.startTopicTraining(topicId);
  }
}

function handleHashNavigation() {
  const hash = window.location.hash;
  if (!hash) return;

  if (hash.startsWith('#quiz/')) {
    const topicId = hash.replace('#quiz/', '');
    window.CodeCoach.activeTopicId = topicId;
    switchTab('quiz');
    if (window.CodeCoach.startTopicTraining) {
      window.CodeCoach.startTopicTraining(topicId);
    }
  } else if (hash.startsWith('#teach-back/')) {
    const topicId = hash.replace('#teach-back/', '');
    openTeachBackModal(topicId);
  } else if (hash.startsWith('#app-challenge/')) {
    const topicId = hash.replace('#app-challenge/', '');
    openAppChallengeModal(topicId);
  } else if (hash === '#retention') {
    switchTab('dashboard');
  } else if (['#chat', '#quiz', '#roadmap', '#dashboard', '#settings'].includes(hash)) {
    switchTab(hash.replace('#', ''));
  }
}

// Streak Badge Synchronization Across Tabs
function updateStreakDisplay(days) {
  const count = parseInt(days, 10) || 0;
  const streakEl = document.getElementById('streakCount');
  if (streakEl) streakEl.textContent = count;

  let rankTitle = 'Rookie';
  if (count >= 30) rankTitle = 'Dark Knight';
  else if (count >= 14) rankTitle = 'Vigilante';
  else if (count >= 4) rankTitle = 'Detective';

  const pill = document.getElementById('streakPill');
  if (pill) {
    pill.title = `${count} Day Training Streak • Rank: ${rankTitle}`;
  }

  if (window.GothamMotion) {
    window.GothamMotion.pulseStreakBadge(count);
  }
}

// Service Worker & Push Alerts
async function initServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      await navigator.serviceWorker.register('/sw.js');
    } catch (e) {
      console.warn('Service Worker note:', e);
    }
  }
}

function initNotificationButton() {
  const btn = document.getElementById('pushNotifBtn');
  if (!('Notification' in window) && btn) {
    btn.style.display = 'none';
    return;
  }

  if (btn) {
    btn.addEventListener('click', async () => {
      await requestAndSubscribePush();
    });
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function requestAndSubscribePush() {
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      showToast('Notifications denied in browser preferences.', 'error');
      return;
    }

    const keyResp = await fetch('/api/push/public-key');
    const { publicKey } = await keyResp.json();
    if (!publicKey) {
      showToast('VAPID public key not configured.', 'error');
      return;
    }

    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    const subJson = sub.toJSON();
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint: sub.endpoint,
        keys: {
          p256dh: subJson.keys.p256dh,
          auth: subJson.keys.auth
        },
        user_agent: navigator.userAgent
      })
    });

    showToast('Gotham Signal alerts armed. Scheduled 8 AM / 8 PM verification checks active.');
    if (window.GothamMotion) window.GothamMotion.swingNotificationBell(true);
  } catch (err) {
    showToast('Failed to register push: ' + err.message, 'error');
  }
}

// Global Settings API
async function loadGlobalSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    window.CodeCoach.userSettings = data;

    if (data.assistant_name) {
      const brandElem = document.getElementById('assistantBrand');
      if (brandElem) brandElem.textContent = data.assistant_name;
      document.title = `${data.assistant_name} • The Dark Knight of .NET`;
    }
  } catch (e) {
    console.warn('Could not load settings:', e);
  }
}

// Gotham Signal Toast Notifications
function showToast(message, type = 'info') {
  const existing = document.querySelectorAll('.gotham-toast');
  existing.forEach(e => e.remove());

  const div = document.createElement('div');
  div.className = `gotham-toast ${type === 'error' ? 'toast-error' : 'toast-signal'}`;
  div.innerHTML = `
    <span class="toast-bat-glyph">${type === 'error' ? '⚠️' : '🦇'}</span>
    <span class="toast-message-text">${message}</span>
  `;
  document.body.appendChild(div);

  setTimeout(() => {
    div.classList.add('fade-out');
    setTimeout(() => div.remove(), 350);
  }, 4000);
}
