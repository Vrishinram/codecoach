/**
 * Core Application Controller for CodeCoach
 * Master-Detail Rail, Theme, Tab Switching, & Telemetry
 */

// Global State
window.CodeCoach = {
  theme: localStorage.getItem('cc_theme') || 'dark',
  activeTab: 'chat',
  userSettings: null,
  activeTopicId: 'variables-and-types',
  activeSetId: null,
  currentQuestion: null
};

// Initialize App
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

// Theme Management
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

// Navigation Tabs & Mobile Bottom Bar Sync
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

  // Toggle View Sections
  document.querySelectorAll('.view-section').forEach(s => {
    s.classList.toggle('active', s.id === `view-${tabName}`);
  });

  // Auto-close rail on mobile when navigating
  const rail = document.getElementById('curriculumRail');
  if (rail && rail.classList.contains('open')) {
    rail.classList.remove('open');
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

// Populate Left Curriculum Rail Tree (Master-Detail)
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
            return `
              <div class="rail-topic-item ${isActive ? 'active' : ''}" onclick="selectRailTopic('${t.id}')">
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${t.title}</span>
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

  // Switch to quiz and start drill
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

// Service Worker & Web Push Registration
async function initServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      await navigator.serviceWorker.register('/sw.js');
    } catch (e) {
      console.warn('Service Worker registration skipped:', e);
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
      showToast('Notification permission denied. Please allow notifications in browser settings.', 'error');
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

    showToast('Device notifications activated! Scheduled C# training reminders enabled.');
  } catch (err) {
    console.error('Error subscribing to push:', err);
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
      document.title = `${data.assistant_name} • Active-Recall C# & .NET 9 Training Engine`;
    }
  } catch (e) {
    console.warn('Could not load settings:', e);
  }
}

// Inline System Toast Notification
function showToast(message, type = 'info') {
  const div = document.createElement('div');
  div.style.position = 'fixed';
  div.style.bottom = '64px';
  div.style.right = '20px';
  div.style.background = type === 'error' ? 'var(--status-error)' : 'var(--accent-cyan-active)';
  div.style.color = '#ffffff';
  div.style.padding = '10px 18px';
  div.style.borderRadius = 'var(--radius-sm)';
  div.style.boxShadow = 'var(--elevation-2)';
  div.style.zIndex = '9999';
  div.style.fontWeight = '600';
  div.style.fontSize = '13.5px';
  div.style.fontFamily = 'var(--font-ui)';
  div.textContent = message;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}
