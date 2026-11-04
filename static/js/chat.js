/**
 * ============================================================================
 * CodeCoach • Real-time Chat with Gotham Noir Theme & Markdown Formatter
 * ============================================================================
 * 
 * Features:
 * - Collapsible Detective Thought Drawer (<think> / <thought> tags never clutter output)
 * - Complete GitHub-Flavored Markdown (GFM) parsing: Tables, Headers, Code Blocks, Quotes
 * - C# Syntax Highlighting via highlight.js with Copy buttons
 * - Bat-flapping streaming indicators & avatar pulsing
 * - WebSocket real-time connection with transparent HTTP fallback for Vercel
 */

let chatSocket = null;
let chatHistory = [];
let activeStreamBubble = null;
let useHttpFallback = false;
let socketConnectAttempts = 0;

// Initialize Marked parser cleanly for Marked v12+
function setupMarked() {
  if (window.marked) {
    try {
      const customRenderer = {
        code({ text, lang }) {
          const language = (lang && hljs.getLanguage(lang)) ? lang : 'csharp';
          let highlighted = '';
          try {
            highlighted = hljs.highlight(text, { language }).value;
          } catch (e) {
            highlighted = hljs.highlightAuto(text).value;
          }
          return `<div class="code-block-wrapper">
            <div class="code-block-header">
              <span class="code-lang-tag">${language.toUpperCase()}</span>
              <button class="copy-btn" onclick="copyCode(this)" title="Copy Code">Copy</button>
            </div>
            <pre><code class="hljs language-${language}">${highlighted}</code></pre>
          </div>`;
        },
        table(header, body) {
          return `<div class="table-responsive-wrapper">
            <table class="gotham-table">
              <thead>${header}</thead>
              <tbody>${body}</tbody>
            </table>
          </div>`;
        }
      };

      marked.use({
        renderer: customRenderer,
        gfm: true,
        breaks: true
      });
    } catch (e) {
      console.warn('Marked.js custom setup note:', e);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setupMarked();
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
      if (socketConnectAttempts >= 2) {
        console.warn('WebSocket unavailable in serverless environment; using HTTP fallback.');
        useHttpFallback = true;
      } else {
        setTimeout(initChatWebSocket, 3000);
      }
    };

    chatSocket.onerror = () => {
      useHttpFallback = true;
    };
  } catch (err) {
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
    if (window.GothamMotion) {
      const tag = activeStreamBubble.querySelector('.repl-speaker-tag');
      window.GothamMotion.pulseAssistantAvatar(tag, true);
    }
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
      
      const tag = activeStreamBubble.querySelector('.repl-speaker-tag');
      if (window.GothamMotion) window.GothamMotion.pulseAssistantAvatar(tag, false);

      bubble.innerHTML = formatMarkdown(rawText);
      const actRow = document.createElement('div');
      actRow.className = 'bubble-actions';
      actRow.style.cssText = 'display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end;';
      actRow.innerHTML = `<button class="btn-secondary" style="font-size: 11px; padding: 2px 8px; opacity: 0.8;" onclick="saveChatAnswerAsNote(this)">💾 Save Note</button>`;
      bubble.appendChild(actRow);

      highlightCodeBlocks(bubble);
      chatHistory.push({ sender: 'assistant', content: rawText });
      activeStreamBubble = null;
    }
  } else if (msg.type === 'stream_error') {
    if (activeStreamBubble) {
      const bubble = activeStreamBubble.querySelector('.message-bubble');
      bubble.innerHTML = `<span style="color: var(--status-error); font-weight: 600;">⚠️ ${msg.error}</span>`;
      const tag = activeStreamBubble.querySelector('.repl-speaker-tag');
      if (window.GothamMotion) window.GothamMotion.pulseAssistantAvatar(tag, false);
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
  speakerTag.innerHTML = sender === 'assistant' 
    ? '<span class="bat-glyph">🦇</span> <span>[SYS::CodeCoach]</span>' 
    : '<span>[USR::You]</span>';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = formatMarkdown(content);

  if (sender === 'assistant') {
    const actRow = document.createElement('div');
    actRow.className = 'bubble-actions';
    actRow.style.cssText = 'display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end;';
    actRow.innerHTML = `<button class="btn-secondary" style="font-size: 11px; padding: 2px 8px; opacity: 0.8;" onclick="saveChatAnswerAsNote(this)">💾 Save Note</button>`;
    bubble.appendChild(actRow);
  }

  highlightCodeBlocks(bubble);

  row.appendChild(speakerTag);
  row.appendChild(bubble);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;

  // Trigger Gotham motion message animation
  if (window.GothamMotion) {
    window.GothamMotion.animateChatMessage(row, sender);
  }
}

function createStreamingBubble() {
  const row = document.createElement('div');
  row.className = 'message-row assistant streaming-active';

  const speakerTag = document.createElement('div');
  speakerTag.className = 'repl-speaker-tag speaker-assistant';
  speakerTag.innerHTML = '<span class="bat-glyph">🦇</span> <span>[SYS::CodeCoach]</span>';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  // Bat-Flapping typing indicator
  const indicator = document.createElement('div');
  indicator.className = 'streaming-status-row';
  indicator.innerHTML = `
    <span class="bat-flap">🦇</span>
    <span class="bat-flap delayed">🦇</span>
    <span class="stream-text" style="display: inline-block;"></span>
  `;
  bubble.appendChild(indicator);

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

    // Send over WebSocket if connected, otherwise HTTP
    if (!useHttpFallback && chatSocket && chatSocket.readyState === WebSocket.OPEN) {
      chatSocket.send(JSON.stringify({
        content: text,
        history: chatHistory.slice(-8)
      }));
    } else {
      await sendHttpChatMessage(text);
    }
  });
}

async function sendHttpChatMessage(text) {
  const container = document.getElementById('chatMessages');
  const streamBubble = createStreamingBubble();
  const textSpan = streamBubble.querySelector('.stream-text');
  textSpan.textContent = 'Deciphering C# architecture...';
  container.appendChild(streamBubble);
  container.scrollTop = container.scrollHeight;

  if (window.GothamMotion) {
    const tag = streamBubble.querySelector('.repl-speaker-tag');
    window.GothamMotion.pulseAssistantAvatar(tag, true);
  }

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
    renderMessageBubble('assistant', `⚠️ Could not transmit command: ${err.message}. Check network connection.`);
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
    window.location.hash = '#dashboard';
  }
}

// ----------------------------------------------------------------------------
// THOUGHT DRAWER STRIPPER & MARKDOWN RENDERER
// ----------------------------------------------------------------------------
function formatMarkdown(text) {
  if (!text) return '';

  let cleanText = text;
  let thoughtHtml = '';

  // Extract <think>...</think> or <thought>...</thought> tags cleanly
  const thinkMatch = cleanText.match(/<(think|thought)>([\s\S]*?)<\/\1>/i);
  if (thinkMatch) {
    const thoughtRaw = thinkMatch[2].trim();
    cleanText = cleanText.replace(thinkMatch[0], '').trim();

    // Render reasoning in a collapsible Gotham Detective analysis drawer
    thoughtHtml = `
      <details class="gotham-thought-drawer">
        <summary>
          <span class="thought-badge">🦇 DETECTIVE REASONING MATRIX</span>
          <span class="thought-toggle-hint">[Inspect analysis]</span>
        </summary>
        <div class="thought-content">${escapeHtml(thoughtRaw)}</div>
      </details>
    `;
  }

  // Also handle unclosed <think> during streaming
  cleanText = cleanText.replace(/<(think|thought)>[\s\S]*$/i, '').trim();

  // Primary: Use marked.js if available
  if (window.marked && typeof window.marked.parse === 'function') {
    try {
      const parsedHtml = window.marked.parse(cleanText);
      return thoughtHtml + parsedHtml;
    } catch (err) {
      console.warn('marked.js parse fallback triggered:', err);
    }
  }

  // Fallback: Comprehensive Markdown & Table Parser
  return thoughtHtml + robustMarkdownFallback(cleanText);
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function robustMarkdownFallback(text) {
  let escaped = escapeHtml(text);

  // Parse GFM Tables: | Col1 | Col2 |
  escaped = escaped.replace(/(?:^|\n)(\|.+?\|\n\|[-:| ]+\|\n(?:\|.+?\|\n?)+)/g, (match) => {
    const lines = match.trim().split('\n');
    if (lines.length < 2) return match;

    const headers = lines[0].split('|').slice(1, -1).map(h => `<th>${h.trim()}</th>`).join('');
    const rows = lines.slice(2).map(line => {
      const cells = line.split('|').slice(1, -1).map(c => `<td>${c.trim()}</td>`).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    return `\n<div class="table-responsive-wrapper"><table class="gotham-table"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>\n`;
  });

  // Code blocks: ```language ... ```
  escaped = escaped.replace(/```(csharp|cs|json|sql|bash|html)?\n([\s\S]*?)```/g, (match, lang, code) => {
    const language = lang || 'csharp';
    return `<div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-lang-tag">${language.toUpperCase()}</span>
        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
      </div>
      <pre><code class="language-${language}">${code.trim()}</code></pre>
    </div>`;
  });

  // Inline code: `var x = 10;`
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // Headings #, ##, ###
  escaped = escaped.replace(/^### (.*$)/gim, '<h3 class="gotham-heading-3">$1</h3>');
  escaped = escaped.replace(/^## (.*$)/gim, '<h2 class="gotham-heading-2">$1</h2>');
  escaped = escaped.replace(/^# (.*$)/gim, '<h1 class="gotham-heading-1">$1</h1>');

  // Bold & Italic
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Bullet items
  escaped = escaped.replace(/^\s*[-•*]\s+(.*$)/gim, '<div class="bullet-item"><span class="bat-bullet">🦇</span><span>$1</span></div>');

  // Blockquotes
  escaped = escaped.replace(/^\s*&gt;\s+(.*$)/gim, '<blockquote class="gotham-blockquote">$1</blockquote>');

  // Paragraph breaks
  escaped = escaped.replace(/\n\n/g, '<div class="paragraph-gap"></div>');

  return escaped;
}

function highlightCodeBlocks(container) {
  if (window.hljs) {
    container.querySelectorAll('pre code').forEach((block) => {
      hljs.highlightElement(block);
    });
  }
}

function saveChatAnswerAsNote(btn) {
  const bubble = btn.closest('.message-bubble');
  const clone = bubble.cloneNode(true);
  const actions = clone.querySelector('.bubble-actions');
  if (actions) actions.remove();
  const text = clone.innerText.trim();
  if (typeof saveNoteDirectly === 'function') {
    saveNoteDirectly("Chat Note: C# Insight", text, "variables-and-types");
  } else {
    showToast('Saved note to personal vault');
  }
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
