/**
 * Real-time WebSocket Chat with Streaming & Syntax Highlighting
 */

let chatSocket = null;
let chatHistory = [];
let activeStreamBubble = null;

document.addEventListener('DOMContentLoaded', () => {
  initChatWebSocket();
  initChatForm();
});

function initChatWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

  chatSocket = new WebSocket(wsUrl);

  chatSocket.onopen = () => {
    console.log('Chat WebSocket connected.');
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
    console.warn('Chat WebSocket disconnected. Reconnecting in 3 seconds...');
    setTimeout(initChatWebSocket, 3000);
  };

  chatSocket.onerror = (err) => {
    console.error('Chat WebSocket error:', err);
  };
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
      // Format markdown & code blocks
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

  const avatar = document.createElement('div');
  avatar.className = `avatar-badge avatar-${sender}`;
  avatar.textContent = sender === 'assistant' ? 'CC' : 'ME';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = formatMarkdown(content);
  highlightCodeBlocks(bubble);

  row.appendChild(avatar);
  row.appendChild(bubble);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function createStreamingBubble() {
  const row = document.createElement('div');
  row.className = 'message-row assistant';

  const avatar = document.createElement('div');
  avatar.className = 'avatar-badge avatar-assistant';
  avatar.textContent = 'CC';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  const textSpan = document.createElement('span');
  textSpan.className = 'stream-text';
  bubble.appendChild(textSpan);

  row.appendChild(avatar);
  row.appendChild(bubble);
  return row;
}

function initChatForm() {
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) return;

    // Render user bubble
    renderMessageBubble('user', text);
    chatHistory.push({ sender: 'user', content: text });

    // Send to WebSocket
    chatSocket.send(JSON.stringify({
      content: text,
      history: chatHistory.slice(-8)
    }));

    input.value = '';
  });
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
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Triple backtick code blocks
  escaped = escaped.replace(/```(csharp|cs|json|sql|bash)?([\s\S]*?)```/g, (match, lang, code) => {
    const language = lang || 'csharp';
    return `<pre><button class="copy-btn" onclick="copyCode(this)">Copy</button><code class="language-${language}">${code.trim()}</code></pre>`;
  });

  // Single backtick inline code
  escaped = escaped.replace(/`([^`]+)`/g, '<code style="background: rgba(30,41,59,0.8); padding: 2px 5px; border-radius: 4px; font-family: var(--font-mono); font-size: 13px;">$1</code>');

  // Bold
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic
  escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Newlines to <br> if not in pre
  escaped = escaped.replace(/\n/g, '<br>');

  return escaped;
}

function highlightCodeBlocks(container) {
  container.querySelectorAll('pre code').forEach((block) => {
    hljs.highlightElement(block);
  });
}

function copyCode(btn) {
  const pre = btn.parentElement;
  const code = pre.querySelector('code');
  if (code) {
    navigator.clipboard.writeText(code.innerText).then(() => {
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy', 2000);
    });
  }
}

