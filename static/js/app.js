/**
 * THE IRON THRONE RPG — TELEGRAM MINI APP CLIENT
 * Mobile-first, Telegram WebApp SDK, Westeros theme
 * Includes Feature 1: Daily Streak & Activity Quests claiming with Double-Click Protection
 */

(function () {
  'use strict';

  // 1. Telegram WebApp SDK init
  const tg = window.Telegram?.WebApp;
  let currentInitData = tg?.initData || '';
  let activeTab = 'tab-profile';
  let activeRankingCategory = 'wealth';
  let cachedDashboardData = null;

  // Initialize Telegram viewport & settings
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      tg.enableClosingConfirmation?.();
      
      // Sync theme header color
      if (tg.setHeaderColor) {
        tg.setHeaderColor('#0b0e14');
      }
      if (tg.setBackgroundColor) {
        tg.setBackgroundColor('#0b0e14');
      }

      // BackButton handler
      tg.BackButton?.onClick(() => {
        haptic('light');
        if (activeModal) {
          hideModal(activeModal);
        } else {
          switchTab('tab-profile');
        }
      });
    } catch (e) {
      console.warn('Telegram WebApp setup error:', e);
    }
  }

  let activeModal = null;

  function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.style.display = 'flex';
    activeModal = modalId;
    haptic('medium');
    if (tg?.BackButton) {
      tg.BackButton.show();
    }
  }

  function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
    if (activeModal === modalId) {
      activeModal = null;
      if (tg?.BackButton) {
        if (activeTab === 'tab-profile') {
          tg.BackButton.hide();
        } else {
          tg.BackButton.show();
        }
      }
    }
  }

  // Trigger haptics safely
  function haptic(type = 'light') {
    try {
      if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred(type);
      }
    } catch (e) {}
  }

  // Number format with commas (e.g. 10,000)
  function formatNum(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('uz-UZ');
  }

  // Escape HTML to prevent XSS
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Visual Asset Manager & Graphics Quality Controller
  const AssetManager = {
    quality: localStorage.getItem('it_graphics_quality') || 'high',

    init() {
      this.applyQuality(this.quality);
      const btn = document.getElementById('btn-toggle-graphics');
      if (btn) {
        btn.addEventListener('click', () => {
          haptic('light');
          this.toggleQuality();
        });
      }
    },

    applyQuality(q) {
      this.quality = q;
      localStorage.setItem('it_graphics_quality', q);
      const btn = document.getElementById('btn-toggle-graphics');
      if (q === 'low') {
        document.body.classList.add('low-graphics');
        if (btn) btn.textContent = '⚡ Tejamkor';
      } else {
        document.body.classList.remove('low-graphics');
        if (btn) btn.textContent = '💎 Yuqori Grafika';
      }
    },

    toggleQuality() {
      const next = this.quality === 'high' ? 'low' : 'high';
      this.applyQuality(next);
      showToast(next === 'low' ? '⚡ Tejamkor grafika rejimi faollashdi' : '💎 Yuqori grafika rejimi faollashdi', 'info');
      return next;
    },

    getUnitIcon(key) {
      const map = {
        infantry: 'assets/units/unit-infantry.svg',
        archers: 'assets/units/unit-archers.svg',
        cavalry: 'assets/units/unit-cavalry.svg',
        spearmen: 'assets/units/unit-spearmen.svg',
        catapults: 'assets/units/unit-catapult.svg',
        siege_towers: 'assets/units/unit-catapult.svg',
        special_troops: 'assets/units/unit-wildfire.svg',
        wildfire: 'assets/units/unit-wildfire.svg'
      };
      return map[key] || 'assets/ui/placeholder.svg';
    },

    getCastleIcon(level = 1, skin = null) {
      if (skin === 'castle_ice') return 'assets/castles/castle-ice.svg';
      if (skin === 'castle_valyrian') return 'assets/castles/castle-valyrian.svg';
      if (skin === 'castle_golden') return 'assets/castles/castle-golden.svg';
      if (level >= 3) return 'assets/castles/castle-tier3.svg';
      if (level >= 2) return 'assets/castles/castle-tier2.svg';
      return 'assets/castles/castle-tier1.svg';
    },

    getDragonPortrait(stage = 'adult', skin = null) {
      if (stage === 'egg') return 'assets/dragons/dragon-egg.svg';
      if (stage === 'baby' || stage === 'hatchling') return 'assets/dragons/dragon-baby.svg';
      if (stage === 'young') return 'assets/dragons/dragon-young.svg';
      if (skin === 'dragon_crimson') return 'assets/dragons/dragon-adult-crimson.svg';
      if (skin === 'dragon_emerald') return 'assets/dragons/dragon-adult-emerald.svg';
      if (skin === 'dragon_golden') return 'assets/dragons/dragon-adult-golden.svg';
      return 'assets/dragons/dragon-adult.svg';
    },

    getHeroPortrait(type = 'lord') {
      if (type === 'maester') return 'assets/heroes/hero-maester.svg';
      if (type === 'spy') return 'assets/heroes/hero-spy.svg';
      return 'assets/heroes/hero-lord.svg';
    }
  };

  // Battle clash cinematic overlay animation
  function playBattleClashAnimation(title = 'JANG KETMOQDA...', subtitle = 'Qilichlar jaranglamoqda!', durationMs = 1200) {
    return new Promise(resolve => {
      const overlay = document.getElementById('battle-clash-overlay');
      if (!overlay || document.body.classList.contains('low-graphics')) {
        haptic('heavy');
        resolve();
        return;
      }
      const titleEl = document.getElementById('battle-clash-title');
      const subEl = document.getElementById('battle-clash-subtitle');
      if (titleEl) titleEl.textContent = title;
      if (subEl) subEl.textContent = subtitle;
      overlay.style.display = 'flex';
      haptic('heavy');

      setTimeout(() => {
        overlay.style.display = 'none';
        resolve();
      }, durationMs);
    });
  }

  // Toast notification utility
  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // 2. Tab Navigation
  function switchTab(tabId) {
    activeTab = tabId;

    // Update bottom nav active state
    document.querySelectorAll('.bottom-nav .nav-item').forEach(btn => {
      if (btn.getAttribute('data-tab') === tabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Update view panels
    document.querySelectorAll('.view-panel').forEach(panel => {
      panel.classList.remove('active');
    });
    const targetPanel = document.getElementById(tabId);
    if (targetPanel) {
      targetPanel.classList.add('active');
    }

    // Manage Telegram BackButton
    if (tg?.BackButton) {
      if (tabId === 'tab-profile') {
        tg.BackButton.hide();
      } else {
        tg.BackButton.show();
      }
    }

    // Scroll to top of viewport
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // 3. Data Fetching
  async function fetchDashboard() {
    showLoading(true);
    hideError();

    // Prepare auth header
    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const response = await fetch('/api/player/dashboard', {
        method: 'GET',
        headers: headers,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errDetail = typeof errorData.detail === 'string' ? errorData.detail : (errorData.error || `Server xatosi: ${response.status}`);
        throw new Error(errDetail);
      }

      const res = await response.json();
      if (!res.success) {
        throw new Error('Serverdan noto‘g‘ri ma‘lumot qaytdi.');
      }

      if (res.is_registered === false) {
        showLoading(false);
        renderOnboarding(res.available_houses || []);
        return;
      }

      if (!res.data) {
        throw new Error('Serverdan noto‘g‘ri ma‘lumot qaytdi.');
      }

      // Hide onboarding and restore bottom navigation
      const onbView = document.getElementById('view-onboarding');
      if (onbView) onbView.style.display = 'none';
      const bNav = document.querySelector('.bottom-nav');
      if (bNav) bNav.style.display = 'flex';

      // Admin button check
      const adminBtn = document.getElementById('btn-open-admin');
      if (adminBtn) {
        adminBtn.style.display = res.is_admin ? 'flex' : 'none';
      }

      cachedDashboardData = res.data;
      renderAll(res.data);
      showLoading(false);
    } catch (err) {
      console.error('Fetch dashboard error:', err);
      showLoading(false);
      showError('Bog‘lanishda uzilish', err.message || 'Server bilan aloqa o‘rnatib bo‘lmadi.');
    }
  }

  // 4. Render All Views
  function renderAll(data) {
    renderHeaderAndProfile(data.profile, data);
    renderDaily(data.daily);
    renderArmy(data.army);
    renderCastles(data.castles);
    renderRankings(data.rankings);
    renderWorld(data.world);
  }

  // Render Header & Profile Tab
  function renderHeaderAndProfile(prof, fullData) {
    if (!prof) return;

    // Header Brief
    const house = prof.house || {};
    document.getElementById('hdr-house-emoji').textContent = house.emoji || '🛡️';
    document.getElementById('hdr-hero-name').textContent = prof.hero_name || prof.full_name || 'Lord';
    document.getElementById('hdr-house-name').textContent = house.name || 'Mustaqil Xonadon';

    // VIP Badge
    const vipEl = document.getElementById('hdr-vip-badge');
    if (prof.vip_tier) {
      vipEl.textContent = prof.vip_tier.toUpperCase();
      vipEl.style.display = 'inline-block';
    } else {
      vipEl.style.display = 'none';
    }

    // Sticky Resources Bar
    document.getElementById('res-gold').textContent = formatNum(prof.gold);
    document.getElementById('res-food').textContent = formatNum(prof.food);
    document.getElementById('res-iron').textContent = formatNum(prof.iron);
    document.getElementById('res-prestige').textContent = formatNum(prof.prestige);

    // Profile Card: Level & XP
    document.getElementById('prof-level').textContent = `${prof.level || 1}-Daraja`;
    document.getElementById('prof-level-title').textContent = prof.level_title || 'Lord';
    const xpPct = prof.xp_progress_pct || 0;
    document.getElementById('prof-xp-fill').style.width = `${Math.min(100, Math.max(0, xpPct))}%`;
    document.getElementById('prof-xp-text').textContent = `${formatNum(prof.xp)} / ${formatNum(prof.xp_next_req)} (${xpPct}%)`;

    // Combat Stats
    document.getElementById('prof-atk').textContent = formatNum(prof.hero_attack || 50);
    document.getElementById('prof-def').textContent = formatNum(prof.hero_defense || 50);
    const armyTotal = prof.army?.total_troops || prof.army?.total || fullData?.army?.troops?.total || 0;
    document.getElementById('prof-army-total').textContent = formatNum(armyTotal);

    // Castles Count in Profile Card
    const castlesCount = fullData?.castles?.total_castles ?? (fullData?.castles?.castles ? fullData.castles.castles.length : 0);
    const castlesEl = document.getElementById('prof-castles-count');
    if (castlesEl) castlesEl.textContent = formatNum(castlesCount);

    // Household Info
    document.getElementById('prof-title').textContent = prof.title || 'Faxriy unvon berilmagan';
    document.getElementById('prof-status').textContent = prof.custom_status ? `"${prof.custom_status}"` : 'Status o‘rnatilmagan';
    
    // Shield
    const shieldEl = document.getElementById('prof-shield');
    const isShieldActive = prof.peace_shield?.is_active || prof.peace_shield?.active || false;
    const hoursLeft = prof.peace_shield?.hours_left ?? Math.ceil((prof.peace_shield?.remaining_seconds || 0) / 3600);
    if (isShieldActive) {
      shieldEl.textContent = `Faol (${hoursLeft} soat)`;
      shieldEl.className = 'info-val text-green';
    } else {
      shieldEl.textContent = 'Faol emas';
      shieldEl.className = 'info-val text-secondary';
    }

    // Guild
    const guildEl = document.getElementById('prof-guild');
    const g = prof.guild;
    if (g && (g.name || g.tag || g.in_guild)) {
      guildEl.textContent = `${g.tag ? g.tag + ' ' : ''}${g.name || 'Gildiya'}`;
    } else {
      guildEl.textContent = 'Gildiyada emas';
    }

    // Income
    const hourlyGold = prof.income_hourly?.gold ?? prof.income_hourly?.total_gold_per_hour ?? 0;
    document.getElementById('prof-hourly-income').textContent = `+${formatNum(hourlyGold)}🪙 / soat`;

    // AI Advisor status refresh
    loadAiAdvisorStatus();
  }

  // Render Daily Streak & Quests (Feature 1)
  function renderDaily(daily) {
    if (!daily) return;

    const streak = daily.streak || {};
    const isClaimed = streak.is_claimed_today;
    const currentDay = streak.current_day || 1;
    const btnStreak = document.getElementById('btn-claim-streak');
    const subtitle = document.getElementById('daily-streak-subtitle');

    if (isClaimed) {
      btnStreak.textContent = '✅ Olingan';
      btnStreak.disabled = true;
      btnStreak.classList.remove('ready');
      subtitle.textContent = `${currentDay}-kun tuhfasi olindi!`;
    } else {
      btnStreak.textContent = '🎁 Olish';
      btnStreak.disabled = false;
      btnStreak.classList.add('ready');
      subtitle.textContent = `Bugungi ${currentDay}-kun tuhfasi tayyor!`;
    }

    // Render 7 days chips
    const streakContainer = document.getElementById('streak-days-container');
    streakContainer.innerHTML = '';
    const calendar = streak.calendar || [];
    calendar.forEach(c => {
      const chip = document.createElement('div');
      chip.className = 'streak-day-chip';
      if (c.is_current) chip.classList.add('active-day');
      if (c.is_completed) chip.classList.add('completed');

      const checkIcon = c.is_completed ? '✓' : '';
      chip.innerHTML = `
        <div class="streak-day-num">${c.day}-K ${checkIcon}</div>
        <div class="streak-day-val">+${c.gold}🪙</div>
      `;
      streakContainer.appendChild(chip);
    });

    // Render Quests
    const questsContainer = document.getElementById('daily-quests-container');
    questsContainer.innerHTML = '';
    const quests = daily.daily_quests || {};
    const doneCount = daily.done_quests_count || 0;
    const totalCount = daily.total_quests_count || 4;
    document.getElementById('quests-progress-badge').textContent = `${doneCount} / ${totalCount}`;

    Object.entries(quests).forEach(([qKey, qInfo]) => {
      const row = document.createElement('div');
      row.className = 'quest-item-row';
      const isDone = qInfo.is_done;
      const isClaimed = qInfo.is_claimed;
      let actionBtn = '';

      if (isClaimed) {
        actionBtn = '<span style="font-size:11px; color:var(--color-green);">✅ Olingan</span>';
      } else if (isDone) {
        actionBtn = `<button class="btn btn-claim quest-btn-claim ready" data-quest="${escapeHtml(qKey)}">Olish (+${qInfo.reward_gold}🪙)</button>`;
      } else {
        actionBtn = `<span style="font-size:11px; color:var(--text-muted);">${qInfo.progress || 0}/${qInfo.target || 1}</span>`;
      }

      row.innerHTML = `
        <div class="quest-item-left">
          <span>${qInfo.emoji || '📜'}</span>
          <div>
            <div class="quest-item-title">${escapeHtml(qInfo.title || qKey)}</div>
            <div class="quest-item-desc">${escapeHtml(qInfo.desc || '')}</div>
          </div>
        </div>
        <div>${actionBtn}</div>
      `;
      questsContainer.appendChild(row);
    });

    // Attach event listeners to quest claim buttons
    questsContainer.querySelectorAll('.quest-btn-claim').forEach(qBtn => {
      qBtn.addEventListener('click', async () => {
        const questKey = qBtn.getAttribute('data-quest');
        await handleClaimQuest(questKey, qBtn);
      });
    });
  }

  // Claim Daily Streak Action (Atomic, Server-Side, Double-Click Protected)
  async function handleClaimStreak() {
    const btn = document.getElementById('btn-claim-streak');
    btn.disabled = true;
    btn.textContent = 'Qabul qilinmoqda...';
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/daily/claim-streak', {
        method: 'POST',
        headers: headers,
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Tuhfani qabul qilishda xatolik.');
      }

      showToast(res.message || '🎉 Kunlik tuhfa qabul qilindi!', 'success');
      haptic('success');
      await fetchDashboard();
    } catch (err) {
      console.error('Claim streak error:', err);
      showToast(err.message, 'error');
      haptic('error');
      btn.disabled = false;
      btn.textContent = '🎁 Olish';
    }
  }

  // Claim Daily Quest Action
  async function handleClaimQuest(questKey, buttonEl) {
    if (buttonEl) {
      buttonEl.disabled = true;
      buttonEl.textContent = '...';
    }
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/daily/claim-quest', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ quest_key: questKey }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Mukofotni olishda xatolik.');
      }

      showToast(res.message || '🎉 Vazifa mukofoti qabul qilindi!', 'success');
      haptic('success');
      await fetchDashboard();
    } catch (err) {
      console.error('Claim quest error:', err);
      showToast(err.message, 'error');
      haptic('error');
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.textContent = 'Olish';
      }
    }
  }

  // ============================================================
  // FEATURE 2: TROOP RECRUITMENT MODAL & LOGIC
  // ============================================================

  let currentRecruitUnit = null;

  function openRecruitModal(unitInfo) {
    currentRecruitUnit = unitInfo;
    const modal = document.getElementById('recruit-modal');
    if (!modal) return;

    document.getElementById('modal-unit-icon').textContent = unitInfo.icon;
    document.getElementById('modal-unit-name').textContent = unitInfo.name;
    document.getElementById('modal-unit-stats').textContent = `⚔️ Atk: ${unitInfo.attack} | 🛡️ Def: ${unitInfo.defense} | 🌾 -${unitInfo.upkeep}/s`;
    document.getElementById('modal-unit-price').textContent = `${unitInfo.goldCost}🪙 Oltin, ${unitInfo.ironCost}⛓️ Temir`;
    
    document.getElementById('recruit-amount-input').value = 10;
    updateRecruitCostPreview();

    modal.style.display = 'flex';
  }

  function closeRecruitModal() {
    const modal = document.getElementById('recruit-modal');
    if (modal) modal.style.display = 'none';
    currentRecruitUnit = null;
  }

  function updateRecruitCostPreview() {
    if (!currentRecruitUnit) return;
    const input = document.getElementById('recruit-amount-input');
    let amount = parseInt(input.value) || 0;
    if (amount < 1) amount = 1;
    input.value = amount;

    const totalGold = amount * currentRecruitUnit.goldCost;
    const totalIron = amount * currentRecruitUnit.ironCost;

    document.getElementById('modal-cost-gold').textContent = `${formatNum(totalGold)}🪙`;
    document.getElementById('modal-cost-iron').textContent = `${formatNum(totalIron)}⛓️`;

    // Visual balance check
    const myGold = cachedDashboardData?.profile?.gold || 0;
    const myIron = cachedDashboardData?.profile?.iron || 0;

    const goldEl = document.getElementById('modal-cost-gold');
    const ironEl = document.getElementById('modal-cost-iron');
    const btn = document.getElementById('btn-confirm-recruit');

    if (totalGold > myGold) {
      goldEl.style.color = 'var(--color-red)';
    } else {
      goldEl.style.color = 'var(--gold-primary)';
    }

    if (totalIron > myIron) {
      ironEl.style.color = 'var(--color-red)';
    } else {
      ironEl.style.color = 'var(--text-secondary)';
    }

    if (totalGold > myGold || totalIron > myIron) {
      btn.disabled = true;
      btn.textContent = '❌ Resurslar Yetarli Emas';
    } else {
      btn.disabled = false;
      btn.textContent = '⚔️ Safga Yollash';
    }
  }

  async function handleConfirmRecruit() {
    if (!currentRecruitUnit) return;
    const input = document.getElementById('recruit-amount-input');
    const amount = parseInt(input.value) || 0;
    if (amount <= 0) return;

    const btn = document.getElementById('btn-confirm-recruit');
    btn.disabled = true;
    btn.textContent = 'Yollanmoqda...';
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/military/recruit', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          unit_type: currentRecruitUnit.key,
          amount: amount
        })
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Qo‘shin yollashda xatolik.');
      }

      closeRecruitModal();
      showToast(res.message || '✅ Safarbarlik muvaffaqiyatli yakunlandi!', 'success');
      haptic('success');
      await fetchDashboard();
    } catch (err) {
      console.error('Recruit error:', err);
      showToast(err.message, 'error');
      haptic('error');
      btn.disabled = false;
      btn.textContent = '⚔️ Safga Yollash';
    }
  }

  // Render Army Tab
  function renderArmy(army) {
    if (!army) return;

    const troops = army.troops || {};
    const configs = army.units_config || {};
    const totalArmy = troops.total || troops.total_troops || 0;
    document.getElementById('army-total-sum').textContent = `${formatNum(totalArmy)} Askar`;

    const unitsContainer = document.getElementById('army-units-container');
    unitsContainer.innerHTML = '';

    const unitTypes = [
      { key: 'infantry', name: 'Piyodalar', icon: '🛡️' },
      { key: 'archers', name: 'Kamonchilar', icon: '🏹' },
      { key: 'cavalry', name: 'Otliq Qo‘shin', icon: '🐎' },
      { key: 'spearmen', name: 'Nayzachilar', icon: '🗡️' },
      { key: 'special_troops', name: 'Maxsus Qo‘shin', icon: '🔥' },
    ];

    unitTypes.forEach(u => {
      const count = troops[u.key] || 0;
      const cfg = configs[u.key] || { attack: 1, defense: 1, food_upkeep: 0.5, gold_cost: 2, iron_cost: 1 };
      const unitImg = AssetManager.getUnitIcon(u.key);
      const card = document.createElement('div');
      card.className = 'unit-card';
      card.innerHTML = `
        <div class="unit-left">
          <div class="unit-icon-wrapper">
            <img src="${unitImg}" class="unit-icon-img" alt="${escapeHtml(u.name)}" loading="lazy" onerror="this.src='assets/ui/placeholder.svg';">
          </div>
          <div>
            <div class="unit-name">${escapeHtml(cfg.name || u.name)}</div>
            <div class="unit-sub">⚔️ Atk: ${cfg.attack} | 🛡️ Def: ${cfg.defense} | 🌾 -${cfg.food_upkeep}/s</div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <div class="unit-count">${formatNum(count)}</div>
          <button class="btn-recruit-open" data-key="${u.key}" data-name="${escapeHtml(cfg.name || u.name)}" data-icon="${u.icon}" data-gcost="${cfg.gold_cost}" data-icost="${cfg.iron_cost}" data-atk="${cfg.attack}" data-def="${cfg.defense}" data-upkeep="${cfg.food_upkeep}">+ Yollash</button>
        </div>
      `;
      unitsContainer.appendChild(card);
    });

    // Attach click listeners to + Yollash buttons
    unitsContainer.querySelectorAll('.btn-recruit-open').forEach(btn => {
      btn.addEventListener('click', () => {
        haptic('light');
        openRecruitModal({
          key: btn.getAttribute('data-key'),
          name: btn.getAttribute('data-name'),
          icon: btn.getAttribute('data-icon'),
          goldCost: Number(btn.getAttribute('data-gcost')),
          ironCost: Number(btn.getAttribute('data-icost')),
          attack: btn.getAttribute('data-atk'),
          defense: btn.getAttribute('data-def'),
          upkeep: btn.getAttribute('data-upkeep'),
        });
      });
    });

    const siegeContainer = document.getElementById('army-siege-container');
    siegeContainer.innerHTML = '';
    const siege = army.siege_weapons || {};
    const siegeTypes = [
      { key: 'catapults', name: 'Katapultalar', icon: '☄️', maxKey: 'max_catapults' },
      { key: 'siege_towers', name: 'Qamal Minoralari', icon: '🗼', maxKey: 'max_siege_towers' },
      { key: 'wildfire', name: 'Yovvoyi Olov (Wildfire)', icon: '🟢', maxKey: 'max_wildfire' },
    ];

    siegeTypes.forEach(s => {
      const count = siege[s.key] || 0;
      const max = siege[s.maxKey] || 10;
      const siegeImg = AssetManager.getUnitIcon(s.key);
      const card = document.createElement('div');
      card.className = 'unit-card';
      card.innerHTML = `
        <div class="unit-left">
          <div class="unit-icon-wrapper">
            <img src="${siegeImg}" class="unit-icon-img" alt="${escapeHtml(s.name)}" loading="lazy" onerror="this.src='assets/ui/placeholder.svg';">
          </div>
          <div>
            <div class="unit-name">${s.name}</div>
            <div class="unit-sub">Qal'a devorlarini yorish quroli</div>
          </div>
        </div>
        <div class="unit-count">${count} / ${max}</div>
      `;
      siegeContainer.appendChild(card);
    });
  }

  // Render Castles Tab (Feature 3)
  function renderCastles(castlesData) {
    if (!castlesData) return;

    const total = castlesData.total_castles || 0;
    const claimableGold = typeof castlesData.total_claimable === 'object'
      ? (castlesData.total_claimable.gold || 0)
      : (castlesData.total_claimable || 0);
    const readyCount = castlesData.ready_castles_count || 0;

    document.getElementById('castles-total-sum').textContent = `${total} ta Qal'a`;
    document.getElementById('castles-accum-sum').textContent = `+${formatNum(claimableGold)}🪙`;
    document.getElementById('prof-castles-count').textContent = total;

    // Collect All Button
    const btnCollectAll = document.getElementById('btn-collect-all-tax');
    if (btnCollectAll) {
      if (readyCount > 0 && claimableGold > 0) {
        btnCollectAll.disabled = false;
        btnCollectAll.classList.add('ready');
        btnCollectAll.textContent = `💰 Barchasidan O'lpon Yig'ish (${readyCount} ta qal'a, +${formatNum(claimableGold)}🪙)`;
      } else {
        btnCollectAll.disabled = true;
        btnCollectAll.classList.remove('ready');
        btnCollectAll.textContent = `⏳ O'lpon to'planmoqda (Hozircha tayyor emas)`;
      }
    }

    const container = document.getElementById('castles-container');
    container.innerHTML = '';

    const list = castlesData.castles || [];
    if (list.length === 0) {
      container.innerHTML = `
        <div class="card text-center" style="padding: 24px;">
          <p style="color: var(--text-secondary);">Sizda hozircha qal'alar mavjud emas.<br>Xaritadan qal'alarni zabt eting!</p>
        </div>
      `;
      return;
    }

    list.forEach(c => {
      const card = document.createElement('div');
      card.className = 'castle-card castle-card-enhanced';
      const taxInfo = c.tax || {};
      const isReady = taxInfo.is_ready || c.is_ready_to_claim;
      const hours = taxInfo.hours_ready || c.hours_accumulated || 0;
      const accumGold = taxInfo.accumulated_gold || c.accumulated_gold || 0;
      const remMin = taxInfo.rem_minutes !== undefined ? taxInfo.rem_minutes : (c.minutes_remaining || 0);

      const actionElement = isReady
        ? `<button class="btn-tax-claim" data-id="${c.id}">💰 Olish (+${formatNum(accumGold)}🪙)</button>`
        : `<span class="castle-tax-badge castle-tax-wait">⏳ ~${remMin} daq</span>`;

      const castleImg = AssetManager.getCastleIcon(c.level || 1, c.skin);
      card.innerHTML = `
        <div class="castle-left">
          <div class="castle-visual-box">
            <img src="${castleImg}" class="castle-visual-img" alt="${escapeHtml(c.name || 'Qal‘a')}" loading="lazy" onerror="this.src='assets/ui/placeholder.svg';">
          </div>
          <div>
            <div class="castle-name">${escapeHtml(c.name || c.castle_name)} <span class="castle-level-badge">${c.level || 1}-Daraja</span></div>
            <div class="castle-sub">📍 ${escapeHtml(c.region || 'Vesteros')} | 🛡️ Def: ${c.defense || c.defense_power || 0} | ${hours}s to'plangan</div>
          </div>
        </div>
        <div>${actionElement}</div>
      `;
      container.appendChild(card);
    });

    // Attach click listeners to individual claim buttons
    container.querySelectorAll('.btn-tax-claim').forEach(btn => {
      btn.addEventListener('click', async () => {
        const castleId = parseInt(btn.getAttribute('data-id'));
        await handleCollectSingleTax(castleId, btn);
      });
    });
  }

  // Collect tax from single castle
  async function handleCollectSingleTax(castleId, buttonEl) {
    if (!castleId) return;
    if (buttonEl) {
      buttonEl.disabled = true;
      buttonEl.textContent = 'Olinmoqda...';
    }
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/castles/collect-tax', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ territory_id: castleId }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'O‘lpon yig‘ishda xatolik.');
      }

      showToast(res.message || '✅ O‘lpon muvaffaqiyatli yig‘ildi!', 'success');
      haptic('success');
      await fetchDashboard();
    } catch (err) {
      console.error('Collect tax error:', err);
      showToast(err.message, 'error');
      haptic('error');
      if (buttonEl) {
        buttonEl.disabled = false;
        buttonEl.textContent = 'Qayta urinish';
      }
    }
  }

  // Collect tax from ALL castles at once
  async function handleCollectAllTaxes() {
    const btn = document.getElementById('btn-collect-all-tax');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Yig‘ilmoqda...';
    }
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/castles/collect-all-tax', {
        method: 'POST',
        headers: headers,
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Barcha o‘lponlarni yig‘ishda xatolik.');
      }

      showToast(res.message || '✅ Barcha qal‘alardan o‘lponlar olindi!', 'success');
      haptic('success');
      await fetchDashboard();
    } catch (err) {
      console.error('Collect all taxes error:', err);
      showToast(err.message, 'error');
      haptic('error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Qayta urinish';
      }
    }
  }

  // ============================================================
  // FEATURE 4: CITADEL QUIZ & ROYAL COUNCIL QUESTS
  // ============================================================

  let currentQuizData = null;
  let currentCouncilData = null;

  async function openCitadelQuizModal() {
    const modal = document.getElementById('quiz-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    haptic('medium');

    document.getElementById('quiz-outcome-card').style.display = 'none';
    document.getElementById('btn-quiz-next').style.display = 'none';
    document.getElementById('quiz-question-text').textContent = 'Saboq savoli yuklanmoqda...';
    document.getElementById('quiz-options-container').innerHTML = '<div class="text-center py-3 text-secondary">Yuklanmoqda...</div>';

    await loadNextQuizQuestion();
  }

  function closeCitadelQuizModal() {
    const modal = document.getElementById('quiz-modal');
    if (modal) modal.style.display = 'none';
    currentQuizData = null;
  }

  async function loadNextQuizQuestion() {
    document.getElementById('quiz-outcome-card').style.display = 'none';
    document.getElementById('btn-quiz-next').style.display = 'none';

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/quests/citadel-quiz', {
        method: 'GET',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Savolni yuklashda xatolik.');
      }

      currentQuizData = res.quiz;
      document.getElementById('quiz-attempts-badge').textContent = `Urinishlar: ${currentQuizData.attempts_remaining} / ${currentQuizData.daily_limit}`;
      document.getElementById('quiz-question-text').textContent = currentQuizData.question;

      const optContainer = document.getElementById('quiz-options-container');
      optContainer.innerHTML = '';

      currentQuizData.options.forEach((optText, idx) => {
        const btn = document.createElement('button');
        btn.className = 'quiz-opt-btn';
        const letters = ['A', 'B', 'C', 'D'];
        btn.innerHTML = `<span style="color:var(--gold-primary); font-family:var(--font-serif); font-weight:700;">${letters[idx] || idx+1}.</span> <span>${escapeHtml(optText)}</span>`;
        btn.addEventListener('click', () => handleQuizAnswerSubmit(idx, btn));
        optContainer.appendChild(btn);
      });
    } catch (err) {
      document.getElementById('quiz-question-text').textContent = err.message;
      document.getElementById('quiz-options-container').innerHTML = '';
      showToast(err.message, 'info');
    }
  }

  async function handleQuizAnswerSubmit(selectedIdx, clickedBtn) {
    if (!currentQuizData) return;
    haptic('medium');

    const optButtons = document.querySelectorAll('#quiz-options-container .quiz-opt-btn');
    optButtons.forEach(b => b.disabled = true);

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/quests/citadel-quiz/answer', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          question_id: currentQuizData.question_id,
          user_answer: selectedIdx
        })
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Javobni tekshirishda xatolik.');
      }

      const outcome = res.data;
      const outcomeCard = document.getElementById('quiz-outcome-card');
      const titleEl = document.getElementById('quiz-outcome-title');
      const descEl = document.getElementById('quiz-outcome-desc');
      const nextBtn = document.getElementById('btn-quiz-next');

      if (outcome.is_correct) {
        haptic('success');
        clickedBtn.classList.add('is-correct');
        outcomeCard.className = 'quiz-outcome-card success mt-3';
        titleEl.textContent = '✅ TO‘G‘RI JAVOB!';
        descEl.innerHTML = `Maesterlar bilimingizni tan olishdi.<br><strong class="text-gold">+${outcome.gold_change}🪙 Oltin, +${outcome.iron_change}⛓️ Temir, +${outcome.xp_change} XP</strong>`;
      } else {
        haptic('error');
        clickedBtn.classList.add('is-wrong');
        if (optButtons[outcome.correct_option_index]) {
          optButtons[outcome.correct_option_index].classList.add('is-correct');
        }
        outcomeCard.className = 'quiz-outcome-card danger mt-3';
        titleEl.textContent = '❌ NOTO‘G‘RI JAVOB!';
        descEl.innerHTML = `To‘g‘ri javob: <strong>${escapeHtml(outcome.correct_option_text)}</strong><br><span style="color:#e63946;">Jarima: ${outcome.gold_change}🪙 oltin</span>`;
      }

      if (outcome.completed_all_daily) {
        descEl.innerHTML += `<br><br>🎉 <strong>Barcha Maester saboqlari bajarildi! Katta bonus berildi!</strong>`;
      }

      outcomeCard.style.display = 'block';

      if (outcome.attempts_remaining > 0) {
        nextBtn.textContent = 'Keyingi Savol ➔';
        nextBtn.onclick = loadNextQuizQuestion;
      } else {
        nextBtn.textContent = 'Tugatish (Bosh Menyu)';
        nextBtn.onclick = closeCitadelQuizModal;
      }
      nextBtn.style.display = 'block';

      document.getElementById('quiz-attempts-badge').textContent = `Urinishlar: ${outcome.attempts_remaining} / 5`;
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
      optButtons.forEach(b => b.disabled = false);
    }
  }

  // --- ROYAL COUNCIL FUNCTIONS ---
  async function openCouncilModal() {
    const modal = document.getElementById('council-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    haptic('medium');

    document.getElementById('council-outcome-card').style.display = 'none';
    document.getElementById('btn-council-next').style.display = 'none';
    document.getElementById('council-situation-text').textContent = 'Kengash masalasi yuklanmoqda...';
    document.getElementById('council-options-container').innerHTML = '<div class="text-center py-3 text-secondary">Yuklanmoqda...</div>';

    await loadNextCouncilDilemma();
  }

  function closeCouncilModal() {
    const modal = document.getElementById('council-modal');
    if (modal) modal.style.display = 'none';
    currentCouncilData = null;
  }

  async function loadNextCouncilDilemma() {
    document.getElementById('council-outcome-card').style.display = 'none';
    document.getElementById('btn-council-next').style.display = 'none';

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/quests/council', {
        method: 'GET',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Masalani yuklashda xatolik.');
      }

      currentCouncilData = res.council;
      document.getElementById('council-attempts-badge').textContent = `Masalalar: ${currentCouncilData.attempts_remaining} / ${currentCouncilData.daily_limit}`;
      document.getElementById('council-reward-hint').textContent = `+${currentCouncilData.reward_gold}🪙 | +5 Nufuz`;
      document.getElementById('council-situation-text').textContent = currentCouncilData.situation;

      const optContainer = document.getElementById('council-options-container');
      optContainer.innerHTML = '';

      currentCouncilData.options.forEach((optText, idx) => {
        const btn = document.createElement('button');
        btn.className = 'quiz-opt-btn';
        btn.innerHTML = `<span style="color:var(--gold-primary); font-family:var(--font-serif); font-weight:700;">${idx+1}.</span> <span>${escapeHtml(optText)}</span>`;
        btn.addEventListener('click', () => handleCouncilChoiceSubmit(idx, btn));
        optContainer.appendChild(btn);
      });
    } catch (err) {
      document.getElementById('council-situation-text').textContent = err.message;
      document.getElementById('council-options-container').innerHTML = '';
      showToast(err.message, 'info');
    }
  }

  async function handleCouncilChoiceSubmit(selectedIdx, clickedBtn) {
    if (!currentCouncilData) return;
    haptic('medium');

    const optButtons = document.querySelectorAll('#council-options-container .quiz-opt-btn');
    optButtons.forEach(b => b.disabled = true);

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/quests/council/choice', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          council_id: currentCouncilData.council_id,
          user_choice: selectedIdx
        })
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Qarorni yuborishda xatolik.');
      }

      const outcome = res.data;
      const outcomeCard = document.getElementById('council-outcome-card');
      const titleEl = document.getElementById('council-outcome-title');
      const descEl = document.getElementById('council-outcome-desc');
      const nextBtn = document.getElementById('btn-council-next');

      if (outcome.is_correct) {
        haptic('success');
        clickedBtn.classList.add('is-correct');
        outcomeCard.className = 'quiz-outcome-card success mt-3';
        titleEl.textContent = '✅ DONO QAROR!';
        descEl.innerHTML = `Lordlar sizning tadbirkorligingizga qoyil qolishdi.<br><strong class="text-gold">+${outcome.gold_gained}🪙 Oltin, +${outcome.prestige_gained} Nufuz</strong>`;
      } else {
        haptic('warning');
        clickedBtn.classList.add('is-wrong');
        outcomeCard.className = 'quiz-outcome-card danger mt-3';
        titleEl.textContent = '❌ NOTO‘G‘RI QAROR!';
        descEl.innerHTML = `Bu qaror aholi noroziligiga sabab bo‘ldi. Mukofot berilmadi.`;
      }

      if (outcome.completed_all_daily) {
        descEl.innerHTML += `<br><br>🎉 <strong>Barcha Kengash maslahatlari yakunlandi! Katta bonus berildi!</strong>`;
      }

      outcomeCard.style.display = 'block';

      if (outcome.attempts_remaining > 0) {
        nextBtn.textContent = 'Keyingi Masala ➔';
        nextBtn.onclick = loadNextCouncilDilemma;
      } else {
        nextBtn.textContent = 'Tugatish (Bosh Menyu)';
        nextBtn.onclick = closeCouncilModal;
      }
      nextBtn.style.display = 'block';

      document.getElementById('council-attempts-badge').textContent = `Masalalar: ${outcome.attempts_remaining} / 2`;
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
      optButtons.forEach(b => b.disabled = false);
    }
  }

  // ============================================================
  // FEATURE 5: 1V1 DUELS & AI CHAMPIONS ARENA
  // ============================================================

  let currentDuelHubData = null;
  let selectedChampion = null;
  let selectedBet = 0;
  let selectedTactic = 'heavy';

  async function openDuelModal() {
    const modal = document.getElementById('duel-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    haptic('medium');

    document.getElementById('duel-outcome-card').style.display = 'none';
    const btn = document.getElementById('btn-start-duel');
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⚔️ Maydonga Tushish (Jang)';
    }

    await loadDuelHubData();
  }

  function closeDuelModal() {
    const modal = document.getElementById('duel-modal');
    if (modal) modal.style.display = 'none';
  }

  async function loadDuelHubData() {
    const champsContainer = document.getElementById('duel-champions-container');
    if (champsContainer && champsContainer.children.length === 0) {
      champsContainer.innerHTML = '<div style="padding:10px; color:var(--text-muted); font-size:11px;">⚔️ Chempionlar chaqirilmoqda...</div>';
    }

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/duels/hub', {
        method: 'GET',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Duel ma‘lumotlarini yuklashda xatolik.');
      }

      currentDuelHubData = res.duel_hub;
      const hero = currentDuelHubData.hero || {};
      const limits = currentDuelHubData.duels_limit || {};

      document.getElementById('duel-hero-name').textContent = hero.name || 'Lord Qahramoni';
      document.getElementById('duel-hero-stats').textContent = `⚔️ Atk: ${hero.attack || 50} | 🛡️ Def: ${hero.defense || 50} | Daraja: ${hero.level || 1}`;
      document.getElementById('duel-attempts-badge').textContent = `Limit: ${limits.remaining || 0} / ${limits.max_daily || 5}`;

      // Render Champions
      champsContainer.innerHTML = '';
      const champs = currentDuelHubData.available_champions || [];

      if (champs.length > 0 && (!selectedChampion || !champs.some(c => c.id === selectedChampion))) {
        selectedChampion = champs[0].id;
      }

      champs.forEach(champ => {
        const card = document.createElement('div');
        card.className = 'champ-card';
        if (champ.id === selectedChampion) card.classList.add('active');

        card.innerHTML = `
          <div>
            <div class="champ-name">${escapeHtml(champ.name)}</div>
            <div class="champ-desc">${escapeHtml(champ.desc || '')}</div>
          </div>
        `;

        card.addEventListener('click', () => {
          haptic('light');
          document.querySelectorAll('#duel-champions-container .champ-card').forEach(c => c.classList.remove('active'));
          card.classList.add('active');
          selectedChampion = champ.id;
        });

        champsContainer.appendChild(card);
      });

      // Bind Bet buttons
      const betButtons = document.querySelectorAll('#duel-bets-container .pill-btn');
      betButtons.forEach(btn => {
        btn.onclick = () => {
          haptic('light');
          betButtons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          selectedBet = parseInt(btn.getAttribute('data-bet')) || 0;
        };
      });

      // Bind Tactics buttons
      const tacticButtons = document.querySelectorAll('#duel-tactics-container .tactic-btn');
      tacticButtons.forEach(btn => {
        btn.onclick = () => {
          haptic('light');
          tacticButtons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          selectedTactic = btn.getAttribute('data-tactic') || 'heavy';
        };
      });

    } catch (err) {
      console.error('Load duel hub error:', err);
      if (champsContainer) {
        champsContainer.innerHTML = `<div style="padding:10px; color:var(--color-red); font-size:11px;">Yuklashda xatolik: ${escapeHtml(err.message)}</div>`;
      }
      showToast(err.message, 'error');
    }
  }

  async function handleStartDuel() {
    if (!selectedChampion) {
      showToast('Iltimos, raqib chempionni tanlang.', 'warning');
      return;
    }

    const btn = document.getElementById('btn-start-duel');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⚔️ Jang ketmoqda...';
    }
    haptic('heavy');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/duels/fight-ai', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          champion_name: selectedChampion,
          bet_gold: selectedBet,
          player_tactic: selectedTactic
        })
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Duelda xatolik yuz berdi.');
      }

      const duelRes = res.data;
      await playBattleClashAnimation('⚔️ MAYDONDA DUEL!', `${selectedChampion} bilan shafqatsiz to‘qnashuv...`, 1200);

      const outcomeCard = document.getElementById('duel-outcome-card');
      const titleEl = document.getElementById('duel-outcome-title');
      const descEl = document.getElementById('duel-outcome-desc');

      if (duelRes.won) {
        haptic('success');
        outcomeCard.className = 'quiz-outcome-card success mt-3';
        titleEl.textContent = '🏆 G‘ALABA!';
        descEl.innerHTML = `${duelRes.outcome}<br><strong class="text-gold">+${duelRes.reward_gold}🪙 Oltin, +${duelRes.reward_prestige} Nufuz, +${duelRes.reward_xp} XP</strong>`;
      } else {
        haptic('error');
        outcomeCard.className = 'quiz-outcome-card danger mt-3';
        titleEl.textContent = '💀 MAG‘LUBIYAT!';
        descEl.innerHTML = `${duelRes.outcome}`;
      }

      outcomeCard.style.display = 'block';
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚔️ Yana Jang Qilish';
      }

      await loadDuelHubData();
      await fetchDashboard();
    } catch (err) {
      console.error('Duel error:', err);
      showToast(err.message, 'error');
      haptic('error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚔️ Maydonga Tushish (Jang)';
      }
    }
  }

  // ============================================================
  // FEATURE 6: IRON BANK OF BRAAVOS
  // ============================================================

  let currentBankData = null;

  async function openBankModal() {
    const modal = document.getElementById('bank-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    haptic('medium');

    switchBankSubView('deposit');
    await loadBankHubData();
  }

  function closeBankModal() {
    const modal = document.getElementById('bank-modal');
    if (modal) modal.style.display = 'none';
  }

  function switchBankSubView(view) {
    const depView = document.getElementById('bank-view-deposit');
    const loanView = document.getElementById('bank-view-loan');
    const depBtn = document.getElementById('bank-tab-btn-deposit');
    const loanBtn = document.getElementById('bank-tab-btn-loan');

    if (view === 'deposit') {
      depView.style.display = 'block';
      loanView.style.display = 'none';
      depBtn.classList.add('active');
      loanBtn.classList.remove('active');
    } else {
      depView.style.display = 'none';
      loanView.style.display = 'block';
      depBtn.classList.remove('active');
      loanBtn.classList.add('active');
    }
  }

  async function loadBankHubData() {
    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/bank/hub', {
        method: 'GET',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Bank ma‘lumotlarini yuklashda xatolik.');
      }

      currentBankData = res.bank;
      const dep = currentBankData.deposit || {};
      const loan = currentBankData.loan || {};

      // Populate Deposit Tab
      document.getElementById('bank-deposit-val').textContent = `${formatNum(dep.current_gold)}🪙 / ${formatNum(dep.max_deposit)}🪙`;
      document.getElementById('bank-hourly-yield').textContent = `+${formatNum(dep.hourly_yield)}🪙 / s`;
      document.getElementById('bank-accumulated-interest').textContent = `${formatNum(dep.accumulated_interest)}🪙`;

      const claimInterestBtn = document.getElementById('btn-claim-bank-interest');
      if (dep.accumulated_interest > 0) {
        claimInterestBtn.disabled = false;
        claimInterestBtn.textContent = `Yechib Olish (+${formatNum(dep.accumulated_interest)}🪙)`;
      } else {
        claimInterestBtn.disabled = true;
        claimInterestBtn.textContent = 'To‘planmoqda...';
      }

      // Populate Loan Tab
      document.getElementById('bank-loan-principal').textContent = `${formatNum(loan.principal_gold)}🪙`;
      document.getElementById('bank-loan-total-due').textContent = `${formatNum(loan.total_due_gold)}🪙`;

      const repayBtn = document.getElementById('btn-repay-bank-loan');
      const takeLoanBox = document.getElementById('bank-take-loan-box');
      const loanStatusEl = document.getElementById('bank-loan-status');

      if (loan.is_active) {
        repayBtn.style.display = 'block';
        repayBtn.textContent = `💰 Qarzni Qaytarish (${formatNum(loan.total_due_gold)}🪙)`;
        takeLoanBox.style.display = 'none';

        if (loan.is_overdue) {
          loanStatusEl.textContent = '⚠️ Muddati o‘tgan! (Overdue)';
          loanStatusEl.className = 'info-val text-red';
        } else {
          loanStatusEl.textContent = `Muddati: ${loan.days_left} kun ${loan.hours_left} soat qoldi`;
          loanStatusEl.className = 'info-val text-gold';
        }
      } else {
        repayBtn.style.display = 'none';
        takeLoanBox.style.display = 'block';
        loanStatusEl.textContent = 'Faol qarz yo‘q';
        loanStatusEl.className = 'info-val text-green';
      }

    } catch (err) {
      console.error('Load bank error:', err);
      showToast(err.message, 'error');
    }
  }

  async function handleBankDeposit() {
    const input = document.getElementById('bank-deposit-input');
    const amount = parseInt(input.value) || 0;
    if (amount <= 0) {
      showToast('Omonat miqdorini to‘g‘ri kiriting.', 'warning');
      return;
    }

    const btn = document.getElementById('btn-submit-bank-deposit');
    if (btn) btn.disabled = true;
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/bank/deposit', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ amount: amount })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Omonat qo‘yishda xatolik.');
      }

      showToast(res.message || '💰 Omonat muvaffaqiyatli qo‘yildi!', 'success');
      haptic('success');
      await loadBankHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleBankWithdraw() {
    const input = document.getElementById('bank-withdraw-input');
    const amount = parseInt(input.value) || 0;
    if (amount <= 0) {
      showToast('Yechiladigan miqdorni kiriting.', 'warning');
      return;
    }

    const btn = document.getElementById('btn-submit-bank-withdraw');
    if (btn) btn.disabled = true;
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/bank/withdraw', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ amount: amount })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Omonatni yechishda xatolik.');
      }

      showToast(res.message || '💰 Omonat xazinangizga qaytarildi!', 'success');
      haptic('success');
      await loadBankHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleBankClaimInterest() {
    const btn = document.getElementById('btn-claim-bank-interest');
    if (btn) btn.disabled = true;
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/bank/claim-interest', {
        method: 'POST',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Foizlarni yechishda xatolik.');
      }

      showToast(res.message || '🎉 Foiz daromadi hamyoningizga o‘tkazildi!', 'success');
      haptic('success');
      await loadBankHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleBankTakeLoan() {
    const input = document.getElementById('bank-loan-input');
    const amount = parseInt(input.value) || 0;
    if (amount <= 0) {
      showToast('Kredit miqdorini kiriting.', 'warning');
      return;
    }

    const btn = document.getElementById('btn-submit-bank-loan');
    if (btn) btn.disabled = true;
    haptic('heavy');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/bank/take-loan', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ amount: amount })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Kredit olishda xatolik.');
      }

      showToast(res.message || '📜 Kredit muvaffaqiyatli olindi!', 'success');
      haptic('success');
      await loadBankHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleBankRepayLoan() {
    const btn = document.getElementById('btn-repay-bank-loan');
    if (btn) btn.disabled = true;
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/bank/repay-loan', {
        method: 'POST',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Qarzni qaytarishda xatolik.');
      }

      showToast(res.message || '✅ Qarz to‘liq qaytarildi!', 'success');
      haptic('success');
      await loadBankHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ============================================================
  // FEATURE 7: GUILD SYSTEM & TREASURY ACTIONS
  // ============================================================

  let currentGuildData = null;
  let selectedGuildResource = 'gold';

  async function openGuildModal() {
    const modal = document.getElementById('guild-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    haptic('medium');

    await loadGuildHubData();
  }

  function closeGuildModal() {
    const modal = document.getElementById('guild-modal');
    if (modal) modal.style.display = 'none';
  }

  async function loadGuildHubData() {
    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/guild/hub', {
        method: 'GET',
        headers: headers,
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Gildiya ma‘lumotlarini yuklashda xatolik.');
      }

      currentGuildData = res.guild_hub;
      const inView = document.getElementById('guild-in-view');
      const outView = document.getElementById('guild-out-view');

      if (currentGuildData.in_guild) {
        inView.style.display = 'block';
        outView.style.display = 'none';

        const g = currentGuildData.guild || {};
        const treasury = g.treasury || {};

        document.getElementById('guild-banner-icon').textContent = g.banner || '🛡️';
        document.getElementById('guild-title-name').textContent = g.name || 'Birodarlik';
        document.getElementById('guild-tag-level').textContent = `[${g.tag || 'TAG'}] • ${g.level || 1}-Daraja (${g.members_count || 1}/${g.max_members || 20})`;
        document.getElementById('guild-treasury-gold').textContent = `${formatNum(treasury.gold)}🪙 Oltin`;
        document.getElementById('guild-treasury-iron').textContent = `${formatNum(treasury.iron)}⛓️ Temir`;

        const buffBox = document.getElementById('guild-buff-active-box');
        if (g.active_buff) {
          buffBox.style.display = 'flex';
          document.getElementById('guild-buff-name').textContent = g.active_buff.name;
          document.getElementById('guild-buff-time').textContent = `${g.active_buff.hours_remaining} soat ${g.active_buff.minutes_remaining} daqiqa qoldi`;
        } else {
          buffBox.style.display = 'none';
        }
      } else {
        inView.style.display = 'none';
        outView.style.display = 'block';
      }

    } catch (err) {
      console.error('Load guild error:', err);
      showToast(err.message, 'error');
    }
  }

  async function handleGuildDeposit() {
    const input = document.getElementById('guild-deposit-input');
    const amount = parseInt(input.value) || 0;
    if (amount <= 0) {
      showToast('Hissa miqdorini to‘g‘ri kiriting.', 'warning');
      return;
    }

    const btn = document.getElementById('btn-submit-guild-deposit');
    if (btn) btn.disabled = true;
    haptic('medium');

    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/guild/deposit', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          resource_type: selectedGuildResource,
          amount: amount
        })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Xazinaga hissa topshirishda xatolik.');
      }

      showToast(res.message || '🛡️ Gildiya xazinasiga muvaffaqiyatli topshirildi!', 'success');
      haptic('success');
      await loadGuildHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleGuildBuff(buffType) {
    haptic('heavy');
    const headers = { 'Content-Type': 'application/json' };
    if (currentInitData) {
      headers['Authorization'] = `tma ${currentInitData}`;
    }

    try {
      const resp = await fetch('/api/actions/guild/buff', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ buff_type: buffType })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Buffni yoqishda xatolik.');
      }

      showToast(res.message || '⚡ Gildiya bafi 24 soatga faollashtirildi!', 'success');
      haptic('success');
      await loadGuildHubData();
      await fetchDashboard();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    }
  }

  // Render Rankings Tab
  function renderRankings(rankingsData) {
    if (!rankingsData) return;

    const myRank = rankingsData.my_ranks?.[activeRankingCategory];
    const myRankEl = document.getElementById('my-rank-val');
    if (myRank) {
      myRankEl.textContent = `${myRank}-o'rin`;
    } else {
      myRankEl.textContent = 'Top 10 da emas';
    }

    const container = document.getElementById('rankings-container');
    container.innerHTML = '';

    const list = rankingsData[activeRankingCategory] || [];
    if (list.length === 0) {
      container.innerHTML = '<p class="text-center text-secondary py-3">Ma‘lumotlar mavjud emas.</p>';
      return;
    }

    list.forEach(item => {
      const row = document.createElement('div');
      row.className = 'rank-row';
      const medalIcon = item.rank === 1 ? '🥇' : item.rank === 2 ? '🥈' : item.rank === 3 ? '🥉' : item.rank;
      const valFormatted = formatNum(item.value);

      row.innerHTML = `
        <div class="rank-left">
          <span class="rank-medal">${medalIcon}</span>
          <div>
            <div style="font-weight: 600;">${escapeHtml(item.name)}</div>
            <div style="font-size: 11px; color: var(--text-secondary);">${escapeHtml(item.house || '')}</div>
          </div>
        </div>
        <div style="font-weight: 700; color: var(--gold-light); font-family: var(--font-serif);">${valFormatted}</div>
      `;
      container.appendChild(row);
    });
  }

  // Render World & Events Tab
  function renderWorld(worldData) {
    if (!worldData) return;

    // Westeros Season Card & Hall of Fame
    const season = worldData.season || {};
    const seasonNumBadge = document.getElementById('season-num-badge');
    if (seasonNumBadge) seasonNumBadge.textContent = `👑 ${season.season_number || 2}-Mavsum`;
    const seasonNameEl = document.getElementById('season-name');
    if (seasonNameEl) seasonNameEl.textContent = season.name || '2-Mavsum: Temir Taxt Qadami';
    const seasonDaysEl = document.getElementById('season-days-left');
    if (seasonDaysEl) seasonDaysEl.textContent = `${season.days_left ?? 14} kun`;
    const seasonStatusBadge = document.getElementById('season-status-badge');
    if (seasonStatusBadge) seasonStatusBadge.textContent = season.status || 'Faol';

    const fameContainer = document.getElementById('season-hall-of-fame-list');
    if (fameContainer) {
      const entries = season.hall_of_fame || [];
      if (entries.length === 0) {
        fameContainer.innerHTML = '<div style="padding:4px 0; color:var(--text-secondary); font-size:11px;">1-Mavsum yakunlangan. Chempion: Liar (@NiclausMikaelson) — House Targaryen</div>';
      } else {
        fameContainer.innerHTML = entries.map(e => `
          <div class="fame-item">
            <div class="fame-season">🏆 ${e.season_number}-Mavsum</div>
            <div class="fame-winner">👑 ${escapeHtml(e.king_name)} <span class="fame-house">(${escapeHtml(e.winner_house)})</span></div>
            <div class="fame-date">${e.date || ''}</div>
          </div>
        `).join('');
      }
    }

    const w = worldData.weather || {};
    document.getElementById('w-emoji').textContent = w.emoji || '🌤️';
    document.getElementById('w-name').textContent = w.name || 'Mo‘tadil Havo';
    document.getElementById('w-desc').textContent = w.description || 'Vesteros bo‘ylab tinchlik hukmron.';
    document.getElementById('w-eff-army').textContent = w.effect_army || 'Normal';
    document.getElementById('w-eff-eco').textContent = w.effect_economy || 'Normal';

    const container = document.getElementById('events-container');
    container.innerHTML = '';

    const events = worldData.events || [];
    events.forEach(e => {
      const card = document.createElement('div');
      card.className = 'event-card';
      const badge = e.is_active
        ? '<span class="event-badge-active">● Hozir Faol</span>'
        : '<span class="event-badge-wait">Kutilmoqda</span>';

      card.innerHTML = `
        <div class="unit-left">
          <span style="font-size: 26px;">${e.emoji || '⚔️'}</span>
          <div>
            <div style="font-weight: 600;">${escapeHtml(e.name)}</div>
            <div style="font-size: 11px; color: var(--text-secondary);">⏰ ${e.time}</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">${escapeHtml(e.description)}</div>
          </div>
        </div>
        <div>${badge}</div>
      `;
      container.appendChild(card);
    });
  }

  // ============================================================
  // FEATURE EXTENSIONS: ONBOARDING, MAP, MARCH, SPY
  // ============================================================

  let selectedOnboardingHouse = null;

  function renderOnboarding(houses) {
    const onbView = document.getElementById('view-onboarding');
    if (!onbView) return;
    onbView.style.display = 'block';

    document.querySelectorAll('.view-panel').forEach(p => {
      if (p.id !== 'view-onboarding') p.style.display = 'none';
    });
    const bNav = document.querySelector('.bottom-nav');
    if (bNav) bNav.style.display = 'none';

    const container = document.getElementById('onboarding-houses-container');
    if (!container) return;

    container.innerHTML = houses.map(h => `
      <div class="house-card" data-code="${h.code}">
        <span class="house-sigil-icon">${h.emoji || '🛡️'}</span>
        <div class="house-card-title">${escapeHtml(h.name)}</div>
        <div class="house-card-motto">"${escapeHtml(h.motto || '')}"</div>
        <div class="house-card-perk">⚡ ${escapeHtml(h.bonus_desc || '')}</div>
      </div>
    `).join('');

    container.querySelectorAll('.house-card').forEach(card => {
      card.addEventListener('click', () => {
        haptic('light');
        container.querySelectorAll('.house-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        selectedOnboardingHouse = card.getAttribute('data-code');
      });
    });
  }

  async function handleRegisterPlayer() {
    if (isActionPending) return;
    const heroName = (document.getElementById('onboarding-hero-name')?.value || '').trim();
    if (heroName.length < 2) {
      showToast('Iltimos, kamida 2 harfdan iborat Lord ismini kiriting.', 'error');
      return;
    }

    const payload = {
      hero_name: heroName,
      house_code: selectedOnboardingHouse || null,
      custom_house_name: (document.getElementById('onboarding-custom-name')?.value || '').trim() || null,
      custom_house_region: (document.getElementById('onboarding-custom-region')?.value || '').trim() || null,
      custom_house_emoji: (document.getElementById('onboarding-custom-emoji')?.value || '').trim() || null,
      custom_castle_name: (document.getElementById('onboarding-custom-castle')?.value || '').trim() || null,
    };

    if (!payload.house_code && !payload.custom_house_name) {
      showToast('Iltimos, Buyuk Xonadonlardan birini tanlang yoki maxsus xonadon yarating.', 'error');
      return;
    }

    const submitBtn = document.getElementById('btn-submit-onboarding');
    if (submitBtn) submitBtn.disabled = true;
    isActionPending = true;
    haptic('medium');

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/player/register', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Ro‘yxatdan o‘tishda xatolik yuz berdi.');
      }

      showToast('👑 Qasamyodingiz qabul qilindi! Vesteros sizni qutlaydi!', 'success');
      haptic('heavy');
      await fetchDashboard();
    } catch (err) {
      console.error('Registration error:', err);
      showToast(err.message, 'error');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
      isActionPending = false;
    }
  }

  // --- MAP & SCOUT ---
  let cachedTerritories = [];

  async function openMapModal() {
    showModal('map-modal');
    await loadMapData();
  }

  function closeMapModal() {
    hideModal('map-modal');
  }

  async function loadMapData() {
    const container = document.getElementById('map-territories-container');
    if (!container) return;
    container.innerHTML = '<div class="text-center py-3 text-secondary">Vesteros xaritasi yuklanmoqda...</div>';

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/map/overview', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Xarita ma‘lumotlarini yuklab bo‘lmadi.');

      cachedTerritories = res.territories || [];
      renderMap(cachedTerritories);
    } catch (err) {
      console.error('Map error:', err);
      container.innerHTML = `<div class="text-center py-3 text-red">Xatolik: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderMap(territories, regionFilter = 'all') {
    const container = document.getElementById('map-territories-container');
    if (!container) return;

    const filtered = (regionFilter === 'all')
      ? territories
      : territories.filter(t => t.region === regionFilter);

    if (!filtered.length) {
      container.innerHTML = '<div class="text-center py-3 text-secondary">Ushbu hududda qal‘alar topilmadi.</div>';
      return;
    }

    container.innerHTML = filtered.map(t => {
      const isMine = t.is_my_castle;
      return `
        <div class="territory-card ${isMine ? 'own-territory' : ''}" data-id="${t.id}">
          <div class="territory-header">
            <div>
              <span class="territory-title">${escapeHtml(t.name)}</span>
              <div class="territory-meta">${escapeHtml(t.region)} • ${escapeHtml(t.tier_label || 'Qal‘a')} • ${t.owner_house ? escapeHtml(t.owner_house.name) : 'Noma‘lum'}</div>
            </div>
            <span class="badge ${isMine ? 'badge-active' : 'badge-gold'}">${isMine ? 'Sizning Qal‘angiz' : `${formatNum(t.defense)} Mudofaa`}</span>
          </div>
          <div class="territory-incomes">
            <span>🪙 +${formatNum(t.gold_income)}/s</span>
            <span>🌾 +${formatNum(t.food_income)}/s</span>
            <span>⛓️ +${formatNum(t.iron_income)}/s</span>
          </div>
          <div class="territory-actions">
            <button class="territory-btn btn-scout-terr" data-id="${t.id}">👁️ Razvedka</button>
            <button class="territory-btn btn-march-terr" data-id="${t.id}">⚔️ Harbiy Yurish</button>
            <button class="territory-btn btn-spy-terr" data-id="${t.id}">🕵️ Josus</button>
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.btn-scout-terr').forEach(btn => {
      btn.addEventListener('click', () => openScoutModal(parseInt(btn.getAttribute('data-id'))));
    });
    container.querySelectorAll('.btn-march-terr').forEach(btn => {
      btn.addEventListener('click', () => {
        closeMapModal();
        openMarchModal(parseInt(btn.getAttribute('data-id')));
      });
    });
    container.querySelectorAll('.btn-spy-terr').forEach(btn => {
      btn.addEventListener('click', () => {
        closeMapModal();
        openEspionageModal(parseInt(btn.getAttribute('data-id')));
      });
    });
  }

  async function openScoutModal(territoryId) {
    showModal('scout-modal');
    const body = document.getElementById('scout-body');
    if (!body) return;
    body.innerHTML = '<div class="text-center py-3 text-secondary">Razvedka qarg‘alari uchirilmoqda...</div>';

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch(`/api/actions/map/scout/${territoryId}`, { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Razvedka ma‘lumotini olib bo‘lmadi.');

      const s = res.scout_report;
      body.innerHTML = `
        <div class="card p-3 mb-2">
          <h4 class="font-serif text-gold">${escapeHtml(s.territory_name)}</h4>
          <p class="text-secondary" style="font-size:11px;">Mintaqa: ${escapeHtml(s.region)} | Egasi: ${escapeHtml(s.owner_house_name || 'Noma‘lum')}</p>
          <div class="d-flex justify-between mt-2" style="font-size:12px;">
            <span>Qal‘a Darajasi: <strong>${s.castle_level}</strong></span>
            <span>Umumiy Mudofaa: <strong class="text-blue">${formatNum(s.effective_defense)}</strong></span>
          </div>
        </div>
        <div class="card p-3 mb-2">
          <h5 class="text-gold font-serif mb-1">🛡️ Garnizon Qurolli Kuchlari</h5>
          <div class="d-flex justify-between" style="font-size:11px;">
            <span>Piyoda: ${formatNum(s.garrison_infantry)}</span>
            <span>Kamonchi: ${formatNum(s.garrison_archers)}</span>
            <span>Otliq: ${formatNum(s.garrison_cavalry)}</span>
            <span>Nayzador: ${formatNum(s.garrison_spearmen)}</span>
          </div>
          <div class="mt-2 text-secondary" style="font-size:11px;">
            Yovvoyi Olov (Wildfire): ${s.wildfire_traps ? '<strong class="text-red">Mavjud!</strong>' : 'Yo‘q'}
          </div>
          <div class="text-secondary" style="font-size:11px;">
            Darvoza Holati: ${s.gates_compromised ? '<strong class="text-green">Buzilgan (Zaif)</strong>' : 'Butun'}
          </div>
        </div>
        <button class="btn btn-primary w-100 mt-2" id="btn-scout-to-march">
          ⚔️ Ushbu Qal‘aga Hujum Uyushtirish
        </button>
      `;

      document.getElementById('btn-scout-to-march')?.addEventListener('click', () => {
        closeScoutModal();
        openMarchModal(s.territory_id);
      });
    } catch (err) {
      console.error('Scout error:', err);
      body.innerHTML = `<div class="text-center py-3 text-red">Xatolik: ${escapeHtml(err.message)}</div>`;
    }
  }

  function closeScoutModal() {
    hideModal('scout-modal');
  }

  // --- MARCH (ATTACK) ---
  async function openMarchModal(preferredTerritoryId = null) {
    showModal('march-modal');
    populateMarchAvailableTroops();
    await loadMarchTargets(preferredTerritoryId);
    await loadActiveMarches();
  }

  function closeMarchModal() {
    hideModal('march-modal');
  }

  function populateMarchAvailableTroops() {
    const army = cachedDashboardData?.army || {};
    const units = army.units || {};
    const siege = army.siege || {};

    document.getElementById('avail-infantry').textContent = formatNum(units.infantry?.count || 0);
    document.getElementById('avail-archers').textContent = formatNum(units.archers?.count || 0);
    document.getElementById('avail-cavalry').textContent = formatNum(units.cavalry?.count || 0);
    document.getElementById('avail-spearmen').textContent = formatNum(units.spearmen?.count || 0);
    document.getElementById('avail-catapults').textContent = formatNum(siege.catapults?.count || 0);
    document.getElementById('avail-towers').textContent = formatNum(siege.siege_towers?.count || 0);

    document.getElementById('march-infantry').value = 0;
    document.getElementById('march-archers').value = 0;
    document.getElementById('march-cavalry').value = 0;
    document.getElementById('march-spearmen').value = 0;
    document.getElementById('march-catapults').value = 0;
    document.getElementById('march-towers').value = 0;
  }

  function applyMarchPercentage(pct) {
    const army = cachedDashboardData?.army || {};
    const units = army.units || {};
    const siege = army.siege || {};

    const factor = pct / 100.0;
    document.getElementById('march-infantry').value = Math.floor((units.infantry?.count || 0) * factor);
    document.getElementById('march-archers').value = Math.floor((units.archers?.count || 0) * factor);
    document.getElementById('march-cavalry').value = Math.floor((units.cavalry?.count || 0) * factor);
    document.getElementById('march-spearmen').value = Math.floor((units.spearmen?.count || 0) * factor);
    document.getElementById('march-catapults').value = Math.floor((siege.catapults?.count || 0) * factor);
    document.getElementById('march-towers').value = Math.floor((siege.siege_towers?.count || 0) * factor);
    haptic('light');
  }

  async function loadMarchTargets(preferredTerritoryId) {
    const select = document.getElementById('march-target-select');
    if (!select) return;

    if (!cachedTerritories.length) {
      try {
        const headers = { 'Content-Type': 'application/json' };
        if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;
        const resp = await fetch('/api/actions/map/overview', { method: 'GET', headers: headers });
        const res = await resp.json();
        cachedTerritories = res.territories || [];
      } catch (e) {}
    }

    const enemies = cachedTerritories.filter(t => !t.is_my_castle);
    select.innerHTML = enemies.map(t => `
      <option value="${t.id}" ${preferredTerritoryId === t.id ? 'selected' : ''}>
        ${escapeHtml(t.name)} (${escapeHtml(t.region)}) — Mudofaa: ${formatNum(t.defense)}
      </option>
    `).join('');

    updateMarchTargetDetails();
  }

  function updateMarchTargetDetails() {
    const select = document.getElementById('march-target-select');
    const terrId = parseInt(select?.value);
    const target = cachedTerritories.find(t => t.id === terrId);
    if (!target) return;

    document.getElementById('march-target-def').textContent = formatNum(target.defense);
    document.getElementById('march-target-dist').textContent = `${target.distance_km || 150} km`;
    document.getElementById('march-target-time').textContent = `${target.travel_seconds || 180} soniya`;
  }

  async function handleDispatchMarch() {
    if (isActionPending) return;
    const select = document.getElementById('march-target-select');
    const targetId = parseInt(select?.value);
    if (!targetId) {
      showToast('Iltimos, nishon qal‘ani tanlang.', 'error');
      return;
    }

    const infantry = parseInt(document.getElementById('march-infantry')?.value) || 0;
    const archers = parseInt(document.getElementById('march-archers')?.value) || 0;
    const cavalry = parseInt(document.getElementById('march-cavalry')?.value) || 0;
    const spearmen = parseInt(document.getElementById('march-spearmen')?.value) || 0;
    const catapults = parseInt(document.getElementById('march-catapults')?.value) || 0;
    const siegeTowers = parseInt(document.getElementById('march-towers')?.value) || 0;

    const totalTroops = infantry + archers + cavalry + spearmen;
    if (totalTroops <= 0) {
      showToast('Kamida 1 nafar askar tanlanishi shart!', 'error');
      return;
    }

    const hasDragon = document.getElementById('march-dragon-toggle')?.checked || false;
    const dragonTactic = document.getElementById('march-dragon-tactic')?.value || 'none';

    const btn = document.getElementById('btn-submit-march');
    if (btn) btn.disabled = true;
    isActionPending = true;
    haptic('medium');

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/battle/march', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          target_territory_id: targetId,
          infantry: infantry,
          archers: archers,
          cavalry: cavalry,
          spearmen: spearmen,
          catapults: catapults,
          siege_towers: siegeTowers,
          has_dragon: hasDragon,
          dragon_tactic: dragonTactic,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Harbiy yurishni boshlashda xatolik yuz berdi.');
      }

      await playBattleClashAnimation('🚩 HARBIY YURISH!', 'Qo‘shinlar qal‘a sari harakatga tushdi...', 1000);

      showToast(`🚩 Harbiy yurish boshlandi! Yetib borish vaqti: ${res.march.travel_seconds}s`, 'success');
      haptic('heavy');
      await fetchDashboard();
      populateMarchAvailableTroops();
      await loadActiveMarches();
    } catch (err) {
      console.error('March dispatch error:', err);
      showToast(err.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
      isActionPending = false;
    }
  }

  async function loadActiveMarches() {
    const list = document.getElementById('active-marches-list');
    if (!list) return;

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/battle/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      const marches = res.active_marches || [];

      if (!marches.length) {
        list.innerHTML = '<div class="text-secondary" style="font-size:11px;">Hozirda harakatdagi harbiy yurishlar yo‘q.</div>';
        return;
      }

      list.innerHTML = marches.map(m => `
        <div class="card p-2 mb-2" style="font-size:11px;">
          <div class="d-flex justify-between">
            <strong class="text-gold">🚩 Nishon: ${escapeHtml(m.target_territory_name || 'Qal‘a')}</strong>
            <span class="text-red">${m.seconds_remaining}s qoldi</span>
          </div>
          <div class="text-secondary mt-1">
            Qo‘shin: ${m.infantry} piyoda, ${m.archers} kamonchi, ${m.cavalry} otliq, ${m.spearmen} nayzador
          </div>
        </div>
      `).join('');
    } catch (e) {
      list.innerHTML = '<div class="text-secondary" style="font-size:11px;">Faol yurishlarni yuklab bo‘lmadi.</div>';
    }
  }

  // --- ESPIONAGE ---
  async function openEspionageModal(territoryId = null) {
    showModal('espionage-modal');
    const select = document.getElementById('espionage-target-select');
    if (select) {
      if (!cachedTerritories.length) {
        try {
          const headers = { 'Content-Type': 'application/json' };
          if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;
          const resp = await fetch('/api/actions/map/overview', { method: 'GET', headers: headers });
          const res = await resp.json();
          cachedTerritories = res.territories || [];
        } catch (e) {}
      }
      const enemies = cachedTerritories.filter(t => !t.is_my_castle);
      select.innerHTML = enemies.map(t => `
        <option value="${t.id}" ${territoryId === t.id ? 'selected' : ''}>
          ${escapeHtml(t.name)} (${escapeHtml(t.region)})
        </option>
      `).join('');
    }
    const resBox = document.getElementById('espionage-result-box');
    if (resBox) resBox.style.display = 'none';
  }

  function closeEspionageModal() {
    hideModal('espionage-modal');
  }

  async function handleExecuteSpyMission(missionType) {
    if (isActionPending) return;
    const select = document.getElementById('espionage-target-select');
    const targetId = parseInt(select?.value);
    if (!targetId) {
      showToast('Iltimos, nishon qal‘ani tanlang.', 'error');
      return;
    }

    isActionPending = true;
    haptic('medium');
    const resBox = document.getElementById('espionage-result-box');
    if (resBox) {
      resBox.style.display = 'block';
      resBox.innerHTML = '<div class="text-secondary">Josus yuborilmoqda...</div>';
    }

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/espionage/execute', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          target_territory_id: targetId,
          mission_type: missionType,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) {
        throw new Error(res.detail || res.error || 'Josuslik amali bajarilmadi.');
      }

      if (res.mission_success) {
        showToast('🕵️ Josuslik operatsiyasi muvaffaqiyatli yakunlandi!', 'success');
        haptic('heavy');
      } else {
        showToast('⚠️ Josus dushman soqchilari tomonidan fosh qilindi!', 'error');
        haptic('error');
      }

      if (resBox) {
        resBox.innerHTML = `
          <h4 class="${res.mission_success ? 'text-green' : 'text-red'} font-serif">${res.mission_success ? 'Muvaffaqiyat!' : 'Fosh bo‘ldi!'}</h4>
          <p class="mt-1" style="font-size:12px;">${escapeHtml(res.report)}</p>
        `;
      }
      await fetchDashboard();
    } catch (err) {
      console.error('Espionage error:', err);
      showToast(err.message, 'error');
      if (resBox) resBox.innerHTML = `<div class="text-red">Xatolik: ${escapeHtml(err.message)}</div>`;
    } finally {
      isActionPending = false;
    }
  }

  // --- DRAGON NEST ---
  async function openDragonModal() {
    showModal('dragon-modal');
    await loadDragonData();
  }

  function closeDragonModal() {
    hideModal('dragon-modal');
  }

  async function loadDragonData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/dragon/status', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Ajdaho ma‘lumotini yuklab bo‘lmadi.');

      const d = res.dragon;
      const vUnclaimed = document.getElementById('dragon-view-unclaimed');
      const vEgg = document.getElementById('dragon-view-egg');
      const vActive = document.getElementById('dragon-view-active');

      if (!d) {
        vUnclaimed.style.display = 'block';
        vEgg.style.display = 'none';
        vActive.style.display = 'none';
      } else if (d.is_egg) {
        vUnclaimed.style.display = 'none';
        vEgg.style.display = 'block';
        vActive.style.display = 'none';
        document.getElementById('dragon-egg-name').textContent = d.name || 'Valyriya Tuxumi';
      } else {
        vUnclaimed.style.display = 'none';
        vEgg.style.display = 'none';
        vActive.style.display = 'block';
        document.getElementById('dragon-name').textContent = d.name || 'Ajdaho';
        document.getElementById('dragon-stage-lbl').textContent = `${d.stage_label || 'Ajdaho'} • ${d.age_days || 1} Kunlik`;
        document.getElementById('dragon-power-val').textContent = formatNum(d.power || 0);
        document.getElementById('dragon-power-bar').style.width = `${Math.min(100, Math.floor((d.power || 0) / 50))}%`;
        const hungerPct = Math.min(100, Math.max(0, 100 - (d.hunger || 0)));
        document.getElementById('dragon-hunger-val').textContent = `To‘qlik: ${hungerPct}%`;
        document.getElementById('dragon-hunger-bar').style.width = `${hungerPct}%`;

        const portraitImg = document.getElementById('dragon-portrait-img');
        if (portraitImg) {
          portraitImg.src = AssetManager.getDragonPortrait(d.stage || 'adult', d.skin);
        }
      }
    } catch (err) {
      console.error('Dragon error:', err);
    }
  }

  async function handleClaimDragonEgg() {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;
      const resp = await fetch('/api/actions/dragon/claim-egg', { method: 'POST', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Tuxumni olib bo‘lmadi.');
      showToast('🥚 Valyriya ajdaho tuxumi sandiqingizga qo‘yildi!', 'success');
      haptic('heavy');
      await loadDragonData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleHatchDragon() {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;
      const resp = await fetch('/api/actions/dragon/hatch', { method: 'POST', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Ajdahoni ochirib bo‘lmadi.');
      showToast('🔥 Ajdaho tuxumdan chiqdi! U Vesteros osmonini zabt etadi!', 'success');
      haptic('heavy');
      await loadDragonData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleFeedDragon() {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;
      const resp = await fetch('/api/actions/dragon/feed', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ food_amount: 50 }),
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Boqishda xatolik.');
      showToast('🥩 Ajdaho to‘yib oziqlandi! Qudrati ortmoqda.', 'success');
      haptic('medium');
      await fetchDashboard();
      await loadDragonData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleTrainDragon() {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;
      const resp = await fetch('/api/actions/dragon/train', { method: 'POST', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Mashg‘ulotda xatolik.');
      showToast('🔥 Ajdaho olov bilan jangga tayyorlandi!', 'success');
      haptic('heavy');
      await fetchDashboard();
      await loadDragonData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- GREAT HOUSE HUB ---
  let selectedHouseDepositResource = 'gold';

  async function openHouseModal() {
    showModal('house-modal');
    await loadHouseData();
  }

  function closeHouseModal() {
    hideModal('house-modal');
  }

  async function loadHouseData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/house/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Xonadon ma‘lumotini yuklab bo‘lmadi.');

      const h = res.house || {};
      document.getElementById('house-sigil').textContent = h.emoji || '🦁';
      document.getElementById('house-title-name').textContent = h.name || 'Buyuk Xonadon';
      document.getElementById('house-motto').textContent = h.motto ? `"${h.motto}"` : '';
      document.getElementById('house-lord-name').textContent = res.lord?.full_name || 'Hali saylanmagan';
      document.getElementById('house-treasury-gold').textContent = `${formatNum(h.treasury_gold || 0)}🪙 Oltin`;
      document.getElementById('house-treasury-iron').textContent = `${formatNum(h.treasury_iron || 0)}⛓️ Temir`;

      const list = document.getElementById('house-members-list');
      const members = res.members || [];
      if (!members.length) {
        list.innerHTML = '<div class="text-secondary" style="font-size:11px;">A‘zolar topilmadi.</div>';
      } else {
        list.innerHTML = members.map(m => `
          <div class="card p-2 mb-2 d-flex justify-between align-center" style="font-size:11px;">
            <div>
              <strong class="text-gold">${escapeHtml(m.full_name)}</strong>
              <div class="text-secondary">${escapeHtml(m.rank_label || 'Ritsar')}</div>
            </div>
            <div class="text-right">
              <div>${formatNum(m.contribution_gold)}🪙</div>
              <div class="text-secondary">${m.prestige} nufuz</div>
            </div>
          </div>
        `).join('');
      }
    } catch (err) {
      console.error('House error:', err);
    }
  }

  async function handleHouseDeposit() {
    if (isActionPending) return;
    const amount = parseInt(document.getElementById('house-deposit-input')?.value) || 0;
    if (amount <= 0) {
      showToast('Iltimos, to‘g‘ri miqdor kiriting.', 'error');
      return;
    }

    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/house/deposit', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          resource_type: selectedHouseDepositResource,
          amount: amount,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Xazinaga hissa topshirib bo‘lmadi.');

      showToast('🏛️ Xonadon xazinasiga boylik muvaffaqiyatli topshirildi!', 'success');
      haptic('heavy');
      await fetchDashboard();
      await loadHouseData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- FREE MARKET & CARAVANS ---
  async function openMarketModal() {
    showModal('market-modal');
    switchMarketTab('lots');
    await loadMarketData();
  }

  function closeMarketModal() {
    hideModal('market-modal');
  }

  function switchMarketTab(tab) {
    const vLots = document.getElementById('market-view-lots');
    const vCreate = document.getElementById('market-view-create');
    const vCaravans = document.getElementById('market-view-caravans');

    document.getElementById('tab-market-lots-btn')?.classList.toggle('active', tab === 'lots');
    document.getElementById('tab-market-create-btn')?.classList.toggle('active', tab === 'create');
    document.getElementById('tab-market-caravans-btn')?.classList.toggle('active', tab === 'caravans');

    if (vLots) vLots.style.display = (tab === 'lots') ? 'block' : 'none';
    if (vCreate) vCreate.style.display = (tab === 'create') ? 'block' : 'none';
    if (vCaravans) vCaravans.style.display = (tab === 'caravans') ? 'block' : 'none';
    haptic('light');
  }

  async function loadMarketData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/trade/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Bozor ma‘lumotini yuklab bo‘lmadi.');

      const lotsCont = document.getElementById('market-lots-container');
      const lots = res.lots || [];
      if (!lots.length) {
        lotsCont.innerHTML = '<div class="text-center py-3 text-secondary">Hozirda sotuvda takliflar yo‘q. Birinchi bo‘lib e‘lon joylashtiring!</div>';
      } else {
        lotsCont.innerHTML = lots.map(l => `
          <div class="trade-lot-card">
            <div class="d-flex justify-between align-center">
              <div>
                <strong>${formatNum(l.offer_amount)} ${escapeHtml(l.offer_resource.toUpperCase())}</strong>
                <span class="text-secondary">evaziga</span>
                <strong class="text-gold">${formatNum(l.request_amount)} ${escapeHtml(l.request_resource.toUpperCase())}</strong>
              </div>
              ${l.is_my_lot
                ? `<button class="btn btn-secondary py-1 px-2 btn-cancel-lot" data-id="${l.id}">Bekor qilish</button>`
                : `<button class="btn btn-primary py-1 px-3 btn-buy-lot" data-id="${l.id}">Sotib olish</button>`
              }
            </div>
          </div>
        `).join('');

        lotsCont.querySelectorAll('.btn-buy-lot').forEach(btn => {
          btn.addEventListener('click', () => handleBuyTradeLot(parseInt(btn.getAttribute('data-id'))));
        });
        lotsCont.querySelectorAll('.btn-cancel-lot').forEach(btn => {
          btn.addEventListener('click', () => handleCancelTradeLot(parseInt(btn.getAttribute('data-id'))));
        });
      }

      const carCont = document.getElementById('market-caravans-container');
      const caravans = res.active_caravans || [];
      if (!caravans.length) {
        carCont.innerHTML = '<div class="text-center py-3 text-secondary">Faol savdo karvonlari yo‘q.</div>';
      } else {
        carCont.innerHTML = caravans.map(c => `
          <div class="card p-2 mb-2" style="font-size:11px;">
            <div class="d-flex justify-between">
              <strong class="text-gold">🐫 Karvon #${c.id}</strong>
              <span class="text-secondary">${c.seconds_remaining}s qoldi</span>
            </div>
            <div class="mt-1">Yuk: ${formatNum(c.resource_amount)} ${c.resource_type} | Kutilayotgan foyda: +${formatNum(c.expected_profit)}🪙</div>
          </div>
        `).join('');
      }
    } catch (err) {
      console.error('Market error:', err);
    }
  }

  async function handleCreateTradeLot() {
    if (isActionPending) return;
    const offRes = document.getElementById('market-offer-res')?.value || 'gold';
    const offAmt = parseInt(document.getElementById('market-offer-amt')?.value) || 0;
    const reqRes = document.getElementById('market-req-res')?.value || 'food';
    const reqAmt = parseInt(document.getElementById('market-req-amt')?.value) || 0;

    if (offAmt <= 0 || reqAmt <= 0) {
      showToast('Iltimos, to‘g‘ri resurs miqdorlarini kiriting.', 'error');
      return;
    }

    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/trade/create-lot', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          offer_resource: offRes,
          offer_amount: offAmt,
          request_resource: reqRes,
          request_amount: reqAmt,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'E‘lonni joylashtirib bo‘lmadi.');

      showToast('⚖️ E‘loningiz bozor peshtaxtasiga joylashtirildi!', 'success');
      haptic('heavy');
      await fetchDashboard();
      switchMarketTab('lots');
      await loadMarketData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleBuyTradeLot(lotId) {
    if (isActionPending) return;
    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/trade/buy', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ trade_id: lotId }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Taklifni sotib olib bo‘lmadi.');

      showToast('⚖️ Savdo muvaffaqiyatli amalga oshirildi!', 'success');
      haptic('heavy');
      await fetchDashboard();
      await loadMarketData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleCancelTradeLot(lotId) {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/trade/cancel-lot', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ trade_id: lotId }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'E‘lonni bekor qilib bo‘lmadi.');

      showToast('E‘lon bekor qilindi, resurslar qaytarildi.', 'info');
      await fetchDashboard();
      await loadMarketData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- RAVEN MESSENGER ---
  async function openRavenModal() {
    showModal('raven-modal');
    switchRavenTab('inbox');
    await loadRavenData();
  }

  function closeRavenModal() {
    hideModal('raven-modal');
  }

  function switchRavenTab(tab) {
    const vInbox = document.getElementById('raven-view-inbox');
    const vSend = document.getElementById('raven-view-send');

    document.getElementById('tab-raven-inbox-btn')?.classList.toggle('active', tab === 'inbox');
    document.getElementById('tab-raven-send-btn')?.classList.toggle('active', tab === 'send');

    if (vInbox) vInbox.style.display = (tab === 'inbox') ? 'block' : 'none';
    if (vSend) vSend.style.display = (tab === 'send') ? 'block' : 'none';
    haptic('light');
  }

  async function loadRavenData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/raven/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Pochta ma‘lumotini olib bo‘lmadi.');

      const cont = document.getElementById('raven-inbox-container');
      const messages = res.inbox || [];
      if (!messages.length) {
        cont.innerHTML = '<div class="text-center py-3 text-secondary">Qarg‘alar xat olib kelgani yo‘q. Sandiq bo‘sh.</div>';
      } else {
        cont.innerHTML = messages.map(m => `
          <div class="raven-scroll-card">
            <div class="d-flex justify-between" style="font-size:11px;">
              <strong class="text-gold">📜 ${escapeHtml(m.sender_name)}</strong>
              <span class="text-secondary">${m.date || ''}</span>
            </div>
            <p class="mt-1" style="font-size:12px; line-height:1.4;">${escapeHtml(m.message)}</p>
            ${m.attached_gold ? `<div class="mt-1 text-gold" style="font-size:11px;">🎁 Ilova: +${formatNum(m.attached_gold)}🪙</div>` : ''}
          </div>
        `).join('');
      }
    } catch (err) {
      console.error('Raven error:', err);
    }
  }

  async function handleSendRaven() {
    if (isActionPending) return;
    const receiverId = parseInt(document.getElementById('raven-receiver-id')?.value);
    const body = (document.getElementById('raven-message-body')?.value || '').trim();
    const gold = parseInt(document.getElementById('raven-attached-gold')?.value) || 0;

    if (!receiverId || body.length < 2) {
      showToast('Iltimos, qabul qiluvchi ID va xabar matnini kiriting.', 'error');
      return;
    }

    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/raven/send', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          receiver_telegram_id: receiverId,
          message_text: body,
          attached_gold: gold,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Qarg‘ani uchirib bo‘lmadi.');

      showToast('🦅 Qarg‘a qora qanotlari bilan xabarni olib uchdi!', 'success');
      haptic('heavy');
      document.getElementById('raven-message-body').value = '';
      await fetchDashboard();
      switchRavenTab('inbox');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- HERO & ARTIFACTS ---
  async function openHeroModal() {
    showModal('hero-modal');
    await loadHeroData();
  }

  function closeHeroModal() {
    hideModal('hero-modal');
  }

  async function loadHeroData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/hero/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Qahramon ma‘lumotini olib bo‘lmadi.');

      const h = res.hero || {};
      document.getElementById('hero-name-val').textContent = h.name || 'Lord Chempioni';
      document.getElementById('hero-atk-val').textContent = formatNum(h.attack || 50);
      document.getElementById('hero-def-val').textContent = formatNum(h.defense || 50);

      const eqArt = res.equipped_artifact;
      const eqName = document.getElementById('equipped-artifact-name');
      const unequipBtn = document.getElementById('btn-unequip-artifact');

      if (eqArt) {
        eqName.innerHTML = `<span class="text-gold">⚔️ ${escapeHtml(eqArt.name)}</span> <small class="text-secondary">(+${eqArt.attack_bonus} Atk, +${eqArt.defense_bonus} Def)</small>`;
        if (unequipBtn) unequipBtn.style.display = 'block';
      } else {
        eqName.textContent = 'Hech narsa taqilmagan';
        if (unequipBtn) unequipBtn.style.display = 'none';
      }

      const listCont = document.getElementById('hero-artifacts-container');
      const artifacts = res.artifacts || [];
      if (!artifacts.length) {
        listCont.innerHTML = '<div class="text-center py-2 text-secondary" style="font-size:11px;">Hozirda sandiqda artefaktlar yo‘q.</div>';
      } else {
        listCont.innerHTML = artifacts.map(a => `
          <div class="artifact-card ${a.is_equipped ? 'equipped' : ''}">
            <div>
              <strong class="text-gold">${escapeHtml(a.name)}</strong>
              <div class="text-secondary" style="font-size:11px;">+${a.attack_bonus} Atk | +${a.defense_bonus} Def</div>
            </div>
            ${a.is_equipped
              ? `<span class="badge badge-active">Taqilgan</span>`
              : `<button class="btn btn-secondary py-1 px-3 btn-equip-art" data-id="${a.id}">Kiyish</button>`
            }
          </div>
        `).join('');

        listCont.querySelectorAll('.btn-equip-art').forEach(btn => {
          btn.addEventListener('click', () => handleEquipArtifact(parseInt(btn.getAttribute('data-id'))));
        });
      }
    } catch (err) {
      console.error('Hero error:', err);
    }
  }

  async function handleEquipArtifact(artifactId) {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/hero/equip', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ artifact_id: artifactId }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Artefaktni kiyib bo‘lmadi.');

      showToast('🗡️ Artefakt jangovar qurollaringizga qo‘shildi!', 'success');
      haptic('heavy');
      await fetchDashboard();
      await loadHeroData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleUnequipArtifact() {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/hero/unequip', { method: 'POST', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Artefaktni yechib bo‘lmadi.');

      showToast('Artefakt yechib olindi.', 'info');
      await fetchDashboard();
      await loadHeroData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- VIP & KOSMETIKA DO'KONI (COSMETICS & ETHICAL MONETIZATION) ---
  let cachedCosmeticsHub = null;
  let currentShopCategory = 'special_and_vip';

  async function openDonateModal() {
    showModal('donate-modal');
    await loadCosmeticsHub();
  }

  function closeDonateModal() {
    hideModal('donate-modal');
  }

  async function loadCosmeticsHub() {
    const container = document.getElementById('cosmetics-items-container');
    if (!container) return;
    container.innerHTML = '<div class="text-center text-secondary py-3">⏳ Do‘kon yuklanmoqda...</div>';

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/cosmetics/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Do‘konni yuklab bo‘lmadi.');

      cachedCosmeticsHub = res.donate_hub || res.cosmetics_hub;
      renderCosmeticsHubHeader(cachedCosmeticsHub);
      renderCosmeticsCategory(currentShopCategory);
    } catch (err) {
      console.error('Cosmetics load error:', err);
      container.innerHTML = `<div class="text-danger text-center py-3">❌ Xatolik: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderCosmeticsHubHeader(hub) {
    if (!hub) return;
    const isVip = hub.is_vip_active;
    const statusText = document.getElementById('user-vip-status-text');
    const badge = document.getElementById('user-vip-badge');
    const expiry = document.getElementById('user-vip-expiry');

    if (statusText) statusText.textContent = isVip ? '👑 Oliyjanob Lord (Noble VIP)' : 'Oddiy Lord';
    if (badge) {
      badge.textContent = isVip ? 'FAOL VIP' : 'BEPUL';
      badge.style.background = isVip ? '#d4af37' : '#444';
      badge.style.color = isVip ? '#000' : '#fff';
    }
    if (expiry) {
      if (isVip && hub.vip_until) {
        expiry.style.display = 'block';
        expiry.textContent = `VIP muddati: ${hub.vip_until.replace('T', ' ').slice(0, 16)} gacha`;
      } else {
        expiry.style.display = 'none';
      }
    }
  }

  function renderCosmeticsCategory(catKey) {
    const container = document.getElementById('cosmetics-items-container');
    if (!container || !cachedCosmeticsHub) return;

    const catalog = cachedCosmeticsHub.catalog || {};
    const items = catalog[catKey] || [];
    const ownedSet = new Set(cachedCosmeticsHub.owned_items || []);
    const equippedMap = cachedCosmeticsHub.equipped || {};

    if (items.length === 0) {
      container.innerHTML = '<div class="text-center text-secondary py-3">Ushbu bo‘limda buyumlar mavjud emas.</div>';
      return;
    }

    let html = '';
    items.forEach(item => {
      const isOwned = ownedSet.has(item.id) || (item.category === 'starter_pack' && cachedCosmeticsHub.has_starter_pack);
      const isVipSub = (item.category === 'vip_subscription');
      const isEquipped = (
        equippedMap.avatar_frame === item.id ||
        equippedMap.castle_skin === item.id ||
        equippedMap.dragon_skin === item.id ||
        equippedMap.message_effect === item.id ||
        equippedMap.title === item.name
      );

      const rarityColor = item.rarity === 'afsonaviy' ? '#ff9900' : item.rarity === 'nodir' ? '#00bfff' : '#aaa';
      const rarityBadge = `<span class="badge" style="background:${rarityColor}22; color:${rarityColor}; border:1px solid ${rarityColor}; font-size:10px;">${escapeHtml(item.rarity_label || item.rarity || 'Oddiy')}</span>`;

      html += `
        <div class="card p-3 mb-2" style="border-left: 3px solid ${rarityColor}; background: rgba(20,20,25,0.7);">
          <div class="d-flex justify-between align-center mb-1">
            <h4 class="font-serif text-gold" style="margin:0; font-size:14px;">${escapeHtml(item.name)}</h4>
            ${rarityBadge}
          </div>
          <p class="text-secondary mt-1" style="font-size:11px; line-height:1.4; white-space:pre-line;">${escapeHtml(item.description || '')}</p>
          <div class="d-flex justify-between align-center mt-2 pt-2" style="border-top:1px solid rgba(255,255,255,0.08);">
            <div>
              <span class="text-gold font-bold" style="font-size:13px;">⭐ ${item.price_stars} Stars</span>
              ${item.price_uzs ? `<span class="text-secondary ms-2" style="font-size:11px;">(${formatNum(item.price_uzs)} so'm)</span>` : ''}
            </div>
            <div class="d-flex gap-1">
              ${isOwned && !isVipSub && item.category !== 'starter_pack' ? `
                <button class="btn ${isEquipped ? 'btn-secondary' : 'btn-primary'} py-1 px-3 btn-equip-cosmetic" data-item-id="${item.id}" style="font-size:11px;">
                  ${isEquipped ? '❌ Yechish' : '✅ Taqish'}
                </button>
              ` : isOwned ? `
                <span class="badge" style="background:#28a745; color:#fff; font-size:11px; padding:4px 8px;">Xarid qilingan</span>
              ` : `
                <button class="btn btn-primary py-1 px-2 btn-buy-cosmetic" data-item-id="${item.id}" style="font-size:11px;">
                  ⭐ Xarid
                </button>
                <button class="btn btn-secondary py-1 px-2 btn-gift-cosmetic" data-item-id="${item.id}" style="font-size:11px;">
                  🎁 Sovg'a
                </button>
              `}
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;

    // Attach button listeners
    container.querySelectorAll('.btn-equip-cosmetic').forEach(b => {
      b.addEventListener('click', () => handleEquipCosmetic(b.getAttribute('data-item-id')));
    });
    container.querySelectorAll('.btn-buy-cosmetic').forEach(b => {
      b.addEventListener('click', () => handleBuyCosmetic(b.getAttribute('data-item-id')));
    });
    container.querySelectorAll('.btn-gift-cosmetic').forEach(b => {
      b.addEventListener('click', () => handleGiftCosmetic(b.getAttribute('data-item-id')));
    });
  }

  async function handleEquipCosmetic(itemId) {
    if (isActionPending || !itemId) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/cosmetics/equip', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ item_id: itemId })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Buyumni taqib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('light');
      cachedCosmeticsHub = res.donate_hub || res.cosmetics_hub;
      renderCosmeticsCategory(currentShopCategory);
      await fetchDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleBuyCosmetic(itemId) {
    if (isActionPending || !itemId) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/cosmetics/buy', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          item_id: itemId,
          payment_provider: 'telegram_stars'
        })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Xaridni amalga oshirib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      cachedCosmeticsHub = res.donate_hub || res.cosmetics_hub;
      renderCosmeticsHubHeader(cachedCosmeticsHub);
      renderCosmeticsCategory(currentShopCategory);
      await fetchDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleGiftCosmetic(itemId) {
    if (isActionPending || !itemId) return;
    const recipientTg = prompt("Sovg'a yuboriluvchi Lordning Telegram ID sini kiriting:");
    if (!recipientTg) return;

    const rId = parseInt(recipientTg.trim());
    if (!rId || isNaN(rId)) {
      showToast("Noto'g'ri Telegram ID kiritildi.", 'error');
      return;
    }

    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/cosmetics/gift', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          recipient_telegram_id: rId,
          item_id: itemId,
          payment_provider: 'telegram_stars'
        })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Sovg‘ani yuborib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- ADMIN CONSOLE ---
  async function openAdminModal() {
    showModal('admin-modal');
    await loadAdminData();
  }

  function closeAdminModal() {
    hideModal('admin-modal');
  }

  async function loadAdminData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/dashboard', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Admin panelni yuklab bo‘lmadi.');

      document.getElementById('admin-stat-users').textContent = `${formatNum(res.total_users || 0)} / ${res.online_today || 0}`;
      document.getElementById('admin-stat-houses').textContent = `${res.total_houses || 0} / ${res.total_castles || 22}`;

      await loadAdminErrorLogs();
      await loadAdminTransactions();
    } catch (err) {
      console.error('Admin error:', err);
      showToast(err.message, 'error');
    }
  }

  async function handleAdminBan() {
    if (isActionPending) return;
    const tgId = parseInt(document.getElementById('admin-ban-tgid')?.value);
    const isBanned = (document.getElementById('admin-ban-status')?.value === 'true');

    if (!tgId) {
      showToast('Iltimos, Telegram ID kiriting.', 'error');
      return;
    }

    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/ban-player', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          target_telegram_id: tgId,
          is_banned: isBanned,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Holatni o‘zgartirib bo‘lmadi.');

      showToast(`O‘yinchi holati yangilandi: ${isBanned ? 'Bloklandi' : 'Blokdan chiqarildi'}.`, 'success');
      haptic('heavy');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleAdminAdjustResources() {
    if (isActionPending) return;
    const tgId = parseInt(document.getElementById('admin-res-tgid')?.value);
    const resType = document.getElementById('admin-res-type')?.value;
    const delta = parseInt(document.getElementById('admin-res-delta')?.value) || 0;

    if (!tgId || delta === 0) {
      showToast('Iltimos, ID va to‘g‘ri miqdor kiriting.', 'error');
      return;
    }

    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/adjust-resources', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          target_telegram_id: tgId,
          resource_type: resType,
          delta_amount: delta,
        }),
      });

      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Resursni o‘tkazib bo‘lmadi.');

      showToast(`Resurs muvaffaqiyatli moslashtirildi: ${delta > 0 ? '+' : ''}${delta} ${resType}!`, 'success');
      haptic('heavy');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- ADMIN SYSTEM ERROR LOGS ---
  async function loadAdminErrorLogs() {
    const container = document.getElementById('admin-errors-list-container');
    if (!container) return;

    container.innerHTML = '<div class="text-muted text-center py-2" style="font-size:12px;">⏳ Xatoliklar jurnali yuklanmoqda...</div>';

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/errors/admin/list?limit=25', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Xatolarni yuklab bo‘lmadi.');

      const errors = res.errors || [];
      if (errors.length === 0) {
        container.innerHTML = '<div class="text-success text-center py-2" style="font-size:12px;">✅ Qayd etilgan tizim xatoliklari mavjud emas!</div>';
        return;
      }

      let html = '';
      errors.forEach(err => {
        const sourceBadge = err.source === 'miniapp' ? '<span class="badge bg-info text-dark" style="font-size:10px;">📱 MiniApp</span>'
          : err.source === 'api' ? '<span class="badge bg-warning text-dark" style="font-size:10px;">⚡ API</span>'
          : '<span class="badge bg-primary" style="font-size:10px;">🤖 Bot</span>';

        const statusBadge = err.is_resolved
          ? '<span class="badge bg-success" style="font-size:10px;">✅ Hal qilindi</span>'
          : `<button class="btn btn-sm btn-outline-warning py-0 px-2 btn-resolve-err" data-err-id="${err.id}" style="font-size:10px;">🛠️ Hal qilish</button>`;

        const countBadge = (err.occurrence_count && err.occurrence_count > 1)
          ? `<span class="badge bg-danger ms-1" style="font-size:10px;">${err.occurrence_count}x</span>`
          : '';

        const timeStr = err.last_seen_at ? err.last_seen_at.replace('T', ' ').slice(0, 19) : '';

        html += `
          <div class="card p-2 mb-2" style="background: rgba(20, 25, 35, 0.85); border: 1px solid ${err.is_resolved ? 'rgba(74, 222, 128, 0.2)' : 'rgba(239, 68, 68, 0.4)'}; border-radius: 6px;">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <div>
                ${sourceBadge} ${countBadge}
                <strong style="font-size:12px; color: #f87171;" class="ms-1">${escapeHtml(err.error_type || 'Xato')}</strong>
              </div>
              <div style="font-size:10px; color: #94a3b8;">${timeStr}</div>
            </div>
            <div style="font-size:11px; color: #e2e8f0; word-break: break-word;" class="mb-1">
              ${escapeHtml(err.error_message || '')}
            </div>
            <div class="d-flex justify-content-between align-items-center" style="font-size:10px; color: #64748b;">
              <span>Joy: <code>${escapeHtml(err.handler_name || 'Noma\'lum')}</code>${err.user_telegram_id ? ` | TG: <code>${err.user_telegram_id}</code>` : ''}</span>
              <div>${statusBadge}</div>
            </div>
          </div>
        `;
      });

      container.innerHTML = html;

      // Attach resolve button event listeners
      container.querySelectorAll('.btn-resolve-err').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const errId = parseInt(btn.getAttribute('data-err-id'));
          if (errId) await handleResolveAdminError(errId);
        });
      });
    } catch (e) {
      console.error('Error loading admin error logs:', e);
      container.innerHTML = `<div class="text-danger text-center py-2" style="font-size:12px;">❌ Xatolarni yuklashda xatolik: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function handleResolveAdminError(errorId) {
    if (isActionPending) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/errors/admin/resolve', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ error_id: errorId })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Xatoni hal qilib bo‘lmadi.');

      showToast('Xatolik hal qilingan deb belgilandi.', 'success');
      haptic('medium');
      await loadAdminErrorLogs();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- ADMIN TRANSACTIONS & REFUNDS ---
  async function loadAdminTransactions() {
    const container = document.getElementById('admin-txs-list-container');
    if (!container) return;

    container.innerHTML = '<div class="text-muted text-center py-2" style="font-size:12px;">⏳ Xaridlar jurnali yuklanmoqda...</div>';

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/transactions', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Tranzaksiyalarni yuklab bo‘lmadi.');

      const txs = res.transactions || [];
      if (txs.length === 0) {
        container.innerHTML = '<div class="text-secondary text-center py-2" style="font-size:12px;">Xaridlar hozircha mavjud emas.</div>';
        return;
      }

      let html = '';
      txs.forEach(t => {
        const isRefunded = (t.status === 'refunded');
        const statusBadge = isRefunded
          ? '<span class="badge" style="background:#dc3545; color:#fff; font-size:10px;">Qaytarilgan (Refund)</span>'
          : '<span class="badge" style="background:#28a745; color:#fff; font-size:10px;">Bajarilgan</span>';

        html += `
          <div class="card p-2 mb-2" style="background:rgba(255,255,255,0.03); border-left:3px solid ${isRefunded ? '#dc3545' : '#28a745'};">
            <div class="d-flex justify-between align-center">
              <div>
                <strong class="text-gold" style="font-size:12px;">#${t.id} ${escapeHtml(t.item_name)}</strong>
                <span class="text-secondary ms-1" style="font-size:10px;">(${escapeHtml(t.provider)})</span>
              </div>
              ${statusBadge}
            </div>
            <div class="d-flex justify-between align-center mt-1" style="font-size:11px;">
              <span class="text-secondary">TG: ${t.telegram_id} ${t.is_gift ? `➡️ ${t.recipient_telegram_id}` : ''}</span>
              <span class="text-gold">⭐ ${t.amount_stars} (${formatNum(t.amount_uzs)} so'm)</span>
            </div>
            <div class="d-flex justify-between align-center mt-1 pt-1" style="border-top:1px solid rgba(255,255,255,0.05); font-size:10px;">
              <span class="text-secondary">${escapeHtml(t.created_at)}</span>
              ${!isRefunded ? `
                <button class="btn btn-outline-danger btn-sm py-0 px-2 btn-refund-tx" data-tx-id="${t.id}" style="font-size:10px;">
                  Bekor qilish (Refund)
                </button>
              ` : ''}
            </div>
          </div>
        `;
      });

      container.innerHTML = html;

      container.querySelectorAll('.btn-refund-tx').forEach(b => {
        b.addEventListener('click', async () => {
          const txId = parseInt(b.getAttribute('data-tx-id'));
          if (txId && confirm(`#${txId} tranzaksiyani bekor qilish va qaytarishni tasdiqlaysizmi?`)) {
            await handleAdminRefund(txId);
          }
        });
      });
    } catch (e) {
      console.error('Error loading admin txs:', e);
      container.innerHTML = `<div class="text-danger text-center py-2" style="font-size:12px;">❌ Xatolik: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function handleAdminRefund(txId) {
    if (isActionPending || !txId) return;
    isActionPending = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/refund', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ tx_id: txId })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Qaytarib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      await loadAdminTransactions();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // --- SEASON & SEASON PASS LOGIC ---
  let cachedSeasonData = null;

  async function openSeasonModal() {
    showModal('season-modal');
    await loadSeasonData();
  }

  function closeSeasonModal() {
    hideModal('season-modal');
  }

  async function loadSeasonData() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/season/hub', { method: 'GET', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Mavsum ma‘lumotlarini yuklab bo‘lmadi.');

      cachedSeasonData = res.data;
      renderSeasonHub(res.data);
    } catch (err) {
      console.error('Season load error:', err);
      showToast(err.message, 'error');
    }
  }

  function renderSeasonHub(data) {
    if (!data) return;
    const season = data.season || {};
    const ps = data.player_state || {};
    const tiers = data.tiers || [];
    const leaderboard = data.leaderboard || [];
    const fame = data.hall_of_fame || [];

    // Header & Countdown
    const badgeEl = document.getElementById('sp-season-badge');
    if (badgeEl) badgeEl.textContent = `👑 ${season.season_number || 1}-Mavsum`;

    const countdownEl = document.getElementById('sp-countdown');
    if (countdownEl) countdownEl.textContent = `⏳ ${season.days_left || 0}k ${season.hours_left || 0}s ${season.minutes_left || 0}d`;

    const titleEl = document.getElementById('sp-theme-title');
    if (titleEl) titleEl.textContent = season.title || 'Temir Taxt Qadami';

    const descEl = document.getElementById('sp-theme-desc');
    if (descEl) descEl.textContent = season.theme_description || '';

    // Profile Quick Banner
    const profSeasonTitle = document.getElementById('prof-season-title');
    if (profSeasonTitle) profSeasonTitle.textContent = `${season.season_number || 1}-Mavsum: ${season.title || 'Temir Taxt Qadami'}`;

    const profSeasonSub = document.getElementById('prof-season-status-sub');
    if (profSeasonSub) profSeasonSub.textContent = `Tier ${ps.pass_tier || 1} • ${formatNum(ps.season_points || 0)} SO • ${ps.has_premium_pass ? '👑 Premium' : 'Bepul'}`;

    // Player Status
    const myPointsEl = document.getElementById('sp-my-points');
    if (myPointsEl) myPointsEl.textContent = `⭐ ${formatNum(ps.season_points || 0)} SO`;

    const myRankEl = document.getElementById('sp-my-rank');
    if (myRankEl) myRankEl.textContent = `Reyting: #${ps.my_rank || 1}`;

    const myTierLbl = document.getElementById('sp-my-tier-lbl');
    if (myTierLbl) myTierLbl.textContent = `Tier ${ps.pass_tier || 1} / 20`;

    const myXpLbl = document.getElementById('sp-my-xp-lbl');
    if (myXpLbl) myXpLbl.textContent = `${ps.xp_in_current_tier || 0} / 100 XP`;

    const xpPct = Math.min(100, Math.floor(((ps.xp_in_current_tier || 0) / 100) * 100));
    const xpBar = document.getElementById('sp-xp-bar');
    if (xpBar) xpBar.style.width = `${xpPct}%`;

    // Buy Button status
    const buyBtn = document.getElementById('btn-sp-buy-pass');
    if (buyBtn) {
      if (ps.has_premium_pass) {
        buyBtn.textContent = '👑 Premium Pass Faol';
        buyBtn.disabled = true;
        buyBtn.classList.remove('btn-primary');
        buyBtn.classList.add('btn-secondary');
      } else {
        buyBtn.textContent = '⭐ Premium Pass (250 Stars)';
        buyBtn.disabled = false;
        buyBtn.classList.add('btn-primary');
        buyBtn.classList.remove('btn-secondary');
      }
    }

    // Render 20 Tiers Track
    const tiersContainer = document.getElementById('sp-tiers-container');
    if (tiersContainer) {
      tiersContainer.innerHTML = tiers.map(t => {
        const isReached = t.is_reached;
        const free = t.free || {};
        const prem = t.premium || {};

        const getBtnHtml = (trk, info) => {
          if (info.status === 'claimed') {
            return `<button class="btn-tier-claim claimed">✅ Olindi</button>`;
          } else if (info.status === 'claimable') {
            return `<button class="btn-tier-claim claimable" data-tier="${t.tier}" data-track="${trk}">🎁 Olish</button>`;
          } else if (info.status === 'requires_premium') {
            return `<button class="btn-tier-claim requires-premium" data-action="buy_pass">⭐ Pass Kerak</button>`;
          } else {
            return `<button class="btn-tier-claim locked" disabled>🔒 Qulf</button>`;
          }
        };

        return `
          <div class="tier-item-row ${isReached ? 'reached' : ''}">
            <div class="tier-badge-col">
              <span class="tier-badge-num">T${t.tier}</span>
              <span style="font-size:9px; color:var(--text-secondary);">${t.xp_required}XP</span>
            </div>
            <div class="tier-cards-container">
              <!-- Free Track -->
              <div class="tier-track-card free">
                <div>
                  <div class="tier-track-label">Bepul</div>
                  <div class="tier-reward-title">${free.icon || '🎖️'} ${escapeHtml(free.name)}</div>
                </div>
                ${getBtnHtml('free', free)}
              </div>
              <!-- Premium Track -->
              <div class="tier-track-card premium">
                <div>
                  <div class="tier-track-label">👑 Premium</div>
                  <div class="tier-reward-title">${prem.icon || '⭐'} ${escapeHtml(prem.name)}</div>
                </div>
                ${getBtnHtml('premium', prem)}
              </div>
            </div>
          </div>
        `;
      }).join('');

      // Wire claim listeners
      tiersContainer.querySelectorAll('.btn-tier-claim.claimable').forEach(b => {
        b.addEventListener('click', async () => {
          const tier = parseInt(b.getAttribute('data-tier'));
          const track = b.getAttribute('data-track');
          await handleClaimTier(tier, track);
        });
      });

      tiersContainer.querySelectorAll('.btn-tier-claim.requires-premium').forEach(b => {
        b.addEventListener('click', () => {
          haptic('light');
          handleBuySeasonPass();
        });
      });
    }

    // Render Leaderboard
    const lbContainer = document.getElementById('sp-leaderboard-list');
    if (lbContainer) {
      if (!leaderboard.length) {
        lbContainer.innerHTML = '<div class="text-secondary text-center py-2" style="font-size:11px;">Mavsum reytingi shakllanmoqda...</div>';
      } else {
        lbContainer.innerHTML = leaderboard.map(l => `
          <div class="card p-2 mb-2 d-flex justify-between align-center" style="font-size:11px; background:rgba(255,255,255,0.02);">
            <div>
              <strong class="text-gold">#${l.rank} ${escapeHtml(l.name)}</strong>
              <div class="text-secondary" style="font-size:10px;">${escapeHtml(l.title)} • Tier ${l.pass_tier}</div>
            </div>
            <span class="season-so-pill">${formatNum(l.season_points)} SO</span>
          </div>
        `).join('');
      }
    }

    // Render Hall of Fame
    const fameContainer = document.getElementById('sp-fame-list');
    if (fameContainer) {
      if (!fame.length) {
        fameContainer.innerHTML = '<div class="text-secondary text-center py-2" style="font-size:11px;">Hozircha yakunlangan mavsumlar yo‘q.</div>';
      } else {
        fameContainer.innerHTML = fame.map(h => `
          <div class="card p-2 mb-2" style="font-size:11px; border-left:3px solid #d4af37;">
            <div class="d-flex justify-between align-center">
              <strong class="text-gold font-serif">${h.season_number}-Mavsum Chempioni</strong>
              <span class="text-secondary" style="font-size:10px;">${escapeHtml(h.concluded_at)}</span>
            </div>
            <div class="mt-1">
              👑 Qirol: <strong>${escapeHtml(h.king_name)}</strong> (${escapeHtml(h.winner_house_name)})<br>
              ⭐ Eng ko'p SO: <strong>${escapeHtml(h.top_so_player_name)}</strong> (${formatNum(h.top_so_points)} SO)
            </div>
          </div>
        `).join('');
      }
    }
  }

  async function handleClaimTier(tier, track) {
    if (isActionPending) return;
    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/season/claim-tier', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ tier: tier, track: track })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Mukofotni olib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      await loadSeasonData();
      await fetchDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleClaimAllSeasonTiers() {
    if (isActionPending) return;
    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/season/claim-all', { method: 'POST', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Mukofotlarni olib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      await loadSeasonData();
      await fetchDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleBuySeasonPass() {
    if (isActionPending) return;
    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/season/buy-pass', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ payment_method: 'stars' })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Pass xarid qilib bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      await loadSeasonData();
      await fetchDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleAdminUpdateSeason() {
    if (isActionPending) return;
    const title = document.getElementById('admin-season-title')?.value;
    const desc = document.getElementById('admin-season-desc')?.value;
    const extendDays = parseInt(document.getElementById('admin-season-extend-days')?.value) || 0;

    isActionPending = true;
    haptic('medium');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/season/update', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          title: title || undefined,
          theme_description: desc || undefined,
          extend_days: extendDays || undefined,
        })
      });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Mavsumni yangilab bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      await loadAdminData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  async function handleAdminConcludeSeason() {
    if (isActionPending) return;
    if (!confirm('⚠️ DIQQAT! Mavsumni majburiy yakunlash, barcha o‘yinchilarga yakuniy mukofotlarni berish va Yumshoq Reset (Soft-Reset) qilishni tasdiqlaysizmi?')) {
      return;
    }

    isActionPending = true;
    haptic('heavy');
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/admin/season/conclude', { method: 'POST', headers: headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) throw new Error(res.detail || 'Mavsumni yakunlab bo‘lmadi.');

      showToast(res.message, 'success');
      haptic('heavy');
      await loadAdminData();
      await fetchDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      isActionPending = false;
    }
  }

  // ============================================================
  // FEATURE 12: AI COUNCIL ADVISOR ("KENGASH MASLAHATCHISI")
  // ============================================================
  let isAiQueryPending = false;

  async function openAiAdvisorModal() {
    showModal('ai-modal');
    await loadAiAdvisorStatus();
    const input = document.getElementById('ai-query-input');
    if (input) setTimeout(() => input.focus(), 300);
  }

  function closeAiAdvisorModal() {
    hideModal('ai-modal');
  }

  async function loadAiAdvisorStatus() {
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/ai/status', { headers });
      const res = await resp.json();
      if (!resp.ok || !res.success) return;

      const badge = document.getElementById('ai-quota-badge');
      if (badge) {
        badge.textContent = `${res.remaining_today}/${res.daily_limit} qoldi`;
        badge.style.background = res.remaining_today > 0 ? 'var(--gold-primary)' : '#e74c3c';
        badge.style.color = res.remaining_today > 0 ? '#000' : '#fff';
      }

      const profSub = document.getElementById('prof-ai-status-sub');
      if (profSub) {
        profSub.textContent = `Buyuk Meyster • ${res.remaining_today} ta savol qoldi`;
      }
    } catch (e) {
      console.warn('AI status yuklashda xatolik:', e);
    }
  }

  function appendAiMessage(role, text) {
    const chat = document.getElementById('ai-chat-history');
    if (!chat) return;

    const bubble = document.createElement('div');
    bubble.className = `ai-msg-bubble ${role === 'user' ? 'ai-msg-user' : 'ai-msg-advisor'}`;

    const formattedText = escapeHtml(text).replace(/\n/g, '<br>');
    if (role === 'user') {
      bubble.innerHTML = `
        <div class="d-flex align-center gap-1 mb-1 justify-end">
          <strong class="text-secondary" style="font-size:10px;">Siz:</strong>
          <span style="font-size:12px;">👤</span>
        </div>
        <p style="font-size:12px; margin:0; line-height:1.4; color:#fff;">${formattedText}</p>
      `;
    } else {
      bubble.innerHTML = `
        <div class="d-flex align-center gap-1 mb-1">
          <span style="font-size:14px;">🧙‍♂️</span>
          <strong class="text-gold" style="font-size:11px;">Buyuk Meyster:</strong>
        </div>
        <div style="font-size:12px; margin:0; line-height:1.45; color:var(--text-primary);">${formattedText}</div>
      `;
    }

    chat.appendChild(bubble);
    chat.scrollTop = chat.scrollHeight;
  }

  function showAiTyping() {
    const chat = document.getElementById('ai-chat-history');
    if (!chat) return null;
    const typing = document.createElement('div');
    typing.id = 'ai-typing-indicator';
    typing.className = 'ai-msg-bubble ai-msg-advisor';
    typing.innerHTML = `
      <div class="d-flex align-center gap-2">
        <span style="font-size:13px;">🧙‍♂️</span>
        <span class="text-secondary" style="font-size:11px;">Meyster mulohaza qilmoqda...</span>
        <span class="ai-typing-indicator">
          <span class="ai-typing-dot"></span>
          <span class="ai-typing-dot"></span>
          <span class="ai-typing-dot"></span>
        </span>
      </div>
    `;
    chat.appendChild(typing);
    chat.scrollTop = chat.scrollHeight;
    return typing;
  }

  function removeAiTyping() {
    const typing = document.getElementById('ai-typing-indicator');
    if (typing) typing.remove();
  }

  async function handleSendAiQuery(customQuery = null) {
    if (isAiQueryPending) return;

    const input = document.getElementById('ai-query-input');
    const query = (customQuery || (input ? input.value : '')).trim();
    if (!query) return;

    if (query.length > 300) {
      showToast('Savol juda uzun (maksimal 300 ta belgi).', 'error');
      return;
    }

    if (input) input.value = '';
    const counter = document.getElementById('ai-char-counter');
    if (counter) counter.textContent = '0 / 300';

    appendAiMessage('user', query);
    showAiTyping();

    isAiQueryPending = true;
    const btnSubmit = document.getElementById('btn-ai-submit');
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.textContent = 'Kutilmoqda...';
    }

    haptic('medium');

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      const resp = await fetch('/api/actions/ai/ask', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ query: query })
      });

      const res = await resp.json();
      removeAiTyping();

      if (!resp.ok || !res.success) {
        const errDetail = res.detail || 'Meyster javob bera olmadi.';
        appendAiMessage('advisor', `⚠️ ${errDetail}`);
        showToast(errDetail, 'error');
      } else {
        appendAiMessage('advisor', res.answer);
        haptic('light');

        if (res.metadata && res.metadata.remaining !== undefined) {
          const badge = document.getElementById('ai-quota-badge');
          if (badge) {
            badge.textContent = `${res.metadata.remaining}/${res.metadata.daily_limit} qoldi`;
            badge.style.background = res.metadata.remaining > 0 ? 'var(--gold-primary)' : '#e74c3c';
            badge.style.color = res.metadata.remaining > 0 ? '#000' : '#fff';
          }
          const profSub = document.getElementById('prof-ai-status-sub');
          if (profSub) {
            profSub.textContent = `Buyuk Meyster • ${res.metadata.remaining} ta savol qoldi`;
          }
        }
      }
    } catch (e) {
      removeAiTyping();
      appendAiMessage('advisor', '⚠️ Tarmoq xatoligi yoki maslahatchi bilan aloqa uzildi. Iltimos, keyinroq urinib ko‘ring.');
      showToast(e.message, 'error');
    } finally {
      isAiQueryPending = false;
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.textContent = 'Yuborish ➔';
      }
    }
  }

  // --- FRONTEND ERROR REPORTING (AUTOMATIC TELEGRAM ERROR LOGGING) ---
  const _reportedErrorsMap = new Map();

  async function reportFrontendError(errData) {
    if (!errData || !errData.error_message) return;

    const errMsg = String(errData.error_message);
    // Tashqi brauzerdan kesh/initData yo'qligi sababli oddiy xabarlarni log qilmaslik
    if (errMsg.includes('Autentifikatsiya talab qilinadi') ||
        errMsg.includes('Telegram ilovasi orqali kiring') ||
        errMsg.includes('initData yetishmayapti') ||
        errMsg.includes('401')) {
      return;
    }

    // Client-side debounce to prevent loop spam (max 1 of same error per 60 seconds)
    const errKey = `${errData.error_type || 'Error'}:${errData.error_message}`;
    const now = Date.now();
    const lastSent = _reportedErrorsMap.get(errKey) || 0;
    if (now - lastSent < 60000) {
      return; // Suppressed client-side
    }
    _reportedErrorsMap.set(errKey, now);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (currentInitData) headers['Authorization'] = `tma ${currentInitData}`;

      await fetch('/api/errors/report', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          error_type: (errData.error_type || 'ClientError').slice(0, 100),
          error_message: String(errData.error_message).slice(0, 1500),
          stack_trace: errData.stack_trace ? String(errData.stack_trace).slice(0, 4000) : null,
          location: (errData.location || (window.location ? window.location.pathname : 'app')).slice(0, 255),
          browser_info: navigator ? navigator.userAgent.slice(0, 255) : null,
          component: (errData.component || 'webapp').slice(0, 100)
        })
      });
    } catch (ignore) {
      // Do not throw from the error reporter
    }
  }

  // Global browser error listeners
  window.onerror = function(message, source, lineno, colno, error) {
    reportFrontendError({
      error_type: error ? (error.name || 'WindowError') : 'WindowError',
      error_message: String(message || 'Noma\'lum xatolik'),
      stack_trace: error ? error.stack : `${source}:${lineno}:${colno}`,
      location: window.location ? window.location.href : '',
      component: 'window.onerror'
    });
    return false;
  };

  window.addEventListener('unhandledrejection', function(event) {
    const reason = event.reason;
    const msg = (reason && reason.message) ? reason.message : String(reason || 'Unhandled Promise Rejection');
    reportFrontendError({
      error_type: (reason && reason.name) ? reason.name : 'UnhandledRejection',
      error_message: msg,
      stack_trace: (reason && reason.stack) ? reason.stack : null,
      location: window.location ? window.location.href : '',
      component: 'unhandledrejection'
    });
  });

  // 5. Loading & Error Handlers
  function showLoading(show) {
    const skeleton = document.getElementById('loading-skeleton');
    if (show) {
      skeleton.style.display = 'block';
    } else {
      skeleton.style.display = 'none';
    }
  }

  function showError(title, desc) {
    const panel = document.getElementById('error-panel');
    document.getElementById('error-title').textContent = title;
    document.getElementById('error-desc').textContent = desc;
    panel.style.display = 'block';

    reportFrontendError({
      error_type: 'UIErrorDisplay',
      error_message: `${title}: ${desc}`,
      location: activeTab || (window.location ? window.location.pathname : ''),
      component: 'showError'
    });
  }

  function hideError() {
    document.getElementById('error-panel').style.display = 'none';
  }

  // 6. Event Listeners Setup
  function setupListeners() {
    // Bottom Nav Tabs
    document.querySelectorAll('.bottom-nav .nav-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        if (tabId && tabId !== activeTab) {
          haptic('light');
          switchTab(tabId);
        }
      });
    });

    // Ranking Category Filter Chips
    document.querySelectorAll('.rankings-filter .filter-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        haptic('light');
        document.querySelectorAll('.rankings-filter .filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        activeRankingCategory = chip.getAttribute('data-category');
        if (cachedDashboardData) {
          renderRankings(cachedDashboardData.rankings);
        }
      });
    });

    // Daily streak claim button
    const claimStreakBtn = document.getElementById('btn-claim-streak');
    claimStreakBtn?.addEventListener('click', handleClaimStreak);

    // Recruit Modal Listeners (Feature 2)
    document.getElementById('modal-recruit-close')?.addEventListener('click', closeRecruitModal);
    document.getElementById('recruit-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'recruit-modal') closeRecruitModal();
    });

    document.getElementById('btn-amount-minus')?.addEventListener('click', () => {
      const input = document.getElementById('recruit-amount-input');
      let val = parseInt(input.value) || 10;
      input.value = Math.max(1, val - 10);
      updateRecruitCostPreview();
    });

    document.getElementById('btn-amount-plus')?.addEventListener('click', () => {
      const input = document.getElementById('recruit-amount-input');
      let val = parseInt(input.value) || 0;
      input.value = Math.min(100000, val + 10);
      updateRecruitCostPreview();
    });

    document.getElementById('recruit-amount-input')?.addEventListener('input', updateRecruitCostPreview);

    document.querySelectorAll('.quick-pills-row .pill-btn[data-amt]').forEach(pill => {
      pill.addEventListener('click', () => {
        haptic('light');
        const amt = parseInt(pill.getAttribute('data-amt')) || 10;
        document.getElementById('recruit-amount-input').value = amt;
        updateRecruitCostPreview();
      });
    });

    document.getElementById('btn-amt-max')?.addEventListener('click', () => {
      haptic('light');
      if (!currentRecruitUnit) return;
      const myGold = cachedDashboardData?.profile?.gold || 0;
      const myIron = cachedDashboardData?.profile?.iron || 0;
      const maxGold = Math.floor(myGold / currentRecruitUnit.goldCost);
      const maxIron = Math.floor(myIron / currentRecruitUnit.ironCost);
      const maxAffordable = Math.max(1, Math.min(maxGold, maxIron));
      document.getElementById('recruit-amount-input').value = maxAffordable;
      updateRecruitCostPreview();
    });

    document.getElementById('btn-confirm-recruit')?.addEventListener('click', handleConfirmRecruit);

    // Castle Tax Collection Listener (Feature 3)
    document.getElementById('btn-collect-all-tax')?.addEventListener('click', handleCollectAllTaxes);

    // Citadel Quiz & Royal Council Quests Listeners (Feature 4)
    document.getElementById('btn-open-citadel-quiz')?.addEventListener('click', openCitadelQuizModal);
    document.getElementById('modal-quiz-close')?.addEventListener('click', closeCitadelQuizModal);
    document.getElementById('quiz-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'quiz-modal') closeCitadelQuizModal();
    });

    document.getElementById('btn-open-council')?.addEventListener('click', openCouncilModal);
    document.getElementById('modal-council-close')?.addEventListener('click', closeCouncilModal);
    document.getElementById('council-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'council-modal') closeCouncilModal();
    });

    // 1v1 Duels Arena Listeners (Feature 5)
    document.getElementById('btn-open-duel-arena')?.addEventListener('click', openDuelModal);
    document.getElementById('banner-open-duel')?.addEventListener('click', openDuelModal);
    document.getElementById('modal-duel-close')?.addEventListener('click', closeDuelModal);
    document.getElementById('duel-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'duel-modal') closeDuelModal();
    });
    document.getElementById('btn-start-duel')?.addEventListener('click', handleStartDuel);

    // Iron Bank Listeners (Feature 6)
    document.getElementById('banner-open-bank')?.addEventListener('click', openBankModal);
    document.getElementById('modal-bank-close')?.addEventListener('click', closeBankModal);
    document.getElementById('bank-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'bank-modal') closeBankModal();
    });
    document.getElementById('bank-tab-btn-deposit')?.addEventListener('click', () => switchBankSubView('deposit'));
    document.getElementById('bank-tab-btn-loan')?.addEventListener('click', () => switchBankSubView('loan'));
    document.getElementById('btn-claim-bank-interest')?.addEventListener('click', handleBankClaimInterest);
    document.getElementById('btn-submit-bank-deposit')?.addEventListener('click', handleBankDeposit);
    document.getElementById('btn-submit-bank-withdraw')?.addEventListener('click', handleBankWithdraw);
    document.getElementById('btn-submit-bank-loan')?.addEventListener('click', handleBankTakeLoan);
    document.getElementById('btn-repay-bank-loan')?.addEventListener('click', handleBankRepayLoan);

    document.querySelectorAll('#bank-deposit-pills .pill-btn[data-amt]').forEach(pill => {
      pill.addEventListener('click', () => {
        haptic('light');
        const amt = parseInt(pill.getAttribute('data-amt')) || 1000;
        document.getElementById('bank-deposit-input').value = amt;
      });
    });

    document.getElementById('btn-bank-deposit-max')?.addEventListener('click', () => {
      haptic('light');
      const myGold = cachedDashboardData?.profile?.gold || 0;
      const canAdd = currentBankData?.deposit?.max_can_add || 50000;
      document.getElementById('bank-deposit-input').value = Math.min(myGold, canAdd);
    });

    // Guild Listeners (Feature 7)
    document.getElementById('row-open-guild')?.addEventListener('click', openGuildModal);
    document.getElementById('modal-guild-close')?.addEventListener('click', closeGuildModal);
    document.getElementById('guild-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'guild-modal') closeGuildModal();
    });

    const resGoldBtn = document.getElementById('btn-guild-res-gold');
    const resIronBtn = document.getElementById('btn-guild-res-iron');

    resGoldBtn?.addEventListener('click', () => {
      haptic('light');
      selectedGuildResource = 'gold';
      resGoldBtn.classList.add('active');
      resIronBtn?.classList.remove('active');
    });

    resIronBtn?.addEventListener('click', () => {
      haptic('light');
      selectedGuildResource = 'iron';
      resIronBtn.classList.add('active');
      resGoldBtn?.classList.remove('active');
    });

    document.querySelectorAll('#guild-deposit-pills .pill-btn[data-amt]').forEach(pill => {
      pill.addEventListener('click', () => {
        haptic('light');
        const amt = parseInt(pill.getAttribute('data-amt')) || 100;
        document.getElementById('guild-deposit-input').value = amt;
      });
    });

    document.getElementById('btn-submit-guild-deposit')?.addEventListener('click', handleGuildDeposit);
    document.getElementById('btn-buff-exp')?.addEventListener('click', () => handleGuildBuff('exp_boost'));
    document.getElementById('btn-buff-combat')?.addEventListener('click', () => handleGuildBuff('combat_boost'));
    document.getElementById('btn-buff-gather')?.addEventListener('click', () => handleGuildBuff('gather_boost'));

    // Refresh button
    const refreshBtn = document.getElementById('btn-refresh');
    refreshBtn?.addEventListener('click', () => {
      haptic('medium');
      fetchDashboard();
    });

    // Error retry button
    const retryBtn = document.getElementById('btn-retry');
    retryBtn?.addEventListener('click', () => {
      haptic('light');
      fetchDashboard();
    });

    // --- ONBOARDING LISTENERS ---
    document.getElementById('btn-submit-onboarding')?.addEventListener('click', handleRegisterPlayer);
    document.getElementById('btn-toggle-custom-house')?.addEventListener('click', () => {
      haptic('light');
      const f = document.getElementById('custom-house-fields');
      if (f) f.style.display = (f.style.display === 'none') ? 'block' : 'none';
    });

    // --- QUICK ACTION PORTALS LISTENERS ---
    document.getElementById('btn-open-map')?.addEventListener('click', openMapModal);
    document.getElementById('btn-castles-open-map')?.addEventListener('click', openMapModal);
    document.getElementById('banner-open-march')?.addEventListener('click', () => openMarchModal());
    document.getElementById('btn-open-dragon')?.addEventListener('click', openDragonModal);
    document.getElementById('btn-open-house')?.addEventListener('click', openHouseModal);
    document.getElementById('btn-open-market')?.addEventListener('click', openMarketModal);
    document.getElementById('btn-open-raven')?.addEventListener('click', openRavenModal);
    document.getElementById('btn-open-hero')?.addEventListener('click', openHeroModal);
    document.getElementById('btn-open-donate')?.addEventListener('click', openDonateModal);
    document.getElementById('btn-open-admin')?.addEventListener('click', openAdminModal);

    // --- MODAL CLOSE BUTTONS & OVERLAY CLICKS ---
    const closeBindings = [
      { closeId: 'modal-map-close', overlayId: 'map-modal', closeFn: closeMapModal },
      { closeId: 'modal-march-close', overlayId: 'march-modal', closeFn: closeMarchModal },
      { closeId: 'modal-scout-close', overlayId: 'scout-modal', closeFn: closeScoutModal },
      { closeId: 'modal-espionage-close', overlayId: 'espionage-modal', closeFn: closeEspionageModal },
      { closeId: 'modal-dragon-close', overlayId: 'dragon-modal', closeFn: closeDragonModal },
      { closeId: 'modal-house-close', overlayId: 'house-modal', closeFn: closeHouseModal },
      { closeId: 'modal-market-close', overlayId: 'market-modal', closeFn: closeMarketModal },
      { closeId: 'modal-raven-close', overlayId: 'raven-modal', closeFn: closeRavenModal },
      { closeId: 'modal-hero-close', overlayId: 'hero-modal', closeFn: closeHeroModal },
      { closeId: 'modal-donate-close', overlayId: 'donate-modal', closeFn: closeDonateModal },
      { closeId: 'modal-season-close', overlayId: 'season-modal', closeFn: closeSeasonModal },
      { closeId: 'modal-admin-close', overlayId: 'admin-modal', closeFn: closeAdminModal },
      { closeId: 'modal-ai-close', overlayId: 'ai-modal', closeFn: closeAiAdvisorModal },
    ];

    closeBindings.forEach(b => {
      document.getElementById(b.closeId)?.addEventListener('click', b.closeFn);
      document.getElementById(b.overlayId)?.addEventListener('click', (e) => {
        if (e.target.id === b.overlayId) b.closeFn();
      });
    });

    // Season Modal & Season Pass Listeners
    document.getElementById('profile-open-season-btn')?.addEventListener('click', () => {
      haptic('light');
      openSeasonModal();
    });

    // AI Council Advisor Listeners (Feature 12)
    document.getElementById('profile-open-ai-btn')?.addEventListener('click', () => {
      haptic('light');
      openAiAdvisorModal();
    });

    document.getElementById('btn-ai-submit')?.addEventListener('click', () => handleSendAiQuery());

    const aiInput = document.getElementById('ai-query-input');
    aiInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSendAiQuery();
      }
    });

    aiInput?.addEventListener('input', (e) => {
      const counter = document.getElementById('ai-char-counter');
      if (counter) counter.textContent = `${e.target.value.length} / 300`;
    });

    document.querySelectorAll('.ai-prompt-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        haptic('light');
        const p = chip.getAttribute('data-prompt');
        handleSendAiQuery(p);
      });
    });

    document.querySelectorAll('.season-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        haptic('light');
        document.querySelectorAll('.season-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.getAttribute('data-tab');
        document.querySelectorAll('.season-tab-content').forEach(c => c.style.display = 'none');
        const target = document.getElementById(`sp-tab-${tab}`);
        if (target) target.style.display = 'block';
      });
    });

    document.getElementById('btn-sp-buy-pass')?.addEventListener('click', handleBuySeasonPass);
    document.getElementById('btn-sp-claim-all')?.addEventListener('click', handleClaimAllSeasonTiers);
    document.getElementById('btn-admin-update-season')?.addEventListener('click', handleAdminUpdateSeason);
    document.getElementById('btn-admin-conclude-season')?.addEventListener('click', handleAdminConcludeSeason);

    // Map Region Filters
    document.querySelectorAll('#map-region-filters .pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        haptic('light');
        document.querySelectorAll('#map-region-filters .pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderMap(cachedTerritories, btn.getAttribute('data-region'));
      });
    });

    // March Percentage Buttons & Target Details
    document.querySelectorAll('#march-pct-pills .pill-btn').forEach(pill => {
      pill.addEventListener('click', () => {
        const pct = parseInt(pill.getAttribute('data-pct')) || 25;
        applyMarchPercentage(pct);
      });
    });

    document.getElementById('march-target-select')?.addEventListener('change', updateMarchTargetDetails);
    document.getElementById('march-dragon-toggle')?.addEventListener('change', (e) => {
      const row = document.getElementById('march-dragon-tactic-row');
      if (row) row.style.display = e.target.checked ? 'block' : 'none';
    });

    document.getElementById('btn-submit-march')?.addEventListener('click', handleDispatchMarch);

    // Espionage Mission Buttons
    document.querySelectorAll('.espionage-mission-card .btn-run-spy').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const m = btn.getAttribute('data-mission');
        handleExecuteSpyMission(m);
      });
    });

    // Dragon Nest Actions
    document.getElementById('btn-claim-dragon-egg')?.addEventListener('click', handleClaimDragonEgg);
    document.getElementById('btn-hatch-dragon')?.addEventListener('click', handleHatchDragon);
    document.getElementById('btn-feed-dragon')?.addEventListener('click', handleFeedDragon);
    document.getElementById('btn-train-dragon')?.addEventListener('click', handleTrainDragon);

    // House Deposit Resource Switcher
    const hGoldBtn = document.getElementById('btn-house-res-gold');
    const hIronBtn = document.getElementById('btn-house-res-iron');
    hGoldBtn?.addEventListener('click', () => {
      haptic('light');
      selectedHouseDepositResource = 'gold';
      hGoldBtn.classList.add('active');
      hIronBtn?.classList.remove('active');
    });
    hIronBtn?.addEventListener('click', () => {
      haptic('light');
      selectedHouseDepositResource = 'iron';
      hIronBtn.classList.add('active');
      hGoldBtn?.classList.remove('active');
    });
    document.getElementById('btn-submit-house-deposit')?.addEventListener('click', handleHouseDeposit);

    // Market Tabs & Submit
    document.getElementById('tab-market-lots-btn')?.addEventListener('click', () => switchMarketTab('lots'));
    document.getElementById('tab-market-create-btn')?.addEventListener('click', () => switchMarketTab('create'));
    document.getElementById('tab-market-caravans-btn')?.addEventListener('click', () => switchMarketTab('caravans'));
    document.getElementById('btn-submit-market-lot')?.addEventListener('click', handleCreateTradeLot);

    // Raven Tabs & Send
    document.getElementById('tab-raven-inbox-btn')?.addEventListener('click', () => switchRavenTab('inbox'));
    document.getElementById('tab-raven-send-btn')?.addEventListener('click', () => switchRavenTab('send'));
    document.getElementById('btn-submit-raven')?.addEventListener('click', handleSendRaven);

    // Hero Unequip
    document.getElementById('btn-unequip-artifact')?.addEventListener('click', handleUnequipArtifact);

    // Shop Category Tabs
    document.querySelectorAll('.shop-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        haptic('light');
        document.querySelectorAll('.shop-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentShopCategory = tab.getAttribute('data-cat') || 'special_and_vip';
        renderCosmeticsCategory(currentShopCategory);
      });
    });

    // Admin Console Actions
    document.getElementById('btn-submit-admin-ban')?.addEventListener('click', handleAdminBan);
    document.getElementById('btn-submit-admin-res')?.addEventListener('click', handleAdminAdjustResources);
    document.getElementById('btn-refresh-admin-errors')?.addEventListener('click', loadAdminErrorLogs);
    document.getElementById('btn-refresh-admin-txs')?.addEventListener('click', loadAdminTransactions);
  }

  // ============================================================
  // STAGE 6: DEEP-LINK ROUTING (TELEGRAM START PARAMETERS)
  // ============================================================

  function handleDeepLinkRouting() {
    const params = new URLSearchParams(window.location.search);
    const startParam = tg?.initDataUnsafe?.start_param || params.get('startapp') || params.get('tab') || window.location.hash.replace('#', '');
    if (!startParam) return;

    console.log('Deep link route detected:', startParam);

    switch (startParam.toLowerCase()) {
      case 'castles':
      case 'tab-castles':
        switchTab('tab-castles');
        break;
      case 'army':
      case 'military':
      case 'tab-army':
        switchTab('tab-army');
        break;
      case 'rankings':
      case 'ranks':
      case 'tab-rankings':
        switchTab('tab-rankings');
        break;
      case 'world':
      case 'events':
      case 'tab-world':
        switchTab('tab-world');
        break;
      case 'map':
        switchTab('tab-profile');
        setTimeout(() => openMapModal(), 300);
        break;
      case 'march':
        switchTab('tab-army');
        setTimeout(() => openMarchModal(), 300);
        break;
      case 'dragon':
        switchTab('tab-profile');
        setTimeout(() => openDragonModal(), 300);
        break;
      case 'house':
        switchTab('tab-profile');
        setTimeout(() => openHouseModal(), 300);
        break;
      case 'market':
      case 'trade':
        switchTab('tab-profile');
        setTimeout(() => openMarketModal(), 300);
        break;
      case 'raven':
      case 'mail':
        switchTab('tab-profile');
        setTimeout(() => openRavenModal(), 300);
        break;
      case 'hero':
      case 'inventory':
        switchTab('tab-profile');
        setTimeout(() => openHeroModal(), 300);
        break;
      case 'donate':
      case 'vip':
        switchTab('tab-profile');
        setTimeout(() => openDonateModal(), 300);
        break;
      case 'season':
      case 'pass':
      case 'season_pass':
        switchTab('tab-profile');
        setTimeout(() => openSeasonModal(), 300);
        break;
      case 'admin':
        switchTab('tab-profile');
        setTimeout(() => openAdminModal(), 300);
        break;
      case 'quiz':
      case 'citadel':
        switchTab('tab-profile');
        setTimeout(() => openCitadelQuizModal(), 300);
        break;
      case 'council':
        switchTab('tab-profile');
        setTimeout(() => openCouncilModal(), 300);
        break;
      case 'duel':
      case 'arena':
        setTimeout(() => openDuelModal(), 300);
        break;
      case 'bank':
      case 'iron_bank':
        setTimeout(() => openBankModal(), 300);
        break;
      case 'guild':
        setTimeout(() => openGuildModal(), 300);
        break;
      case 'profile':
      default:
        switchTab('tab-profile');
        break;
    }
  }

  // 7. Initialize Application
  document.addEventListener('DOMContentLoaded', async () => {
    AssetManager.init();
    setupListeners();
    await fetchDashboard();
    handleDeepLinkRouting();
  });

})();
