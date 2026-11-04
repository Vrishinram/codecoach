/**
 * Core Application Controller for CodeCoach PWA
 */

// Global State
window.CodeCoach = {
  theme: localStorage.getItem('cc_theme') || 'dark',
  activeTab: 'chat',
  userSettings: null,
  activeTopicId: null,
  activeSetId: null,
  currentQuestion: null
};

// Initialize PWA and DOM Events
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initTabs();
  initServiceWorker();
  initNotificationButton();
  handleHashNavigation();

  // Load initial settings
  await loadGlobalSettings();

  // Check if placement test completed
  checkPlacementFirstLaunch();
});

// Theme Management
function initTheme() {
  const html = document.documentElement;
  html.setAttribute('data-theme', window.CodeCoach.theme);
  const btn = document.getElementById('themeToggleBtn');
  btn.textContent = window.CodeCoach.theme === 'dark' ? '☀️' : '🌙';

  btn.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    window.CodeCoach.theme = next;
    localStorage.setItem('cc_theme', next);
    btn.textContent = next === 'dark' ? '☀️' : '🌙';

    // Switch highlight.js theme
    const hljsTheme = document.getElementById('hljs-theme');
    if (hljsTheme) {
      hljsTheme.href = next === 'dark'
        ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css'
        : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    }
  });
}

// Navigation Tabs
function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      switchTab(target);
    });
  });

  window.addEventListener('hashchange', handleHashNavigation);
}

function switchTab(tabName) {
  window.CodeCoach.activeTab = tabName;
  document.querySelectorAll('.nav-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabName);
  });
  document.querySelectorAll('.view-section').forEach(s => {
    s.classList.toggle('active', s.id === `view-${tabName}`);
  });

  if (tabName === 'dashboard') {
    loadDashboardStats();
  } else if (tabName === 'roadmap') {
    loadRoadmap();
  } else if (tabName === 'settings') {
    loadSettingsView();
  }
}

function handleHashNavigation() {
  const hash = window.location.hash;
  if (!hash) return;

  if (hash.startsWith('#quiz/')) {
    const topicId = hash.replace('#quiz/', '');
    switchTab('quiz');
    startTopicTraining(topicId);
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
      const reg = await navigator.serviceWorker.register('/sw.js');
      console.log('CodeCoach Service Worker registered:', reg.scope);
    } catch (e) {
      console.error('Service Worker registration failed:', e);
    }
  }
}

function initNotificationButton() {
  const btn = document.getElementById('pushNotifBtn');
  if (!('Notification' in window)) {
    btn.style.display = 'none';
    return;
  }

  btn.addEventListener('click', async () => {
    await requestAndSubscribePush();
  });
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
      alert('Notification permission denied. Please allow notifications in your browser settings.');
      return;
    }

    const keyResp = await fetch('/api/push/public-key');
    const { publicKey } = await keyResp.json();
    if (!publicKey) {
      alert('VAPID public key not configured in .env.');
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

    alert('Device notifications successfully activated! You will receive scheduled C# reminders.');
  } catch (err) {
    console.error('Error subscribing to push:', err);
    alert('Failed to register push subscription: ' + err.message);
  }
}

// Global Settings API
async function loadGlobalSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    window.CodeCoach.userSettings = data;

    // Update Brand Name in Header
    if (data.assistant_name) {
      document.getElementById('assistantBrand').textContent = data.assistant_name;
      document.title = `${data.assistant_name} • Real-Time C# & .NET Educator`;
    }
  } catch (e) {
    console.warn('Could not load settings:', e);
  }
}

function checkPlacementFirstLaunch() {
  const placementDone = localStorage.getItem('cc_placement_done');
  if (!placementDone) {
    // Show prompt or option to take placement test
    console.log('First launch detected - placement test available.');
  }
}

// Toast Alert
function showToast(message, type = 'info') {
  const div = document.createElement('div');
  div.style.position = 'fixed';
  div.style.bottom = '24px';
  div.style.right = '24px';
  div.style.background = type === 'error' ? '#ef4444' : '#0284c7';
  div.style.color = '#ffffff';
  div.style.padding = '12px 20px';
  div.style.borderRadius = '8px';
  div.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
  div.style.zIndex = '9999';
  div.style.fontWeight = '600';
  div.textContent = message;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}

