/**
 * ============================================================================
 * CodeCoach • Gotham Noir Motion Engine (GSAP & ScrollTrigger)
 * ============================================================================
 * 
 * Provides all 14 motion design behaviors for the Batman-inspired Gotham theme:
 *  1. Intro Bat-Signal Loader (sweeping beam, cloud emblem flicker, skippable)
 *  2. Tab & View Slash Transitions (angular diagonal wipe)
 *  3. Chat Message In-Animations (user slide-right, assistant fog-reveal)
 *  4. Bat-Flap Typing & Token Streaming Indicator
 *  5. Quiz Card 3D Tilt & Answer Feedback (Yellow flash vs screen shake)
 *  6. Set Completion Bat-Swarm Confetti & Score Count-Up
 *  7. Roadmap Node Mastery Unlock & Connecting Line Draw
 *  8. Dashboard Telemetry Count-Ups & Growing Meters
 *  9. Hover Light Sweeps & Focus Rings
 * 10. Notification Bell Swing
 * 11. Flame-to-Bat Streak Badge Animation & Milestone Bursts
 * 12. Modal Diagonal Slash Reveals
 * 13. Parallax Skyline, Drifting Mist, & Throttled Lightning
 * 14. Signal-Yellow Edge Toasts
 * 
 * Tunable Timings & Constants are configured at the top of this file.
 */

window.GothamMotion = (function() {
  'use strict';

  // --------------------------------------------------------------------------
  // TUNABLE TIMINGS & CONFIGURATION
  // --------------------------------------------------------------------------
  const CONFIG = {
    introDuration: 2.8,          // Total seconds for Bat-Signal sweep & reveal
    tabWipeDuration: 0.35,       // Seconds for diagonal tab wipe
    cardTiltAngle: 5,            // Degrees of 3D card tilt on entrance
    shakeIntensity: 6,           // Pixels of screen shake on wrong answer
    maxLightningPerMin: 2,       // Rare, safe lightning frequency (strictly < 3/sec)
    soundEnabledDefault: false,  // Web Audio procedural sound effects OFF by default
  };

  // Check prefers-reduced-motion
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Audio Context (Synthesized procedural sound effects - no external audio files required)
  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx && (window.AudioContext || window.webkitAudioContext)) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContextClass();
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playProceduralSound(type) {
    if (!isSoundEnabled() || prefersReducedMotion) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;

      const now = ctx.currentTime;
      if (type === 'whoosh') {
        // Soft atmospheric whoosh
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const filter = ctx.createBiquadFilter();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(140, now);
        osc.frequency.exponentialRampToValueAtTime(60, now + 0.25);

        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(400, now);

        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

        osc.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now);
        osc.stop(now + 0.25);
      } else if (type === 'signal') {
        // Subtle electric hum/chime
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.15);

        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.2);
      } else if (type === 'correct') {
        // High harmonic double-tone
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        const gain = ctx.createGain();

        osc1.type = 'sine';
        osc2.type = 'sine';
        osc1.frequency.setValueAtTime(523.25, now); // C5
        osc2.frequency.setValueAtTime(659.25, now); // E5

        gain.gain.setValueAtTime(0.09, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);

        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + 0.35);
        osc2.stop(now + 0.35);
      } else if (type === 'wrong') {
        // Low industrial thud
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(110, now);
        osc.frequency.exponentialRampToValueAtTime(55, now + 0.2);

        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.2);
      }
    } catch (e) {
      // Audio error suppressed silently
    }
  }

  function isSoundEnabled() {
    const val = localStorage.getItem('gotham_sound');
    return val === null ? CONFIG.soundEnabledDefault : val === 'true';
  }

  function toggleSound() {
    const nextState = !isSoundEnabled();
    localStorage.setItem('gotham_sound', nextState ? 'true' : 'false');
    updateSoundButtonUI(nextState);
    if (nextState) playProceduralSound('signal');
    return nextState;
  }

  function updateSoundButtonUI(enabled) {
    const btn = document.getElementById('soundToggleBtn');
    if (btn) {
      btn.innerHTML = enabled ? '🔊' : '🔇';
      btn.title = enabled ? 'Sound Effects: ON (Click to Mute)' : 'Sound Effects: MUTED (Click to Enable)';
    }
  }

  // --------------------------------------------------------------------------
  // 1. INTRO LOADER: BAT-SIGNAL SWEEP & REVEAL
  // --------------------------------------------------------------------------
  function initIntroLoader() {
    const introEl = document.getElementById('gothamIntroLoader');
    if (!introEl) return;

    // Check if user already saw intro this session
    const hasSeen = sessionStorage.getItem('gotham_intro_seen');
    if (hasSeen || prefersReducedMotion) {
      introEl.style.display = 'none';
      return;
    }

    if (typeof gsap === 'undefined') {
      introEl.style.display = 'none';
      return;
    }

    const beam = introEl.querySelector('.signal-beam');
    const cloudTarget = introEl.querySelector('.signal-cloud-target');
    const emblem = introEl.querySelector('.signal-emblem-reveal');
    const introText = introEl.querySelector('.intro-tagline');
    const skipBtn = introEl.querySelector('#skipIntroBtn');

    const tl = gsap.timeline({
      onComplete: () => dismissIntroLoader(introEl)
    });

    // Animate Bat-Signal sweeping up from city horizon into Gotham storm clouds
    tl.set(beam, { scaleY: 0, transformOrigin: 'bottom center', opacity: 0 })
      .set(cloudTarget, { scale: 0.6, opacity: 0 })
      .set(emblem, { opacity: 0, scale: 0.85 })
      .set(introText, { opacity: 0, y: 12 })
      .to(beam, {
        duration: 0.9,
        scaleY: 1,
        opacity: 0.85,
        ease: 'power3.out'
      })
      .to(cloudTarget, {
        duration: 0.6,
        scale: 1,
        opacity: 0.9,
        ease: 'power2.out'
      }, '-=0.3')
      // Emblem flicker effect on cloud
      .to(emblem, {
        duration: 0.15,
        opacity: 0.4,
        ease: 'rough'
      })
      .to(emblem, { duration: 0.08, opacity: 0.1 })
      .to(emblem, { duration: 0.12, opacity: 0.85 })
      .to(emblem, { duration: 0.06, opacity: 0.4 })
      .to(emblem, {
        duration: 0.4,
        opacity: 1,
        scale: 1,
        ease: 'back.out(1.5)',
        onStart: () => playProceduralSound('signal')
      })
      .to(introText, {
        duration: 0.5,
        opacity: 1,
        y: 0,
        ease: 'power2.out'
      }, '-=0.2')
      .to({}, { duration: 0.8 }) // Hold reveal for 0.8s
      .to(introEl, {
        duration: 0.6,
        opacity: 0,
        ease: 'power3.inOut'
      });

    // Skip handler
    if (skipBtn) {
      skipBtn.addEventListener('click', () => {
        tl.kill();
        dismissIntroLoader(introEl);
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && introEl.style.display !== 'none') {
        tl.kill();
        dismissIntroLoader(introEl);
      }
    }, { once: true });
  }

  function dismissIntroLoader(el) {
    if (!el) return;
    sessionStorage.setItem('gotham_intro_seen', 'true');
    if (typeof gsap !== 'undefined' && !prefersReducedMotion) {
      gsap.to(el, {
        duration: 0.4,
        opacity: 0,
        onComplete: () => {
          el.style.display = 'none';
          animateAppEntry();
        }
      });
    } else {
      el.style.display = 'none';
      animateAppEntry();
    }
  }

  function animateAppEntry() {
    if (prefersReducedMotion || typeof gsap === 'undefined') return;
    const header = document.querySelector('.app-header');
    const rail = document.querySelector('.curriculum-rail');
    const workspace = document.querySelector('.main-workspace');

    gsap.fromTo(header, 
      { y: -30, opacity: 0 }, 
      { duration: 0.5, y: 0, opacity: 1, ease: 'power2.out' }
    );
    gsap.fromTo(rail, 
      { x: -30, opacity: 0 }, 
      { duration: 0.55, x: 0, opacity: 1, ease: 'power2.out', delay: 0.1 }
    );
    gsap.fromTo(workspace, 
      { y: 20, opacity: 0 }, 
      { duration: 0.55, y: 0, opacity: 1, ease: 'power2.out', delay: 0.15 }
    );
  }

  // --------------------------------------------------------------------------
  // 2. VIEW / TAB TRANSITIONS: ANGULAR SLASH WIPE
  // --------------------------------------------------------------------------
  function transitionToView(targetSection) {
    if (!targetSection) return;
    playProceduralSound('whoosh');

    if (prefersReducedMotion || typeof gsap === 'undefined') {
      document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
      targetSection.classList.add('active');
      return;
    }

    const wipe = document.getElementById('gothamSlashWipe');
    if (!wipe) {
      document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
      targetSection.classList.add('active');
      gsap.fromTo(targetSection, { opacity: 0, y: 15 }, { opacity: 1, y: 0, duration: 0.3 });
      return;
    }

    const tl = gsap.timeline();
    tl.set(wipe, { display: 'block', clipPath: 'polygon(0 0, 0 0, 0 100%, 0 100%)' })
      .to(wipe, {
        duration: CONFIG.tabWipeDuration * 0.5,
        clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 100%)',
        ease: 'power3.inOut',
        onComplete: () => {
          document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
          targetSection.classList.add('active');
          window.scrollTo(0, 0);
        }
      })
      .to(wipe, {
        duration: CONFIG.tabWipeDuration * 0.5,
        clipPath: 'polygon(100% 0, 100% 0, 100% 100%, 100% 100%)',
        ease: 'power3.inOut',
        onComplete: () => {
          wipe.style.display = 'none';
          gsap.fromTo(targetSection, 
            { opacity: 0, y: 10 }, 
            { opacity: 1, y: 0, duration: 0.25, ease: 'power2.out' }
          );
        }
      });
  }

  // --------------------------------------------------------------------------
  // 3. CHAT MESSAGE IN-ANIMATIONS
  // --------------------------------------------------------------------------
  function animateChatMessage(row, sender) {
    if (prefersReducedMotion || typeof gsap === 'undefined' || !row) return;

    if (sender === 'user') {
      // User message slides in fast from the right
      gsap.fromTo(row,
        { x: 35, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.3, ease: 'power2.out' }
      );
    } else {
      // Assistant message emerges smoothly from shadow/mist
      gsap.fromTo(row,
        { opacity: 0, y: 16, filter: 'blur(3px)' },
        { opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.4, ease: 'power3.out' }
      );
    }
  }

  // --------------------------------------------------------------------------
  // 4. BAT-FLAP TYPING & TOKEN STREAMING PULSE
  // --------------------------------------------------------------------------
  function createBatFlapIndicator() {
    const el = document.createElement('div');
    el.className = 'bat-flap-indicator';
    el.innerHTML = `
      <span class="bat-mini-icon">🦇</span>
      <span class="bat-mini-icon">🦇</span>
      <span class="bat-mini-icon">🦇</span>
      <span class="stream-status-label">Analyzing Gotham code matrix...</span>
    `;
    return el;
  }

  function pulseAssistantAvatar(element, active = true) {
    if (!element || typeof gsap === 'undefined' || prefersReducedMotion) return;
    if (active) {
      gsap.to(element, {
        borderColor: '#f5c518',
        boxShadow: '0 0 12px rgba(245, 197, 24, 0.45)',
        duration: 0.6,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut'
      });
    } else {
      gsap.killTweensOf(element);
      gsap.to(element, {
        borderColor: 'var(--border-subtle)',
        boxShadow: 'none',
        duration: 0.3
      });
    }
  }

  // --------------------------------------------------------------------------
  // 5. QUIZ CARDS: 3D TILT & VERIFICATION FEEDBACK
  // --------------------------------------------------------------------------
  function animateQuizCardEnter(cardEl) {
    if (!cardEl || prefersReducedMotion || typeof gsap === 'undefined') return;
    gsap.fromTo(cardEl,
      { opacity: 0, y: 22, rotateX: CONFIG.cardTiltAngle, transformPerspective: 800 },
      { opacity: 1, y: 0, rotateX: 0, duration: 0.45, ease: 'power2.out' }
    );
  }

  function triggerAnswerFeedback(isCorrect) {
    playProceduralSound(isCorrect ? 'correct' : 'wrong');

    if (prefersReducedMotion || typeof gsap === 'undefined') return;

    const quizCard = document.querySelector('.quiz-card');
    if (!quizCard) return;

    if (isCorrect) {
      // Yellow signal flash on correct answer
      gsap.timeline()
        .to(quizCard, {
          borderColor: '#f5c518',
          boxShadow: '0 0 24px rgba(245, 197, 24, 0.55)',
          duration: 0.15
        })
        .to(quizCard, {
          borderColor: 'var(--border-steel)',
          boxShadow: 'none',
          duration: 0.5,
          ease: 'power2.out'
        });
    } else {
      // Screen shake and crimson edge pulse on wrong answer
      gsap.timeline()
        .to(quizCard, {
          x: -CONFIG.shakeIntensity,
          borderColor: '#e11d48',
          boxShadow: '0 0 20px rgba(225, 29, 72, 0.5)',
          duration: 0.06
        })
        .to(quizCard, { x: CONFIG.shakeIntensity, duration: 0.06 })
        .to(quizCard, { x: -CONFIG.shakeIntensity * 0.6, duration: 0.06 })
        .to(quizCard, { x: CONFIG.shakeIntensity * 0.4, duration: 0.06 })
        .to(quizCard, { x: 0, duration: 0.06 })
        .to(quizCard, {
          borderColor: 'var(--border-steel)',
          boxShadow: 'none',
          duration: 0.4
        });
    }
  }

  // --------------------------------------------------------------------------
  // 6. SET COMPLETION: BAT-SWARM FLUTTER & COUNT-UP
  // --------------------------------------------------------------------------
  function triggerBatSwarmCelebration(targetScore = 88) {
    playProceduralSound('signal');

    // Create fluttering bat particles
    const container = document.body;
    const batCount = prefersReducedMotion ? 0 : 28;

    for (let i = 0; i < batCount; i++) {
      const bat = document.createElement('div');
      bat.className = 'gotham-flying-bat';
      bat.textContent = '🦇';
      bat.style.position = 'fixed';
      bat.style.bottom = '-40px';
      bat.style.left = `${Math.random() * 100}vw`;
      bat.style.fontSize = `${Math.random() * 18 + 14}px`;
      bat.style.pointerEvents = 'none';
      bat.style.zIndex = '9999';
      bat.style.opacity = '0.9';
      container.appendChild(bat);

      if (typeof gsap !== 'undefined') {
        const destX = (Math.random() - 0.5) * 200;
        const duration = Math.random() * 1.6 + 1.4;

        gsap.to(bat, {
          y: -window.innerHeight - 80,
          x: `+=${destX}`,
          rotation: (Math.random() - 0.5) * 60,
          scale: Math.random() * 0.6 + 0.8,
          duration: duration,
          ease: 'power1.out',
          delay: Math.random() * 0.4,
          onComplete: () => bat.remove()
        });
      } else {
        setTimeout(() => bat.remove(), 2500);
      }
    }
  }

  // --------------------------------------------------------------------------
  // 7. ROADMAP MASTERY UNLOCK & CONNECTING LINE DRAW
  // --------------------------------------------------------------------------
  function animateMasteryUnlock(nodeEl) {
    if (!nodeEl || prefersReducedMotion || typeof gsap === 'undefined') return;
    playProceduralSound('signal');

    // Lock break pop
    gsap.timeline()
      .to(nodeEl, {
        scale: 1.15,
        borderColor: '#f5c518',
        boxShadow: '0 0 28px rgba(245, 197, 24, 0.65)',
        duration: 0.25,
        ease: 'back.out(2)'
      })
      .to(nodeEl, {
        scale: 1,
        duration: 0.35,
        ease: 'power2.out'
      });
  }

  // --------------------------------------------------------------------------
  // 8. DASHBOARD TELEMETRY ANIMATION (NUMBERS & GAUGES)
  // --------------------------------------------------------------------------
  function animateDashboardNumbers() {
    if (prefersReducedMotion || typeof gsap === 'undefined') return;

    // Animate counters
    const numberIds = ['statMastered', 'statReviewing', 'statLearning', 'statLocked', 'statTokens', 'streakCount'];
    numberIds.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const targetVal = parseInt(el.textContent.replace(/,/g, ''), 10) || 0;
      if (targetVal <= 0) return;

      const obj = { val: 0 };
      gsap.to(obj, {
        val: targetVal,
        duration: 1.2,
        ease: 'power2.out',
        onUpdate: () => {
          el.textContent = Math.round(obj.val).toLocaleString();
        }
      });
    });

    // Animate segmented mastery bar
    const bar = document.getElementById('masterySegmentedBar');
    if (bar) {
      gsap.fromTo(bar.children,
        { scaleX: 0, transformOrigin: 'left center' },
        { scaleX: 1, duration: 0.8, stagger: 0.12, ease: 'power2.out' }
      );
    }
  }

  // --------------------------------------------------------------------------
  // 10. NOTIFICATION BELL SWING
  // --------------------------------------------------------------------------
  function swingNotificationBell(active = true) {
    const bell = document.getElementById('pushNotifBtn');
    if (!bell || prefersReducedMotion || typeof gsap === 'undefined') return;

    if (active) {
      gsap.to(bell, {
        rotation: 14,
        duration: 0.15,
        yoyo: true,
        repeat: 5,
        ease: 'sine.inOut',
        onComplete: () => {
          gsap.set(bell, { rotation: 0 });
        }
      });
    }
  }

  // --------------------------------------------------------------------------
  // 11. STREAK BADGE FLAME-TO-BAT FLICKER
  // --------------------------------------------------------------------------
  function pulseStreakBadge(streakDays) {
    const badge = document.getElementById('streakPill');
    if (!badge || prefersReducedMotion || typeof gsap === 'undefined') return;

    if (streakDays >= 7) {
      // Milestone burst for 7+ or 30+ day detectives
      gsap.timeline()
        .to(badge, {
          scale: 1.25,
          borderColor: '#f5c518',
          boxShadow: '0 0 20px rgba(245, 197, 24, 0.7)',
          duration: 0.25,
          ease: 'back.out(2)'
        })
        .to(badge, {
          scale: 1,
          duration: 0.35,
          ease: 'power2.out'
        });
    }
  }

  // --------------------------------------------------------------------------
  // 12. MODAL DIAGONAL SLASH REVEALS
  // --------------------------------------------------------------------------
  function openModalAnimated(modalEl) {
    if (!modalEl) return;
    playProceduralSound('whoosh');
    modalEl.classList.add('active');

    const content = modalEl.querySelector('.modal-content');
    if (content && typeof gsap !== 'undefined' && !prefersReducedMotion) {
      gsap.fromTo(content,
        {
          opacity: 0,
          scale: 0.94,
          clipPath: 'polygon(0 0, 100% 0, 100% 0, 0 0)'
        },
        {
          opacity: 1,
          scale: 1,
          clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 100%)',
          duration: 0.35,
          ease: 'power3.out'
        }
      );
    }
  }

  function closeModalAnimated(modalEl, callback) {
    if (!modalEl) return;
    const content = modalEl.querySelector('.modal-content');

    if (content && typeof gsap !== 'undefined' && !prefersReducedMotion) {
      gsap.to(content, {
        opacity: 0,
        scale: 0.95,
        duration: 0.2,
        ease: 'power2.in',
        onComplete: () => {
          modalEl.classList.remove('active');
          if (callback) callback();
        }
      });
    } else {
      modalEl.classList.remove('active');
      if (callback) callback();
    }
  }

  // --------------------------------------------------------------------------
  // 13. PARALLAX SKYLINE & RARE LIGHTNING FLASH (< 3/sec Photosensitivity Safe)
  // --------------------------------------------------------------------------
  let lightningTimer = null;

  function initAmbientGothamAtmosphere() {
    if (prefersReducedMotion) return;

    // Subtle mousemove parallax on background skyline layers
    const skylineLayerBack = document.querySelector('.skyline-layer-back');
    const skylineLayerMid = document.querySelector('.skyline-layer-mid');

    window.addEventListener('mousemove', (e) => {
      const normX = (e.clientX / window.innerWidth - 0.5) * 2;
      const normY = (e.clientY / window.innerHeight - 0.5) * 2;

      if (skylineLayerBack) {
        skylineLayerBack.style.transform = `translate3d(${normX * 8}px, ${normY * 4}px, 0)`;
      }
      if (skylineLayerMid) {
        skylineLayerMid.style.transform = `translate3d(${normX * 16}px, ${normY * 8}px, 0)`;
      }
    }, { passive: true });

    // Rare, soft ambient lightning (strictly throttled to max 1 flash every 25s)
    scheduleNextLightning();

    // Pause when tab hidden to conserve CPU/GPU
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        clearTimeout(lightningTimer);
      } else {
        scheduleNextLightning();
      }
    });
  }

  function scheduleNextLightning() {
    clearTimeout(lightningTimer);
    if (prefersReducedMotion) return;

    // Random interval between 20 to 45 seconds
    const intervalMs = Math.random() * 25000 + 20000;
    lightningTimer = setTimeout(triggerSoftLightning, intervalMs);
  }

  function triggerSoftLightning() {
    if (document.hidden || prefersReducedMotion) return;

    const flashOverlay = document.getElementById('gothamLightningFlash');
    if (!flashOverlay || typeof gsap === 'undefined') return;

    // A single, soft atmospheric flash (opacity <= 0.18, lasting only 120ms total)
    // Strictly prevents photosensitive triggers (never > 3 flashes per second)
    const tl = gsap.timeline({
      onComplete: scheduleNextLightning
    });

    tl.to(flashOverlay, { opacity: 0.16, duration: 0.05, ease: 'power1.in' })
      .to(flashOverlay, { opacity: 0.04, duration: 0.04 })
      .to(flashOverlay, { opacity: 0.12, duration: 0.03 })
      .to(flashOverlay, { opacity: 0, duration: 0.15, ease: 'power2.out' });
  }

  // --------------------------------------------------------------------------
  // INITIALIZATION ON DOM READY
  // --------------------------------------------------------------------------
  function init() {
    initIntroLoader();
    initAmbientGothamAtmosphere();
    updateSoundButtonUI(isSoundEnabled());

    const soundBtn = document.getElementById('soundToggleBtn');
    if (soundBtn) {
      soundBtn.addEventListener('click', toggleSound);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API
  return {
    transitionToView,
    animateChatMessage,
    createBatFlapIndicator,
    pulseAssistantAvatar,
    animateQuizCardEnter,
    triggerAnswerFeedback,
    triggerBatSwarmCelebration,
    animateMasteryUnlock,
    animateDashboardNumbers,
    swingNotificationBell,
    pulseStreakBadge,
    openModalAnimated,
    closeModalAnimated,
    toggleSound,
    isSoundEnabled,
    playProceduralSound
  };
})();
