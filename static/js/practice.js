/**
 * ============================================================================
 * CodeCoach • Practice Arena Controller (Phase 1)
 * ============================================================================
 * 
 * 1. In-Browser C# Code Playground & Challenge Runner (CodeMirror)
 * 2. Bug Hunt Mode (Clickable line debugging with Zoro/Gotham feedback)
 * 3. Compiler Error & Stack Trace Decoder
 * 4. Refactor Challenge (4-part rubric evaluation)
 * 5. 60-Second Output Predictor Speed Rounds
 */

let playgroundEditor = null;
let refactorEditor = null;
let currentChallenges = [];
let activeChallenge = null;

// Bug Hunt State
let currentBugScenarios = [];
let activeBugScenario = null;
let bugSelectedLines = new Set();

// Refactor State
let currentRefactorScenarios = [];
let activeRefactorScenario = null;

// Output Predictor State
let activePredictorRound = null;
let predictorAnswers = [];
let predictorTimer = null;
let predictorTimeRemaining = 60;
let predictorQuestionIdx = 0;
let questionStartTime = 0;

document.addEventListener('DOMContentLoaded', () => {
  initPracticeSubTabs();
  initCompilerDecoderQuickChips();
});

// Switch between Practice sub-modes (Playground, Bug Hunt, Decoder, Refactor, Speed Round)
function initPracticeSubTabs() {
  const subTabBtns = document.querySelectorAll('.practice-subtab-btn');
  subTabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.submode;
      switchPracticeSubMode(target);
    });
  });
}

function switchPracticeSubMode(modeName) {
  document.querySelectorAll('.practice-subtab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.submode === modeName);
  });

  document.querySelectorAll('.practice-mode-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `practice-panel-${modeName}`);
  });

  if (modeName === 'playground') {
    initPlaygroundEditor();
    if (!currentChallenges.length) loadPlaygroundChallenges();
  } else if (modeName === 'bughunt') {
    if (!currentBugScenarios.length) loadBugHuntScenarios();
  } else if (modeName === 'refactor') {
    initRefactorEditor();
    if (!currentRefactorScenarios.length) loadRefactorScenarios();
  } else if (modeName === 'predictor') {
    // Reset view
    document.getElementById('predictorWelcomeDeck').style.display = 'block';
    document.getElementById('predictorActiveRoundDeck').style.display = 'none';
    document.getElementById('predictorResultDeck').style.display = 'none';
  }
}

// ----------------------------------------------------------------------------
// 1. IN-BROWSER C# CODE PLAYGROUND & CHALLENGES
// ----------------------------------------------------------------------------
function initPlaygroundEditor() {
  const textarea = document.getElementById('playgroundCodeEditor');
  if (!textarea) return;

  if (!playgroundEditor && window.CodeMirror) {
    playgroundEditor = CodeMirror.fromTextArea(textarea, {
      mode: 'text/x-csharp',
      theme: 'nord',
      lineNumbers: true,
      matchBrackets: true,
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      autoCloseBrackets: true
    });
    playgroundEditor.setSize('100%', 360);
  }
}

async function loadPlaygroundChallenges() {
  try {
    const res = await fetch('/api/practice/challenges');
    currentChallenges = await res.json();
    const select = document.getElementById('playgroundChallengeSelect');
    if (!select) return;

    select.innerHTML = '<option value="scratchpad">-- Free Scratchpad (Standalone Execution) --</option>';
    currentChallenges.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `[${c.difficulty.toUpperCase()}] ${c.title}`;
      select.appendChild(opt);
    });

    select.addEventListener('change', () => {
      onPlaygroundChallengeSelect(select.value);
    });
  } catch (e) {
    console.warn('Could not load coding challenges:', e);
  }
}

function onPlaygroundChallengeSelect(challengeId) {
  const descEl = document.getElementById('playgroundChallengeDescription');
  const runTestsBtn = document.getElementById('runChallengeTestsBtn');

  if (challengeId === 'scratchpad') {
    activeChallenge = null;
    descEl.style.display = 'none';
    runTestsBtn.style.display = 'none';
    if (playgroundEditor) {
      playgroundEditor.setValue(`using System;

public class Program
{
    public static void Main()
    {
        Console.WriteLine("Hello Gotham! Welcome to C# 13 in-browser playground.");
        
        int[] numbers = [10, 20, 30, 40];
        Console.WriteLine($"Sum: {Sum(numbers)}");
    }

    public static int Sum(ReadOnlySpan<int> span)
    {
        int total = 0;
        foreach (int n in span) total += n;
        return total;
    }
}`);
    }
  } else {
    activeChallenge = currentChallenges.find(c => c.id === challengeId);
    if (!activeChallenge) return;

    descEl.style.display = 'block';
    descEl.innerHTML = `<strong>Challenge:</strong> ${activeChallenge.description}`;
    runTestsBtn.style.display = 'inline-flex';

    if (playgroundEditor) {
      playgroundEditor.setValue(activeChallenge.starter_code);
    }
  }
}

async function runPlaygroundCode() {
  if (!playgroundEditor) return;
  const code = playgroundEditor.getValue().trim();
  if (!code) {
    showToast('Playground editor is empty.', 'error');
    return;
  }

  const btn = document.getElementById('runPlaygroundBtn');
  const outputPre = document.getElementById('playgroundStdout');
  const stderrPre = document.getElementById('playgroundStderr');
  const metaSpan = document.getElementById('playgroundExecutionMeta');
  const warningBanner = document.getElementById('playgroundWarningBanner');

  btn.disabled = true;
  btn.innerHTML = '⚡ Compiling & Running...';
  outputPre.textContent = 'Executing C# binary in secure sandbox...';
  stderrPre.textContent = '';
  warningBanner.style.display = 'none';

  try {
    const res = await fetch('/api/practice/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    const data = await res.json();

    outputPre.textContent = data.stdout || '(Program completed with no standard output)';
    stderrPre.textContent = data.stderr || '';

    metaSpan.textContent = `Engine: ${data.engine.toUpperCase()} • Time: ${data.execution_time_ms}ms • Exit Code: ${data.exit_code}`;

    if (data.is_simulated && data.warning) {
      warningBanner.style.display = 'block';
      warningBanner.textContent = data.warning;
    }
  } catch (err) {
    outputPre.textContent = '';
    stderrPre.textContent = `Client Execution Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '▶ Execute C# Code';
  }
}

async function runActiveChallengeTests() {
  if (!activeChallenge || !playgroundEditor) return;
  const code = playgroundEditor.getValue().trim();
  const testResultsContainer = document.getElementById('challengeTestResultsContainer');
  testResultsContainer.style.display = 'block';
  testResultsContainer.innerHTML = '<div style="color: var(--text-muted); font-family: var(--font-mono); padding: 12px;">Running test matrix against sandbox...</div>';

  try {
    const res = await fetch(`/api/practice/challenges/${activeChallenge.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    const data = await res.json();

    testResultsContainer.innerHTML = `
      <div style="font-family: var(--font-display); font-size: 20px; color: ${data.passed ? 'var(--status-success)' : 'var(--status-error)'}; margin-bottom: 8px;">
        ${data.passed ? '✅ ALL TESTS PASSED' : '⚠️ TEST MATRIX VERIFICATION FAILED'} (${data.tests_passed}/${data.tests_total})
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        ${data.test_results.map(tr => `
          <div style="padding: 10px 14px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-left: 3px solid ${tr.passed ? 'var(--status-success)' : 'var(--status-error)'}; border-radius: var(--radius-xs); font-family: var(--font-mono); font-size: 12.5px;">
            <div style="display: flex; justify-content: space-between;">
              <span>Test #${tr.test_index} ${tr.is_hidden ? '(Hidden Verification Test)' : ''}</span>
              <strong style="color: ${tr.passed ? 'var(--status-success)' : 'var(--status-error)'};">${tr.passed ? 'PASSED' : 'FAILED'}</strong>
            </div>
            ${!tr.is_hidden ? `
              <div style="color: var(--text-muted); margin-top: 4px;">Expected: <code>${tr.expected_output}</code> | Actual: <code>${tr.actual_output}</code></div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    `;

    if (data.passed && window.GothamMotion) {
      window.GothamMotion.playProceduralSound('correct');
      window.GothamMotion.triggerBatSwarmCelebration();
    }
  } catch (err) {
    testResultsContainer.innerHTML = `<div style="color: var(--status-error);">Test execution error: ${err.message}</div>`;
  }
}

// ----------------------------------------------------------------------------
// 2. BUG HUNT MODE
// ----------------------------------------------------------------------------
async function loadBugHuntScenarios() {
  try {
    const res = await fetch('/api/practice/bug-hunt');
    currentBugScenarios = await res.json();
    if (currentBugScenarios.length) {
      displayBugHuntScenario(currentBugScenarios[0].id);
    }
  } catch (e) {
    console.warn('Could not load bug hunt scenarios:', e);
  }
}

async function displayBugHuntScenario(scenarioId) {
  try {
    const res = await fetch(`/api/practice/bug-hunt/${scenarioId}`);
    activeBugScenario = await res.json();
    bugSelectedLines.clear();

    document.getElementById('bugHuntTitle').textContent = `🐞 ${activeBugScenario.title.toUpperCase()}`;
    document.getElementById('bugHuntDifficultyBadge').textContent = activeBugScenario.difficulty.toUpperCase();
    document.getElementById('bugHuntDescription').textContent = activeBugScenario.description;
    document.getElementById('bugHuntBugsCountLabel').textContent = `Defects Hidden: ${activeBugScenario.total_bugs}`;
    document.getElementById('bugHuntFeedbackDeck').style.display = 'none';

    renderBugHuntCodeSnippet(activeBugScenario.code_snippet);
  } catch (e) {
    console.error('Error displaying bug scenario:', e);
  }
}

function renderBugHuntCodeSnippet(code) {
  const codeLinesContainer = document.getElementById('bugHuntCodeLines');
  codeLinesContainer.innerHTML = '';
  const lines = code.split('\n');

  lines.forEach((lineText, idx) => {
    const lineNum = idx + 1;
    const row = document.createElement('div');
    row.className = 'bug-hunt-line-row';
    row.dataset.line = lineNum;

    row.innerHTML = `
      <span class="bug-hunt-line-num">${lineNum}</span>
      <span class="bug-hunt-line-code">${escapeHtml(lineText || ' ')}</span>
      <span class="bug-hunt-target-flag">🎯</span>
    `;

    row.addEventListener('click', () => {
      toggleBugLineSelection(lineNum, row);
    });

    codeLinesContainer.appendChild(row);
  });
}

function toggleBugLineSelection(lineNum, rowElement) {
  if (bugSelectedLines.has(lineNum)) {
    bugSelectedLines.delete(lineNum);
    rowElement.classList.remove('selected-target');
  } else {
    bugSelectedLines.add(lineNum);
    rowElement.classList.add('selected-target');
  }

  const submitBtn = document.getElementById('submitBugHuntBtn');
  submitBtn.textContent = `Eliminate Selected (${bugSelectedLines.size} Target${bugSelectedLines.size === 1 ? '' : 's'})`;
}

async function submitBugHuntInspection() {
  if (!activeBugScenario) return;
  if (bugSelectedLines.size === 0) {
    showToast('Click one or more suspicious code lines first.', 'error');
    return;
  }

  const feedbackDeck = document.getElementById('bugHuntFeedbackDeck');
  feedbackDeck.style.display = 'block';
  feedbackDeck.innerHTML = '<div style="color: var(--text-muted); font-family: var(--font-mono); padding: 12px;">Evaluating detective analysis...</div>';

  try {
    const res = await fetch(`/api/practice/bug-hunt/${activeBugScenario.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        selected_lines: Array.from(bugSelectedLines)
      })
    });
    const result = await res.json();

    feedbackDeck.innerHTML = `
      <div style="font-family: var(--font-display); font-size: 22px; color: ${result.all_found ? 'var(--status-success)' : 'var(--accent-yellow)'}; margin-bottom: 6px;">
        ${result.feedback}
      </div>
      <div style="font-family: var(--font-mono); font-size: 12.5px; color: var(--text-muted); margin-bottom: 14px;">
        Accuracy: <strong>${result.score}%</strong> • Detected: <strong>${result.found_count}/${result.total_bugs}</strong> bugs • False Alarms: <strong>${result.false_positives.length}</strong>
      </div>
      <div style="display: flex; flex-direction: column; gap: 10px;">
        ${result.detected_bugs.map(b => `
          <div style="padding: 12px 14px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-left: 3px solid var(--status-success); border-radius: var(--radius-xs);">
            <div style="font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--status-success);">LINE ${b.line} // ${b.bug_type.toUpperCase()}</div>
            <p style="font-size: 13.5px; margin: 4px 0 8px; color: var(--text-primary);">${b.explanation}</p>
            <div style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-yellow); background: var(--bg-code); padding: 6px 10px; border-radius: 2px;">
              <strong>FIX:</strong> <code>${b.fix_code}</code>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    if (result.all_found && window.GothamMotion) {
      window.GothamMotion.playProceduralSound('correct');
    }
  } catch (err) {
    feedbackDeck.innerHTML = `<div style="color: var(--status-error);">Evaluation failed: ${err.message}</div>`;
  }
}

function loadNextBugHuntScenario() {
  if (!currentBugScenarios.length) return;
  const currentIdx = currentBugScenarios.findIndex(s => s.id === activeBugScenario?.id);
  const nextIdx = (currentIdx + 1) % currentBugScenarios.length;
  displayBugHuntScenario(currentBugScenarios[nextIdx].id);
}

// ----------------------------------------------------------------------------
// 3. COMPILER ERROR DECODER
// ----------------------------------------------------------------------------
function initCompilerDecoderQuickChips() {
  const chips = document.querySelectorAll('.decoder-quick-chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const input = document.getElementById('compilerErrorInput');
      input.value = chip.dataset.errorSample;
      submitCompilerDecode();
    });
  });
}

async function submitCompilerDecode() {
  const input = document.getElementById('compilerErrorInput');
  const errorText = input.value.trim();
  if (!errorText) {
    showToast('Please paste a compiler diagnostic or exception message.', 'error');
    return;
  }

  const resultContainer = document.getElementById('compilerDecodeResult');
  const btn = document.getElementById('decodeCompilerErrorBtn');
  resultContainer.style.display = 'block';
  resultContainer.innerHTML = '<div style="color: var(--text-muted); font-family: var(--font-mono); padding: 20px; text-align: center;">Deciphering compiler diagnostic telemetry...</div>';
  btn.disabled = true;

  try {
    const res = await fetch('/api/practice/compiler-decoder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error_text: errorText })
    });
    const d = await res.json();

    resultContainer.innerHTML = `
      <div style="border: 1px solid var(--border-steel); border-left: 4px solid var(--accent-yellow); background: var(--bg-surface); padding: var(--space-md); border-radius: var(--radius-xs);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <h3 style="font-family: var(--font-display); font-size: 22px; color: var(--accent-yellow); margin: 0;">${d.error_title}</h3>
          ${d.error_code ? `<span class="badge badge-topic">${d.error_code}</span>` : ''}
        </div>
        
        <p style="font-size: 15px; color: var(--text-primary); line-height: 1.5; margin-bottom: 16px;">
          ${d.plain_explanation}
        </p>

        <div style="margin-bottom: 14px;">
          <h4 style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">PROBABLE ROOT CAUSES:</h4>
          <ul style="padding-left: 20px; font-size: 13.5px; color: var(--text-secondary); line-height: 1.6;">
            ${d.likely_causes.map(c => `<li>${c}</li>`).join('')}
          </ul>
        </div>

        <div style="margin-bottom: 16px;">
          <h4 style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">RECOMMENDED ACTION:</h4>
          <p style="font-size: 13.5px; color: var(--text-secondary);">${d.recommended_fix}</p>
        </div>

        ${d.code_example_before && d.code_example_after ? `
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px;">
            <div style="background: var(--bg-code); padding: 10px; border-radius: var(--radius-xs); border: 1px solid var(--status-error);">
              <span style="font-family: var(--font-mono); font-size: 11px; color: var(--status-error); font-weight: 700;">❌ BEFORE (CAUSES ERROR)</span>
              <pre style="margin-top: 6px; font-family: var(--font-mono); font-size: 12px; overflow-x: auto;"><code>${escapeHtml(d.code_example_before)}</code></pre>
            </div>
            <div style="background: var(--bg-code); padding: 10px; border-radius: var(--radius-xs); border: 1px solid var(--status-success);">
              <span style="font-family: var(--font-mono); font-size: 11px; color: var(--status-success); font-weight: 700;">✅ AFTER (CORRECTED)</span>
              <pre style="margin-top: 6px; font-family: var(--font-mono); font-size: 12px; overflow-x: auto;"><code>${escapeHtml(d.code_example_after)}</code></pre>
            </div>
          </div>
        ` : ''}

        ${d.related_topic_id ? `
          <div style="margin-top: 18px; border-top: 1px solid var(--border-subtle); padding-top: 12px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 13px; color: var(--text-muted);">Curriculum Mapping: <strong>${d.related_topic_title || d.related_topic_id}</strong></span>
            <button class="btn-secondary" style="font-size: 12px; padding: 4px 10px;" onclick="window.location.hash='#quiz/${d.related_topic_id}'">Train This Topic &rarr;</button>
          </div>
        ` : ''}
      </div>
    `;
  } catch (err) {
    resultContainer.innerHTML = `<div style="color: var(--status-error);">Decoder analysis failed: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// 4. REFACTOR CHALLENGE
// ----------------------------------------------------------------------------
function initRefactorEditor() {
  const textarea = document.getElementById('refactorCodeEditor');
  if (!textarea) return;

  if (!refactorEditor && window.CodeMirror) {
    refactorEditor = CodeMirror.fromTextArea(textarea, {
      mode: 'text/x-csharp',
      theme: 'nord',
      lineNumbers: true,
      matchBrackets: true,
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      autoCloseBrackets: true
    });
    refactorEditor.setSize('100%', 320);
  }
}

async function loadRefactorScenarios() {
  try {
    const res = await fetch('/api/practice/refactor');
    currentRefactorScenarios = await res.json();
    const select = document.getElementById('refactorScenarioSelect');
    if (!select) return;

    select.innerHTML = '';
    currentRefactorScenarios.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.title;
      select.appendChild(opt);
    });

    select.addEventListener('change', () => {
      onRefactorScenarioSelect(select.value);
    });

    if (currentRefactorScenarios.length) {
      onRefactorScenarioSelect(currentRefactorScenarios[0].id);
    }
  } catch (e) {
    console.warn('Could not load refactor scenarios:', e);
  }
}

function onRefactorScenarioSelect(scenarioId) {
  activeRefactorScenario = currentRefactorScenarios.find(s => s.id === scenarioId);
  if (!activeRefactorScenario) return;

  document.getElementById('refactorDescription').textContent = activeRefactorScenario.description;
  document.getElementById('refactorBadCodeDisplay').textContent = activeRefactorScenario.bad_code;
  if (window.hljs) hljs.highlightElement(document.getElementById('refactorBadCodeDisplay'));

  if (refactorEditor) {
    refactorEditor.setValue(activeRefactorScenario.bad_code);
  }
  document.getElementById('refactorFeedbackContainer').style.display = 'none';
}

async function submitRefactorChallenge() {
  if (!activeRefactorScenario || !refactorEditor) return;
  const refactored_code = refactorEditor.getValue().trim();
  if (!refactored_code) {
    showToast('Refactored code cannot be empty.', 'error');
    return;
  }

  const container = document.getElementById('refactorFeedbackContainer');
  const btn = document.getElementById('submitRefactorBtn');
  container.style.display = 'block';
  container.innerHTML = '<div style="color: var(--text-muted); font-family: var(--font-mono); padding: 18px; text-align: center;">Grading refactoring against 4-part architectural rubric...</div>';
  btn.disabled = true;

  try {
    const res = await fetch(`/api/practice/refactor/${activeRefactorScenario.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refactored_code })
    });
    const d = await res.json();

    container.innerHTML = `
      <div style="padding: var(--space-md); background: var(--bg-surface); border: 1px solid var(--border-steel); border-left: 4px solid ${d.passed ? 'var(--status-success)' : 'var(--status-error)'}; border-radius: var(--radius-xs);">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px;">
          <h3 style="font-family: var(--font-display); font-size: 24px; color: ${d.passed ? 'var(--status-success)' : 'var(--status-error)'}; margin: 0;">
            ${d.passed ? '🎉 REFACTORING VERIFIED' : '⚠️ REVISIONS RECOMMENDED'} (SCORE: ${d.score}%)
          </h3>
          <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">Pass Threshold: 70%</span>
        </div>

        <p style="font-size: 14.5px; color: var(--text-primary); margin-bottom: 16px;">${d.feedback}</p>

        <!-- 4-part Rubric Matrix -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px;">
          <div style="padding: 8px; background: var(--bg-code); text-align: center; border-radius: var(--radius-xs);">
            <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">READABILITY</div>
            <div style="font-family: var(--font-display); font-size: 18px; color: var(--accent-yellow);">${d.readability_score}%</div>
          </div>
          <div style="padding: 8px; background: var(--bg-code); text-align: center; border-radius: var(--radius-xs);">
            <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">C# IDIOMS</div>
            <div style="font-family: var(--font-display); font-size: 18px; color: var(--accent-yellow);">${d.idiom_score}%</div>
          </div>
          <div style="padding: 8px; background: var(--bg-code); text-align: center; border-radius: var(--radius-xs);">
            <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">CORRECTNESS</div>
            <div style="font-family: var(--font-display); font-size: 18px; color: var(--accent-yellow);">${d.correctness_score}%</div>
          </div>
          <div style="padding: 8px; background: var(--bg-code); text-align: center; border-radius: var(--radius-xs);">
            <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">PERFORMANCE</div>
            <div style="font-family: var(--font-display); font-size: 18px; color: var(--accent-yellow);">${d.performance_score}%</div>
          </div>
        </div>

        <!-- Ideal Comparison -->
        <details style="margin-top: 14px; background: var(--bg-code); padding: 10px; border-radius: var(--radius-xs); border: 1px dashed var(--border-steel);">
          <summary style="cursor: pointer; font-family: var(--font-mono); font-size: 12px; color: var(--accent-yellow);">🦇 Click to inspect model architect refactoring</summary>
          <pre style="margin-top: 8px; font-family: var(--font-mono); font-size: 12.5px; overflow-x: auto;"><code>${escapeHtml(d.ideal_comparison)}</code></pre>
        </details>
      </div>
    `;

    if (d.passed && window.GothamMotion) {
      window.GothamMotion.playProceduralSound('correct');
    }
  } catch (err) {
    container.innerHTML = `<div style="color: var(--status-error);">Refactor grading failed: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// 5. 60-SECOND OUTPUT PREDICTOR SPEED ROUNDS
// ----------------------------------------------------------------------------
async function startOutputPredictorSpeedRound() {
  const welcomeDeck = document.getElementById('predictorWelcomeDeck');
  const activeDeck = document.getElementById('predictorActiveRoundDeck');
  const resultDeck = document.getElementById('predictorResultDeck');

  welcomeDeck.style.display = 'none';
  resultDeck.style.display = 'none';
  activeDeck.style.display = 'block';

  try {
    const res = await fetch('/api/practice/output-predictor/round');
    activePredictorRound = await res.json();
    predictorAnswers = [];
    predictorQuestionIdx = 0;
    predictorTimeRemaining = 60;

    startPredictorTimer();
    renderPredictorQuestion();
  } catch (e) {
    showToast('Failed to start speed round: ' + e.message, 'error');
  }
}

function startPredictorTimer() {
  clearInterval(predictorTimer);
  const timerDisplay = document.getElementById('predictorTimerClock');

  predictorTimer = setInterval(() => {
    predictorTimeRemaining--;
    if (timerDisplay) timerDisplay.textContent = `${predictorTimeRemaining}s`;

    if (predictorTimeRemaining <= 0) {
      clearInterval(predictorTimer);
      finishOutputPredictorRound();
    }
  }, 1000);
}

function renderPredictorQuestion() {
  if (!activePredictorRound || predictorQuestionIdx >= activePredictorRound.questions.length) {
    finishOutputPredictorRound();
    return;
  }

  const q = activePredictorRound.questions[predictorQuestionIdx];
  questionStartTime = performance.now();

  document.getElementById('predictorQuestionCounter').textContent = `Question ${predictorQuestionIdx + 1} of ${activePredictorRound.questions.length}`;
  document.getElementById('predictorQuestionSnippet').textContent = q.code_snippet;
  if (window.hljs) hljs.highlightElement(document.getElementById('predictorQuestionSnippet'));

  const optionsGrid = document.getElementById('predictorOptionsGrid');
  optionsGrid.innerHTML = '';

  q.options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'option-btn';
    btn.innerHTML = `
      <span class="option-key-badge">${opt.charAt(0)}</span>
      <span>${opt.slice(2).trim()}</span>
    `;
    btn.addEventListener('click', () => {
      onPredictorAnswerSelect(opt.charAt(0));
    });
    optionsGrid.appendChild(btn);
  });
}

function onPredictorAnswerSelect(choice) {
  const q = activePredictorRound.questions[predictorQuestionIdx];
  const timeSpent = (performance.now() - questionStartTime) / 1000.0;

  predictorAnswers.push({
    question_id: q.id,
    selected_option: choice,
    time_spent_seconds: timeSpent
  });

  if (window.GothamMotion) window.GothamMotion.playProceduralSound('whoosh');

  predictorQuestionIdx++;
  renderPredictorQuestion();
}

async function finishOutputPredictorRound() {
  clearInterval(predictorTimer);
  const activeDeck = document.getElementById('predictorActiveRoundDeck');
  const resultDeck = document.getElementById('predictorResultDeck');

  activeDeck.style.display = 'none';
  resultDeck.style.display = 'block';
  resultDeck.innerHTML = '<div style="color: var(--text-muted); font-family: var(--font-mono); padding: 32px; text-align: center;">Calculating score, speed bonuses, and streak multipliers...</div>';

  try {
    const res = await fetch('/api/practice/output-predictor/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        round_id: activePredictorRound.round_id,
        answers: predictorAnswers
      })
    });
    const d = await res.json();

    resultDeck.innerHTML = `
      <div class="report-card" style="text-align: center; max-width: 640px; margin: 0 auto;">
        <div style="font-family: var(--font-display); font-size: 38px; color: var(--accent-yellow);">${d.total_score} PTS</div>
        <div style="font-family: var(--font-mono); font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">
          Accuracy: <strong>${d.correct_count}/${d.total_questions}</strong> • Max Streak: <strong>${d.max_streak}x</strong> • Speed Bonus: <strong>+${d.speed_bonus} pts</strong>
        </div>

        <div style="display: flex; flex-direction: column; gap: 10px; text-align: left; margin: 20px 0;">
          ${d.results.map((r, idx) => `
            <div style="padding: 10px 14px; background: var(--bg-surface); border: 1px solid var(--border-steel); border-left: 3px solid ${r.is_correct ? 'var(--status-success)' : 'var(--status-error)'}; border-radius: var(--radius-xs); font-size: 13px;">
              <div style="display: flex; justify-content: space-between; font-family: var(--font-mono);">
                <span>Q${idx + 1}: Expected <code>${r.correct_output}</code> (You picked: <code>${r.user_answer}</code>)</span>
                <strong style="color: ${r.is_correct ? 'var(--status-success)' : 'var(--status-error)'};">${r.is_correct ? 'CORRECT' : 'INCORRECT'}</strong>
              </div>
              <div style="color: var(--text-muted); margin-top: 4px; font-size: 12.5px;">${r.explanation}</div>
            </div>
          `).join('')}
        </div>

        <button class="btn-primary" onclick="startOutputPredictorSpeedRound()">⚡ Play Another Round</button>
      </div>
    `;

    if (d.total_score >= 300 && window.GothamMotion) {
      window.GothamMotion.triggerBatSwarmCelebration();
    }
  } catch (e) {
    resultDeck.innerHTML = `<div style="color: var(--status-error);">Round calculation failed: ${e.message}</div>`;
  }
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
