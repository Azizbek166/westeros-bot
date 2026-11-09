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
        switchTab('tab-profile');
      });
    } catch (e) {
      console.warn('Telegram WebApp setup error:', e);
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
      if (!res.success || !res.data) {
        throw new Error('Serverdan noto‘g‘ri ma‘lumot qaytdi.');
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
      const card = document.createElement('div');
      card.className = 'unit-card';
      card.innerHTML = `
        <div class="unit-left">
          <span class="unit-icon">${u.icon}</span>
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
      const card = document.createElement('div');
      card.className = 'unit-card';
      card.innerHTML = `
        <div class="unit-left">
          <span class="unit-icon">${s.icon}</span>
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
      card.className = 'castle-card';
      const taxInfo = c.tax || {};
      const isReady = taxInfo.is_ready || c.is_ready_to_claim;
      const hours = taxInfo.hours_ready || c.hours_accumulated || 0;
      const accumGold = taxInfo.accumulated_gold || c.accumulated_gold || 0;
      const remMin = taxInfo.rem_minutes !== undefined ? taxInfo.rem_minutes : (c.minutes_remaining || 0);

      const actionElement = isReady
        ? `<button class="btn-tax-claim" data-id="${c.id}">💰 Olish (+${formatNum(accumGold)}🪙)</button>`
        : `<span class="castle-tax-badge castle-tax-wait">⏳ ~${remMin} daq</span>`;

      card.innerHTML = `
        <div class="castle-left">
          <span class="castle-icon">🏰</span>
          <div>
            <div class="castle-name">${escapeHtml(c.name || c.castle_name)}</div>
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
    setupListeners();
    await fetchDashboard();
    handleDeepLinkRouting();
  });

})();
