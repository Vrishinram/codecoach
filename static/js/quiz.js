/**
 * ============================================================================
 * CodeCoach • Quiz & Verification Controller (Gotham Noir Edition)
 * ============================================================================
 */

let activeQuestion = null;
let currentSetId = null;
let currentTopicId = null;
let placementQuestions = [];
let trainingAbortController = null;
let trainingStatusInterval = null;

window.CodeCoach.startTopicTraining = startTopicTraining;
window.CodeCoach.nextQuestion = () => fetchNextQuestion();
window.CodeCoach.showHint = showHint;
window.CodeCoach.skipQuestion = skipQuestion;

function cancelTrainingLoad() {
  if (trainingAbortController) {
    trainingAbortController.abort();
  }
  if (trainingStatusInterval) {
    clearInterval(trainingStatusInterval);
  }
  const container = document.getElementById('quizContent');
  container.innerHTML = `
    <div class="quiz-card" style="text-align: center; padding: 36px 20px;">
      <div style="font-size: 36px; margin-bottom: 12px;">🦇</div>
      <h3 style="font-family: var(--font-display); font-size: 26px; color: var(--accent-yellow); margin-bottom: 8px;">CALIBRATION ABORTED</h3>
      <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 20px;">Operation cancelled. Choose another topic or return to the roadmap.</p>
      <button class="btn-primary" onclick="window.location.hash='#roadmap'">Curriculum Roadmap &rarr;</button>
    </div>
  `;
}

async function startTopicTraining(topicId) {
  currentTopicId = topicId;
  const container = document.getElementById('quizContent');

  const statusSteps = [
    `Scanning Gotham C# syllabus for ${topicId}...`,
    "Calibrating 25 active-recall questions...",
    "Analyzing .NET 9 memory layout and compiler edge cases...",
    "Configuring four-gate verification criteria...",
    "Locking in question matrix..."
  ];
  let stepIdx = 0;

  container.innerHTML = `
    <div class="quiz-card" style="text-align: center; padding: 48px 20px;">
      <div class="loading-bat-spinner">🦇</div>
      <h3 style="font-family: var(--font-display); font-size: 28px; color: var(--accent-yellow); margin-top: 14px; letter-spacing: 1px;">PREPARING GOTHAM DRILL</h3>
      <p id="trainingLoadingStatusText" style="color: var(--text-secondary); font-size: 14px; margin: 12px 0 24px; min-height: 20px; font-family: var(--font-mono);">${statusSteps[0]}</p>
      
      <div style="display: flex; justify-content: center; gap: 12px;">
        <button class="btn-secondary" onclick="cancelTrainingLoad()" style="font-size: 13px; padding: 8px 18px;">
          ✕ Cancel Drill
        </button>
      </div>
    </div>
  `;

  if (trainingStatusInterval) clearInterval(trainingStatusInterval);
  trainingStatusInterval = setInterval(() => {
    stepIdx = (stepIdx + 1) % statusSteps.length;
    const statusEl = document.getElementById('trainingLoadingStatusText');
    if (statusEl) statusEl.textContent = statusSteps[stepIdx];
  }, 2200);

  trainingAbortController = new AbortController();
  const timeoutId = setTimeout(() => trainingAbortController.abort(), 18000);

  try {
    const res = await fetch(`/api/quiz/start/${topicId}`, { 
      method: 'POST',
      signal: trainingAbortController.signal
    });
    clearTimeout(timeoutId);
    clearInterval(trainingStatusInterval);

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Server returned HTTP ${res.status}`);
    }

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
    clearTimeout(timeoutId);
    clearInterval(trainingStatusInterval);
    const msg = err.name === 'AbortError' ? 'Drill generation cancelled or timed out.' : err.message;
    container.innerHTML = `
      <div class="quiz-card" style="border-color: var(--status-error); text-align: center; padding: 36px 20px;">
        <div style="font-size: 36px; margin-bottom: 12px;">⚠️</div>
        <h3 style="font-family: var(--font-display); font-size: 24px; color: var(--status-error); margin-bottom: 8px;">CALIBRATION INTERRUPTED</h3>
        <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 20px;">${msg}</p>
        <div style="display: flex; justify-content: center; gap: 12px;">
          <button class="btn-primary" onclick="startTopicTraining('${topicId}')">🔄 Retry Drill</button>
          <button class="btn-secondary" onclick="window.location.hash='#roadmap'">Back to Roadmap</button>
        </div>
      </div>
    `;
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

  let typeLabel = 'MULTIPLE CHOICE';
  if (q.question_type === 'output_prediction') typeLabel = 'OUTPUT PREDICTION';
  else if (q.question_type === 'fill_blank') typeLabel = 'FILL-IN-THE-BLANK';
  else if (q.question_type === 'coding') typeLabel = 'C# CODING TASK';

  let inputHtml = '';
  if (q.question_type === 'mcq') {
    inputHtml = `<div class="options-grid">
      ${q.options.map(opt => `
        <button class="option-btn" onclick="submitAnswer('${opt.charAt(0)}')">
          <span class="option-key-badge">${opt.charAt(0)}</span>
          <span class="option-text">${opt.slice(2).trim() || opt}</span>
        </button>
      `).join('')}
    </div>`;
  } else if (q.question_type === 'output_prediction' || q.question_type === 'fill_blank') {
    const placeholder = q.question_type === 'fill_blank' ? 'Type token replacing ___' : 'Type exact expected compiler output';
    inputHtml = `<div class="text-answer-box">
      <input type="text" id="textAnswerInput" class="chat-input" placeholder="${placeholder}" style="width: 100%; margin-bottom: 12px;" autocomplete="off">
      <button class="btn-primary" onclick="submitTextAnswer()">Verify Answer &rarr;</button>
    </div>`;
  } else {
    inputHtml = `<div class="text-answer-box">
      <textarea id="codeAnswerInput" class="code-editor-area" placeholder="// Write your C# solution"></textarea>
      <button class="btn-primary" style="margin-top: 12px;" onclick="submitCodeAnswer()">Submit C# Code &rarr;</button>
    </div>`;
  }

  container.innerHTML = `
    <div class="quiz-card">
      <div class="quiz-header">
        <div class="quiz-badge-group">
          <span class="badge badge-topic">🦇 ${q.subtopic || q.topic_id}</span>
          <span class="badge badge-type">${typeLabel}</span>
          <span class="badge badge-diff">LEVEL ${q.difficulty}/5</span>
        </div>
        <div class="quiz-progress-text">QUESTION ${q.question_index} OF ${totalQuestions}</div>
      </div>

      <div class="quiz-prompt">${q.prompt}</div>

      ${q.code_snippet ? `
        <div class="quiz-code-box">
          <pre><code class="language-csharp">${escapeHtml(q.code_snippet)}</code></pre>
        </div>
      ` : ''}

      ${inputHtml}

      <div id="feedbackContainer" style="display: none;"></div>
      <div id="hintContainer" style="display: none; padding: 12px 14px; background: rgba(245, 197, 24, 0.08); border-left: 3px solid var(--accent-yellow); border-radius: var(--radius-xs); font-size: 13.5px; margin-bottom: 18px; color: var(--accent-yellow); font-family: var(--font-mono);"></div>

      <div class="quiz-footer">
        <button class="btn-secondary" onclick="showHint()">💡 Tactical Hint</button>
        <button class="btn-secondary" onclick="skipQuestion()">Skip Question &rarr;</button>
      </div>
    </div>
  `;

  // Syntax highlighting
  container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));

  // 3D Card Tilt Entrance Animation
  if (window.GothamMotion) {
    const card = container.querySelector('.quiz-card');
    window.GothamMotion.animateQuizCardEnter(card);
  }
}

async function submitAnswer(userAnswer) {
  if (!activeQuestion) return;

  // Immediate visual feedback on click (eliminates perceived lag)
  const allBtns = document.querySelectorAll('.option-btn');
  let selectedBtn = null;

  allBtns.forEach(btn => {
    btn.disabled = true;
    const badge = btn.querySelector('.option-key-badge');
    const key = badge ? badge.textContent.trim() : btn.textContent.trim().charAt(0);
    if (key === userAnswer) {
      selectedBtn = btn;
      btn.classList.add('evaluating');
    }
  });

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
    displayAnswerFeedback(result, selectedBtn);
  } catch (err) {
    showToast('Failed to evaluate answer: ' + err.message, 'error');
    allBtns.forEach(btn => btn.disabled = false);
    if (selectedBtn) selectedBtn.classList.remove('evaluating');
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

function displayAnswerFeedback(result, selectedBtn) {
  const fb = document.getElementById('feedbackContainer');
  fb.className = `feedback-box ${result.is_correct ? 'correct' : 'wrong'}`;
  fb.style.display = 'block';

  // Remove evaluating state
  if (selectedBtn) selectedBtn.classList.remove('evaluating');

  // Highlight correct and wrong options
  document.querySelectorAll('.option-btn').forEach(btn => {
    btn.disabled = true;
    const badge = btn.querySelector('.option-key-badge');
    const key = badge ? badge.textContent.trim() : btn.textContent.trim().charAt(0);
    if (key === result.correct_answer) {
      btn.classList.add('selected-correct');
    } else if (selectedBtn === btn && !result.is_correct) {
      btn.classList.add('selected-wrong');
    }
  });

  // Motion design feedback (yellow flash vs screen shake + sound)
  if (window.GothamMotion) {
    window.GothamMotion.triggerAnswerFeedback(result.is_correct);
  }

  fb.innerHTML = `
    <div class="feedback-title">${result.is_correct ? '✅ VERIFIED: CORRECT' : '❌ INCORRECT SELECTION'}</div>
    <div class="feedback-explanation">
      <div style="margin-bottom: 6px;"><strong>EXPECTED:</strong> <code class="inline-code">${result.correct_answer}</code></div>
      ${result.explanation}
    </div>
    <div style="margin-top: 14px; text-align: right;">
      <button class="btn-primary" onclick="fetchNextQuestion()">Next Question &rarr;</button>
    </div>
  `;
}

function showHint() {
  if (!activeQuestion || !activeQuestion.hint) {
    showToast('No tactical hint available for this question.');
    return;
  }
  const h = document.getElementById('hintContainer');
  h.textContent = `💡 HINT: ${activeQuestion.hint}`;
  h.style.display = 'block';
}

function skipQuestion() {
  fetchNextQuestion();
}

// ----------------------------------------------------------------------------
// 25-QUESTION LEARNING REPORT & VERIFICATION GATES
// ----------------------------------------------------------------------------
async function loadLearningReport(setId) {
  const container = document.getElementById('quizContent');
  container.innerHTML = `
    <div class="quiz-card" style="text-align: center; padding: 48px 20px;">
      <div class="loading-bat-spinner">🦇</div>
      <div style="font-family: var(--font-display); font-size: 24px; color: var(--accent-yellow); margin-top: 14px;">COMPILING RETENTION TELEMETRY</div>
    </div>
  `;

  try {
    const res = await fetch(`/api/quiz/report/${setId}`);
    const r = await res.json();

    const scoreClass = r.passed ? 'passed' : 'failed';
    container.innerHTML = `
      <div class="report-card">
        <div class="report-header">
          <div class="score-circle ${scoreClass}">
            <span class="score-number">${r.score.toFixed(0)}%</span>
            <span class="score-label">${r.passed ? 'BENCHMARK MET' : 'NEEDS RETEST'}</span>
          </div>
          <h2 style="font-family: var(--font-display); font-size: 28px; margin-top: 14px;">SET #${r.set_number} COMPLETED: ${r.topic_title}</h2>
          <p style="color: ${r.passed ? 'var(--status-success)' : 'var(--status-error)'}; font-weight: 600; margin-top: 6px; font-family: var(--font-mono); font-size: 13.5px;">
            ${r.passed ? '🛡️ PASSED 70% MASTERY THRESHOLD' : '⚠️ BELOW 70% THRESHOLD. FOCUSED RETRY RECOMMENDED.'}
          </p>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 24px 0;">
          <div class="telemetry-card">
            <div style="font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--status-success); margin-bottom: 8px;">💪 VERIFIED STRENGTHS</div>
            <div class="subtopic-tags">
              ${r.strengths.length ? r.strengths.map(s => `<span class="tag-strength">${s}</span>`).join('') : '<span style="font-size: 13px; color: var(--text-muted);">None detected</span>'}
            </div>
          </div>
          <div class="telemetry-card">
            <div style="font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--status-error); margin-bottom: 8px;">🎯 TARGETED GAPS</div>
            <div class="subtopic-tags">
              ${r.weak_spots.length ? r.weak_spots.map(w => `<span class="tag-weak">${w}</span>`).join('') : '<span style="font-size: 13px; color: var(--status-success);">Zero gaps identified</span>'}
            </div>
          </div>
        </div>

        <!-- 4-Gate Mastery Status Box -->
        <div class="telemetry-card" style="margin-bottom: 24px;">
          <h3 style="font-family: var(--font-display); font-size: 20px; color: var(--accent-yellow); margin-bottom: 8px;">VERIFICATION GATE CHECKLIST</h3>
          <p style="color: var(--text-muted); font-size: 13.5px; margin-bottom: 16px;">${r.recommended_action}</p>
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            ${!r.passed ? `
              <button class="btn-primary" onclick="retrySet('${r.topic_id}')">🔄 Start Focused Retry</button>
            ` : ''}
            <button class="btn-secondary" onclick="openTeachBackModal('${r.topic_id}')">
              ${r.teach_back_status === 'Passed' ? '✅ Gate 2: Teach-Back Verified' : '📝 Gate 2: Teach-Back Check'}
            </button>
            <button class="btn-secondary" onclick="openAppChallengeModal('${r.topic_id}')">
              ${r.app_challenge_status === 'Passed' ? '✅ Gate 3: Coding Verified' : '💻 Gate 3: Application Check'}
            </button>
          </div>
        </div>

        <div style="text-align: center; margin-top: 24px;">
          <button class="btn-primary" onclick="window.location.hash = '#roadmap'">Back to Curriculum Roadmap &rarr;</button>
        </div>
      </div>
    `;

    // Trigger Bat Swarm Celebration on Set Completion
    if (window.GothamMotion && r.passed) {
      window.GothamMotion.triggerBatSwarmCelebration(r.score);
    }
  } catch (err) {
    container.innerHTML = `<div class="quiz-card" style="color: var(--status-error);">Error loading telemetry report: ${err.message}</div>`;
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

// ----------------------------------------------------------------------------
// MODALS: TEACH-BACK, CODING CHALLENGE, & PLACEMENT CALIBRATION
// ----------------------------------------------------------------------------
function openTeachBackModal(topicId) {
  currentTopicId = topicId;
  document.getElementById('teachBackTopicTitle').textContent = topicId;
  document.getElementById('teachBackResult').style.display = 'none';
  const modal = document.getElementById('teachBackModal');
  if (window.GothamMotion) window.GothamMotion.openModalAnimated(modal);
  else modal.classList.add('active');
}

function closeTeachBackModal() {
  const modal = document.getElementById('teachBackModal');
  if (window.GothamMotion) window.GothamMotion.closeModalAnimated(modal);
  else modal.classList.remove('active');
}

async function submitTeachBack() {
  const explanation = document.getElementById('teachBackInput').value.trim();
  if (!explanation) return;

  const btn = document.getElementById('teachBackSubmitBtn');
  btn.disabled = true;
  btn.textContent = 'Evaluating Rubric...';

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
      <div class="feedback-title">${result.passed ? '🎉 TEACH-BACK VERIFIED' : '⚠️ REFINEMENT NEEDED'} (SCORE: ${result.overall_score}%)</div>
      <div style="font-size: 13px; margin: 8px 0; font-family: var(--font-mono);">
        Accuracy: <strong>${result.accuracy_score}%</strong> • Completeness: <strong>${result.completeness_score}%</strong> • Clarity: <strong>${result.clarity_score}%</strong>
      </div>
      <p style="font-size: 13.5px; line-height: 1.5;">${result.feedback}</p>
    `;

    if (result.passed) {
      showToast('Teach-Back verification passed!');
      if (window.GothamMotion) window.GothamMotion.playProceduralSound('correct');
    }
  } catch (err) {
    showToast('Teach-back evaluation failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Submit for Rubric Evaluation';
  }
}

async function openAppChallengeModal(topicId) {
  currentTopicId = topicId;
  const modal = document.getElementById('appChallengeModal');
  if (window.GothamMotion) window.GothamMotion.openModalAnimated(modal);
  else modal.classList.add('active');

  const promptBox = document.getElementById('appChallengePromptText');
  const codeBox = document.getElementById('appChallengeCodeInput');
  document.getElementById('appChallengeResult').style.display = 'none';

  promptBox.textContent = 'Deciphering coding challenge...';
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
  const modal = document.getElementById('appChallengeModal');
  if (window.GothamMotion) window.GothamMotion.closeModalAnimated(modal);
  else modal.classList.remove('active');
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
      <div class="feedback-title">${result.passed ? '🎉 CODE REVIEW PASSED' : '⚠️ REVISIONS REQUIRED'} (SCORE: ${result.score}%)</div>
      <p style="font-size: 13.5px; margin-bottom: 8px;">${result.feedback}</p>
      <div style="font-size: 12.5px; font-family: var(--font-mono); display: flex; flex-direction: column; gap: 4px;">
        <div><strong>Correctness:</strong> ${result.correctness_notes}</div>
        <div><strong>Edge Cases:</strong> ${result.edge_case_notes}</div>
        <div><strong>Style:</strong> ${result.style_notes}</div>
      </div>
    `;

    if (result.passed) {
      showToast('Practical application challenge passed!');
      if (window.GothamMotion) window.GothamMotion.playProceduralSound('correct');
    }
  } catch (err) {
    showToast('Code review failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Submit for Code Review';
  }
}

async function openPlacementModal() {
  const modal = document.getElementById('placementModal');
  if (window.GothamMotion) window.GothamMotion.openModalAnimated(modal);
  else modal.classList.add('active');

  const container = document.getElementById('placementQuestionsContainer');
  container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 24px;">Calibrating 10 diagnostic questions...</div>';

  try {
    const res = await fetch('/api/placement/questions');
    placementQuestions = await res.json();

    container.innerHTML = placementQuestions.map((q, idx) => `
      <div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-steel);">
        <div style="font-weight: 600; font-size: 14.5px; margin-bottom: 8px; color: var(--text-primary);">Q${idx + 1}. ${q.prompt}</div>
        ${q.code_snippet ? `<div class="quiz-code-box"><pre><code class="language-csharp">${escapeHtml(q.code_snippet)}</code></pre></div>` : ''}
        <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
          ${q.options.map((opt, optIdx) => `
            <label style="display: flex; align-items: center; gap: 10px; font-size: 13.5px; cursor: pointer; padding: 8px 12px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-radius: var(--radius-xs);">
              <input type="radio" name="placement_q_${q.id}" value="${optIdx}">
              <span>${opt}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `).join('');

    container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  } catch (e) {
    container.innerHTML = '<div style="color: var(--status-error);">Failed to load diagnostic test.</div>';
  }
}

function closePlacementModal() {
  const modal = document.getElementById('placementModal');
  if (window.GothamMotion) window.GothamMotion.closeModalAnimated(modal);
  else modal.classList.remove('active');
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
    closePlacementModal();
    alert(`Diagnostic Completed! Score: ${result.score}%\n\n${result.message}`);
    loadRoadmap();
  } catch (err) {
    showToast('Placement submit failed: ' + err.message, 'error');
  }
}
