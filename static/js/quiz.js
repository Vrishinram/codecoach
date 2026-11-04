/**
 * Quiz & Learning Verification Controller
 */

let activeQuestion = null;
let currentSetId = null;
let currentTopicId = null;
let placementQuestions = [];

window.CodeCoach.startTopicTraining = startTopicTraining;
window.CodeCoach.nextQuestion = () => fetchNextQuestion();
window.CodeCoach.showHint = showHint;
window.CodeCoach.skipQuestion = skipQuestion;

async function startTopicTraining(topicId) {
  currentTopicId = topicId;
  const container = document.getElementById('quizContent');
  container.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted);">
    <div style="font-size: 24px; margin-bottom: 8px;">⏳</div>
    <div>Preparing training set for <strong>${topicId}</strong>...</div>
  </div>`;

  try {
    const res = await fetch(`/api/quiz/start/${topicId}`, { method: 'POST' });
    const data = await res.json();
    currentSetId = data.set_id;

    if (data.is_completed) {
      loadLearningReport(currentSetId);
    } else if (data.current_question) {
      renderQuestion(data.current_question, data.total_questions);
    } else {
      fetchNextQuestion();
    }
  } catch (err) {
    container.innerHTML = `<div class="quiz-card" style="border-color: #ef4444;">
      <h3 style="color: #ef4444; margin-bottom: 8px;">Failed to start set</h3>
      <p>${err.message}</p>
    </div>`;
  }
}

async function fetchNextQuestion() {
  if (!currentTopicId) return;
  try {
    const res = await fetch(`/api/quiz/current/${currentTopicId}`);
    const data = await res.json();
    if (data.is_completed) {
      loadLearningReport(data.set_id || currentSetId);
    } else if (data.current_question) {
      renderQuestion(data.current_question);
    }
  } catch (err) {
    console.error('Error fetching question:', err);
  }
}

function renderQuestion(q, totalQuestions = 25) {
  activeQuestion = q;
  const container = document.getElementById('quizContent');

  let typeLabel = 'Multiple Choice';
  if (q.question_type === 'output_prediction') typeLabel = 'Output Prediction';
  else if (q.question_type === 'fill_blank') typeLabel = 'Fill-in-the-Blank';
  else if (q.question_type === 'coding') typeLabel = 'C# Coding Task';

  let inputHtml = '';
  if (q.question_type === 'mcq') {
    inputHtml = `<div class="options-grid">
      ${q.options.map(opt => `
        <button class="option-btn" onclick="submitAnswer('${opt.charAt(0)}')">
          <span style="font-weight: 700; color: var(--accent-cyan);">${opt.slice(0, 2)}</span>
          <span>${opt.slice(2)}</span>
        </button>
      `).join('')}
    </div>`;
  } else if (q.question_type === 'output_prediction' || q.question_type === 'fill_blank') {
    const placeholder = q.question_type === 'fill_blank' ? 'Type the token replacing ___' : 'Type exact expected output';
    inputHtml = `<div class="text-answer-box">
      <input type="text" id="textAnswerInput" class="chat-input" placeholder="${placeholder}" style="width: 100%; margin-bottom: 12px;" autocomplete="off">
      <button class="btn-primary" onclick="submitTextAnswer()">Submit Answer</button>
    </div>`;
  } else {
    // Coding task
    inputHtml = `<div class="text-answer-box">
      <textarea id="codeAnswerInput" class="code-editor-area" placeholder="// Write your C# code here"></textarea>
      <button class="btn-primary" style="margin-top: 12px;" onclick="submitCodeAnswer()">Submit C# Code</button>
    </div>`;
  }

  container.innerHTML = `
    <div class="quiz-card">
      <div class="quiz-header">
        <div class="quiz-badge-group">
          <span class="badge badge-topic">${q.subtopic || q.topic_id}</span>
          <span class="badge badge-type">${typeLabel}</span>
          <span class="badge badge-diff">Difficulty ${q.difficulty}/5</span>
        </div>
        <div class="quiz-progress-text">Question ${q.question_index} of ${totalQuestions}</div>
      </div>

      <div class="quiz-prompt">${q.prompt}</div>

      ${q.code_snippet ? `
        <pre class="code-snippet-box"><code class="language-csharp">${q.code_snippet}</code></pre>
      ` : ''}

      ${inputHtml}

      <div id="feedbackContainer" style="display: none;"></div>
      <div id="hintContainer" style="display: none; padding: 12px; background: rgba(245,158,11,0.1); border-left: 3px solid #f59e0b; border-radius: 4px; font-size: 13.5px; margin-bottom: 18px; color: #f59e0b;"></div>

      <div class="quiz-footer">
        <button class="btn-secondary" onclick="showHint()">💡 Hint</button>
        <button class="btn-secondary" onclick="skipQuestion()">Skip &rarr;</button>
      </div>
    </div>
  `;

  // Highlight snippet code
  container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
}

async function submitAnswer(userAnswer) {
  if (!activeQuestion) return;

  try {
    const res = await fetch('/api/quiz/submit-answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question_id: activeQuestion.id,
        user_answer: userAnswer
      })
    });
    const result = await res.json();
    displayAnswerFeedback(result);
  } catch (err) {
    showToast('Failed to evaluate answer: ' + err.message, 'error');
  }
}

function submitTextAnswer() {
  const val = document.getElementById('textAnswerInput').value.trim();
  if (val) submitAnswer(val);
}

function submitCodeAnswer() {
  const val = document.getElementById('codeAnswerInput').value.trim();
  if (val) submitAnswer(val);
}

function displayAnswerFeedback(result) {
  const fb = document.getElementById('feedbackContainer');
  fb.className = `feedback-box ${result.is_correct ? 'correct' : 'wrong'}`;
  fb.style.display = 'block';

  // Disable options / inputs
  document.querySelectorAll('.option-btn').forEach(btn => {
    btn.disabled = true;
    if (btn.textContent.trim().startsWith(result.correct_answer)) {
      btn.classList.add('correct');
    }
  });

  fb.innerHTML = `
    <div class="feedback-title">${result.is_correct ? '✅ Correct!' : '❌ Incorrect'}</div>
    <div class="feedback-explanation">
      <strong>Expected:</strong> <code>${result.correct_answer}</code><br>
      ${result.explanation}
    </div>
    <div style="margin-top: 14px; text-align: right;">
      <button class="btn-primary" onclick="fetchNextQuestion()">Next Question &rarr;</button>
    </div>
  `;
}

function showHint() {
  if (!activeQuestion || !activeQuestion.hint) {
    showToast('No hint available for this question.');
    return;
  }
  const h = document.getElementById('hintContainer');
  h.textContent = `💡 Hint: ${activeQuestion.hint}`;
  h.style.display = 'block';
}

function skipQuestion() {
  fetchNextQuestion();
}

// Learning Report
async function loadLearningReport(setId) {
  const container = document.getElementById('quizContent');
  container.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted);">
    <div>Analyzing your learning report...</div>
  </div>`;

  try {
    const res = await fetch(`/api/quiz/report/${setId}`);
    const r = await res.json();

    const scoreClass = r.passed ? 'passed' : 'failed';
    container.innerHTML = `
      <div class="report-card">
        <div class="report-header">
          <div class="score-circle ${scoreClass}">${r.score.toFixed(0)}%</div>
          <h2 style="font-size: 22px; font-weight: 700;">Set #${r.set_number} Completed: ${r.topic_title}</h2>
          <p style="color: ${r.passed ? '#34d399' : '#f87171'}; font-weight: 600; margin-top: 6px;">
            ${r.passed ? '🎉 Passed the set threshold (70%)' : '⚠️ Below pass score (70%). Retry set recommended.'}
          </p>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px;">
          <div style="background: var(--bg-app); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px;">
            <div style="font-size: 13px; font-weight: 700; color: #34d399; margin-bottom: 8px;">💪 STRENGTHS</div>
            <div class="subtopic-tags">
              ${r.strengths.map(s => `<span class="tag-strength">${s}</span>`).join('')}
            </div>
          </div>
          <div style="background: var(--bg-app); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px;">
            <div style="font-size: 13px; font-weight: 700; color: #f87171; margin-bottom: 8px;">🎯 WEAK SPOTS</div>
            <div class="subtopic-tags">
              ${r.weak_spots.length ? r.weak_spots.map(w => `<span class="tag-weak">${w}</span>`).join('') : '<span style="font-size: 13px; color: var(--text-muted);">None detected!</span>'}
            </div>
          </div>
        </div>

        <!-- Learning Verification Steps Box -->
        <div style="background: var(--bg-app); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 20px; margin-bottom: 24px;">
          <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Learning Verification Status</h3>
          <p style="color: var(--text-muted); font-size: 13.5px; margin-bottom: 16px;">${r.recommended_action}</p>
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            ${!r.passed ? `
              <button class="btn-primary" onclick="retrySet('${r.topic_id}')">🔄 Start Focused Retry Set</button>
            ` : ''}
            <button class="btn-secondary" onclick="openTeachBackModal('${r.topic_id}')">
              ${r.teach_back_status === 'Passed' ? '✅ Teach-Back Verified' : '📝 Step 2: Teach-Back Check'}
            </button>
            <button class="btn-secondary" onclick="openAppChallengeModal('${r.topic_id}')">
              ${r.app_challenge_status === 'Passed' ? '✅ Practical Coding Verified' : '💻 Step 3: Application Check'}
            </button>
          </div>
        </div>

        <!-- Curated Links -->
        ${r.start_links.length || r.end_links.length ? `
          <div style="margin-top: 24px;">
            <h4 style="font-size: 14px; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; margin-bottom: 10px;">Recommended Learning Resources</h4>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              ${[...r.start_links, ...r.end_links].map(l => `
                <a href="${l.url}" target="_blank" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-app); border: 1px solid var(--border-color); border-radius: 6px; text-decoration: none; color: var(--text-main);">
                  <span><strong>${l.type === 'video' ? '📺' : '📄'}</strong> ${l.title}</span>
                  <span style="font-size: 12px; color: var(--accent-cyan);">&nearr; Open</span>
                </a>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <div style="margin-top: 28px; text-align: center;">
          <button class="btn-primary" onclick="window.location.hash = '#roadmap'">Back to Roadmap &rarr;</button>
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="quiz-card" style="color: #ef4444;">Error generating report: ${err.message}</div>`;
  }
}

async function retrySet(topicId) {
  try {
    const res = await fetch(`/api/quiz/retry/${topicId}`, { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
    currentSetId = data.set_id;
    if (data.first_question) {
      renderQuestion(data.first_question);
    } else {
      fetchNextQuestion();
    }
  } catch (e) {
    showToast('Failed to start retry set: ' + e.message, 'error');
  }
}

// Teach-Back Verification
function openTeachBackModal(topicId) {
  currentTopicId = topicId;
  document.getElementById('teachBackTopicTitle').textContent = topicId;
  document.getElementById('teachBackResult').style.display = 'none';
  document.getElementById('teachBackModal').classList.add('active');
}

function closeTeachBackModal() {
  document.getElementById('teachBackModal').classList.remove('active');
}

async function submitTeachBack() {
  const explanation = document.getElementById('teachBackInput').value.trim();
  if (!explanation) return;

  const btn = document.getElementById('teachBackSubmitBtn');
  btn.disabled = true;
  btn.textContent = 'Grading...';

  try {
    const res = await fetch('/api/verification/teach-back', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic_id: currentTopicId,
        student_explanation: explanation
      })
    });
    const result = await res.json();

    const resDiv = document.getElementById('teachBackResult');
    resDiv.style.display = 'block';
    resDiv.className = `feedback-box ${result.passed ? 'correct' : 'wrong'}`;
    resDiv.innerHTML = `
      <div class="feedback-title">${result.passed ? '🎉 Teach-Back Passed!' : '⚠️ Needs Improvement'} (Score: ${result.overall_score}%)</div>
      <div style="font-size: 13px; margin: 8px 0;">
        Accuracy: <strong>${result.accuracy_score}%</strong> • Completeness: <strong>${result.completeness_score}%</strong> • Clarity: <strong>${result.clarity_score}%</strong>
      </div>
      <p style="font-size: 13.5px;">${result.feedback}</p>
      ${result.missing_points && result.missing_points.length ? `
        <div style="margin-top: 8px; font-size: 12.5px;">
          <strong>Points to remember:</strong>
          <ul style="padding-left: 20px; margin-top: 4px;">
            ${result.missing_points.map(p => `<li>${p}</li>`).join('')}
          </ul>
        </div>
      ` : ''}
    `;

    if (result.passed) {
      showToast('Teach-Back verification passed!');
    }
  } catch (err) {
    showToast('Teach-back evaluation failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Submit Explanation';
  }
}

// Practical Application Challenge
async function openAppChallengeModal(topicId) {
  currentTopicId = topicId;
  const modal = document.getElementById('appChallengeModal');
  modal.classList.add('active');
  const promptBox = document.getElementById('appChallengePromptText');
  const codeBox = document.getElementById('appChallengeCodeInput');
  document.getElementById('appChallengeResult').style.display = 'none';

  promptBox.textContent = 'Loading challenge...';
  try {
    const res = await fetch(`/api/verification/app-challenge/${topicId}`);
    const data = await res.json();
    promptBox.textContent = data.prompt;
    codeBox.value = data.starter_code || 'public class Solution\n{\n    \n}';
  } catch (e) {
    promptBox.textContent = 'Failed to load challenge prompt.';
  }
}

function closeAppChallengeModal() {
  document.getElementById('appChallengeModal').classList.remove('active');
}

async function submitAppChallenge() {
  const code = document.getElementById('appChallengeCodeInput').value.trim();
  if (!code) return;

  const btn = document.getElementById('appChallengeSubmitBtn');
  btn.disabled = true;
  btn.textContent = 'Reviewing Code...';

  try {
    const res = await fetch('/api/verification/app-challenge/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic_id: currentTopicId,
        student_code: code
      })
    });
    const result = await res.json();

    const resDiv = document.getElementById('appChallengeResult');
    resDiv.style.display = 'block';
    resDiv.className = `feedback-box ${result.passed ? 'correct' : 'wrong'}`;
    resDiv.innerHTML = `
      <div class="feedback-title">${result.passed ? '🎉 Code Review Passed!' : '⚠️ Needs Revisions'} (Score: ${result.score}%)</div>
      <p style="font-size: 13.5px; margin-bottom: 8px;">${result.feedback}</p>
      <div style="font-size: 12.5px; display: flex; flex-direction: column; gap: 4px;">
        <div><strong>Correctness:</strong> ${result.correctness_notes}</div>
        <div><strong>Edge Cases:</strong> ${result.edge_case_notes}</div>
        <div><strong>Style:</strong> ${result.style_notes}</div>
      </div>
    `;

    if (result.passed) {
      showToast('Application challenge passed!');
    }
  } catch (err) {
    showToast('Code review failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Submit for Code Review';
  }
}

// 10-Question Placement Test
async function openPlacementModal() {
  const modal = document.getElementById('placementModal');
  modal.classList.add('active');
  const container = document.getElementById('placementQuestionsContainer');
  container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 20px;">Loading 10 placement questions...</div>';

  try {
    const res = await fetch('/api/placement/questions');
    placementQuestions = await res.json();

    container.innerHTML = placementQuestions.map((q, idx) => `
      <div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);">
        <div style="font-weight: 700; font-size: 14.5px; margin-bottom: 8px;">Q${idx + 1}. ${q.prompt}</div>
        ${q.code_snippet ? `<pre class="code-snippet-box"><code class="language-csharp">${q.code_snippet}</code></pre>` : ''}
        <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
          ${q.options.map((opt, optIdx) => `
            <label style="display: flex; align-items: center; gap: 8px; font-size: 13.5px; cursor: pointer; padding: 6px 10px; background: var(--bg-app); border-radius: 4px;">
              <input type="radio" name="placement_q_${q.id}" value="${optIdx}">
              <span>${opt}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `).join('');

    container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  } catch (e) {
    container.innerHTML = '<div style="color: #ef4444;">Failed to load placement test.</div>';
  }
}

function closePlacementModal() {
  document.getElementById('placementModal').classList.remove('active');
}

async function submitPlacementTest() {
  const answers = [];
  placementQuestions.forEach(q => {
    const selected = document.querySelector(`input[name="placement_q_${q.id}"]:checked`);
    if (selected) {
      answers.push({
        question_id: q.id,
        selected_option_index: parseInt(selected.value, 10)
      });
    }
  });

  if (answers.length < placementQuestions.length) {
    if (!confirm(`You have answered ${answers.length} of ${placementQuestions.length} questions. Submit anyway?`)) {
      return;
    }
  }

  try {
    const res = await fetch('/api/placement/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers })
    });
    const result = await res.json();
    localStorage.setItem('cc_placement_done', 'true');
    closePlacementModal();
    alert(`Placement Completed! Score: ${result.score}%\n\n${result.message}`);
    loadRoadmap();
  } catch (err) {
    showToast('Placement submit failed: ' + err.message, 'error');
  }
}

