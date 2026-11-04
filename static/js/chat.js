/**
 * Real-time Chat with Markdown Rendering, C# Syntax Highlighting, & Fallback Streaming
 */

let chatSocket = null;
let chatHistory = [];
let activeStreamBubble = null;
let useHttpFallback = false;
let socketConnectAttempts = 0;

// Setup marked.js renderer
if (window.marked) {
  const customRenderer = new marked.Renderer();

  customRenderer.code = function(code, lang) {
    const language = (lang && hljs.getLanguage(lang)) ? lang : 'csharp';
    let highlighted = '';
    try {
      highlighted = hljs.highlight(code, { language }).value;
    } catch (e) {
      highlighted = hljs.highlightAuto(code).value;
    }
    return `<div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-lang-tag">${language}</span>
        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
      </div>
      <pre><code class="hljs language-${language}">${highlighted}</code></pre>
    </div>`;
  };

  marked.setOptions({
    renderer: customRenderer,
    gfm: true,
    breaks: true,
    mangle: false,
    headerIds: false
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initChatWebSocket();
  initChatForm();
});

function initChatWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

  try {
    chatSocket = new WebSocket(wsUrl);

    chatSocket.onopen = () => {
      console.log('Chat WebSocket connected.');
      useHttpFallback = false;
      socketConnectAttempts = 0;
    };

    chatSocket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleIncomingChatMessage(msg);
      } catch (e) {
        console.error('Error parsing WS message:', e);
      }
    };

    chatSocket.onclose = () => {
      socketConnectAttempts++;
      // If repeatedly closed (e.g. on Vercel serverless functions), switch to HTTP fallback
      if (socketConnectAttempts >= 2) {
        console.warn('WebSocket unavailable in this environment (e.g. Vercel serverless). Using HTTP chat fallback.');
        useHttpFallback = true;
      } else {
        setTimeout(initChatWebSocket, 3000);
      }
    };

    chatSocket.onerror = (err) => {
      console.warn('Chat WebSocket connection failed; HTTP fallback enabled.');
      useHttpFallback = true;
    };
  } catch (err) {
    console.warn('WebSocket init exception; falling back to HTTP:', err);
    useHttpFallback = true;
  }
}

function handleIncomingChatMessage(msg) {
  const container = document.getElementById('chatMessages');

  if (msg.type === 'message') {
    renderMessageBubble(msg.sender, msg.content);
    chatHistory.push({ sender: msg.sender, content: msg.content });
  } else if (msg.type === 'stream_start') {
    activeStreamBubble = createStreamingBubble();
    container.appendChild(activeStreamBubble);
    container.scrollTop = container.scrollHeight;
  } else if (msg.type === 'token') {
    if (activeStreamBubble) {
      const textSpan = activeStreamBubble.querySelector('.stream-text');
      textSpan.textContent += msg.content;
      container.scrollTop = container.scrollHeight;
    }
  } else if (msg.type === 'stream_end') {
    if (activeStreamBubble) {
      const textSpan = activeStreamBubble.querySelector('.stream-text');
      const rawText = textSpan.textContent;
      const bubble = activeStreamBubble.querySelector('.message-bubble');
      bubble.innerHTML = formatMarkdown(rawText);
      highlightCodeBlocks(bubble);
      chatHistory.push({ sender: 'assistant', content: rawText });
      activeStreamBubble = null;
    }
  } else if (msg.type === 'stream_error') {
    if (activeStreamBubble) {
      const bubble = activeStreamBubble.querySelector('.message-bubble');
      bubble.innerHTML = `<span style="color: #ef4444; font-weight: 600;">⚠️ ${msg.error}</span>`;
      activeStreamBubble = null;
    } else {
      renderMessageBubble('assistant', `⚠️ ${msg.error}`);
    }
  } else if (msg.type === 'command_action') {
    executeCommandAction(msg);
  }
}

function renderMessageBubble(sender, content) {
  const container = document.getElementById('chatMessages');
  const row = document.createElement('div');
  row.className = `message-row ${sender}`;

  const speakerTag = document.createElement('div');
  speakerTag.className = `repl-speaker-tag speaker-${sender}`;
  speakerTag.textContent = sender === 'assistant' ? '[SYS::CodeCoach]' : '[USR::You]';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = formatMarkdown(content);
  highlightCodeBlocks(bubble);

  row.appendChild(speakerTag);
  row.appendChild(bubble);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function createStreamingBubble() {
  const row = document.createElement('div');
  row.className = 'message-row assistant';

  const speakerTag = document.createElement('div');
  speakerTag.className = 'repl-speaker-tag speaker-assistant';
  speakerTag.textContent = '[SYS::CodeCoach]';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  const textSpan = document.createElement('span');
  textSpan.className = 'stream-text';
  bubble.appendChild(textSpan);

  row.appendChild(speakerTag);
  row.appendChild(bubble);
  return row;
}

function initChatForm() {
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    input.value = '';

    // Render user bubble
    renderMessageBubble('user', text);
    chatHistory.push({ sender: 'user', content: text });

    // If WebSocket is open and working, send over WS
    if (!useHttpFallback && chatSocket && chatSocket.readyState === WebSocket.OPEN) {
      chatSocket.send(JSON.stringify({
        content: text,
        history: chatHistory.slice(-8)
      }));
    } else {
      // Fallback: send via HTTP
      await sendHttpChatMessage(text);
    }
  });
}

async function sendHttpChatMessage(text) {
  const container = document.getElementById('chatMessages');
  const streamBubble = createStreamingBubble();
  const textSpan = streamBubble.querySelector('.stream-text');
  textSpan.textContent = 'Thinking...';
  container.appendChild(streamBubble);
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: text,
        history: chatHistory.slice(-8)
      })
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    streamBubble.remove();

    if (data.type === 'command_action') {
      executeCommandAction(data);
    } else {
      renderMessageBubble('assistant', data.content || 'No response.');
      chatHistory.push({ sender: 'assistant', content: data.content });
    }
  } catch (err) {
    streamBubble.remove();
    renderMessageBubble('assistant', `⚠️ Could not send message: ${err.message}. Please check your connection.`);
  }
}

function insertSlashCommand(cmd) {
  const input = document.getElementById('chatInput');
  input.value = cmd;
  input.focus();
}

function executeCommandAction(data) {
  if (data.action === 'start_topic') {
    showToast(data.message);
    window.location.hash = `#quiz/${data.topic_id}`;
  } else if (data.action === 'next_question') {
    if (window.CodeCoach.nextQuestion) {
      window.CodeCoach.nextQuestion();
    } else {
      window.location.hash = '#quiz';
    }
  } else if (data.action === 'request_hint') {
    if (window.CodeCoach.showHint) window.CodeCoach.showHint();
  } else if (data.action === 'skip_question') {
    if (window.CodeCoach.skipQuestion) window.CodeCoach.skipQuestion();
  } else if (data.action === 'show_links') {
    window.location.hash = '#dashboard';
  } else if (data.action === 'open_reviews') {
    window.location.hash = '#retention';
  }
}

// Markdown & Code Highlighter Helpers
function formatMarkdown(text) {
  if (!text) return '';

  // Use marked.js if available for complete GitHub-flavored Markdown
  if (window.marked && typeof window.marked.parse === 'function') {
    try {
      return window.marked.parse(text);
    } catch (err) {
      console.warn('marked.js parsing error, using fallback:', err);
    }
  }

  // Robust Regex Fallback
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks
  escaped = escaped.replace(/```(csharp|cs|json|sql|bash)?([\s\S]*?)```/g, (match, lang, code) => {
    const language = lang || 'csharp';
    return `<div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-lang-tag">${language}</span>
        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
      </div>
      <pre><code class="language-${language}">${code.trim()}</code></pre>
    </div>`;
  });

  // Inline code
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // Headings
  escaped = escaped.replace(/^### (.*$)/gim, '<h3 style="font-size: 16px; margin: 12px 0 6px 0; font-weight: 700;">$1</h3>');
  escaped = escaped.replace(/^## (.*$)/gim, '<h2 style="font-size: 18px; margin: 14px 0 8px 0; font-weight: 700;">$1</h2>');
  escaped = escaped.replace(/^# (.*$)/gim, '<h1 style="font-size: 20px; margin: 16px 0 8px 0; font-weight: 700;">$1</h1>');

  // Bold & Italic
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Bullet items
  escaped = escaped.replace(/^\s*[-•*]\s+(.*$)/gim, '<div style="display: flex; gap: 8px; margin: 4px 0;"><span>•</span><span>$1</span></div>');

  // Paragraph breaks
  escaped = escaped.replace(/\n\n/g, '<div style="height: 10px;"></div>');

  return escaped;
}

function highlightCodeBlocks(container) {
  container.querySelectorAll('pre code').forEach((block) => {
    hljs.highlightElement(block);
  });
}

function copyCode(btn) {
  const wrapper = btn.closest('.code-block-wrapper') || btn.parentElement;
  const code = wrapper.querySelector('code');
  if (code) {
    navigator.clipboard.writeText(code.innerText).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
      }, 2000);
    });
  }
}
