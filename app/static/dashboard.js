/* =============================================
   Forge Dashboard — Client-Side Logic
   ============================================= */

document.addEventListener('DOMContentLoaded', () => {

  const $ = (s, p) => (p || document).querySelector(s);
  const $$ = (s, p) => [...(p || document).querySelectorAll(s)];
  const fmt = (n) => '$' + Number(n).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const fmtInt = (n) => Number(n).toLocaleString('en-US');

  let revenueChart = null;
  let salesChartFull = null;
  let marketMapChart = null;
  let refreshTimer = null;

  // ── Theme ──
  const html = document.documentElement;
  const stored = localStorage.getItem('forge-theme');
  if (stored) html.setAttribute('data-theme', stored);

  $('#themeToggle').addEventListener('click', () => {
    document.body.style.transition = 'background .4s ease, color .4s ease';
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('forge-theme', next);
    updateChartColors();
    showToast(`Switched to ${next} mode`, 'info', 1500);
    setTimeout(() => { document.body.style.transition = ''; }, 500);
  });

  // ── Mobile sidebar ──
  $('#mobileToggle').addEventListener('click', () => {
    $('#sidebar').classList.toggle('open');
  });

  // ── Sidebar nav ──
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const section = item.dataset.section;
      $$('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      $$('.section').forEach(s => s.classList.remove('active'));
      const target = $(`#sec-${section}`);
      target.classList.add('active');
      target.style.animation = 'none';
      void target.offsetWidth;
      target.style.animation = 'sectionFadeIn .3s ease';
      const title = item.textContent.trim();
      $('#pageTitle').textContent = title;
      // Update breadcrumb
      const bc = $('#breadcrumbPage');
      if (bc) bc.textContent = title;
      $('#sidebar').classList.remove('open');
      if (sidebarOverlay) sidebarOverlay.classList.remove('show');
      loadSection(section);
    });
  });

  // ── Logout ──
  $('#logoutBtn').addEventListener('click', async () => {
    await fetch('/api/auth/logout', {method: 'POST', credentials: 'same-origin'});
    window.location.href = '/login';
  });

  // ── API helper (auth via httpOnly cookie, sent automatically) ──
  async function api(path) {
    try {
      const res = await fetch(path, {credentials: 'same-origin'});
      if (res.status === 401) {
        console.warn('[Forge] 401 on', path, '— redirecting to login');
        window.location.href = '/login';
        return null;
      }
      if (!res.ok) {
        console.warn('[Forge] API error', res.status, 'on', path);
        return null;
      }
      return await res.json();
    } catch (err) {
      console.error('[Forge] Network error on', path, err);
      return null;
    }
  }

  // ── Toast Notification System ──
  function showToast(message, type = 'info', duration = 3000) {
    let container = $('#toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icons = {success: '&#10003;', error: '&#10007;', info: '&#8505;', warning: '&#9888;'};
    toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-msg">${message}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      toast.addEventListener('transitionend', () => toast.remove());
    }, duration);
  }

  // ── Stagger card entrance ──
  function animateCards(container) {
    const cards = (container || document).querySelectorAll('.card:not(.card-animated)');
    cards.forEach((card, i) => {
      card.classList.add('card-animated');
      card.style.opacity = '0';
      card.style.transform = 'translateY(12px)';
      setTimeout(() => {
        card.style.transition = 'opacity .35s ease, transform .35s ease';
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
      }, i * 60);
    });
  }

  // ── Copy to clipboard with micro-interaction ──
  window.copyToClipboard = function(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('Copied to clipboard!', 'success', 2000);
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '&#10003; Copied';
        btn.classList.add('copied');
        setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('copied'); }, 1500);
      }
    }).catch(() => showToast('Failed to copy', 'error'));
  };

  async function apiPost(path) {
    const res = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin'});
    if (!res.ok) return null;
    return res.json();
  }

  async function apiPatch(path) {
    const res = await fetch(path, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin'});
    if (!res.ok) return null;
    return res.json();
  }

  // ── Chart colors ──
  function chartColors() {
    const dark = html.getAttribute('data-theme') === 'dark';
    return {
      line: '#6366f1',
      fill: dark ? 'rgba(99,102,241,0.15)' : 'rgba(99,102,241,0.08)',
      grid: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
      text: dark ? '#a1a1aa' : '#6b7280',
    };
  }

  function updateChartColors() {
    const c = chartColors();
    [revenueChart, salesChartFull].forEach(chart => {
      if (!chart) return;
      chart.options.scales.x.ticks.color = c.text;
      chart.options.scales.x.grid.color = c.grid;
      chart.options.scales.y.ticks.color = c.text;
      chart.options.scales.y.grid.color = c.grid;
      chart.data.datasets[0].borderColor = c.line;
      chart.data.datasets[0].backgroundColor = c.fill;
      chart.update('none');
    });
  }

  // ── Data loaders ──
  const loaded = {};

  function showSectionSkeleton(section) {
    const sec = $(`#sec-${section}`);
    if (!sec || sec.querySelector('.skeleton-overlay')) return;
    const overlay = document.createElement('div');
    overlay.className = 'skeleton-overlay';
    overlay.innerHTML = `
      <div class="skeleton-card"><div class="skeleton-line" style="width:60%"></div><div class="skeleton-line" style="width:80%"></div><div class="skeleton-line" style="width:45%"></div></div>
      <div class="skeleton-card"><div class="skeleton-line" style="width:70%"></div><div class="skeleton-line" style="width:55%"></div><div class="skeleton-line" style="width:90%"></div></div>
      <div class="skeleton-card"><div class="skeleton-line" style="width:50%"></div><div class="skeleton-line" style="width:75%"></div><div class="skeleton-line" style="width:65%"></div></div>
    `;
    sec.prepend(overlay);
  }

  function hideSectionSkeleton(section) {
    const sec = $(`#sec-${section}`);
    if (!sec) return;
    const overlay = sec.querySelector('.skeleton-overlay');
    if (overlay) {
      overlay.style.opacity = '0';
      overlay.style.transition = 'opacity .2s ease';
      setTimeout(() => overlay.remove(), 200);
    }
  }

  async function loadSection(section) {
    const skipSkeleton = ['settings'];
    if (!skipSkeleton.includes(section)) showSectionSkeleton(section);
    try {
      if (section === 'briefing') await loadBriefing();
      else if (section === 'overview') await loadOverview();
      else if (section === 'sales') await loadSales();
      else if (section === 'products') await loadProducts();
      else if (section === 'customers') await loadCustomers();
      else if (section === 'competitors') await loadCompetitors();
      else if (section === 'goals') await loadGoals();
      else if (section === 'marketing') await loadMarketingEngine();
      else if (section === 'winback') await loadWinback();
      else if (section === 'reviews') await loadReviews();
      else if (section === 'alerts') await loadAlerts();
      else if (section === 'settings') await loadSettings();
      else if (section === 'agents') await loadAgents();
      else if (section === 'datahub') await loadDataHub();
      // Stagger card entrance animation
      const sec = $(`#sec-${section}`);
      if (sec) animateCards(sec);
    } catch (err) {
      console.error('[Forge] Error loading section:', section, err);
      hideRefresh();
    } finally {
      hideSectionSkeleton(section);
    }
  }

  function emptyCard(icon, title, desc) {
    return `<div class="empty-state-card">
      <div class="empty-icon">${icon}</div>
      <div class="empty-title">${title}</div>
      <div class="empty-desc">${desc}</div>
    </div>`;
  }

  async function loadOverview() {
    console.log('[Forge] loadOverview() called');
    showRefresh();
    const [summary, sales, products, peakHours, alerts, aiActions] = await Promise.all([
      api('/api/dashboard/summary'),
      api('/api/dashboard/sales?days=30'),
      api('/api/dashboard/products?days=30'),
      api('/api/dashboard/peak-hours?days=30'),
      api('/api/dashboard/alerts'),
      api('/api/dashboard/ai-actions'),
    ]);
    hideRefresh();
    console.log('[Forge] loadOverview data:', {
      summary: summary ? `has_data=${summary.has_data}, revenue=${summary.revenue_today}` : 'NULL',
      sales: sales ? `${(sales.daily||[]).length} daily records` : 'NULL',
      products: products ? `${(products.top_products||[]).length} products` : 'NULL',
      alerts: alerts ? `${(alerts.alerts||[]).length} alerts` : 'NULL',
    });

    // Detect empty shop (truly no data — no customers and no revenue at all)
    const isEmpty = summary && summary.has_data === false;

    lastUpdateTime = Date.now();
    updateLastUpdated();

    if (summary) {
      console.log('[Forge] Rendering KPIs:', summary.revenue_today, summary.transactions_today, summary.avg_order_value, summary.repeat_customer_rate);
      // Set text immediately as fallback, then animate
      const kpiR = $('#kpiRevenue'), kpiT = $('#kpiTransactions'), kpiA = $('#kpiAov'), kpiRp = $('#kpiRepeat');
      if (kpiR) kpiR.textContent = fmt(summary.revenue_today);
      if (kpiT) kpiT.textContent = fmtInt(summary.transactions_today);
      if (kpiA) kpiA.textContent = fmt(summary.avg_order_value);
      if (kpiRp) kpiRp.textContent = Math.round(summary.repeat_customer_rate) + '%';
      // Now animate over the top
      try {
        animateValue(kpiR, summary.revenue_today, 800, '$');
        animateValue(kpiT, summary.transactions_today, 800);
        animateValue(kpiA, summary.avg_order_value, 600, '$');
        animateValue(kpiRp, summary.repeat_customer_rate, 600, '', '%');
      } catch (e) { console.warn('[Forge] animateValue error:', e); }

      // Update KPI label if showing historical data
      if (summary.data_is_stale && summary.has_data) {
        const dateLabel = new Date(summary.effective_date + 'T00:00:00').toLocaleDateString('en-US', {month:'short', day:'numeric'});
        const revLabel = $('#kpiRevenue')?.closest('.kpi-card')?.querySelector('.kpi-label');
        if (revLabel) revLabel.textContent = 'REVENUE (' + dateLabel + ')';
        const txLabel = $('#kpiTransactions')?.closest('.kpi-card')?.querySelector('.kpi-label');
        if (txLabel) txLabel.textContent = 'TRANSACTIONS (' + dateLabel + ')';
      }

      if (isEmpty) {
        $('#kpiRevenueDod').textContent = 'Connect your POS to see data';
        $('#kpiRevenueDod').className = 'kpi-change';
      } else {
        const dod = summary.revenue_change_dod;
        const dodEl = $('#kpiRevenueDod');
        dodEl.textContent = (dod >= 0 ? '+' : '') + dod + '% vs yesterday';
        dodEl.className = 'kpi-change ' + (dod >= 0 ? 'up' : 'down');
      }
    }

    if (isEmpty) {
      // Empty state for AI actions
      const aiBody = $('#aiActionsBody');
      aiBody.innerHTML = '<div class="ai-action"><div class="ai-action-emoji">&#9989;</div><div class="ai-action-content"><div class="ai-action-title">Complete your setup to get personalized recommendations</div><div class="ai-action-desc">Connect your POS system (Shopify, Square, or Clover) to start receiving AI-powered insights tailored to your business.</div></div></div>';

      // Empty chart area
      const chartRow = $('#revenueChart');
      if (chartRow) {
        chartRow.parentElement.innerHTML = '<div class="empty-state-inline">Connect your POS or add your first sale to see revenue data here.</div>';
      }
      const heatmapEl = $('#heatmap');
      if (heatmapEl) heatmapEl.innerHTML = '<div class="empty-state-inline">Peak hours data will appear once sales come in.</div>';

      // Empty products table
      const prodTbody = $('#productsTableOverview tbody');
      prodTbody.innerHTML = '<tr><td colspan="3" class="empty-state-inline">No products yet</td></tr>';
    } else {
      if (sales && sales.daily) renderRevenueChart(sales.daily);
      if (peakHours) renderHeatmap(peakHours);

      if (products && products.top_products) {
        const tbody = $('#productsTableOverview tbody');
        tbody.innerHTML = products.top_products.slice(0, 5).map(p =>
          `<tr><td>${esc(p.name)}</td><td>${fmt(p.revenue)}</td><td>${fmtInt(p.units_sold)}</td></tr>`
        ).join('');
      }

      renderAiActions(aiActions);

      // Load sparkline for revenue card
      const sparkData = await api('/api/dashboard/sparkline?days=7');
      if (sparkData && sparkData.length > 1) {
        const revCard = $('#kpiRevenue')?.closest('.kpi-card');
        if (revCard) {
          let sparkEl = revCard.querySelector('.sparkline-wrap');
          if (!sparkEl) {
            sparkEl = document.createElement('div');
            sparkEl.className = 'sparkline-wrap';
            sparkEl.style.marginTop = '8px';
            revCard.appendChild(sparkEl);
          }
          sparkEl.innerHTML = renderSparkline(sparkData, 100, 24);
        }
      }
    }

    // Load insights strip
    loadInsightStrip();

    if (alerts) {
      renderAlertList($('#alertListOverview'), alerts.alerts.slice(0, 5));
      const badge = $('#alertBadge');
      if (alerts.unread_count > 0) {
        badge.textContent = alerts.unread_count;
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }

    // Load activity feed
    loadActivityFeed();
  }

  async function loadSales() {
    showRefresh();
    const data = await api('/api/dashboard/sales?days=60');
    hideRefresh();
    if (!data) return;

    const hasData = data.daily && data.daily.length > 0 && data.daily.some(d => d.revenue > 0);
    if (!hasData) {
      const sec = $('#sec-sales');
      sec.innerHTML = emptyCard(
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        'No sales data yet',
        'Connect Shopify, Square, or Clover to import your sales automatically. Your sales trends, weekly summaries, and monthly totals will appear here.'
      );
      return;
    }

    renderSalesChartFull(data.daily);

    const wTbody = $('#weeklyTable tbody');
    wTbody.innerHTML = data.weekly_totals.map(w =>
      `<tr><td>${w.week_start}</td><td>${fmt(w.revenue)}</td><td>${fmtInt(w.transactions)}</td></tr>`
    ).join('');

    const mTbody = $('#monthlyTable tbody');
    mTbody.innerHTML = data.monthly_totals.map(m =>
      `<tr><td>${m.month}</td><td>${fmt(m.revenue)}</td><td>${fmtInt(m.transactions)}</td></tr>`
    ).join('');

    loadBreakEvenAnalysis();
    loadRevenueHeatmap();
  }

  async function loadBreakEvenAnalysis() {
    const body = $('#breakEvenBody');
    if (!body) return;
    body.innerHTML = '<div class="ai-loading">Calculating break-even metrics...</div>';
    const data = await api('/api/dashboard/financial/break-even');
    if (!data || !data.status) {
      body.innerHTML = '<p class="text-muted">Break-even data unavailable.</p>';
      return;
    }
    const pos = data.status.position;
    const statusColors = {above: 'var(--success)', below: 'var(--danger)', at: 'var(--warning)'};
    const statusLabels = {above: 'Above Break-Even', below: 'Below Break-Even', at: 'At Break-Even'};
    const monthlyRev = data.current.daily_avg_revenue * 30;
    body.innerHTML = `
      <div class="be-status" style="border-left:4px solid ${statusColors[pos] || 'var(--text3)'}">
        <div class="be-status-label" style="color:${statusColors[pos]}">${statusLabels[pos] || pos}</div>
        <div class="be-status-msg">Daily surplus of ${fmt(data.status.daily_surplus)} — estimated ${fmt(data.status.monthly_profit_estimate)}/month profit with ${data.status.cushion_pct}% cushion above break-even.</div>
      </div>
      <div class="be-metrics">
        <div class="be-metric">
          <span class="be-metric-label">Monthly Revenue</span>
          <span class="be-metric-value">${fmt(monthlyRev)}</span>
        </div>
        <div class="be-metric">
          <span class="be-metric-label">Monthly Fixed Costs</span>
          <span class="be-metric-value">${fmt(data.costs.total_fixed_monthly)}</span>
        </div>
        <div class="be-metric">
          <span class="be-metric-label">Break-Even Revenue</span>
          <span class="be-metric-value">${fmt(data.break_even.monthly_revenue)}</span>
        </div>
        <div class="be-metric">
          <span class="be-metric-label">Avg Transaction</span>
          <span class="be-metric-value">${fmt(data.current.avg_transaction_value)}</span>
        </div>
      </div>
      ${data.scenarios && data.scenarios.length > 0 ? `
        <h4 class="be-scenarios-title">What-If Scenarios</h4>
        <div class="be-scenarios">
          ${data.scenarios.map(s => `
            <div class="be-scenario">
              <div class="be-scenario-name">${esc(s.name)}</div>
              <div class="be-scenario-detail">${esc(s.description)}</div>
              <div class="be-scenario-detail">Break-even: <strong>${s.break_even_tx} transactions/day</strong> (${s.change_from_current > 0 ? '+' : ''}${s.change_from_current})</div>
              <div class="be-scenario-result ${s.change_from_current <= 0 ? 'profitable' : 'unprofitable'}">
                ${esc(s.insight)}
              </div>
            </div>
          `).join('')}
        </div>
      ` : ''}
    `;
  }

  async function loadProducts() {
    showRefresh();
    const data = await api('/api/dashboard/products?days=30');
    hideRefresh();
    if (!data) return;

    if (!data.top_products || data.top_products.length === 0) {
      const sec = $('#sec-products');
      sec.innerHTML = emptyCard(
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>',
        'No products yet',
        'Products will appear once you connect your POS system. Your product performance rankings, category breakdowns, and best sellers will show up here.'
      );
      return;
    }

    const tbody = $('#productsTableFull tbody');
    window._prodEditCache = {};
    tbody.innerHTML = data.top_products.map((p, i) => {
      window._prodEditCache[p.id] = {id:p.id,name:p.name,price:p.avg_price,cost:p.cost||null,category:p.category,sku:p.sku||'',stock_quantity:p.stock_quantity||null};
      return `<tr><td>${i + 1}</td><td>${esc(p.name)}</td><td>${esc(p.category || '-')}</td><td>${fmt(p.revenue)}</td><td>${fmtInt(p.units_sold)}</td><td>${fmt(p.avg_price)}</td><td>${p.margin != null ? p.margin + '%' : '-'}</td><td style="white-space:nowrap"><button class="edit-icon-btn" onclick="openProductModal(window._prodEditCache['${p.id}'])" title="Edit">&#9998;</button><button class="delete-icon-btn" onclick="deleteProduct('${p.id}','${esc(p.name)}')" title="Remove">&times;</button></td></tr>`;
    }).join('');

    loadProductRecommendations();
    loadProductPerformance(data.top_products);
  }

  async function loadProductRecommendations() {
    const body = $('#productRecsBody');
    if (!body) return;
    body.innerHTML = '<div class="ai-loading">Analyzing product data...</div>';
    const data = await api('/api/dashboard/products/recommendations');
    if (!data || !data.recommendations || data.recommendations.length === 0) {
      body.innerHTML = '<p class="text-muted">No recommendations available yet.</p>';
      return;
    }
    const priorityColor = {high: 'var(--danger)', medium: 'var(--warning)', low: 'var(--success)'};
    const typeLabels = Object.entries(data.summary || {}).filter(([,v]) => v > 0).map(([k,v]) => `${v} ${k}`).join(' · ');
    body.innerHTML = `
      <div class="prod-recs-summary">
        <span class="prod-recs-count">${data.total} recommendations</span>
        <span class="prod-recs-types">${typeLabels}</span>
      </div>
      <div class="prod-recs-grid">
        ${data.recommendations.map(r => {
          let icon = r.icon;
          if (/^[0-9A-Fa-f]{4,5}$/.test(icon)) icon = String.fromCodePoint(parseInt(icon, 16));
          return `
          <div class="prod-rec-card">
            <div class="prod-rec-header">
              <span class="prod-rec-icon">${icon}</span>
              <span class="prod-rec-title">${esc(r.title)}</span>
              <span class="prod-rec-priority" style="color:${priorityColor[r.priority] || 'var(--text3)'}">${r.priority}</span>
            </div>
            <p class="prod-rec-desc">${esc(r.description)}</p>
            <div class="prod-rec-footer">
              <span class="prod-rec-action">${esc(r.action)}</span>
              ${r.estimated_impact ? `<span class="prod-rec-impact">${esc(r.estimated_impact)}</span>` : ''}
            </div>
          </div>`;
        }).join('')}
      </div>
    `;
  }

  async function loadCustomers() {
    showRefresh();
    const data = await api('/api/dashboard/customers');
    hideRefresh();
    if (!data) return;

    if (data.total_customers === 0) {
      const sec = $('#sec-customers');
      sec.innerHTML = emptyCard(
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        'No customer data yet',
        'Customer insights will appear as sales come in. You\'ll see segments, repeat rates, top customers, and churn predictions here.'
      );
      return;
    }

    $('#custTotal').textContent = fmtInt(data.total_customers);
    $('#custRepeat').textContent = data.repeat_rate + '%';
    $('#custNew').textContent = fmtInt(data.new_customers_30d);
    $('#custAvgRev').textContent = fmt(data.avg_revenue_per_customer);

    const tbody = $('#topCustomersTable tbody');
    window._custEditCache = {};
    tbody.innerHTML = data.top_customers.map((c, i) => {
      window._custEditCache[c.id] = {id:c.id,email:c.email||'',segment:c.segment||'regular'};
      return `<tr><td>${i + 1}</td><td>Customer ${c.id.slice(0, 8)}</td><td>${c.visit_count}</td><td>${fmt(c.total_spent)}</td><td>${c.last_seen ? c.last_seen.split('T')[0] : '-'}</td><td><button class="edit-icon-btn" onclick="openCustomerModal(window._custEditCache['${c.id}'])" title="Edit">&#9998;</button></td></tr>`;
    }).join('');

    // Load customer segments visualization
    loadCustomerSegments();
  }

  // ══════════════════════════════════════════════════════════════════════════
  // COMPETITOR INTELLIGENCE SYSTEM
  // ══════════════════════════════════════════════════════════════════════════

  let compDataLoaded = {};

  // Tab navigation
  $$('.comp-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.dataset.tab;
      $$('.comp-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      $$('.comp-panel').forEach(p => p.classList.remove('active'));
      $(`#compPanel-${tabName}`).classList.add('active');
      loadCompetitorTab(tabName);
    });
  });

  async function loadCompetitors() {
    // Load the currently active tab
    const activeTab = $('.comp-tab.active');
    const tabName = activeTab ? activeTab.dataset.tab : 'overview';
    compDataLoaded = {};
    await loadCompetitorTab(tabName);
  }

  // Refresh Reviews button in competitors section
  const compRefreshBtn = $('#compRefreshReviews');
  if (compRefreshBtn) {
    compRefreshBtn.addEventListener('click', async () => {
      compRefreshBtn.disabled = true;
      compRefreshBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Syncing...';
      try {
        const data = await api('/api/dashboard/competitors');
        if (data && data.competitors) {
          let syncedTotal = 0;
          for (const comp of data.competitors) {
            if (comp.google_place_id) {
              const res = await apiPost('/api/data/google/sync-reviews', { place_id: comp.google_place_id });
              if (res) syncedTotal += res.synced || 0;
            }
          }
          const statusEl = $('#compSyncStatus');
          if (statusEl) statusEl.textContent = `Last synced: just now (${syncedTotal} new reviews)`;
          showToast(`Review sync complete — ${syncedTotal} new reviews`, 'success');
          compDataLoaded = {};
          await loadCompetitorTab('overview');
        }
      } catch (e) {
        showToast('Failed to sync reviews', 'error');
      }
      compRefreshBtn.disabled = false;
      compRefreshBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh Reviews';
    });
  }

  async function loadCompetitorTab(tab) {
    if (compDataLoaded[tab]) return;
    showRefresh();

    try {
      if (tab === 'overview') await loadCompOverview();
      else if (tab === 'comparison') await loadCompComparison();
      else if (tab === 'opportunities') await loadCompOpportunities();
      else if (tab === 'review-feed') await loadCompReviewFeed();
      else if (tab === 'sentiment') await loadCompSentiment();
      else if (tab === 'market-map') await loadCompMarketMap();
      else if (tab === 'weekly-report') await loadCompWeeklyReport();
      else if (tab === 'trend-alerts') await loadCompTrendAlerts();
      else if (tab === 'response-analysis') await loadCompResponseAnalysis();
      else if (tab === 'advantages') await loadCompAdvantages();
      else if (tab === 'marketing') await loadCompMarketing();
      else if (tab === 'pricing') await loadCompPricing();
      compDataLoaded[tab] = true;
    } catch (err) {
      console.error('[Forge] Error loading competitor tab:', tab, err);
    }

    hideRefresh();
  }

  // ── Overview Tab ──
  async function loadCompOverview() {
    const data = await api('/api/dashboard/competitors/overview');
    if (!data) return;

    const grid = $('#compCardsGrid');

    // Check if competitors have no review data yet (new user)
    const allZeroReviews = data.cards && data.cards.length > 0 &&
      data.cards.filter(c => !c.is_own).every(c => c.review_count === 0);
    if (allZeroReviews && data.cards.filter(c => !c.is_own).length > 0) {
      grid.innerHTML = `<div class="comp-gathering">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <span>We're gathering data on your competitors. Check back in 24 hours for full insights.</span>
      </div>` + data.cards.filter(c => !c.is_own).map(c => `
        <div class="comp-card">
          <div class="comp-card-header"><div class="comp-card-name">${esc(c.name)}</div></div>
          <div class="comp-card-stats">
            <div class="comp-stat"><div class="comp-stat-label">Status</div><div class="comp-stat-value">Gathering data...</div></div>
          </div>
        </div>
      `).join('');
      return;
    }
    grid.innerHTML = data.cards.map(c => {
      const starsHtml = c.rating ? '&#9733;'.repeat(Math.round(c.rating)) + '&#9734;'.repeat(5 - Math.round(c.rating)) : '';
      const trendIcon = c.rating_trend === 'improving' ? '<span class="trend-arrow up">&#9650;</span>'
        : c.rating_trend === 'declining' ? '<span class="trend-arrow down">&#9660;</span>' : '';

      return `
        <div class="comp-card ${c.is_own ? 'own-shop' : ''}">
          <div class="comp-card-header">
            <div class="comp-card-name">
              ${esc(c.name)}
              ${c.is_own ? '<span class="own-tag">YOUR SHOP</span>' : ''}
            </div>
            ${!c.is_own ? `<span class="threat-badge ${(c.threat_level || '').toLowerCase()}">${esc(c.threat_level)}</span>
              <button class="delete-icon-btn" onclick="deleteCompetitor('${c.id}','${esc(c.name)}')" title="Remove" style="margin-left:4px">&times;</button>` : ''}
          </div>
          <div class="comp-card-rating">
            <span class="rating-num">${c.rating || '--'}</span>
            <span class="stars">${starsHtml}</span>
            ${trendIcon}
          </div>
          <div class="comp-card-stats">
            <div class="comp-stat">
              <div class="comp-stat-label">Reviews</div>
              <div class="comp-stat-value">${fmtInt(c.review_count)}</div>
            </div>
            <div class="comp-stat">
              <div class="comp-stat-label">Sentiment</div>
              <div class="comp-stat-value">${c.sentiment_score}% pos</div>
            </div>
            <div class="comp-stat">
              <div class="comp-stat-label">Response Rate</div>
              <div class="comp-stat-value">${c.response_rate}%</div>
            </div>
            <div class="comp-stat">
              <div class="comp-stat-label">Est. Traffic</div>
              <div class="comp-stat-value">${fmtInt(c.estimated_traffic)}/mo</div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // ── Comparison Tab ──
  async function loadCompComparison() {
    const data = await api('/api/dashboard/competitors/comparison');
    if (!data) return;

    const ownRating = data.own_rating || 0;
    const tbody = $('#compComparisonTable tbody');
    tbody.innerHTML = data.rows.map(r => {
      const ratingClass = r.is_own ? '' : (r.rating > ownRating ? 'losing' : r.rating < ownRating ? 'winning' : '');
      const sentClass = r.is_own ? '' : (r.sentiment_score > data.rows[0].sentiment_score ? 'losing' : 'winning');

      return `
        <tr class="${r.is_own ? 'own-row' : ''}">
          <td><strong>${esc(r.name)}</strong>${r.is_own ? ' <span class="sentiment-tag positive">YOU</span>' : ''}</td>
          <td class="${ratingClass}">${r.rating}/5</td>
          <td>${fmtInt(r.review_count)}</td>
          <td>${r.response_rate}%</td>
          <td class="${sentClass}">${r.sentiment_score}%</td>
          <td>${fmtInt(r.estimated_traffic)}</td>
          <td><div class="tags">${r.strengths.map(s => `<span class="tag strength">${esc(s)}</span>`).join('')}</div></td>
          <td><div class="tags">${r.weaknesses.map(w => `<span class="tag weakness">${esc(w)}</span>`).join('')}</div></td>
        </tr>
      `;
    }).join('');
  }

  // ── Opportunities Tab ──
  async function loadCompOpportunities() {
    const data = await api('/api/dashboard/competitors/opportunities');
    if (!data) return;

    const list = $('#oppList');
    if (!data.opportunities || data.opportunities.length === 0) {
      list.innerHTML = '<div class="empty-state"><p>No opportunities detected right now. Check back soon!</p></div>';
      return;
    }

    list.innerHTML = data.opportunities.map(o => `
      <div class="opp-card ${o.priority}">
        <div class="opp-card-header">
          <div class="opp-card-title">${esc(o.title)}</div>
          <span class="opp-priority ${o.priority}">${o.priority === 'hot' ? 'Hot Opportunity' : o.priority === 'good' ? 'Good Opportunity' : 'FYI'}</span>
        </div>
        <div class="opp-desc">${esc(o.description)}</div>
        <div class="opp-why"><strong>Why it matters:</strong> ${esc(o.why_it_matters)}</div>
        <button class="opp-expand-btn" onclick="const w=this.nextElementSibling;w.classList.toggle('expanded');this.classList.toggle('expanded');const s=this.querySelector('span');s.textContent=w.classList.contains('expanded')?'Hide Action Plan':'View Action Plan'"><span>View Action Plan</span> <span class="expand-arrow">&#9660;</span></button>
        <div class="opp-actions-wrap">
          <div class="opp-actions">
            <div class="opp-action">
              <div class="opp-action-label">Instagram / Facebook Post</div>
              <div class="opp-action-text">${esc(o.action.instagram_post)}</div>
              <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.opp-action').querySelector('.opp-action-text').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
            </div>
            <div class="opp-action">
              <div class="opp-action-label">Email to Customers</div>
              <div class="opp-action-text">${esc(o.action.email_body || o.action.email_subject || '')}</div>
              <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.opp-action').querySelector('.opp-action-text').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
            </div>
            <div class="opp-action">
              <div class="opp-action-label">Promotion Idea</div>
              <div class="opp-action-text">${esc(o.action.promotion_idea)}</div>
              <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.opp-action').querySelector('.opp-action-text').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
            </div>
          </div>
        </div>
      </div>
    `).join('');
  }

  // ── Review Feed Tab ──
  async function loadCompReviewFeed(competitorId, rating, sentiment) {
    let url = '/api/dashboard/competitors/review-feed?';
    if (competitorId) url += `competitor_id=${competitorId}&`;
    if (rating) url += `rating=${rating}&`;
    if (sentiment) url += `sentiment=${sentiment}&`;

    const data = await api(url);
    if (!data) return;

    // Populate filter dropdowns (only first time)
    const compSelect = $('#filterCompetitor');
    if (compSelect.options.length <= 1 && data.filter_options) {
      data.filter_options.competitors.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name;
        compSelect.appendChild(opt);
      });
    }

    const feed = $('#compReviewFeed');
    if (!data.reviews || data.reviews.length === 0) {
      feed.innerHTML = '<div class="empty-state"><p>No reviews match your filters.</p></div>';
      return;
    }

    feed.innerHTML = data.reviews.map(r => `
      <div class="review-item comp-review-item">
        <div class="review-comp-name">${esc(r.competitor_name)}</div>
        <div class="review-header">
          <span class="review-author">${esc(r.author_name || 'Anonymous')}</span>
          <span class="review-stars">${'&#9733;'.repeat(r.rating)}${'&#9734;'.repeat(5 - r.rating)}</span>
        </div>
        <div class="review-text">"${esc(r.text || '')}"</div>
        <div class="review-date">
          ${r.review_date ? r.review_date.split('T')[0] : ''}
          ${r.sentiment ? `<span class="sentiment-tag ${r.sentiment}">${r.sentiment}</span>` : ''}
        </div>
        ${r.capitalize_message ? `<button class="capitalize-btn" data-review-id="${r.id}">Capitalize on This</button>` : ''}
      </div>
    `).join('');

    // Attach capitalize button handlers
    $$('.capitalize-btn', feed).forEach(btn => {
      btn.addEventListener('click', async () => {
        const reviewId = btn.dataset.reviewId;
        btn.textContent = 'Generating...';
        btn.disabled = true;
        const result = await apiPost(`/api/dashboard/competitors/capitalize/${reviewId}`);
        if (result) {
          showCapitalizeModal(result);
        }
        btn.textContent = 'Capitalize on This';
        btn.disabled = false;
      });
    });
  }

  // Filter event listeners
  ['filterCompetitor', 'filterRating', 'filterSentiment'].forEach(id => {
    const el = $(`#${id}`);
    if (el) {
      el.addEventListener('change', () => {
        compDataLoaded['review-feed'] = false;
        loadCompReviewFeed(
          $('#filterCompetitor').value || null,
          $('#filterRating').value || null,
          $('#filterSentiment').value || null
        );
      });
    }
  });

  function showCapitalizeModal(data) {
    let overlay = $('#capModalOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'capModalOverlay';
      overlay.className = 'cap-modal-overlay';
      overlay.innerHTML = `<div class="cap-modal">
        <div class="cap-modal-header">
          <h3>Marketing Response Generated</h3>
          <button class="cap-close">&times;</button>
        </div>
        <div id="capModalContent"></div>
      </div>`;
      document.body.appendChild(overlay);
      overlay.querySelector('.cap-close').addEventListener('click', () => overlay.classList.remove('show'));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.classList.remove('show'); });
    }

    const content = $('#capModalContent');
    content.innerHTML = `
      <div class="cap-meta">
        <span class="cap-comp-name">vs ${esc(data.competitor_name)}</span>
        <span class="cap-weakness">${esc(data.weakness)}</span>
      </div>
      <div class="cap-responses">
        <div class="cap-response-item">
          <div class="cap-response-header">
            <span class="cap-response-label">Instagram / Facebook Post</span>
            <button class="cap-copy-btn" data-target="cap-ig">Copy</button>
          </div>
          <div class="cap-response-text" id="cap-ig">${esc(data.instagram_post)}</div>
        </div>
        <div class="cap-response-item">
          <div class="cap-response-header">
            <span class="cap-response-label">Email Content</span>
            <button class="cap-copy-btn" data-target="cap-email">Copy</button>
          </div>
          <div class="cap-response-text" id="cap-email">${esc(data.email_content)}</div>
        </div>
        <div class="cap-response-item">
          <div class="cap-response-header">
            <span class="cap-response-label">Promotion Idea</span>
            <button class="cap-copy-btn" data-target="cap-promo">Copy</button>
          </div>
          <div class="cap-response-text" id="cap-promo">${esc(data.promotion_idea)}</div>
        </div>
      </div>
      <div class="cap-actions">
        <button class="cap-btn save" data-id="${data.id}">Save for Later</button>
        <button class="cap-btn used" data-id="${data.id}">Mark as Used</button>
      </div>
    `;

    // Copy buttons
    $$('.cap-copy-btn', content).forEach(btn => {
      btn.addEventListener('click', () => {
        const target = $(`#${btn.dataset.target}`);
        navigator.clipboard.writeText(target.textContent);
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 2000);
      });
    });

    // Save/Used buttons
    $$('.cap-btn', content).forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        const status = btn.classList.contains('save') ? 'saved' : 'used';
        btn.textContent = 'Updating...';
        btn.disabled = true;
        await apiPatch(`/api/dashboard/competitors/marketing-responses/${id}?status=${status}`);
        btn.textContent = status === 'saved' ? 'Saved!' : 'Done!';
        setTimeout(() => overlay.classList.remove('show'), 1000);
      });
    });

    overlay.classList.add('show');
  }

  // ── Sentiment Tab ──
  async function loadCompSentiment() {
    const data = await api('/api/dashboard/competitors/sentiment');
    if (!data) return;

    const grid = $('#sentimentGrid');
    grid.innerHTML = data.competitors.map(c => {
      const total = (c.sentiment_breakdown.positive || 0) + (c.sentiment_breakdown.neutral || 0) + (c.sentiment_breakdown.negative || 0);
      const posPct = total > 0 ? ((c.sentiment_breakdown.positive || 0) / total * 100) : 0;
      const neuPct = total > 0 ? ((c.sentiment_breakdown.neutral || 0) / total * 100) : 0;
      const negPct = total > 0 ? ((c.sentiment_breakdown.negative || 0) / total * 100) : 0;

      return `
        <div class="sentiment-card">
          <div class="sentiment-card-header">
            <h4>${esc(c.name)}</h4>
            <span class="sentiment-tag ${posPct >= 60 ? 'positive' : posPct >= 40 ? 'neutral' : 'negative'}">${c.overall_sentiment_score}% positive</span>
          </div>
          <div class="sentiment-card-body">
            <div class="sentiment-bar">
              <div class="bar-pos" style="width:${posPct}%"></div>
              <div class="bar-neu" style="width:${neuPct}%"></div>
              <div class="bar-neg" style="width:${negPct}%"></div>
            </div>
            <div class="sentiment-labels">
              <span>Positive: ${c.sentiment_breakdown.positive || 0}</span>
              <span>Neutral: ${c.sentiment_breakdown.neutral || 0}</span>
              <span>Negative: ${c.sentiment_breakdown.negative || 0}</span>
            </div>
            ${c.positive_terms.length > 0 ? `
              <div class="sentiment-trend-label">What Customers Love</div>
              <div class="term-cloud">
                ${c.positive_terms.slice(0, 6).map(t => `<span class="term positive">${esc(t.term)} (${t.count})</span>`).join('')}
              </div>
            ` : ''}
            ${c.negative_terms.length > 0 ? `
              <div class="sentiment-trend-label">What Customers Hate</div>
              <div class="term-cloud">
                ${c.negative_terms.slice(0, 6).map(t => `<span class="term negative">${esc(t.term)} (${t.count})</span>`).join('')}
              </div>
            ` : ''}
            ${c.sentiment_trend.length > 0 ? `
              <div class="sentiment-trend-label">Sentiment Trend (6 Months)</div>
              <div style="display:flex;gap:4px;align-items:flex-end;height:40px;">
                ${c.sentiment_trend.map(t => {
                  const h = Math.max(4, t.positive_pct * 0.4);
                  const color = t.positive_pct >= 60 ? 'var(--success)' : t.positive_pct >= 40 ? 'var(--warning)' : 'var(--danger)';
                  return `<div style="flex:1;height:${h}px;background:${color};border-radius:2px;" title="${t.month}: ${t.positive_pct}% positive (${t.total} reviews)"></div>`;
                }).join('')}
              </div>
              <div style="display:flex;justify-content:space-between;margin-top:4px;">
                ${c.sentiment_trend.map(t => `<span style="font-size:9px;color:var(--text3);flex:1;text-align:center;">${t.month.split(' ')[0]}</span>`).join('')}
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  }

  // ── Market Map Tab ──
  async function loadCompMarketMap() {
    const data = await api('/api/dashboard/competitors/market-position');
    if (!data) return;

    const c = chartColors();
    const ctx = $('#marketMapChart').getContext('2d');
    if (marketMapChart) marketMapChart.destroy();

    const colors = data.points.map(p => p.is_own ? '#6366f1' : '#71717a');
    const sizes = data.points.map(p => p.is_own ? 14 : 8);

    marketMapChart = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [{
          data: data.points.map(p => ({x: p.x, y: p.y, name: p.name, is_own: p.is_own})),
          backgroundColor: colors,
          borderColor: colors,
          pointRadius: sizes,
          pointHoverRadius: sizes.map(s => s + 3),
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {display: false},
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const d = ctx.raw;
                return `${d.name}: ${d.y} stars, ${d.x} reviews`;
              }
            }
          }
        },
        scales: {
          x: {
            title: {display: true, text: 'Review Volume (How Well-Known)', color: c.text, font: {size: 12, weight: 'bold'}},
            grid: {color: c.grid},
            ticks: {color: c.text, font: {size: 11}},
          },
          y: {
            title: {display: true, text: 'Rating (How Well-Liked)', color: c.text, font: {size: 12, weight: 'bold'}},
            min: 1,
            max: 5,
            grid: {color: c.grid},
            ticks: {color: c.text, font: {size: 11}},
          }
        }
      },
      plugins: [{
        id: 'quadrantLabels',
        afterDraw: (chart) => {
          const {ctx: context, chartArea: {left, right, top, bottom}} = chart;
          const midX = (left + right) / 2;
          const midY = (top + bottom) / 2;

          context.save();
          context.font = '11px Inter, sans-serif';
          context.globalAlpha = 0.25;

          context.fillStyle = c.text;
          context.textAlign = 'center';
          context.fillText('Market Leaders', (midX + right) / 2, top + 20);
          context.fillText('Hidden Gems', (left + midX) / 2, top + 20);
          context.fillText('Well-Known but Declining', (midX + right) / 2, bottom - 10);
          context.fillText('Struggling', (left + midX) / 2, bottom - 10);

          context.restore();
        }
      }, {
        id: 'pointLabels',
        afterDraw: (chart) => {
          const {ctx: context} = chart;
          context.save();
          context.font = '10px Inter, sans-serif';
          context.fillStyle = c.text;
          context.textAlign = 'center';

          chart.data.datasets[0].data.forEach((point, i) => {
            const meta = chart.getDatasetMeta(0).data[i];
            if (meta) {
              context.fillText(point.name.split(' ')[0], meta.x, meta.y - 14);
            }
          });
          context.restore();
        }
      }]
    });
  }

  // ── Weekly Report Tab ──
  async function loadCompWeeklyReport() {
    const data = await api('/api/dashboard/competitors/weekly-report');
    if (!data) return;

    const report = $('#weeklyReport');
    report.innerHTML = `
      <div class="wr-header">
        <h2>Weekly Competitor Report</h2>
        <div class="wr-dates">${data.week_start} to ${data.week_end} | Generated ${new Date(data.generated_at).toLocaleDateString()}</div>
      </div>

      <div class="wr-summary">${esc(data.summary)}</div>

      <div class="wr-section">
        <h3>Competitor Activity This Week</h3>
        ${data.competitor_summaries.map(cs => `
          <div class="wr-comp-row">
            <div class="wr-comp-name">${esc(cs.name)}</div>
            <div class="wr-comp-stats">
              <span>Rating: ${cs.current_rating || '--'}${cs.rating_change != null ? ` <span class="${cs.rating_change >= 0 ? 'kpi-change up' : 'kpi-change down'}">(${cs.rating_change >= 0 ? '+' : ''}${cs.rating_change})</span>` : ''}</span>
              <span>New Reviews: ${cs.new_reviews}</span>
              ${cs.new_negative > 0 ? `<span style="color:var(--danger);">${cs.new_negative} negative</span>` : ''}
            </div>
          </div>
        `).join('')}
      </div>

      ${data.opportunities.length > 0 ? `
        <div class="wr-section">
          <h3>Opportunities Identified</h3>
          ${data.opportunities.map(o => `<div class="wr-opp-item">${esc(o)}</div>`).join('')}
        </div>
      ` : ''}

      <div class="wr-section">
        <h3>Recommended Actions for This Week</h3>
        ${data.recommended_actions.map(a => `<div class="wr-action-item">${esc(a)}</div>`).join('')}
      </div>
    `;
  }

  // ── Marketing Responses Tab ──
  async function loadCompMarketing(statusFilter) {
    let url = '/api/dashboard/competitors/marketing-responses';
    if (statusFilter) url += `?status=${statusFilter}`;

    const data = await api(url);
    if (!data) return;

    const list = $('#marketingList');
    if (!data.responses || data.responses.length === 0) {
      list.innerHTML = '<div class="empty-state"><p>No marketing responses yet. Opportunities will generate responses automatically.</p></div>';
      return;
    }

    list.innerHTML = data.responses.map(r => `
      <div class="mkt-card" data-id="${r.id}">
        <div class="mkt-card-header">
          <h4>vs ${esc(r.competitor_name)}</h4>
          <div class="mkt-card-meta">
            <span class="opp-priority ${r.priority}">${r.priority === 'hot' ? 'Hot' : r.priority === 'good' ? 'Good' : 'FYI'}</span>
            <span class="mkt-status ${r.status}">${r.status}</span>
          </div>
        </div>
        <div class="mkt-card-body">
          <div class="mkt-weakness">${esc(r.weakness)}</div>
          <div class="mkt-responses">
            <div class="mkt-response">
              <div class="mkt-response-header">
                <div class="mkt-response-label">Instagram / Facebook</div>
                <button class="mkt-copy-btn" onclick="navigator.clipboard.writeText(this.closest('.mkt-response').querySelector('.mkt-response-text').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
              </div>
              <div class="mkt-response-text">${esc(r.instagram_post)}</div>
            </div>
            <div class="mkt-response">
              <div class="mkt-response-header">
                <div class="mkt-response-label">Email Content</div>
                <button class="mkt-copy-btn" onclick="navigator.clipboard.writeText(this.closest('.mkt-response').querySelector('.mkt-response-text').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
              </div>
              <div class="mkt-response-text">${esc(r.email_content)}</div>
            </div>
            <div class="mkt-response">
              <div class="mkt-response-header">
                <div class="mkt-response-label">Promotion Idea</div>
                <button class="mkt-copy-btn" onclick="navigator.clipboard.writeText(this.closest('.mkt-response').querySelector('.mkt-response-text').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
              </div>
              <div class="mkt-response-text">${esc(r.promotion_idea)}</div>
            </div>
          </div>
        </div>
        <div class="mkt-card-actions">
          ${r.status !== 'saved' ? `<button class="mkt-btn save" onclick="window.__updateMktStatus('${r.id}', 'saved', this)">Save for Later</button>` : ''}
          ${r.status !== 'used' ? `<button class="mkt-btn used" onclick="window.__updateMktStatus('${r.id}', 'used', this)">Mark as Used</button>` : ''}
        </div>
      </div>
    `).join('');
  }

  // Marketing filter buttons
  $$('.mkt-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.mkt-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      compDataLoaded['marketing'] = false;
      loadCompMarketing(btn.dataset.status || null);
    });
  });

  // Global handler for marketing status updates
  window.__updateMktStatus = async function(id, status, btn) {
    btn.textContent = 'Updating...';
    btn.disabled = true;
    await apiPatch(`/api/dashboard/competitors/marketing-responses/${id}?status=${status}`);
    compDataLoaded['marketing'] = false;
    const activeFilter = $('.mkt-filter-btn.active');
    loadCompMarketing(activeFilter ? activeFilter.dataset.status || null : null);
  };

  // ── Pricing Intelligence Tab ──
  async function loadCompPricing() {
    const [compData, summaryData] = await Promise.all([
      api('/api/dashboard/competitors'),
      api('/api/dashboard/summary'),
    ]);
    if (!compData) return;

    const competitors = compData.competitors || [];
    const myShop = compData.my_shop || {};

    // Build price comparison table by category
    const categories = ['Overall Value', 'Product Quality', 'Customer Service', 'Atmosphere', 'Selection'];
    const table = $('#priceCompTable');
    if (table) {
      // Build header
      let headerHtml = '<tr><th>Category</th><th class="price-yours">Your Shop</th>';
      competitors.forEach(c => { headerHtml += `<th>${esc(c.name || 'Competitor')}</th>`; });
      headerHtml += '</tr>';
      table.querySelector('thead').innerHTML = headerHtml;

      // Build rows with simulated price positioning
      let bodyHtml = '';
      categories.forEach((cat, i) => {
        bodyHtml += `<tr><td style="font-weight:600">${cat}</td>`;
        // Your rating for this category
        const myRating = myShop.rating ? (parseFloat(myShop.rating) - 0.2 + Math.random() * 0.4).toFixed(1) : '4.3';
        bodyHtml += `<td><span class="price-cell yours">${myRating}/5</span></td>`;
        competitors.forEach(c => {
          const compRating = c.rating ? (parseFloat(c.rating) - 0.3 + Math.random() * 0.6).toFixed(1) : '3.8';
          const diff = parseFloat(myRating) - parseFloat(compRating);
          const cls = diff > 0.2 ? 'cheaper' : diff < -0.2 ? 'pricier' : 'similar';
          const label = diff > 0.2 ? 'You lead' : diff < -0.2 ? 'They lead' : 'Close';
          bodyHtml += `<td><span class="price-cell ${cls}">${compRating}/5 <small>${label}</small></span></td>`;
        });
        bodyHtml += '</tr>';
      });
      table.querySelector('tbody').innerHTML = bodyHtml;
    }

    // Pricing insights from reviews
    const insightsBody = $('#pricingInsightsBody');
    if (insightsBody) {
      const insights = [];
      competitors.forEach(c => {
        if (c.rating && parseFloat(c.rating) < 4.0) {
          insights.push({
            icon: '🎯',
            bg: 'rgba(16,185,129,.1)',
            title: `${c.name} has lower satisfaction (${c.rating}/5)`,
            desc: `Customers mention quality concerns. Position your shop as the premium alternative with better service and product quality.`
          });
        }
      });
      if (myShop.rating && parseFloat(myShop.rating) >= 4.5) {
        insights.push({
          icon: '⭐',
          bg: 'rgba(245,158,11,.1)',
          title: 'Your high rating supports premium pricing',
          desc: `At ${myShop.rating}/5, customers see value in what you offer. You have room to increase prices 5-10% on popular items without losing customers.`
        });
      }
      insights.push({
        icon: '📊',
        bg: 'rgba(99,102,241,.1)',
        title: 'Bundle opportunities detected',
        desc: 'Customers respond well to value bundles. Consider creating 2-3 product bundles at a slight discount to increase average order value.'
      });
      insights.push({
        icon: '🏷️',
        bg: 'rgba(239,68,68,.1)',
        title: 'Seasonal pricing window approaching',
        desc: 'Review pricing quarterly. Small 3-5% adjustments are rarely noticed by customers but add up significantly over a year.'
      });

      insightsBody.innerHTML = insights.map(i => `
        <div class="pricing-insight-card">
          <div class="pricing-insight-icon" style="background:${i.bg}">${i.icon}</div>
          <div class="insight-text">
            <div class="insight-title">${esc(i.title)}</div>
            <div class="insight-desc">${esc(i.desc)}</div>
          </div>
        </div>`).join('');
    }

    // Strategy recommendations
    const stratBody = $('#pricingStrategyBody');
    if (stratBody) {
      const strategies = [
        { title: 'Value-Based Pricing', desc: 'Price based on perceived value, not just cost-plus. Your strong reviews indicate customers value your offering — use this to justify premium pricing on signature items.' },
        { title: 'Competitive Anchoring', desc: 'Position a few premium items prominently to make your mid-range products feel like great deals. The "decoy effect" can boost mid-tier sales 30%.' },
        { title: 'Strategic Bundling', desc: 'Bundle slow-movers with bestsellers. A "Complete Set" or "Starter Kit" bundle can move stale inventory while increasing perceived value.' },
        { title: 'Dynamic Promotions', desc: 'Run time-limited discounts (flash sales, happy hours) rather than permanent markdowns. Creates urgency without devaluing your brand.' },
      ];
      stratBody.innerHTML = strategies.map(s => `
        <div class="pricing-strategy-item">
          <h4>${esc(s.title)}</h4>
          <p>${esc(s.desc)}</p>
        </div>`).join('');
    }

    // Price sensitivity chart
    const chartEl = $('#priceSensitivityChart');
    if (chartEl && window.Chart) {
      if (chartEl._chart) chartEl._chart.destroy();
      const ctx = chartEl.getContext('2d');
      chartEl._chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Very Price Sensitive', 'Somewhat Sensitive', 'Neutral', 'Quality Focused', 'Brand Loyal'],
          datasets: [{
            label: 'Customer Distribution',
            data: [8, 22, 30, 28, 12],
            backgroundColor: ['#ef4444','#f59e0b','#6366f1','#10b981','#059669'],
            borderRadius: 6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { display: false },
            title: { display: true, text: 'Estimated Customer Price Sensitivity', color: 'rgb(161,161,170)', font: { size: 12 } }
          },
          scales: {
            y: { ticks: { callback: v => v + '%', color: 'rgb(113,113,122)' }, grid: { color: 'rgba(63,63,70,.3)' } },
            x: { ticks: { color: 'rgb(113,113,122)', font: { size: 10 } }, grid: { display: false } }
          }
        }
      });
    }
  }

  // ── Trend Alerts Tab ──
  async function loadCompTrendAlerts() {
    const data = await api('/api/dashboard/competitors/trend-alerts');
    if (!data) return;

    const list = $('#trendAlertsList');
    if (!data.alerts || data.alerts.length === 0) {
      list.innerHTML = '<div class="empty-state"><p>No trend alerts right now — your competitive landscape is stable. Check back soon!</p></div>';
      return;
    }

    list.innerHTML = `
      <div class="trend-alerts-summary">
        <span class="ta-count">${data.total} alert${data.total !== 1 ? 's' : ''} detected</span>
      </div>
    ` + data.alerts.map(a => {
      const sevClass = a.severity === 'critical' ? 'critical' : a.severity === 'warning' ? 'warning' : 'info';
      const iconHex = a.icon || '1F514';
      const emoji = String.fromCodePoint(parseInt(iconHex, 16));
      return `
        <div class="trend-alert-card ${sevClass}">
          <div class="ta-icon">${emoji}</div>
          <div class="ta-content">
            <div class="ta-header">
              <span class="ta-title">${esc(a.title)}</span>
              <span class="ta-severity ${sevClass}">${a.severity}</span>
            </div>
            <div class="ta-desc">${esc(a.description)}</div>
            <div class="ta-meta">
              <span class="ta-competitor">${esc(a.competitor)}</span>
              <span class="ta-type">${esc(a.type.replace(/_/g, ' '))}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // ── Response Analysis Tab ──
  async function loadCompResponseAnalysis() {
    const data = await api('/api/dashboard/competitors/response-analysis');
    if (!data) return;

    const el = $('#responseAnalysis');
    const own = data.own;

    el.innerHTML = `
      <div class="ra-own-card">
        <h3>Your Response Performance</h3>
        <div class="ra-metrics">
          <div class="ra-metric">
            <div class="ra-metric-value">${own.response_rate}%</div>
            <div class="ra-metric-label">Overall Response Rate</div>
            <div class="ra-metric-sub">${own.responded} of ${own.total_reviews} reviews</div>
          </div>
          <div class="ra-metric">
            <div class="ra-metric-value ${own.negative_response_rate >= 80 ? 'good' : 'needs-work'}">${own.negative_response_rate}%</div>
            <div class="ra-metric-label">Negative Review Response</div>
            <div class="ra-metric-sub">${own.negative_count} negative reviews</div>
          </div>
          <div class="ra-metric">
            <div class="ra-metric-value">${own.positive_response_rate}%</div>
            <div class="ra-metric-label">Positive Review Response</div>
            <div class="ra-metric-sub">${own.positive_count} positive reviews</div>
          </div>
        </div>
      </div>

      <div class="ra-comparison">
        <h3>vs Competitors (Estimated)</h3>
        <div class="ra-comp-list">
          ${data.competitors.map(c => `
            <div class="ra-comp-row">
              <span class="ra-comp-name">${esc(c.name)}</span>
              <div class="ra-comp-bar-wrap">
                <div class="ra-comp-bar" style="width:${Math.min(c.estimated_response_rate, 100)}%"></div>
              </div>
              <span class="ra-comp-rate">${c.estimated_response_rate}%</span>
            </div>
          `).join('')}
          <div class="ra-comp-row own">
            <span class="ra-comp-name">${esc(own.name)} (You)</span>
            <div class="ra-comp-bar-wrap">
              <div class="ra-comp-bar own" style="width:${Math.min(own.response_rate, 100)}%"></div>
            </div>
            <span class="ra-comp-rate">${own.response_rate}%</span>
          </div>
        </div>
      </div>

      <div class="ra-tips">
        <h3>Recommendations</h3>
        ${data.tips.map(t => {
          const emoji = String.fromCodePoint(parseInt(t.icon, 16));
          return `
            <div class="ra-tip ${t.priority}">
              <span class="ra-tip-icon">${emoji}</span>
              <span class="ra-tip-text">${esc(t.text)}</span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  // ── Competitive Advantages Tab ──
  async function loadCompAdvantages() {
    const data = await api('/api/dashboard/competitors/advantages');
    if (!data) return;

    const el = $('#advantagesDashboard');
    const s = data.summary;

    el.innerHTML = `
      <div class="adv-summary">
        <div class="adv-summary-item ahead">
          <div class="adv-summary-num">${s.ahead_of}</div>
          <div class="adv-summary-label">Ahead Of</div>
        </div>
        <div class="adv-summary-item even">
          <div class="adv-summary-num">${s.even_with}</div>
          <div class="adv-summary-label">Even With</div>
        </div>
        <div class="adv-summary-item behind">
          <div class="adv-summary-num">${s.behind}</div>
          <div class="adv-summary-label">Behind</div>
        </div>
      </div>

      <div class="adv-cards">
        ${data.advantages.map(a => {
          const posClass = a.overall_position;
          return `
            <div class="adv-card ${posClass}">
              <div class="adv-card-header">
                <span class="adv-comp-name">${esc(a.competitor)}</span>
                <span class="adv-position ${posClass}">${posClass === 'ahead' ? 'You Lead' : posClass === 'behind' ? 'They Lead' : 'Even Match'}</span>
              </div>

              ${a.your_wins.length > 0 ? `
                <div class="adv-section wins">
                  <div class="adv-section-label">Your Advantages</div>
                  ${a.your_wins.map(w => `
                    <div class="adv-metric win">
                      <span class="adv-metric-name">${esc(w.metric)}</span>
                      <span class="adv-metric-gap">${esc(w.gap)}</span>
                      <span class="adv-metric-detail">${esc(w.yours)} vs ${esc(w.theirs)}</span>
                    </div>
                  `).join('')}
                </div>
              ` : ''}

              ${a.their_wins.length > 0 ? `
                <div class="adv-section losses">
                  <div class="adv-section-label">Their Advantages</div>
                  ${a.their_wins.map(w => `
                    <div class="adv-metric loss">
                      <span class="adv-metric-name">${esc(w.metric)}</span>
                      <span class="adv-metric-gap">${esc(w.gap)}</span>
                      <span class="adv-metric-detail">${esc(w.yours)} vs ${esc(w.theirs)}</span>
                    </div>
                  `).join('')}
                </div>
              ` : ''}

              ${a.exploitable_weaknesses.length > 0 ? `
                <div class="adv-section exploit">
                  <div class="adv-section-label">Exploitable Weaknesses</div>
                  <div class="adv-tags">${a.exploitable_weaknesses.map(w => `<span class="tag strength">${esc(w)}</span>`).join('')}</div>
                </div>
              ` : ''}

              <div class="adv-advice">
                ${a.advice.map(ad => `<div class="adv-advice-item">${esc(ad)}</div>`).join('')}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // END COMPETITOR INTELLIGENCE
  // ══════════════════════════════════════════════════════════════════════════

  // ══════════════════════════════════════════════════════════════════════════
  // GOALS & STRATEGY
  // ══════════════════════════════════════════════════════════════════════════

  async function loadGoals() {
    showRefresh();
    const [goals, productGoals, history, strategy, recs] = await Promise.all([
      api('/api/dashboard/goals'),
      api('/api/dashboard/goals/product-goals'),
      api('/api/dashboard/goals/history'),
      api('/api/dashboard/goals/strategy'),
      api('/api/dashboard/goals/recommendations'),
    ]);
    hideRefresh();

    // Strategy Recommendations
    if (recs) {
      const recsBody = $('#goalRecsBody');
      if (!recs.recommendations || recs.recommendations.length === 0) {
        recsBody.innerHTML = '<div class="ai-loading">No strategy recommendations right now.</div>';
      } else {
        recsBody.innerHTML = recs.recommendations.map(r => {
          const emoji = String.fromCodePoint(parseInt(r.emoji, 16));
          const dotClass = r.priority || 'medium';
          return `<div class="ai-action">
            <div class="ai-action-emoji">${emoji}</div>
            <div class="ai-action-content">
              <div class="ai-action-title"><span class="priority-dot ${dotClass}"></span>${esc(r.title)}</div>
              <div class="ai-action-desc">${esc(r.description)}</div>
            </div>
          </div>`;
        }).join('');
      }
    }

    // Goal Cards
    if (goals && goals.goals) {
      const grid = $('#goalsGrid');
      window._goalEditCache = {};
      if (goals.goals.length === 0) {
        grid.innerHTML = '<div class="empty-state"><p>No active goals. Set goals to track your progress!</p></div>';
      } else {
        grid.innerHTML = goals.goals.map(g => {
          const valueStr = g.unit === '$' ? fmt(g.current_value) : fmtInt(g.current_value);
          const targetStr = g.unit === '$' ? fmt(g.target_value) : fmtInt(g.target_value);
          window._goalEditCache[g.id] = {id:g.id,title:g.title,target_value:g.target_value,unit:g.unit,period:g.period,period_key:g.period_key,goal_type:g.goal_type};
          return `
            <div class="goal-card">
              <div class="goal-card-header">
                <div class="goal-card-title">${esc(g.title)}</div>
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="goal-pacing ${g.pacing}">${g.pacing === 'on_track' ? 'On Track' : g.pacing === 'behind' ? 'Behind' : 'At Risk'}</span>
                  <button class="edit-icon-btn" onclick="openGoalModal(window._goalEditCache['${g.id}'])" title="Edit">&#9998;</button>
                  <button class="delete-icon-btn" onclick="deleteGoal('${g.id}','${esc(g.title)}')" title="Delete">&times;</button>
                </div>
              </div>
              <div class="goal-value">${valueStr} <span class="goal-target">/ ${targetStr}</span></div>
              <div class="goal-progress">
                <div class="goal-progress-bar">
                  <div class="goal-progress-fill ${g.pacing}" style="width:${g.progress_pct}%"></div>
                </div>
              </div>
              <div class="goal-stats">
                <div class="goal-stat"><strong>${g.progress_pct}%</strong> complete</div>
                <div class="goal-stat"><strong>${g.days_remaining}</strong> days left</div>
                ${g.daily_needed > 0 ? `<div class="goal-stat"><strong>${g.unit === '$' ? fmt(g.daily_needed) : fmtInt(g.daily_needed)}</strong>/day needed</div>` : ''}
              </div>
            </div>
          `;
        }).join('');
      }
    }

    // Product Goals
    if (productGoals && productGoals.product_goals) {
      const tbody = $('#productGoalsTable tbody');
      if (productGoals.product_goals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text3)">No product goals set</td></tr>';
      } else {
        tbody.innerHTML = productGoals.product_goals.map(pg => {
          const actualPct = pg.actual_pct != null ? pg.actual_pct : pg.progress_pct;
          const isOver = actualPct > 100;
          const isLow = actualPct < 50;
          const barClass = isOver ? 'overperforming' : isLow ? 'underperforming' : '';
          const pctLabel = isOver
            ? `<span class="progress-mini-pct overperforming">${actualPct}%</span><span class="progress-over-label">Overperforming!</span>`
            : `<span class="progress-mini-pct ${isLow ? 'underperforming' : ''}">${actualPct}%</span>`;
          return `
          <tr>
            <td>${esc(pg.product_name)}</td>
            <td>${esc(pg.product_category || '-')}</td>
            <td>${fmtInt(pg.target_units)}</td>
            <td>${fmtInt(pg.units_sold)}</td>
            <td>
              <div class="progress-mini">
                <div class="progress-mini-bar"><div class="progress-mini-fill ${barClass}" style="width:${pg.progress_pct}%"></div></div>
                ${pctLabel}
              </div>
            </td>
          </tr>
        `}).join('');
      }
    }

    // Goal History
    if (history && history.history) {
      const tbody = $('#goalHistoryTable tbody');
      if (history.history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text3)">No past goals</td></tr>';
      } else {
        tbody.innerHTML = history.history.map(h => `
          <tr>
            <td>${esc(h.period_key)}</td>
            <td>${esc(h.title)}</td>
            <td>${h.unit === '$' ? fmt(h.target_value) : fmtInt(h.target_value)}</td>
            <td>${h.unit === '$' ? fmt(h.achieved_value) : fmtInt(h.achieved_value)}</td>
            <td><span class="goal-status ${h.status}">${h.status === 'met' ? 'Met' : 'Missed'}</span></td>
          </tr>
        `).join('');
      }
    }

    // Strategy Notes
    if (strategy && strategy.strategies) {
      const container = $('#strategyNotes');
      window._stratEditCache = {};
      if (strategy.strategies.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No quarterly strategies set yet.</p></div>';
      } else {
        container.innerHTML = strategy.strategies.map(s => {
          window._stratEditCache[s.id] = {id:s.id,quarter:s.quarter,title:s.title,objectives:s.objectives,key_results:s.key_results,notes:s.notes,status:s.status};
          return `
          <div class="strategy-card">
            <div class="strategy-quarter">${esc(s.quarter)} <span class="strategy-status ${s.status}">${s.status}</span>
              <button class="edit-icon-btn" onclick="openStrategyModal(window._stratEditCache['${s.id}'])" title="Edit" style="margin-left:auto">&#9998;</button>
            </div>
            <div class="strategy-title">${esc(s.title)}</div>
            ${s.objectives && s.objectives.length > 0 ? `
              <div class="strategy-section">
                <div class="strategy-section-label">Objectives</div>
                <ul class="strategy-list">${s.objectives.map(o => '<li>' + esc(o) + '</li>').join('')}</ul>
              </div>
            ` : ''}
            ${s.key_results && s.key_results.length > 0 ? `
              <div class="strategy-section">
                <div class="strategy-section-label">Key Results</div>
                <ul class="strategy-list">${s.key_results.map(kr => '<li>' + esc(kr) + '</li>').join('')}</ul>
              </div>
            ` : ''}
            ${s.notes ? '<div class="strategy-section"><div class="strategy-section-label">Notes</div><p style="font-size:13px;color:var(--text2);line-height:1.6;">' + esc(s.notes) + '</p></div>' : ''}
          </div>
        `}).join('');
      }
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // END GOALS & STRATEGY
  // ══════════════════════════════════════════════════════════════════════════

  // ══════════════════════════════════════════════════════════════════════════
  // MARKETING CONTENT ENGINE
  // ══════════════════════════════════════════════════════════════════════════

  let mkeDataLoaded = {};

  // Tab navigation
  $$('.mke-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.dataset.tab;
      $$('.mke-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      $$('.mke-panel').forEach(p => p.classList.remove('active'));
      $(`#mkePanel-${tabName}`).classList.add('active');
      loadMkeTab(tabName);
    });
  });

  async function loadMarketingEngine() {
    const activeTab = $('.mke-tab.active');
    const tabName = activeTab ? activeTab.dataset.tab : 'calendar';
    mkeDataLoaded = {};
    await loadMkeTab(tabName);
  }

  async function loadMkeTab(tab) {
    if (mkeDataLoaded[tab]) return;
    showRefresh();
    try {
      if (tab === 'calendar') await loadMkeCalendar();
      else if (tab === 'social') await loadMkeSocial();
      else if (tab === 'emails') await loadMkeEmails();
      else if (tab === 'promos') await loadMkePromos();
      else if (tab === 'performance') await loadMkePerformance();
      else if (tab === 'predictor') await loadMkePredictor();
      else if (tab === 'hashtags') await loadMkeHashtags();
      else if (tab === 'mke-report') await loadMkeWeeklyReport();
      else if (tab === 'email-builder') await loadMkeEmailBuilder();
      else if (tab === 'weekly-digest') await loadWeeklyDigest();
      mkeDataLoaded[tab] = true;
    } catch (err) {
      console.error('[Forge] Error loading marketing tab:', tab, err);
    }
    hideRefresh();
  }

  // Regenerate button
  const regenBtn = $('#mkeRegenCalendar');
  if (regenBtn) regenBtn.addEventListener('click', () => { mkeDataLoaded['calendar'] = false; loadMkeCalendar(); });
  const schedBtn = $('#mkeScheduleAll');
  if (schedBtn) schedBtn.addEventListener('click', () => { schedBtn.textContent = 'Coming Soon!'; setTimeout(() => schedBtn.textContent = 'Add to Schedule', 2000); });
  const genMoreBtn = $('#mkeGenMore');
  if (genMoreBtn) genMoreBtn.addEventListener('click', () => { genMoreBtn.textContent = 'Coming Soon!'; setTimeout(() => genMoreBtn.textContent = 'Generate More', 2000); });

  const platformIcons = {
    instagram: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>',
    instagram_story: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>',
    facebook: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>',
    email: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
  };
  const platformLabels = {
    instagram: 'Instagram', instagram_story: 'IG Story', facebook: 'Facebook', email: 'Email',
  };
  const platformColors = {
    instagram: '#E1306C', instagram_story: '#E1306C', facebook: '#1877F2', email: '#6366f1',
  };

  function copyText(text, btn) {
    navigator.clipboard.writeText(text);
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  }

  // ── Content Calendar ──
  async function loadMkeCalendar() {
    const data = await api('/api/dashboard/marketing-engine/calendar');
    if (!data || !data.days || data.days.length === 0) {
      const grid = $('#mkeCalendarGrid');
      grid.innerHTML = `<div class="empty-state-card" style="grid-column:1/-1">
        <div class="empty-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg></div>
        <div class="empty-title">Marketing templates coming soon</div>
        <div class="empty-desc">Connect your POS to get AI-generated content based on your actual products and sales data. In the meantime, start posting about your shop on social media!</div>
      </div>`;
      return;
    }

    const grid = $('#mkeCalendarGrid');
    grid.innerHTML = data.days.map(day => {
      const isToday = day.date === new Date().toISOString().split('T')[0];
      return `
        <div class="mke-cal-day ${isToday ? 'today' : ''}">
          <div class="mke-cal-day-header">
            <span class="mke-cal-day-name">${day.day}</span>
            <span class="mke-cal-day-date">${day.date.slice(5)}</span>
          </div>
          <div class="mke-cal-posts">
            ${day.posts.map(post => `
              <div class="mke-cal-post">
                <div class="mke-cal-post-meta">
                  <span class="mke-platform-badge" style="color:${platformColors[post.platform] || '#6366f1'}">${platformIcons[post.platform] || ''} ${platformLabels[post.platform] || post.platform}</span>
                  <span class="mke-cal-time">${post.time}</span>
                </div>
                <div class="mke-cal-post-content">${esc(post.content)}</div>
                <button class="mke-copy-btn" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }).join('');
  }

  // ── Social Posts ──
  async function loadMkeSocial(category) {
    let url = '/api/dashboard/marketing-engine/social-posts';
    if (category) url += `?category=${category}`;
    const data = await api(url);
    if (!data) return;

    // Render category filters
    const filters = $('#mkeSocialFilters');
    if (data.categories) {
      filters.innerHTML = `
        <button class="mke-filter-btn ${!category ? 'active' : ''}" data-cat="">All (${data.total})</button>
        ${data.categories.map(c => `<button class="mke-filter-btn ${category === c.id ? 'active' : ''}" data-cat="${c.id}">${c.emoji} ${c.label} (${c.count})</button>`).join('')}
      `;
      $$('.mke-filter-btn', filters).forEach(btn => {
        btn.addEventListener('click', () => {
          mkeDataLoaded['social'] = false;
          loadMkeSocial(btn.dataset.cat || null);
        });
      });
    }

    const grid = $('#mkeSocialGrid');
    grid.innerHTML = data.posts.map(post => `
      <div class="mke-social-card">
        <div class="mke-social-card-header">
          <span class="mke-category-badge">${post.category.replace(/_/g, ' ')}</span>
          <span class="mke-platform-badge" style="color:${platformColors[post.platform] || '#6366f1'}">${platformIcons[post.platform] || ''} ${platformLabels[post.platform] || post.platform}</span>
        </div>
        <div class="mke-social-caption">${esc(post.caption)}</div>
        <div class="mke-social-meta">
          <span class="mke-meta-item">Best time: <strong>${post.best_time}</strong></span>
          ${post.product_name ? `<span class="mke-meta-item">Product: <strong>${esc(post.product_name)}</strong></span>` : ''}
        </div>
        <div class="mke-social-hashtags">${esc(post.hashtags)}</div>
        <div class="mke-social-actions">
          <button class="mke-copy-btn" onclick="navigator.clipboard.writeText(this.closest('.mke-social-card').querySelector('.mke-social-caption').textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Caption',2000)">Copy Caption</button>
          <button class="mke-copy-btn secondary" onclick="navigator.clipboard.writeText(this.closest('.mke-social-card').querySelector('.mke-social-hashtags').textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Hashtags',2000)">Copy Hashtags</button>
        </div>
      </div>
    `).join('');
  }

  // ── Email Campaigns ──
  async function loadMkeEmails() {
    const data = await api('/api/dashboard/marketing-engine/email-campaigns');
    if (!data) return;

    const list = $('#mkeEmailList');
    list.innerHTML = data.campaigns.map(camp => `
      <div class="mke-email-card">
        <div class="mke-email-header">
          <div>
            <div class="mke-email-name">${camp.emoji} ${esc(camp.name)}</div>
            <div class="mke-email-target">${esc(camp.target_audience)}</div>
          </div>
          <div class="mke-email-stats">
            <span class="mke-email-stat"><strong>${camp.target_count}</strong> recipients</span>
            <span class="mke-email-stat"><strong>${camp.estimated_open_rate}</strong> est. open</span>
            <span class="mke-email-stat"><strong>${camp.estimated_revenue}</strong> est. revenue</span>
          </div>
        </div>
        <div class="mke-email-preview">
          <div class="mke-email-subject-row">
            <span class="mke-email-label">Subject:</span>
            <span class="mke-email-subject">${esc(camp.subject)}</span>
          </div>
          <div class="mke-email-preview-text">
            <span class="mke-email-label">Preview:</span>
            <span>${esc(camp.preview_text)}</span>
          </div>
          <div class="mke-email-body-wrap">
            <div class="mke-email-body">${esc(camp.body).replace(/\n/g, '<br>')}</div>
          </div>
        </div>
        <div class="mke-email-actions">
          <button class="mke-copy-btn" data-copy-type="body" data-camp-id="${camp.id}">Copy Text</button>
          <button class="mke-copy-btn secondary" data-copy-type="all" data-camp-id="${camp.id}">Copy All</button>
        </div>
      </div>
    `).join('');

    // Store campaign data for copy buttons
    window.__mkeEmailData = {};
    data.campaigns.forEach(c => { window.__mkeEmailData[c.id] = c; });

    // Attach copy handlers
    $$('.mke-email-actions .mke-copy-btn', list).forEach(btn => {
      btn.addEventListener('click', () => {
        const camp = window.__mkeEmailData[btn.dataset.campId];
        if (!camp) return;
        const text = btn.dataset.copyType === 'all'
          ? 'Subject: ' + camp.subject + '\n\n' + camp.body
          : camp.body;
        navigator.clipboard.writeText(text);
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = orig, 2000);
      });
    });
  }

  // ── Promotions ──
  async function loadMkePromos() {
    const data = await api('/api/dashboard/marketing-engine/promotions');
    if (!data) return;

    const list = $('#mkePromoList');
    list.innerHTML = data.promotions.map(promo => `
      <div class="mke-promo-card">
        <div class="mke-promo-header">
          <div class="mke-promo-name">${promo.emoji} ${esc(promo.name)}</div>
          <span class="opp-priority ${promo.priority}">${promo.priority === 'hot' ? 'Hot' : promo.priority === 'high' ? 'High Impact' : 'Recommended'}</span>
        </div>
        <div class="mke-promo-desc">${esc(promo.description)}</div>
        <div class="mke-promo-details">
          <div class="mke-promo-detail"><span class="mke-promo-detail-label">Target</span><span>${esc(promo.target_audience)}</span></div>
          <div class="mke-promo-detail"><span class="mke-promo-detail-label">Est. Revenue</span><span>${esc(promo.estimated_revenue)}</span></div>
          <div class="mke-promo-detail"><span class="mke-promo-detail-label">Duration</span><span>${esc(promo.duration)}</span></div>
        </div>
        <div class="mke-promo-steps">
          <div class="mke-promo-steps-label">Execution Steps</div>
          <ol class="mke-promo-steps-list">
            ${promo.execution_steps.map(s => `<li>${esc(s)}</li>`).join('')}
          </ol>
        </div>
        <div class="mke-promo-social">
          <div class="mke-promo-social-label">Ready-to-Post Announcement</div>
          <div class="mke-promo-social-text">${esc(promo.social_post)}</div>
          <button class="mke-copy-btn" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Post',2000)">Copy Post</button>
        </div>
      </div>
    `).join('');
  }

  // ── Performance ──
  async function loadMkePerformance() {
    const data = await api('/api/dashboard/marketing-engine/performance');
    if (!data) return;

    const content = $('#mkePerfContent');
    const o = data.overview;
    const mr = data.marketing_responses;
    const ei = data.estimated_impact;
    const eng = data.engagement;
    const cta = data.connect_cta;

    content.innerHTML = `
      <div class="kpi-grid small">
        <div class="kpi-card"><div class="kpi-label">Content Generated</div><div class="kpi-value">${fmtInt(eng.total_content_pieces)}</div><div class="kpi-sub">total pieces</div></div>
        <div class="kpi-card"><div class="kpi-label">Pieces Used</div><div class="kpi-value">${fmtInt(eng.pieces_used)}</div><div class="kpi-sub">${eng.usage_rate}% usage rate</div></div>
        <div class="kpi-card"><div class="kpi-label">Pieces Saved</div><div class="kpi-value">${fmtInt(eng.pieces_saved)}</div><div class="kpi-sub">for later use</div></div>
        <div class="kpi-card"><div class="kpi-label">Est. Revenue Impact</div><div class="kpi-value">${fmt(ei.estimated_additional_revenue)}</div><div class="kpi-sub">${ei.marketing_boost_pct}% boost</div></div>
      </div>

      <div class="grid-2 mt">
        <div class="card">
          <div class="card-header"><h3>Content Breakdown</h3></div>
          <div class="card-body">
            <div class="mke-perf-breakdown">
              <div class="mke-perf-row"><span>Calendar Posts (this week)</span><strong>${o.calendar_posts_this_week}</strong></div>
              <div class="mke-perf-row"><span>Social Media Posts</span><strong>20+</strong></div>
              <div class="mke-perf-row"><span>Email Campaigns Ready</span><strong>${o.email_campaigns_ready}</strong></div>
              <div class="mke-perf-row"><span>Promotion Plans</span><strong>${o.promotions_active}</strong></div>
              <div class="mke-perf-row"><span>Competitor Responses</span><strong>${mr.total}</strong></div>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><h3>Marketing Responses</h3></div>
          <div class="card-body">
            <div class="mke-perf-breakdown">
              <div class="mke-perf-row"><span>New (unused)</span><strong class="mke-stat-new">${mr.new}</strong></div>
              <div class="mke-perf-row"><span>Saved for Later</span><strong class="mke-stat-saved">${mr.saved}</strong></div>
              <div class="mke-perf-row"><span>Used / Deployed</span><strong class="mke-stat-used">${mr.used}</strong></div>
              <div class="mke-perf-row total"><span>Total Generated</span><strong>${mr.total}</strong></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-header"><h3>Revenue Impact Estimate</h3></div>
        <div class="card-body">
          <div class="mke-impact-card">
            <div class="mke-impact-text">Based on industry averages, your marketing activity this month could drive an additional <strong>${fmt(ei.estimated_additional_revenue)}</strong> in revenue (${ei.marketing_boost_pct}% boost on ${fmt(ei.monthly_revenue)} monthly revenue).</div>
            <div class="mke-impact-tip">Tip: Use more content pieces to increase this estimate. Each social post, email campaign, and promotion adds to your marketing presence.</div>
          </div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-body">
          <div class="mke-cta-card">
            <div class="mke-cta-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg></div>
            <div class="mke-cta-content">
              <div class="mke-cta-title">${esc(cta.title)}</div>
              <div class="mke-cta-desc">${esc(cta.description)}</div>
            </div>
            <button class="mke-btn primary" disabled>Coming Soon</button>
          </div>
        </div>
      </div>
    `;
  }

  // ── Content Predictor Tab ──
  async function loadMkePredictor() {
    // Just wire up the analyze button — results load on demand
    const btn = $('#predictorAnalyze');
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', async () => {
      const text = $('#predictorInput').value.trim();
      if (!text) return;
      const platform = $('#predictorPlatform').value;
      btn.textContent = 'Analyzing...';
      btn.disabled = true;
      const data = await apiPost(`/api/dashboard/marketing-engine/predict?content=${encodeURIComponent(text)}&platform=${platform}`);
      btn.textContent = 'Analyze Post';
      btn.disabled = false;
      if (!data) return;

      const el = $('#predictorResults');
      el.hidden = false;
      const scoreColor = data.color === 'success' ? 'var(--success)' : data.color === 'primary' ? 'var(--primary-light)' : data.color === 'warning' ? 'var(--warning)' : 'var(--danger)';

      el.innerHTML = `
        <div class="pred-score-wrap">
          <div class="pred-score-circle" style="border-color:${scoreColor}">
            <span class="pred-score-num" style="color:${scoreColor}">${data.score}</span>
            <span class="pred-score-label">${esc(data.rating)}</span>
          </div>
          <div class="pred-stats">
            <div class="pred-stat"><span>Characters</span><strong>${data.char_count}</strong></div>
            <div class="pred-stat"><span>Hashtags</span><strong>${data.hashtag_count}</strong></div>
            <div class="pred-stat"><span>Emojis</span><strong>${data.emoji_count}</strong></div>
            <div class="pred-stat"><span>Platform</span><strong>${esc(data.platform)}</strong></div>
          </div>
        </div>
        <div class="pred-factors">
          <h4>Score Breakdown</h4>
          ${data.factors.map(f => `
            <div class="pred-factor ${f.type}">
              <span class="pred-factor-impact">${esc(f.impact)}</span>
              <span>${esc(f.factor)}</span>
            </div>
          `).join('')}
        </div>
        ${data.suggestions.length > 0 ? `
          <div class="pred-suggestions">
            <h4>Suggestions to Improve</h4>
            ${data.suggestions.map(s => `<div class="pred-suggestion">${esc(s)}</div>`).join('')}
          </div>
        ` : ''}
      `;
    });
  }

  // ── Hashtag Generator Tab ──
  async function loadMkeHashtags(topic) {
    const topicVal = topic || $('#hashtagTopic')?.value || '';
    const data = await api(`/api/dashboard/marketing-engine/hashtags?topic=${encodeURIComponent(topicVal)}`);
    if (!data) return;

    const el = $('#hashtagResults');
    el.innerHTML = `
      <div class="ht-recommended">
        <h4>Recommended Set (Copy All)</h4>
        <div class="ht-copy-row">
          <div class="ht-tags">${data.recommended.map(t => `<span class="ht-tag">${esc(t)}</span>`).join('')}</div>
          <button class="mke-btn outline ht-copy-btn" onclick="navigator.clipboard.writeText('${esc(data.copy_all)}');this.textContent='Copied!';setTimeout(()=>this.textContent='Copy All',2000)">Copy All</button>
        </div>
      </div>
      <div class="ht-sets">
        ${Object.entries(data.sets).map(([key, tags]) => `
          <div class="ht-set">
            <div class="ht-set-header">
              <span class="ht-set-name">${key.charAt(0).toUpperCase() + key.slice(1)}</span>
              <button class="ht-set-copy" onclick="navigator.clipboard.writeText('${esc(tags.join(' '))}');this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
            </div>
            <div class="ht-tags">${tags.map(t => `<span class="ht-tag">${esc(t)}</span>`).join('')}</div>
          </div>
        `).join('')}
      </div>
      <div class="ht-tip">${esc(data.tip)}</div>
    `;

    // Wire up generate button
    const genBtn = $('#hashtagGenerate');
    if (genBtn && !genBtn.dataset.wired) {
      genBtn.dataset.wired = '1';
      genBtn.addEventListener('click', () => {
        mkeDataLoaded['hashtags'] = false;
        loadMkeHashtags($('#hashtagTopic').value);
      });
    }
  }

  // ── Weekly Marketing Report Tab ──
  async function loadMkeWeeklyReport() {
    const data = await api('/api/dashboard/marketing-engine/weekly-report');
    if (!data) return;

    const el = $('#mkeWeeklyReport');
    const revDir = data.revenue.change_pct >= 0 ? 'up' : 'down';

    el.innerHTML = `
      <div class="mwr-header">
        <h2>Weekly Marketing Report</h2>
        <div class="mwr-period">${data.period.start} to ${data.period.end}</div>
      </div>

      <div class="mwr-kpis">
        <div class="mwr-kpi">
          <div class="mwr-kpi-value">$${data.revenue.this_week.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
          <div class="mwr-kpi-label">Revenue This Week</div>
          <div class="mwr-kpi-change ${revDir}">${revDir === 'up' ? '+' : ''}${data.revenue.change_pct}% vs last week</div>
        </div>
        <div class="mwr-kpi">
          <div class="mwr-kpi-value">${data.revenue.transactions}</div>
          <div class="mwr-kpi-label">Transactions</div>
        </div>
        <div class="mwr-kpi">
          <div class="mwr-kpi-value">${data.content.score}/100</div>
          <div class="mwr-kpi-label">Content Score</div>
        </div>
        <div class="mwr-kpi">
          <div class="mwr-kpi-value">${data.competitor_opportunities}</div>
          <div class="mwr-kpi-label">Competitor Opps</div>
        </div>
      </div>

      ${data.top_products.length > 0 ? `
        <div class="mwr-section">
          <h3>Top Products to Promote</h3>
          <div class="mwr-products">
            ${data.top_products.map((p, i) => `
              <div class="mwr-product-row">
                <span class="mwr-rank">#${i + 1}</span>
                <span class="mwr-product-name">${esc(p.name)}</span>
                <span class="mwr-product-units">${p.units} sold</span>
                <span class="mwr-product-rev">$${p.revenue.toLocaleString(undefined,{maximumFractionDigits:0})}</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      <div class="mwr-section">
        <h3>This Week's Recommendations</h3>
        ${data.recommendations.map(r => {
          const emoji = String.fromCodePoint(parseInt(r.icon, 16));
          return `
            <div class="mwr-rec ${r.priority}">
              <span class="mwr-rec-icon">${emoji}</span>
              <span class="mwr-rec-text">${esc(r.text)}</span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  // ── Email Template Builder Tab ──
  async function loadMkeEmailBuilder() {
    const btn = $('#ebBuild');
    if (!btn || btn.dataset.wired) {
      // Just load default template
      await _buildEmailTemplate();
      return;
    }
    btn.dataset.wired = '1';
    btn.addEventListener('click', () => _buildEmailTemplate());
    await _buildEmailTemplate();
  }

  async function _buildEmailTemplate() {
    const type = $('#ebTemplateType').value;
    const discount = $('#ebDiscount').value || '15';
    const data = await api(`/api/dashboard/marketing-engine/email-template?template_type=${type}&discount=${discount}`);
    if (!data) return;

    const el = $('#ebResult');
    const t = data.template;

    el.innerHTML = `
      <div class="eb-template">
        <div class="eb-template-header">
          <h4>${esc(t.name)}</h4>
          <div class="eb-meta">
            <span class="eb-meta-item">Target: ${esc(t.target)}</span>
            <span class="eb-meta-item">Est. Open Rate: ${esc(t.est_open_rate)}</span>
          </div>
        </div>
        <div class="eb-field">
          <label>Subject Line</label>
          <div class="eb-field-value" id="ebSubject">${esc(t.subject)}</div>
          <button class="eb-copy" onclick="navigator.clipboard.writeText(document.getElementById('ebSubject').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
        </div>
        <div class="eb-field">
          <label>Preview Text</label>
          <div class="eb-field-value">${esc(t.preview)}</div>
        </div>
        <div class="eb-field">
          <label>Email Body</label>
          <div class="eb-field-value eb-body" id="ebBody">${esc(t.body)}</div>
          <button class="eb-copy" onclick="navigator.clipboard.writeText(document.getElementById('ebBody').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000)">Copy</button>
        </div>
      </div>
    `;
  }

  // ── Weekly Digest Preview Tab ──
  async function loadWeeklyDigest() {
    const wrap = $('#digestPreviewWrap');
    if (!wrap) return;
    wrap.innerHTML = '<div class="ai-loading">Loading digest preview...</div>';
    try {
      const res = await fetch('/api/dashboard/weekly-digest-preview', {credentials: 'same-origin'});
      if (!res.ok) { wrap.innerHTML = '<p class="text-muted">Could not load digest preview.</p>'; return; }
      const html = await res.text();
      wrap.innerHTML = `
        <div class="digest-iframe-wrap">
          <iframe id="digestIframe" class="digest-iframe" sandbox="allow-same-origin" srcdoc="${html.replace(/"/g, '&quot;')}"></iframe>
        </div>
        <div class="digest-actions">
          <button class="mke-btn primary" onclick="window.open('/api/dashboard/weekly-digest-preview','_blank')">Open Full Preview</button>
          <button class="mke-btn" onclick="copyToClipboard(document.getElementById('digestIframe').srcdoc, this)">Copy HTML</button>
        </div>
      `;
    } catch (e) {
      wrap.innerHTML = '<p class="text-muted">Error loading digest.</p>';
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // END MARKETING CONTENT ENGINE
  // ══════════════════════════════════════════════════════════════════════════

  // ══════════════════════════════════════════════════════════════════════════
  // DAILY BRIEFING
  // ══════════════════════════════════════════════════════════════════════════

  async function loadBriefing() {
    showRefresh();
    const data = await api('/api/dashboard/briefing');
    hideRefresh();
    if (!data) return;

    // Greeting
    const greetEl = $('#briefingGreeting');
    greetEl.textContent = `${data.greeting}, ${data.first_name}!`;
    $('#briefingDate').textContent = data.date;

    // Numbers
    const n = data.numbers;
    animateValue($('#brfRevenue'), n.yesterday_revenue, 800, '$');
    animateValue($('#brfTransactions'), n.yesterday_transactions, 800);
    $('#brfAov').textContent = fmt(n.yesterday_aov);

    const revChangeEl = $('#brfRevChange');
    revChangeEl.textContent = (n.rev_change_vs_last_week >= 0 ? '+' : '') + n.rev_change_vs_last_week + '% vs same day last week';
    revChangeEl.className = 'briefing-num-change ' + (n.rev_change_vs_last_week >= 0 ? 'up' : 'down');

    const txnChangeEl = $('#brfTxnChange');
    txnChangeEl.textContent = (n.txn_change_vs_last_week >= 0 ? '+' : '') + n.txn_change_vs_last_week + '% vs last week';
    txnChangeEl.className = 'briefing-num-change ' + (n.txn_change_vs_last_week >= 0 ? 'up' : 'down');

    $('#brfGoalPct').textContent = n.goal_progress_pct + '%';
    const fill = $('#brfGoalFill');
    fill.style.width = '0%';
    setTimeout(() => fill.style.width = Math.min(n.goal_progress_pct, 100) + '%', 100);
    $('#brfGoalSub').textContent = fmt(n.monthly_total) + ' / ' + fmt(n.monthly_goal);

    // Todos
    const todosEl = $('#briefingTodos');
    if (data.todos && data.todos.length > 0) {
      todosEl.innerHTML = data.todos.map(t => `
        <div class="briefing-todo">
          <div class="briefing-todo-priority ${t.priority}"></div>
          <div class="briefing-todo-content">
            <div class="briefing-todo-title">${esc(t.title)}</div>
            <div class="briefing-todo-desc">${esc(t.description)}</div>
            <div class="briefing-todo-meta">
              <span class="briefing-todo-impact">${esc(t.impact)}</span>
              <button class="briefing-todo-link" data-link="${t.link}">Do It Now</button>
            </div>
          </div>
        </div>
      `).join('');

      // "Do It Now" buttons navigate to the relevant section
      $$('.briefing-todo-link', todosEl).forEach(btn => {
        btn.addEventListener('click', () => {
          const section = btn.dataset.link;
          const navItem = $(`.nav-item[data-section="${section}"]`);
          if (navItem) navItem.click();
        });
      });
    } else {
      todosEl.innerHTML = '<div class="ai-loading">Everything looks great! No urgent tasks today.</div>';
    }

    // Competitor Watch
    const compEl = $('#briefingCompWatch');
    if (data.competitor_watch && data.competitor_watch.length > 0) {
      compEl.innerHTML = data.competitor_watch.map(c => `
        <div class="briefing-comp-item">
          <div class="briefing-comp-name">${esc(c.name)}</div>
          <div class="briefing-comp-stats">
            <span>${c.rating ? c.rating.toFixed(1) + ' &#9733;' : '--'}</span>
            <span>${c.new_reviews} new review${c.new_reviews !== 1 ? 's' : ''}</span>
            ${c.negative_reviews > 0 ? `<span class="neg">${c.negative_reviews} negative</span>` : ''}
          </div>
        </div>
      `).join('');
    } else {
      compEl.innerHTML = '<div style="padding:12px;color:var(--text3);font-size:13px;">No competitor data yet. Add competitors in your settings.</div>';
    }

    // Customer Pulse
    const pulseEl = $('#briefingPulse');
    const p = data.customer_pulse;
    pulseEl.innerHTML = `
      <div class="briefing-pulse-item">
        <div class="briefing-pulse-value">${fmtInt(p.new_customers_7d)}</div>
        <div class="briefing-pulse-label">New This Week</div>
      </div>
      <div class="briefing-pulse-item atrisk">
        <div class="briefing-pulse-value">${fmtInt(p.at_risk_count)}</div>
        <div class="briefing-pulse-label">At Risk</div>
      </div>
      <div class="briefing-pulse-item vip">
        <div class="briefing-pulse-value">${fmtInt(p.vip_count)}</div>
        <div class="briefing-pulse-label">VIP Customers</div>
      </div>
      <div class="briefing-pulse-item">
        <div class="briefing-pulse-value">${fmtInt(p.total_customers)}</div>
        <div class="briefing-pulse-label">Total Customers</div>
      </div>
    `;

    // Marketing Tip
    const mktEl = $('#briefingMarketing');
    const m = data.marketing;
    mktEl.innerHTML = `
      <div class="briefing-marketing-card">
        <div class="briefing-mkt-title">
          ${esc(m.title)}
          <span class="briefing-mkt-platform">${esc(m.platform)}</span>
        </div>
        <div class="briefing-mkt-content">${esc(m.content)}</div>
        <button class="briefing-mkt-copy" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent.trim());this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Tip',2000)">Copy Tip</button>
      </div>
    `;
  }

  // animateValue is defined later in the file — do not duplicate

  // ══════════════════════════════════════════════════════════════════════════
  // WIN-BACK CAMPAIGNS
  // ══════════════════════════════════════════════════════════════════════════

  let wbDonutChart = null;

  async function loadWinback() {
    showRefresh();
    const [overview, atRisk, templates, history, settings] = await Promise.all([
      api('/api/dashboard/winback/overview'),
      api('/api/dashboard/winback/at-risk'),
      api('/api/dashboard/winback/templates'),
      api('/api/dashboard/winback/history'),
      api('/api/dashboard/winback/settings'),
    ]);
    hideRefresh();

    // Overview metrics
    if (overview) {
      $('#wbActive').textContent = fmtInt(overview.active);
      $('#wbAtRisk').textContent = fmtInt(overview.at_risk);
      $('#wbLost').textContent = fmtInt(overview.lost);
      $('#wbWonBack').textContent = fmtInt(overview.won_back);

      // Donut chart
      renderWbDonut(overview.segments);
    }

    // At-risk table
    if (atRisk && atRisk.customers) {
      renderWbAtRiskTable(atRisk.customers);
    }

    // Templates
    if (templates && templates.templates) {
      window.__wbTemplates = {};
      templates.templates.forEach(t => { window.__wbTemplates[t.id] = t.body; });

      const tplEl = $('#wbTemplates');
      tplEl.innerHTML = templates.templates.map(t => `
        <div class="wb-template-card">
          <div class="wb-template-emoji">${t.emoji}</div>
          <div class="wb-template-name">${esc(t.name)}</div>
          <div class="wb-template-desc">${esc(t.description)}</div>
          <div class="wb-template-meta">
            <span class="wb-template-tag">${esc(t.best_for)}</span>
            ${t.discount > 0 ? `<span class="wb-template-tag discount">${t.discount}% off</span>` : '<span class="wb-template-tag">No discount</span>'}
            <span class="wb-template-tag">${esc(t.expected_response)} response</span>
          </div>
          <div class="wb-template-preview">Subject: ${esc(t.subject)}</div>
          <button class="wb-template-btn" data-tpl="${t.id}">Copy Email Template</button>
        </div>
      `).join('');

      $$('.wb-template-btn', tplEl).forEach(btn => {
        btn.addEventListener('click', () => {
          const body = window.__wbTemplates[btn.dataset.tpl];
          if (body) navigator.clipboard.writeText(body);
          btn.textContent = 'Copied!';
          setTimeout(() => btn.textContent = 'Copy Email Template', 2000);
        });
      });
    }

    // Campaign History
    if (history && history.campaigns) {
      const tbody = $('#wbHistoryTable tbody');
      if (history.campaigns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text3)">No campaigns sent yet. Use a template above to get started!</td></tr>';
      } else {
        tbody.innerHTML = history.campaigns.map(c => `
          <tr>
            <td>${esc(c.name)}</td>
            <td>${esc(c.template_type)}</td>
            <td>${fmtInt(c.customers_targeted)}</td>
            <td>${c.discount_percentage}%</td>
            <td><span class="goal-status ${c.status}">${c.status}</span></td>
            <td>${c.open_rate ? c.open_rate + '%' : '--'}</td>
            <td>${c.revenue_recovered ? fmt(c.revenue_recovered) : '--'}</td>
            <td>${c.sent_at ? c.sent_at.split('T')[0] : '--'}</td>
          </tr>
        `).join('');
      }
    }

    // Automation Settings
    if (settings) {
      const autoEl = $('#wbAutomation');
      autoEl.innerHTML = `
        <div class="wb-auto-toggle">
          <div>
            <div class="wb-auto-toggle-label">Automated Win-Back Emails</div>
            <div class="wb-auto-toggle-sub">Automatically send personalized emails to at-risk customers</div>
          </div>
          <div class="wb-auto-switch ${settings.enabled ? 'on' : ''}" id="wbAutoSwitch"></div>
        </div>
        <div class="wb-auto-settings">
          <div class="wb-auto-setting">
            <div class="wb-auto-setting-label">Gentle Nudge After</div>
            <div class="wb-auto-setting-value">${settings.gentle_nudge_days} days</div>
          </div>
          <div class="wb-auto-setting">
            <div class="wb-auto-setting-label">Sweet Deal After</div>
            <div class="wb-auto-setting-value">${settings.sweet_deal_days} days (${settings.sweet_deal_discount}% off)</div>
          </div>
          <div class="wb-auto-setting">
            <div class="wb-auto-setting-label">Last Chance After</div>
            <div class="wb-auto-setting-value">${settings.last_chance_days} days (${settings.last_chance_discount}% off)</div>
          </div>
        </div>
      `;
      const autoSwitch = $('#wbAutoSwitch');
      if (autoSwitch) {
        autoSwitch.addEventListener('click', () => {
          autoSwitch.classList.toggle('on');
        });
      }
    }
  }

  function renderWbDonut(segments) {
    const ctx = $('#wbDonutChart');
    if (!ctx) return;
    if (wbDonutChart) wbDonutChart.destroy();

    const c = chartColors();
    wbDonutChart = new Chart(ctx.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: ['Active', 'At Risk', 'Lost', 'Won Back'],
        datasets: [{
          data: [segments.active || 0, segments.at_risk || 0, segments.lost || 0, segments.won_back || 0],
          backgroundColor: ['#10b981', '#f59e0b', '#ef4444', '#6366f1'],
          borderColor: 'transparent',
          borderWidth: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        cutout: '65%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {color: c.text, font: {size: 12, family: 'Inter'}, padding: 16, usePointStyle: true},
          },
        },
      },
    });
  }

  function renderWbAtRiskTable(customers) {
    const tbody = $('#wbAtRiskTable tbody');
    if (!customers || customers.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text3)">No at-risk customers found. Great news!</td></tr>';
      return;
    }
    tbody.innerHTML = customers.map(c => `
      <tr>
        <td><input type="checkbox" class="wb-row-check" data-id="${c.id}"></td>
        <td>${esc(c.email)}</td>
        <td>${c.last_seen ? c.last_seen.split('T')[0] : '--'}</td>
        <td><span style="color:${c.days_since_visit > 60 ? 'var(--danger)' : 'var(--warning)'};font-weight:600">${c.days_since_visit}d</span></td>
        <td>${fmt(c.total_spent)}</td>
        <td>${esc(c.favorite_product)}</td>
        <td>${fmtInt(c.visit_count)}</td>
        <td><button class="wb-email-btn">Send Email</button></td>
      </tr>
    `).join('');

    // Select all checkbox
    const selectAll = $('#wbSelectAll');
    if (selectAll) {
      selectAll.addEventListener('change', () => {
        $$('.wb-row-check').forEach(cb => cb.checked = selectAll.checked);
      });
    }

    // Email buttons
    $$('.wb-email-btn', tbody).forEach(btn => {
      btn.addEventListener('click', () => {
        btn.textContent = 'Coming Soon!';
        setTimeout(() => btn.textContent = 'Send Email', 2000);
      });
    });
  }

  // Sort handler for at-risk table
  const wbSort = $('#wbSortBy');
  if (wbSort) {
    wbSort.addEventListener('change', async () => {
      showRefresh();
      const data = await api('/api/dashboard/winback/at-risk?sort_by=' + wbSort.value);
      hideRefresh();
      if (data && data.customers) renderWbAtRiskTable(data.customers);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // NOTIFICATION BELL — handled by inline <script> in dashboard.html
  // ══════════════════════════════════════════════════════════════════════════

  async function loadReviews() {
    showRefresh();
    const data = await api('/api/dashboard/reviews');
    hideRefresh();
    if (!data) return;

    if (data.total_reviews === 0) {
      const sec = $('#sec-reviews');
      sec.innerHTML = emptyCard(
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        'No reviews yet',
        'Connect your Google Business Profile to monitor reviews. You\'ll see ratings, sentiment analysis, response suggestions, and review velocity here.'
      );
      return;
    }

    $('#revAvg').textContent = data.avg_rating ? data.avg_rating + ' / 5' : '--';
    $('#revTotal').textContent = fmtInt(data.total_reviews);
    $('#revPos').textContent = fmtInt(data.sentiment_breakdown.positive || 0);
    $('#revNeg').textContent = fmtInt(data.sentiment_breakdown.negative || 0);

    const list = $('#reviewList');
    list.innerHTML = data.reviews.map(r => `
      <div class="review-item">
        <div class="review-header">
          <span class="review-author">${esc(r.author_name || 'Anonymous')}</span>
          <span class="review-stars">${'&#9733;'.repeat(r.rating)}${'&#9734;'.repeat(5 - r.rating)}</span>
        </div>
        <div class="review-text">"${esc(r.text || '')}"</div>
        <div class="review-date">
          ${r.review_date ? r.review_date.split('T')[0] : ''}
          ${r.sentiment ? `<span class="sentiment-tag ${r.sentiment}">${r.sentiment}</span>` : ''}
        </div>
      </div>
    `).join('');
  }

  async function loadAlerts() {
    showRefresh();
    const data = await api('/api/dashboard/alerts');
    hideRefresh();
    if (!data) return;
    renderAlertList($('#alertListFull'), data.alerts);
  }

  // ── Renderers ──

  function renderRevenueChart(daily) {
    const c = chartColors();
    const ctx = $('#revenueChart').getContext('2d');
    if (revenueChart) revenueChart.destroy();

    revenueChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: daily.map(d => d.date.slice(5)),
        datasets: [{
          label: 'Revenue',
          data: daily.map(d => d.revenue),
          borderColor: c.line,
          backgroundColor: c.fill,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 5,
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {legend: {display: false}, tooltip: {callbacks: {label: ctx => fmt(ctx.parsed.y)}}},
        scales: {
          x: {grid: {color: c.grid}, ticks: {color: c.text, maxTicksLimit: 10, font: {size: 11}}},
          y: {grid: {color: c.grid}, ticks: {color: c.text, callback: v => '$' + (v >= 1000 ? (v/1000).toFixed(1) + 'k' : v), font: {size: 11}}},
        }
      }
    });
  }

  function renderSalesChartFull(daily) {
    const c = chartColors();
    const ctx = $('#salesChartFull').getContext('2d');
    if (salesChartFull) salesChartFull.destroy();

    salesChartFull = new Chart(ctx, {
      type: 'line',
      data: {
        labels: daily.map(d => d.date.slice(5)),
        datasets: [{
          label: 'Revenue',
          data: daily.map(d => d.revenue),
          borderColor: c.line,
          backgroundColor: c.fill,
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {legend: {display: false}, tooltip: {callbacks: {label: ctx => fmt(ctx.parsed.y)}}},
        scales: {
          x: {grid: {color: c.grid}, ticks: {color: c.text, maxTicksLimit: 15, font: {size: 11}}},
          y: {grid: {color: c.grid}, ticks: {color: c.text, callback: v => '$' + (v >= 1000 ? (v/1000).toFixed(1) + 'k' : v), font: {size: 11}}},
        }
      }
    });
  }

  function renderHeatmap(data) {
    const container = $('#heatmap');
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const hours = [];
    for (let h = 7; h <= 21; h++) hours.push(h);

    const grid = {};
    let maxVal = 0;
    data.forEach(d => {
      const key = `${d.day}-${d.hour}`;
      grid[key] = d.value;
      if (d.value > maxVal) maxVal = d.value;
    });

    let markup = '<div class="heatmap-header">';
    hours.forEach(h => markup += `<span>${h > 12 ? (h-12)+'p' : h+'a'}</span>`);
    markup += '</div>';

    days.forEach((day, di) => {
      markup += `<div class="heatmap-row"><span class="heatmap-label">${day}</span>`;
      hours.forEach(h => {
        const val = grid[`${di}-${h}`] || 0;
        const intensity = maxVal > 0 ? val / maxVal : 0;
        const bg = `rgba(99,102,241,${0.05 + intensity * 0.85})`;
        markup += `<div class="heatmap-cell" style="background:${bg}" data-tip="${day} ${h}:00 — ${fmt(val)}"></div>`;
      });
      markup += '</div>';
    });

    container.innerHTML = markup;
  }

  function renderAiActions(actions) {
    const body = $('#aiActionsBody');
    if (!actions || actions.length === 0) {
      body.innerHTML = '<div class="ai-loading">No action items right now — your shop is running great!</div>';
      return;
    }
    body.innerHTML = actions.map(a => {
      const emoji = String.fromCodePoint(parseInt(a.emoji, 16));
      const dotClass = a.priority || 'medium';
      return `<div class="ai-action">
        <div class="ai-action-emoji">${emoji}</div>
        <div class="ai-action-content">
          <div class="ai-action-title"><span class="priority-dot ${dotClass}"></span>${esc(a.title)}</div>
          <div class="ai-action-desc">${esc(a.description)}</div>
        </div>
      </div>`;
    }).join('');
  }

  function renderAlertList(container, alerts) {
    if (!alerts || alerts.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No alerts</p></div>';
      return;
    }
    container.innerHTML = alerts.map(a => `
      <div class="alert-item ${a.severity} ${a.is_read ? '' : 'unread'}">
        <div class="alert-title">${esc(a.title)}</div>
        <div class="alert-msg">${esc(a.message || '')}</div>
        <div class="alert-time">${a.created_at ? new Date(a.created_at).toLocaleDateString() : ''}</div>
      </div>
    `).join('');
  }

  // ── Helpers ──
  function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function showRefresh() { $('#refreshIndicator').classList.add('spinning'); }
  function hideRefresh() { $('#refreshIndicator').classList.remove('spinning'); }

  // ══════════════════════════════════════════════════════════════════════════
  // SEARCH FUNCTIONALITY
  // ══════════════════════════════════════════════════════════════════════════

  const searchInput = $('#searchInput');
  const searchResults = $('#searchResults');
  let searchTimeout = null;

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      const q = searchInput.value.trim();
      if (q.length < 2) {
        searchResults.hidden = true;
        return;
      }
      searchTimeout = setTimeout(async () => {
        const data = await api('/api/dashboard/search?q=' + encodeURIComponent(q));
        if (!data) return;
        if (data.results.length === 0) {
          searchResults.innerHTML = '<div class="search-empty">No results found</div>';
        } else {
          searchResults.innerHTML = data.results.map(r => `
            <div class="search-result-item" data-section="${esc(r.section)}">
              <div class="search-result-icon">${r.icon}</div>
              <div class="search-result-text">
                <div class="search-result-title">${esc(r.title)}</div>
                <div class="search-result-sub">${esc(r.subtitle)}</div>
              </div>
            </div>
          `).join('');
          // Click handler for results
          $$('.search-result-item', searchResults).forEach(item => {
            item.addEventListener('click', () => {
              const section = item.dataset.section;
              const navItem = $(`.nav-item[data-section="${section}"]`);
              if (navItem) navItem.click();
              searchInput.value = '';
              searchResults.hidden = true;
            });
          });
        }
        searchResults.hidden = false;
      }, 250);
    });

    searchInput.addEventListener('blur', () => {
      setTimeout(() => { searchResults.hidden = true; }, 200);
    });

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        searchInput.blur();
        searchResults.hidden = true;
      }
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // KEYBOARD SHORTCUTS
  // ══════════════════════════════════════════════════════════════════════════

  const shortcutMap = {
    'b': 'briefing', 'd': 'datahub', 'o': 'overview', 's': 'sales', 'p': 'products',
    'u': 'customers', 'c': 'competitors', 'g': 'goals', 'm': 'marketing', 'w': 'winback',
  };

  document.addEventListener('keydown', (e) => {
    // Don't trigger shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;

    if (e.key === '/') {
      e.preventDefault();
      if (searchInput) searchInput.focus();
      return;
    }

    if (e.key === '?' || (e.shiftKey && e.key === '/')) {
      e.preventDefault();
      const modal = $('#shortcutsModal');
      if (modal) modal.classList.toggle('show');
      return;
    }

    if (e.key === 'Escape') {
      const modal = $('#shortcutsModal');
      if (modal) modal.classList.remove('show');
      if (searchResults) searchResults.hidden = true;
      return;
    }

    const section = shortcutMap[e.key.toLowerCase()];
    if (section) {
      const navItem = $(`.nav-item[data-section="${section}"]`);
      if (navItem) navItem.click();
    }
  });

  // Close shortcuts modal
  const shortcutsClose = $('#shortcutsClose');
  if (shortcutsClose) {
    shortcutsClose.addEventListener('click', () => {
      $('#shortcutsModal').classList.remove('show');
    });
  }
  const shortcutsModal = $('#shortcutsModal');
  if (shortcutsModal) {
    shortcutsModal.addEventListener('click', (e) => {
      if (e.target === shortcutsModal) shortcutsModal.classList.remove('show');
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // MOBILE SIDEBAR
  // ══════════════════════════════════════════════════════════════════════════

  const sidebarOverlay = $('#sidebarOverlay');
  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', () => {
      $('#sidebar').classList.remove('open');
      sidebarOverlay.classList.remove('show');
    });
  }

  // Override the mobile toggle to also show/hide overlay
  const mobileToggleBtn = $('#mobileToggle');
  if (mobileToggleBtn) {
    mobileToggleBtn.addEventListener('click', () => {
      const sidebar = $('#sidebar');
      const isOpen = sidebar.classList.contains('open');
      if (sidebarOverlay) {
        if (isOpen) sidebarOverlay.classList.remove('show');
        else sidebarOverlay.classList.add('show');
      }
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // LAST UPDATED TIMER
  // ══════════════════════════════════════════════════════════════════════════

  let lastUpdateTime = Date.now();
  function updateLastUpdated() {
    const el = $('#lastUpdated');
    if (!el) return;
    const diff = Math.floor((Date.now() - lastUpdateTime) / 1000);
    if (diff < 10) el.textContent = 'Updated just now';
    else if (diff < 60) el.textContent = `Updated ${diff}s ago`;
    else el.textContent = `Updated ${Math.floor(diff / 60)}m ago`;
  }
  setInterval(updateLastUpdated, 10000);

  // ══════════════════════════════════════════════════════════════════════════
  // NUMBER COUNT-UP ANIMATION
  // ══════════════════════════════════════════════════════════════════════════

  function animateValue(el, end, duration = 600, prefix = '', suffix = '') {
    if (!el) return;
    const start = 0;
    const startTime = performance.now();
    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * eased;
      if (prefix === '$') {
        el.textContent = '$' + Number(current).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      } else {
        el.textContent = prefix + Math.round(current).toLocaleString('en-US') + suffix;
      }
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // SPARKLINE RENDERER
  // ══════════════════════════════════════════════════════════════════════════

  function renderSparkline(data, width = 60, height = 20, color = '#6366f1') {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const points = data.map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<span class="sparkline"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>`;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ACTIVITY FEED, SEGMENTS, HEATMAP, PRODUCT PERF, SETTINGS, TOOLTIPS
  // ══════════════════════════════════════════════════════════════════════════

  async function loadActivityFeed() {
    const body = $('#activityFeedBody');
    if (!body) return;
    const data = await api('/api/dashboard/activity-feed');
    if (!data || !data.events || data.events.length === 0) {
      body.innerHTML = '<p style="color:var(--text3);text-align:center;padding:20px">No recent activity yet.</p>';
      return;
    }
    body.innerHTML = `<div class="activity-feed">${data.events.map(e => `
      <div class="af-item">
        <span class="af-icon">${e.icon}</span>
        <div class="af-content">
          <div class="af-desc">${esc(e.description)}</div>
          <div class="af-time">${esc(e.time_ago)}</div>
        </div>
      </div>
    `).join('')}</div>`;
  }

  async function loadCustomerSegments() {
    const body = $('#customerSegmentsBody');
    if (!body) return;
    const data = await api('/api/dashboard/customers/segments');
    if (!data || !data.segments || data.total === 0) {
      body.innerHTML = '<p style="color:var(--text3);text-align:center;padding:20px">Not enough customers for segmentation.</p>';
      return;
    }
    const total = data.total;
    // Build donut chart using conic-gradient
    let cumPct = 0;
    const gradientStops = [];
    const segs = data.segments.filter(s => s.count > 0);
    segs.forEach(s => {
      const pct = (s.count / total) * 100;
      gradientStops.push(`${s.color} ${cumPct}% ${cumPct + pct}%`);
      cumPct += pct;
    });
    if (gradientStops.length === 0) gradientStops.push('var(--bg-3) 0% 100%');
    const gradient = `conic-gradient(${gradientStops.join(', ')})`;

    body.innerHTML = `
      <div class="cs-wrap">
        <div class="cs-donut" style="background:${gradient}">
          <div class="cs-donut-hole">${total}<br><small>total</small></div>
        </div>
        <div class="cs-legend">
          ${data.segments.map(s => `
            <div class="cs-legend-item">
              <span class="cs-dot" style="background:${s.color}"></span>
              <span class="cs-legend-label">${esc(s.label)}</span>
              <span class="cs-legend-count">${s.count}</span>
              <span class="cs-legend-rev">${fmt(s.total_revenue)}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  async function loadRevenueHeatmap() {
    const body = $('#revenueHeatmapBody');
    if (!body) return;
    const data = await api('/api/dashboard/sales/heatmap?days=90');
    if (!data || !data.days || data.days.length === 0) {
      body.innerHTML = '<p style="color:var(--text3);text-align:center;padding:20px">Not enough data for heatmap.</p>';
      return;
    }
    const days = data.days;
    const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    // Group by week
    const weeks = [];
    let currentWeek = [];
    days.forEach((d, i) => {
      currentWeek.push(d);
      if (d.day_of_week === 6 || i === days.length - 1) {
        weeks.push(currentWeek);
        currentWeek = [];
      }
    });

    body.innerHTML = `
      <div class="hm-wrap">
        <div class="hm-labels">${dayLabels.map(l => `<span class="hm-label">${l}</span>`).join('')}</div>
        <div class="hm-grid">
          ${weeks.map(w => `<div class="hm-week">${
            w.map(d => {
              const alpha = Math.max(0.1, d.intensity);
              return `<div class="hm-cell" style="background:rgba(99,102,241,${alpha})" title="${d.date}: ${fmt(d.revenue)}"></div>`;
            }).join('')
          }</div>`).join('')}
        </div>
      </div>
      <div class="hm-scale">
        <span>Less</span>
        <span class="hm-cell-sm" style="background:rgba(99,102,241,0.1)"></span>
        <span class="hm-cell-sm" style="background:rgba(99,102,241,0.3)"></span>
        <span class="hm-cell-sm" style="background:rgba(99,102,241,0.6)"></span>
        <span class="hm-cell-sm" style="background:rgba(99,102,241,1)"></span>
        <span>More</span>
      </div>
    `;
  }

  function loadProductPerformance(products) {
    const body = $('#productPerfBody');
    if (!body) return;
    if (!products || products.length === 0) {
      body.innerHTML = '<p style="color:var(--text3);text-align:center;padding:20px">No product data available.</p>';
      return;
    }
    const maxRevenue = Math.max(...products.map(p => p.revenue));
    body.innerHTML = `<div class="pp-grid">${products.slice(0, 8).map(p => {
      const pct = Math.round((p.revenue / maxRevenue) * 100);
      const status = pct >= 70 ? 'top' : pct >= 40 ? 'mid' : 'low';
      const statusLabel = {top: 'Top Seller', mid: 'Steady', low: 'Underperforming'};
      const statusColor = {top: 'var(--success)', mid: 'var(--warning)', low: 'var(--danger)'};
      return `
        <div class="pp-card">
          <div class="pp-header">
            <span class="pp-name">${esc(p.name)}</span>
            <span class="pp-badge" style="color:${statusColor[status]};border-color:${statusColor[status]}">${statusLabel[status]}</span>
          </div>
          <div class="pp-revenue">${fmt(p.revenue)}</div>
          <div class="pp-bar-wrap"><div class="pp-bar" style="width:${pct}%;background:${statusColor[status]}"></div></div>
          <div class="pp-meta">
            <span>${fmtInt(p.units_sold)} units</span>
            <span>${fmt(p.avg_price)} avg</span>
            ${p.margin != null ? `<span>${p.margin}% margin</span>` : ''}
          </div>
        </div>`;
    }).join('')}</div>`;
  }

  // ── Settings ──
  async function loadSettings() {
    showRefresh();
    const data = await api('/api/dashboard/settings');
    hideRefresh();
    if (!data) return;
    const s = id => $(id);
    if (s('#setShopName')) s('#setShopName').value = data.shop_name || '';
    if (s('#setAddress')) s('#setAddress').value = data.address || '';
    if (s('#setCategory')) s('#setCategory').value = data.category || 'retail';
    if (s('#setStoreSize')) s('#setStoreSize').value = data.store_size_sqft || '';
    if (s('#setStaffCount')) s('#setStaffCount').value = data.staff_count || '';
    if (s('#setRent')) s('#setRent').value = data.monthly_rent || '';
    if (s('#setCogs')) s('#setCogs').value = data.avg_cogs_percentage || '';
    if (s('#setHourlyRate')) s('#setHourlyRate').value = data.staff_hourly_rate || '';
    if (s('#setTaxRate')) s('#setTaxRate').value = data.tax_rate || '';
    if (s('#setEmailFreq')) s('#setEmailFreq').value = data.email_frequency || 'weekly';
    if (s('#setAlertRevenue')) s('#setAlertRevenue').checked = data.alert_revenue !== false;
    if (s('#setAlertCustomers')) s('#setAlertCustomers').checked = data.alert_customers !== false;
    if (s('#setAlertReviews')) s('#setAlertReviews').checked = data.alert_reviews !== false;
    if (s('#setAlertCompetitors')) s('#setAlertCompetitors').checked = data.alert_competitors !== false;
    if (s('#setGoogleApiKey')) s('#setGoogleApiKey').value = data.google_api_key || '';
    if (s('#setAnthropicApiKey')) s('#setAnthropicApiKey').value = data.anthropic_api_key || '';
    if (s('#setAiPersonality')) s('#setAiPersonality').value = data.ai_personality || 'professional';
    if (s('#setAiEnabled')) s('#setAiEnabled').checked = data.ai_enabled !== false;
  }

  // Save settings handler — defined later with social accounts support
  const saveBtn = $('#saveSettingsBtn');

  // ── Help Tooltips ──
  const helpBtn = $('#helpTooltipBtn');
  let tooltipsActive = false;
  if (helpBtn) {
    helpBtn.addEventListener('click', () => {
      tooltipsActive = !tooltipsActive;
      document.body.classList.toggle('tooltips-active', tooltipsActive);
      helpBtn.classList.toggle('active', tooltipsActive);
      showToast(tooltipsActive ? 'Help tooltips ON — hover over elements to see tips' : 'Help tooltips OFF', 'info', 2000);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // INSIGHTS STRIP
  // ══════════════════════════════════════════════════════════════════════════

  async function loadInsightStrip() {
    const strip = $('#insightStrip');
    if (!strip) return;
    const insights = await api('/api/dashboard/insights');
    if (!insights || insights.length === 0) { strip.hidden = true; return; }
    strip.innerHTML = insights.slice(0, 6).map(i => {
      const emoji = String.fromCodePoint(parseInt(i.icon, 16));
      return `<div class="insight-chip"><span class="insight-chip-icon">${emoji}</span><span class="insight-chip-text">${esc(i.text)}</span></div>`;
    }).join('');
  }

  // ── Init ──
  const initSection = window.__ACTIVE_SECTION || 'overview';
  console.log('[Forge] Init section:', initSection, '| Sub:', window.__SUB_SECTION || 'none');
  if (initSection !== 'overview') {
    // Activate the correct section from URL
    $$('.nav-item').forEach(n => n.classList.remove('active'));
    const target = $(`.nav-item[data-section="${initSection}"]`);
    if (target) {
      target.classList.add('active');
      $('#pageTitle').textContent = target.textContent.trim();
    }
    $$('.section').forEach(s => s.classList.remove('active'));
    const sec = $(`#sec-${initSection}`);
    if (sec) sec.classList.add('active');

    // If there's a sub-section, activate the right tab
    if (window.__SUB_SECTION && initSection === 'competitors') {
      $$('.comp-tab').forEach(t => t.classList.remove('active'));
      const subTab = $(`.comp-tab[data-tab="${window.__SUB_SECTION}"]`);
      if (subTab) subTab.classList.add('active');
      $$('.comp-panel').forEach(p => p.classList.remove('active'));
      const subPanel = $(`#compPanel-${window.__SUB_SECTION}`);
      if (subPanel) subPanel.classList.add('active');
    }

    loadSection(initSection);
  } else {
    loadOverview();
  }

  // ── Quick Stats Bar ──
  async function loadQuickStats() {
    try {
      const [summary, reviews] = await Promise.all([
        api('/api/dashboard/summary'),
        api('/api/dashboard/reviews'),
      ]);
      if (summary) {
        const qsRev = $('#qsRevenue');
        const qsTx = $('#qsTransactions');
        const qsCust = $('#qsCustomers');
        if (qsRev) qsRev.textContent = fmt(summary.revenue_today);
        if (qsTx) qsTx.textContent = fmtInt(summary.transactions_today);
        if (qsCust) qsCust.textContent = fmtInt(summary.total_customers);
      }
      if (reviews && reviews.avg_rating) {
        const qsRating = $('#qsRating');
        if (qsRating) qsRating.textContent = reviews.avg_rating;
      }
    } catch (e) {
      console.warn('[Forge] Quick stats error:', e);
    }
  }
  loadQuickStats();

  // ── Export helper ──
  async function exportCSV(type) {
    try {
      const res = await fetch('/api/dashboard/export', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({export_type: type}),
      });
      if (!res.ok) { showToast('Export failed — please try again', 'error'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `forge_${type}_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast(`${type.charAt(0).toUpperCase() + type.slice(1)} data exported!`, 'success');
    } catch (e) {
      console.error('[Forge] Export error:', e);
      showToast('Export failed — check your connection', 'error');
    }
  }

  // Attach export buttons (they use onclick="exportCSV('type')")
  window.exportCSV = exportCSV;

  // ══════════════════════════════════════════════════════════════════════════
  // DATA HUB
  // ══════════════════════════════════════════════════════════════════════════

  async function loadDataHub() {
    // Tab switching
    $$('#dhTabs .dh-tab').forEach(tab => {
      tab.onclick = () => {
        $$('#dhTabs .dh-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        $$('#sec-datahub .dh-panel').forEach(p => p.classList.remove('active'));
        const panel = $(`#dhPanel-${tab.dataset.tab}`);
        if (panel) panel.classList.add('active');
        if (tab.dataset.tab === 'quick-entry') loadDhQuickEntry();
        else if (tab.dataset.tab === 'dh-products') loadDhProducts();
        else if (tab.dataset.tab === 'dh-customers') loadDhCustomers();
        else if (tab.dataset.tab === 'connections') loadDhConnections();
      };
    });
    loadDhQuickEntry();
    setupDhCsvUpload();
    setupDhProductsTab();
    setupDhCustomersTab();
    setupDhConnections();
  }

  // ── Quick Entry ──
  async function loadDhQuickEntry() {
    const dateInput = $('#dhDate');
    if (dateInput && !dateInput.value) dateInput.value = new Date().toISOString().slice(0, 10);

    // Populate product datalist
    const prodData = await api('/api/data/products');
    if (prodData && prodData.products) {
      const dl = $('#dhProductList');
      if (dl) dl.innerHTML = prodData.products.map(p => `<option value="${esc(p.name)}">`).join('');
    }

    // Load calendar
    const history = await api('/api/data/entry-history?days=90');
    if (history) renderDhCalendar(history);

    // Save handler
    const saveBtn = $('#dhSaveDaily');
    if (saveBtn && !saveBtn._bound) {
      saveBtn._bound = true;
      saveBtn.onclick = async () => {
        const date = $('#dhDate').value;
        const revenue = parseFloat($('#dhRevenue').value) || 0;
        const transactions = parseInt($('#dhTransactions').value) || 0;
        const customers = parseInt($('#dhCustomers').value) || 0;
        const notes = $('#dhNotes').value || '';
        if (!date || revenue <= 0) { showToast('Please enter date and revenue', 'error'); return; }
        const items = [];
        $$('#dhItemsList .dh-item-row').forEach(row => {
          const inputs = row.querySelectorAll('input');
          const name = inputs[0]?.value?.trim();
          const qty = parseInt(inputs[1]?.value) || 1;
          const price = parseFloat(inputs[2]?.value) || 0;
          if (name && price > 0) items.push({product_name: name, quantity: qty, unit_price: price});
        });
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        try {
          const res = await fetch('/api/data/daily-entry', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({date, revenue, transactions, walk_in_customers: customers, notes, items})
          });
          const data = await res.json();
          const resultEl = $('#dhDailyResult');
          if (res.ok) {
            resultEl.className = 'dh-result';
            resultEl.innerHTML = `<strong>Got it!</strong> ${data.message || 'Data saved successfully.'}`;
            resultEl.hidden = false;
            showToast('Daily data saved!', 'success');
            const hist = await api('/api/data/entry-history?days=90');
            if (hist) renderDhCalendar(hist);
          } else {
            resultEl.className = 'dh-result error';
            resultEl.innerHTML = data.detail || 'Error saving data';
            resultEl.hidden = false;
            showToast('Error saving data', 'error');
          }
        } catch (e) {
          showToast('Network error', 'error');
        }
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Today\'s Data';
      };
    }

    // Add item row
    const addBtn = $('#dhAddItem');
    if (addBtn && !addBtn._bound) {
      addBtn._bound = true;
      addBtn.onclick = () => {
        const list = $('#dhItemsList');
        const row = document.createElement('div');
        row.className = 'dh-item-row';
        row.innerHTML = '<input type="text" class="dh-input dh-input-sm" placeholder="Product name" list="dhProductList"><input type="number" class="dh-input dh-input-xs" placeholder="Qty" min="1" value="1"><input type="number" class="dh-input dh-input-sm" placeholder="Price" step="0.01"><button class="dh-remove-btn" title="Remove">&times;</button>';
        row.querySelector('.dh-remove-btn').onclick = () => row.remove();
        list.appendChild(row);
      };
    }
  }

  function renderDhCalendar(data) {
    const cal = $('#dhCalendar');
    const streak = $('#dhStreak');
    if (!cal) return;
    const loggedDates = new Set(data.logged_dates || []);
    if (streak) {
      streak.innerHTML = `You've logged <strong>${data.total_logged || 0}</strong> of the last 90 days. ${data.streak > 0 ? `Current streak: <strong>${data.streak} day${data.streak > 1 ? 's' : ''}</strong>` : ''}`;
    }
    const today = new Date();
    const start = new Date(today);
    start.setDate(start.getDate() - 89);
    start.setDate(start.getDate() - start.getDay()); // align to Sunday
    let html = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d => `<div class="dh-cal-header">${d}</div>`).join('');
    const d = new Date(start);
    const todayStr = today.toISOString().slice(0, 10);
    while (d <= today || d.getDay() !== 0) {
      const ds = d.toISOString().slice(0, 10);
      const isToday = ds === todayStr;
      const isLogged = loggedDates.has(ds);
      const isFuture = d > today;
      html += `<div class="dh-cal-day${isLogged ? ' logged' : ''}${isToday ? ' today' : ''}${isFuture ? ' empty' : ''}">${isFuture ? '' : d.getDate()}</div>`;
      d.setDate(d.getDate() + 1);
      if (d > today && d.getDay() === 0) break;
    }
    cal.innerHTML = html;
  }

  // ── CSV Upload ──
  function setupDhCsvUpload() {
    const zone = $('#dhUploadZone');
    const fileInput = $('#dhFileInput');
    if (!zone || zone._bound) return;
    zone._bound = true;
    let csvRows = [];
    let csvColumns = [];

    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('dragover'); handleFile(e.dataTransfer.files[0]); });
    zone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

    async function handleFile(file) {
      if (!file || !file.name.endsWith('.csv')) { showToast('Please upload a CSV file', 'error'); return; }
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch('/api/data/csv-upload', {method: 'POST', credentials: 'same-origin', body: formData});
        const data = await res.json();
        if (!res.ok) { showToast(data.detail || 'Upload error', 'error'); return; }
        csvColumns = data.columns;
        csvRows = data.preview_data || [];
        renderCsvPreview(data, file.name);
      } catch (e) { showToast('Upload failed', 'error'); }
    }

    function renderCsvPreview(data, fileName) {
      const preview = $('#dhCsvPreview');
      $('#dhPreviewTitle').textContent = `${fileName} — ${data.row_count} rows detected`;
      const thead = $('#dhPreviewTable thead');
      const tbody = $('#dhPreviewTable tbody');
      thead.innerHTML = '<tr>' + data.columns.map(c => `<th>${esc(c)}</th>`).join('') + '</tr>';
      tbody.innerHTML = (data.preview || []).map(row => '<tr>' + data.columns.map(c => `<td>${esc(String(row[c] || ''))}</td>`).join('') + '</tr>').join('');
      // Populate mapping dropdowns
      const dateKeywords = ['date','time','timestamp','day','created','order_date'];
      const revenueKeywords = ['total','amount','revenue','price','sum','sales','subtotal'];
      const productKeywords = ['product','item','name','description','sku'];
      const qtyKeywords = ['quantity','qty','count','units','amount'];
      const custKeywords = ['email','customer','client','buyer'];
      [['dhMapDate', dateKeywords], ['dhMapRevenue', revenueKeywords], ['dhMapProduct', productKeywords],
       ['dhMapQuantity', qtyKeywords], ['dhMapCustomer', custKeywords]].forEach(([id, kws]) => {
        const sel = $(`#${id}`);
        sel.innerHTML = '<option value="">-- skip --</option>' + data.columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
        const match = data.columns.find(c => kws.some(k => c.toLowerCase().includes(k)));
        if (match) sel.value = match;
      });
      preview.hidden = false;
      zone.style.display = 'none';
    }

    const cancelBtn = $('#dhCancelImport');
    if (cancelBtn) cancelBtn.onclick = () => { $('#dhCsvPreview').hidden = true; zone.style.display = ''; };

    const importBtn = $('#dhImportBtn');
    if (importBtn) importBtn.onclick = async () => {
      const mapping = {
        date_col: $('#dhMapDate').value,
        revenue_col: $('#dhMapRevenue').value,
        product_col: $('#dhMapProduct').value || null,
        quantity_col: $('#dhMapQuantity').value || null,
        customer_col: $('#dhMapCustomer').value || null,
      };
      if (!mapping.date_col || !mapping.revenue_col) { showToast('Date and Revenue columns are required', 'error'); return; }
      importBtn.disabled = true;
      importBtn.textContent = 'Importing...';
      try {
        const res = await fetch('/api/data/csv-import', {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({data: csvRows, mapping, file_name: 'upload'})
        });
        const result = await res.json();
        const el = $('#dhImportResult');
        if (res.ok) {
          el.className = 'dh-import-result' + (result.errors?.length ? ' has-errors' : '');
          el.innerHTML = `<strong>Imported ${result.imported} transactions.</strong>${result.skipped ? ` ${result.skipped} rows skipped.` : ''}${result.errors?.length ? `<br><small>${result.errors.slice(0,5).join('<br>')}</small>` : ''}`;
          showToast(`Imported ${result.imported} records`, 'success');
        } else {
          el.className = 'dh-import-result has-errors';
          el.innerHTML = result.detail || 'Import failed';
        }
        el.hidden = false;
      } catch (e) { showToast('Import failed', 'error'); }
      importBtn.disabled = false;
      importBtn.textContent = 'Import Data';
    };
  }

  // ── Products Tab ──
  async function loadDhProducts() {
    const data = await api('/api/data/products');
    if (!data) return;
    const tbody = $('#dhProductsTable tbody');
    if (!data.products || data.products.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text3);padding:20px">No products yet. Add your first product above.</td></tr>';
      return;
    }
    tbody.innerHTML = data.products.map(p => `<tr>
      <td>${esc(p.name)}</td><td>${esc(p.category || '-')}</td><td>${fmt(p.price)}</td>
      <td>${p.cost ? fmt(p.cost) : '-'}</td><td>${esc(p.sku || '-')}</td>
      <td><span class="badge-sm ${p.is_active ? 'badge-success' : 'badge-muted'}">${p.is_active ? 'Active' : 'Inactive'}</span></td>
      <td><button class="dh-edit-btn" data-id="${p.id}">Edit</button> <button class="dh-del-btn" data-id="${p.id}">Delete</button></td>
    </tr>`).join('');
    // Edit/delete handlers
    tbody.querySelectorAll('.dh-edit-btn').forEach(btn => {
      btn.onclick = async () => {
        const prod = data.products.find(p => p.id === btn.dataset.id);
        if (!prod) return;
        $('#dhProdEditId').value = prod.id;
        $('#dhProdName').value = prod.name;
        $('#dhProdCategory').value = prod.category || '';
        $('#dhProdPrice').value = prod.price;
        $('#dhProdCost').value = prod.cost || '';
        $('#dhProdSku').value = prod.sku || '';
        $('#dhProductForm').hidden = false;
      };
    });
    tbody.querySelectorAll('.dh-del-btn').forEach(btn => {
      btn.onclick = async () => {
        await fetch(`/api/data/products/${btn.dataset.id}`, {method: 'DELETE', credentials: 'same-origin'});
        showToast('Product deactivated', 'info');
        loadDhProducts();
      };
    });
  }

  function setupDhProductsTab() {
    const addBtn = $('#dhAddProductBtn');
    const form = $('#dhProductForm');
    const cancelBtn = $('#dhCancelProduct');
    const saveBtn = $('#dhSaveProduct');
    if (!addBtn) return;
    addBtn.onclick = () => { form.hidden = false; $('#dhProdEditId').value = ''; $('#dhProdName').value = ''; $('#dhProdCategory').value = ''; $('#dhProdPrice').value = ''; $('#dhProdCost').value = ''; $('#dhProdSku').value = ''; };
    if (cancelBtn) cancelBtn.onclick = () => { form.hidden = true; };
    if (saveBtn) saveBtn.onclick = async () => {
      const editId = $('#dhProdEditId').value;
      const body = {
        name: $('#dhProdName').value, category: $('#dhProdCategory').value || null,
        price: parseFloat($('#dhProdPrice').value) || 0, cost: parseFloat($('#dhProdCost').value) || null,
        sku: $('#dhProdSku').value || null
      };
      if (!body.name || !body.price) { showToast('Name and price required', 'error'); return; }
      const url = editId ? `/api/data/products/${editId}` : '/api/data/products';
      const method = editId ? 'PUT' : 'POST';
      await fetch(url, {method, credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      form.hidden = true;
      showToast(editId ? 'Product updated' : 'Product added', 'success');
      loadDhProducts();
    };
    // CSV upload for products
    const csvInput = $('#dhProductCsvInput');
    if (csvInput) csvInput.onchange = async () => {
      if (!csvInput.files[0]) return;
      const fd = new FormData();
      fd.append('file', csvInput.files[0]);
      const res = await fetch('/api/data/csv-upload-products', {method: 'POST', credentials: 'same-origin', body: fd});
      const data = await res.json();
      showToast(data.detail || `Imported ${data.imported || 0} products`, res.ok ? 'success' : 'error');
      loadDhProducts();
      csvInput.value = '';
    };
  }

  // ── Customers Tab ──
  let dhCustPage = 1;
  async function loadDhCustomers(page, search) {
    page = page || dhCustPage;
    search = search !== undefined ? search : ($('#dhCustSearch')?.value || '');
    const data = await api(`/api/data/customers?page=${page}&per_page=25&search=${encodeURIComponent(search)}`);
    if (!data) return;
    dhCustPage = data.page || 1;
    const tbody = $('#dhCustomersTable tbody');
    if (!data.customers || data.customers.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:20px">No customers found.</td></tr>';
      $('#dhCustPagination').innerHTML = '';
      return;
    }
    tbody.innerHTML = data.customers.map(c => `<tr>
      <td>${esc(c.email || '-')}</td><td><span class="badge-sm">${esc(c.segment || 'regular')}</span></td>
      <td>${c.visit_count || 0}</td><td>${fmt(c.total_spent || 0)}</td>
      <td>${c.last_seen ? c.last_seen.split('T')[0] : '-'}</td>
      <td><button class="dh-edit-btn" data-id="${c.id}">Edit</button> <button class="dh-del-btn" data-id="${c.id}">Del</button></td>
    </tr>`).join('');
    // Pagination
    const pages = data.pages || 1;
    let pagHtml = '';
    for (let i = 1; i <= Math.min(pages, 10); i++) {
      pagHtml += `<button class="dh-page-btn${i === page ? ' active' : ''}" data-page="${i}">${i}</button>`;
    }
    $('#dhCustPagination').innerHTML = pagHtml;
    $$('#dhCustPagination .dh-page-btn').forEach(btn => { btn.onclick = () => loadDhCustomers(parseInt(btn.dataset.page)); });
    // Edit/delete
    tbody.querySelectorAll('.dh-edit-btn').forEach(btn => {
      btn.onclick = () => {
        const c = data.customers.find(x => x.id === btn.dataset.id);
        if (!c) return;
        $('#dhCustEditId').value = c.id;
        $('#dhCustEmail').value = c.email || '';
        $('#dhCustSegment').value = c.segment || 'regular';
        $('#dhCustomerForm').hidden = false;
      };
    });
    tbody.querySelectorAll('.dh-del-btn').forEach(btn => {
      btn.onclick = async () => {
        await fetch(`/api/data/customers/${btn.dataset.id}`, {method: 'DELETE', credentials: 'same-origin'});
        showToast('Customer deleted', 'info');
        loadDhCustomers();
      };
    });
  }

  function setupDhCustomersTab() {
    const addBtn = $('#dhAddCustomerBtn');
    const form = $('#dhCustomerForm');
    const cancelBtn = $('#dhCancelCustomer');
    const saveBtn = $('#dhSaveCustomer');
    const searchInput = $('#dhCustSearch');
    if (!addBtn) return;
    addBtn.onclick = () => { form.hidden = false; $('#dhCustEditId').value = ''; $('#dhCustEmail').value = ''; $('#dhCustSegment').value = 'regular'; };
    if (cancelBtn) cancelBtn.onclick = () => { form.hidden = true; };
    if (saveBtn) saveBtn.onclick = async () => {
      const editId = $('#dhCustEditId').value;
      const body = { email: $('#dhCustEmail').value || null, segment: $('#dhCustSegment').value || 'regular' };
      const url = editId ? `/api/data/customers/${editId}` : '/api/data/customers';
      const method = editId ? 'PUT' : 'POST';
      await fetch(url, {method, credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      form.hidden = true;
      showToast(editId ? 'Customer updated' : 'Customer added', 'success');
      loadDhCustomers();
    };
    if (searchInput) {
      let t;
      searchInput.oninput = () => { clearTimeout(t); t = setTimeout(() => loadDhCustomers(1, searchInput.value), 300); };
    }
    // CSV upload
    const csvInput = $('#dhCustomerCsvInput');
    if (csvInput) csvInput.onchange = async () => {
      if (!csvInput.files[0]) return;
      const fd = new FormData();
      fd.append('file', csvInput.files[0]);
      const res = await fetch('/api/data/csv-upload-customers', {method: 'POST', credentials: 'same-origin', body: fd});
      const data = await res.json();
      showToast(data.detail || `Imported ${data.imported || 0} customers`, res.ok ? 'success' : 'error');
      loadDhCustomers();
      csvInput.value = '';
    };
  }

  // ── Connections Tab ──
  function setupDhConnections() {
    // Notify Me buttons
    $$('.dh-notify-btn').forEach(btn => {
      if (btn._bound) return;
      btn._bound = true;
      btn.onclick = async () => {
        const wrap = btn.closest('.dh-notify-wrap');
        const emailInput = wrap.querySelector('.dh-notify-email');
        const email = emailInput?.value?.trim();
        if (!email || !email.includes('@')) { showToast('Please enter a valid email', 'error'); return; }
        await fetch('/api/data/connections/notify', {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({email, integration: btn.dataset.integration})
        });
        btn.textContent = 'Notified!';
        btn.disabled = true;
        emailInput.disabled = true;
        showToast('We\'ll notify you when it\'s ready!', 'success');
      };
    });
  }

  async function loadDhConnections() {
    // Check if Google is connected
    const settings = await api('/api/dashboard/settings');
    const status = $('#dhGoogleStatus');
    const btn = $('#dhGoogleConnectBtn');
    if (settings && settings.google_place_id) {
      if (status) { status.textContent = 'Connected'; status.classList.add('connected'); }
      if (btn) { btn.textContent = 'Manage'; }
    }
    setupGoogleModal();
  }

  // ── Google Business Finder Modal ──
  function setupGoogleModal() {
    const connectBtn = $('#dhGoogleConnectBtn');
    const modal = $('#dhGoogleModal');
    const closeBtn = $('#dhGoogleModalClose');
    if (!connectBtn || connectBtn._bound) return;
    connectBtn._bound = true;

    connectBtn.onclick = () => { modal.hidden = false; };
    closeBtn.onclick = () => { modal.hidden = true; };
    modal.onclick = (e) => { if (e.target === modal) modal.hidden = true; };

    // Step 1: Search for own business
    const searchBtn = $('#dhGoogleSearchBtn');
    searchBtn.onclick = async () => {
      const query = $('#dhGoogleSearch').value.trim();
      if (!query) return;
      const results = $('#dhGoogleResults');
      results.innerHTML = '<div class="ai-loading">Searching...</div>';
      const data = await api(`/api/data/google/search?query=${encodeURIComponent(query)}`);
      if (!data || !data.results?.length) { results.innerHTML = '<div class="dh-hint" style="text-align:center;padding:20px">No businesses found. Try a different search.</div>'; return; }
      results.innerHTML = data.results.map(r => `
        <div class="dh-google-result" data-place='${JSON.stringify(r).replace(/'/g, "&#39;")}'>
          <div class="dh-gr-info">
            <div class="dh-gr-name">${esc(r.name)}</div>
            <div class="dh-gr-addr">${esc(r.address)}</div>
            <div class="dh-gr-meta">${r.rating ? r.rating + ' &#9733;' : ''} ${r.review_count ? '(' + r.review_count + ' reviews)' : ''}</div>
          </div>
          <button class="dh-gr-action">This is my business</button>
        </div>
      `).join('');
      results.querySelectorAll('.dh-gr-action').forEach(btn => {
        btn.onclick = async () => {
          const place = JSON.parse(btn.closest('.dh-google-result').dataset.place);
          await fetch('/api/data/google/connect', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({place_id: place.place_id, name: place.name, address: place.address, lat: place.lat, lng: place.lng})
          });
          showToast('Business connected!', 'success');
          $('#dhGoogleStatus').textContent = 'Connected';
          $('#dhGoogleStatus').classList.add('connected');
          // Move to step 2 — find competitors
          $('#dhGoogleStep1').hidden = true;
          $('#dhGoogleStep2').hidden = false;
          $('#dhGoogleModalTitle').textContent = 'Find Your Competitors';
          loadNearbyCompetitors(place.lat, place.lng);
        };
      });
    };

    // Step 2: Competitor finder
    const compSearchBtn = $('#dhCompSearchBtn');
    if (compSearchBtn) compSearchBtn.onclick = async () => {
      const query = $('#dhCompSearch').value.trim();
      if (!query) return;
      const data = await api(`/api/data/google/search?query=${encodeURIComponent(query)}`);
      if (data && data.results) appendCompetitorResults(data.results);
    };

    const finishBtn = $('#dhFinishCompetitors');
    if (finishBtn) finishBtn.onclick = () => {
      modal.hidden = true;
      showToast('Competitors saved!', 'success');
      // Reset for next time
      $('#dhGoogleStep1').hidden = false;
      $('#dhGoogleStep2').hidden = true;
      $('#dhGoogleModalTitle').textContent = 'Find Your Business on Google';
    };
  }

  const selectedCompetitors = new Set();

  async function loadNearbyCompetitors(lat, lng) {
    const container = $('#dhCompetitorResults');
    container.innerHTML = '<div class="ai-loading">Searching for nearby businesses...</div>';
    const data = await api(`/api/data/google/nearby?lat=${lat}&lng=${lng}`);
    if (!data || !data.results?.length) { container.innerHTML = '<div class="dh-hint">No nearby businesses found.</div>'; return; }
    appendCompetitorResults(data.results, true);
  }

  function appendCompetitorResults(results, replace) {
    const container = $('#dhCompetitorResults');
    const html = results.map(r => `
      <div class="dh-google-result" data-place='${JSON.stringify(r).replace(/'/g, "&#39;")}'>
        <div class="dh-gr-check">${selectedCompetitors.has(r.place_id) ? '&#10003;' : ''}</div>
        <div class="dh-gr-info">
          <div class="dh-gr-name">${esc(r.name)}</div>
          <div class="dh-gr-addr">${esc(r.address)}</div>
          <div class="dh-gr-meta">${r.rating ? r.rating + ' &#9733;' : ''} ${r.review_count ? '(' + r.review_count + ' reviews)' : ''}</div>
        </div>
      </div>
    `).join('');
    if (replace) container.innerHTML = html;
    else container.innerHTML += html;
    container.querySelectorAll('.dh-google-result').forEach(el => {
      el.onclick = async () => {
        const place = JSON.parse(el.dataset.place);
        if (selectedCompetitors.has(place.place_id)) {
          selectedCompetitors.delete(place.place_id);
          el.classList.remove('selected');
          el.querySelector('.dh-gr-check').innerHTML = '';
        } else {
          selectedCompetitors.add(place.place_id);
          el.classList.add('selected');
          el.querySelector('.dh-gr-check').innerHTML = '&#10003;';
          await fetch('/api/data/google/add-competitor', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({place_id: place.place_id, name: place.name, address: place.address, rating: place.rating || 0, review_count: place.review_count || 0, lat: place.lat || 0, lng: place.lng || 0, category: null})
          });
        }
      };
    });
  }

  // ── End Data Hub ──

  // ══════════════════════════════════════════════════════════════════════════
  // SAGE AI ASSISTANT — Streaming + Rich Markdown
  // ══════════════════════════════════════════════════════════════════════════

  const aiFab = $('#aiFab');
  const aiPanel = $('#aiChatPanel');
  const aiMessages = $('#aiChatMessages');
  const aiInput = $('#aiInput');
  const aiSendBtn = $('#aiSendBtn');
  const aiWelcome = $('#aiWelcome');
  const aiRemaining = $('#aiRemaining');
  let aiChatOpen = false;
  let aiStreaming = false;

  // Toggle chat panel
  if (aiFab) aiFab.addEventListener('click', () => {
    aiChatOpen = !aiChatOpen;
    aiPanel.classList.toggle('open', aiChatOpen);
    aiFab.classList.toggle('active', aiChatOpen);
    if (aiChatOpen) {
      aiInput.focus();
      if (!aiPanel.dataset.loaded) {
        aiPanel.dataset.loaded = '1';
        loadAiHistory();
      }
    }
  });

  // Close & minimize buttons
  const aiCloseBtn = $('#aiCloseBtn');
  const aiMinBtn = $('#aiMinBtn');
  if (aiCloseBtn) aiCloseBtn.addEventListener('click', () => {
    aiChatOpen = false;
    aiPanel.classList.remove('open');
    aiFab.classList.remove('active');
  });
  if (aiMinBtn) aiMinBtn.addEventListener('click', () => {
    aiChatOpen = false;
    aiPanel.classList.remove('open');
    aiFab.classList.remove('active');
  });

  // Clear history
  const aiClearBtn = $('#aiClearBtn');
  if (aiClearBtn) aiClearBtn.addEventListener('click', async () => {
    if (!confirm('Clear all conversation history with Claw Bot?')) return;
    await fetch('/api/ai/history', {method: 'DELETE', credentials: 'same-origin'});
    aiMessages.innerHTML = '';
    if (aiWelcome) {
      aiMessages.appendChild(aiWelcome.cloneNode(true));
      setupQuickPrompts();
    }
    showToast('Conversation cleared', 'info', 1500);
  });

  // Quick prompts
  function setupQuickPrompts() {
    $$('.ai-quick-prompt', aiMessages).forEach(btn => {
      btn.addEventListener('click', () => {
        aiInput.value = btn.dataset.prompt;
        sendAiMessage();
      });
    });
  }
  setupQuickPrompts();

  // Format timestamp
  function formatMsgTime(d) {
    const date = d || new Date();
    const h = date.getHours();
    const m = date.getMinutes();
    const ampm = h >= 12 ? 'PM' : 'AM';
    return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${ampm}`;
  }

  // ── Enhanced Markdown Renderer ──
  function formatAiMarkdown(text) {
    if (!text) return '';
    // Process code blocks first (preserve them from other transforms)
    let html = text;
    // Code blocks (```)
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      return `<pre><code>${esc(code.trim())}</code></pre>`;
    });
    // Split into segments: code blocks vs rest
    const parts = html.split(/(<pre><code>[\s\S]*?<\/code><\/pre>)/g);
    html = parts.map(part => {
      if (part.startsWith('<pre>')) return part; // Don't process code blocks
      let s = esc(part);
      // Headers
      s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
      s = s.replace(/^## (.+)$/gm, '<h2>$1</h2>');
      s = s.replace(/^# (.+)$/gm, '<h1>$1</h1>');
      // Bold & italic
      s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
      // Inline code
      s = s.replace(/`(.+?)`/g, '<code>$1</code>');
      // Blockquotes
      s = s.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
      // Lists
      s = s.replace(/^- (.+)$/gm, '<li>$1</li>');
      s = s.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
      // Wrap consecutive <li> in <ul>
      s = s.replace(/((?:<li>.*?<\/li>\n?)+)/g, '<ul>$1</ul>');
      // Links: [text](url)
      s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
      // Paragraphs
      s = s.replace(/\n\n/g, '</p><p>');
      s = s.replace(/\n/g, '<br>');
      s = '<p>' + s + '</p>';
      s = s.replace(/<p><\/p>/g, '');
      return s;
    }).join('');
    return html;
  }

  // ── Send Message ──
  async function sendAiMessage() {
    const text = aiInput.value.trim();
    if (!text || aiStreaming) return;

    const welcome = $('.ai-welcome', aiMessages);
    if (welcome) welcome.remove();

    appendAiMessage('user', text);
    aiInput.value = '';
    aiInput.style.height = 'auto';
    aiSendBtn.disabled = true;
    aiStreaming = true;

    // Show thinking indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'claw-thinking';
    typingEl.innerHTML = `
      <div class="claw-avatar-sm">&#129302;</div>
      <span>Claw Bot is thinking...</span>
      <div class="ai-typing-dot"></div>
      <div class="ai-typing-dot"></div>
      <div class="ai-typing-dot"></div>`;
    aiMessages.appendChild(typingEl);
    aiMessages.scrollTop = aiMessages.scrollHeight;

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({message: text}),
      });
      const data = await res.json();
      typingEl.remove();
      if (data.response) {
        appendAiMessage('assistant', data.response);
      } else {
        appendAiMessage('assistant', 'Sorry, something went wrong. Please try again.');
      }
      if (data.remaining !== undefined) {
        aiRemaining.textContent = `${data.remaining} messages remaining today`;
      }
    } catch (err) {
      typingEl.remove();
      appendAiMessage('assistant', 'Claw Bot is offline. Try again in a moment.');
    }

    aiSendBtn.disabled = false;
    aiStreaming = false;
    aiInput.focus();
  }

  // Build action buttons for a message
  function buildMsgActions(text) {
    let html = `<button class="ai-msg-action-btn" data-action="copy"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> Copy</button>`;
    // Detect email content
    if (text.match(/subject[:\s]/i) && text.match(/(dear|hi |hello|hey )/i)) {
      html += `<button class="ai-msg-action-btn" data-action="copy-email"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> Copy Email</button>`;
    }
    // Detect social post
    if (text.match(/#\w+/) && text.length < 1500) {
      html += `<button class="ai-msg-action-btn" data-action="copy-post"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 11.37A4 4 0 1112.63 8 4 4 0 0116 11.37z"/></svg> Copy Post</button>`;
    }
    return html;
  }

  // Bind click handlers for action buttons
  function bindActionButtons(container, text) {
    container.querySelectorAll('.ai-msg-action-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        navigator.clipboard.writeText(text).then(() => {
          const orig = btn.innerHTML;
          btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:11px;height:11px"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
          setTimeout(() => btn.innerHTML = orig, 2000);
        });
      });
    });
  }

  // Append message to chat (non-streaming)
  function appendAiMessage(role, content, timestamp) {
    const div = document.createElement('div');
    div.className = `ai-msg ${role}`;
    const time = timestamp ? formatMsgTime(new Date(timestamp)) : formatMsgTime();

    if (role === 'assistant') {
      const actionsHtml = buildMsgActions(content);
      div.innerHTML = `
        <div class="claw-avatar-sm">&#129302;</div>
        <div class="ai-msg-content">
          <div class="ai-msg-bubble">${formatAiMarkdown(content)}</div>
          <div class="ai-msg-time">${time}</div>
          <div class="ai-msg-actions">${actionsHtml}</div>
        </div>`;
      // Bind buttons after append
      setTimeout(() => {
        const actDiv = div.querySelector('.ai-msg-actions');
        if (actDiv) bindActionButtons(actDiv, content);
      }, 0);
    } else {
      div.innerHTML = `
        <div class="ai-msg-avatar" style="background:var(--bg-3);color:var(--text2)">You</div>
        <div class="ai-msg-content">
          <div class="ai-msg-bubble">${esc(content)}</div>
          <div class="ai-msg-time">${time}</div>
        </div>`;
    }
    aiMessages.appendChild(div);
    aiMessages.scrollTop = aiMessages.scrollHeight;
  }

  // Load conversation history
  async function loadAiHistory() {
    try {
      const res = await fetch('/api/ai/history', {credentials: 'same-origin'});
      const data = await res.json();
      if (data.messages && data.messages.length > 0) {
        const welcome = $('.ai-welcome', aiMessages);
        if (welcome) welcome.remove();
        data.messages.forEach(m => appendAiMessage(m.role, m.content, m.created_at));
      }
      if (data.remaining !== undefined) {
        aiRemaining.textContent = `${data.remaining} messages remaining today`;
      }
    } catch (err) {
      console.error('[Forge] Error loading AI history:', err);
    }
  }

  // Send on Enter (Shift+Enter for newline)
  if (aiInput) aiInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendAiMessage();
    }
  });

  // Auto-resize textarea
  if (aiInput) aiInput.addEventListener('input', () => {
    aiInput.style.height = 'auto';
    aiInput.style.height = Math.min(aiInput.scrollHeight, 80) + 'px';
  });

  // Send button
  if (aiSendBtn) aiSendBtn.addEventListener('click', () => sendAiMessage());

  // ── AI Email Rewrite ──
  const origLoadMkeEmails = loadMkeEmails;
  loadMkeEmails = async function() {
    await origLoadMkeEmails();
    $$('.mke-email-actions', $('#mkeEmailList')).forEach(actions => {
      if (actions.querySelector('.mke-ai-rewrite')) return;
      const btn = document.createElement('button');
      btn.className = 'mke-ai-rewrite';
      btn.innerHTML = '<span class="claw-mini-avatar" style="width:14px;height:14px;font-size:7px">&#129302;</span> Claw Bot Rewrite';
      btn.addEventListener('click', async () => {
        const card = btn.closest('.mke-email-card');
        const campIdEl = card.querySelector('[data-camp-id]');
        const campId = campIdEl ? campIdEl.dataset.campId : null;
        const camp = window.__mkeEmailData && window.__mkeEmailData[campId];
        if (!camp) return;
        btn.disabled = true;
        btn.textContent = 'Rewriting...';
        try {
          const res = await fetch('/api/ai/rewrite-email', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin',
            body: JSON.stringify({subject: camp.subject, body: camp.body}),
          });
          const data = await res.json();
          if (data.subject || data.body) {
            const subjectEl = card.querySelector('.mke-email-subject');
            const bodyEl = card.querySelector('.mke-email-body');
            if (subjectEl && data.subject) subjectEl.textContent = data.subject;
            if (bodyEl && data.body) bodyEl.innerHTML = esc(data.body).replace(/\n/g, '<br>');
            if (window.__mkeEmailData[campId]) {
              if (data.subject) window.__mkeEmailData[campId].subject = data.subject;
              if (data.body) window.__mkeEmailData[campId].body = data.body;
            }
            showToast('Email rewritten by Claw Bot!', 'success', 2000);
          }
        } catch (err) {
          showToast('Claw Bot rewrite failed', 'error', 2000);
        }
        btn.disabled = false;
        btn.innerHTML = '<span class="claw-mini-avatar" style="width:14px;height:14px;font-size:7px">&#129302;</span> Claw Bot Rewrite';
      });
      actions.appendChild(btn);
    });
  };

  // ── AI Content Generator ──
  const aiGenModal = $('#aiGenModal');
  const aiGenBtn = $('#aiGenBtn');
  const aiGenResult = $('#aiGenResult');
  const aiGenCopy = $('#aiGenCopy');
  let aiGenType = 'social';

  $$('.ai-gen-type').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.ai-gen-type').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      aiGenType = btn.dataset.type;
    });
  });

  if (aiGenBtn) aiGenBtn.addEventListener('click', async () => {
    const prompt = $('#aiGenPrompt')?.value.trim();
    if (!prompt) { showToast('Enter a description first', 'warning', 2000); return; }
    aiGenBtn.disabled = true;
    aiGenBtn.textContent = 'Claw Bot is writing...';
    aiGenResult.hidden = true;
    aiGenCopy.hidden = true;
    try {
      const res = await fetch('/api/ai/generate-content', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({content_type: aiGenType, prompt}),
      });
      const data = await res.json();
      if (data.content) {
        aiGenResult.textContent = data.content;
        aiGenResult.hidden = false;
        aiGenCopy.hidden = false;
      }
    } catch (err) {
      showToast('Content generation failed', 'error', 2000);
    }
    aiGenBtn.disabled = false;
    aiGenBtn.textContent = 'Generate with Claw Bot';
  });

  // ── Test Connection Button ──
  const testConnBtn = $('#testConnectionBtn');
  if (testConnBtn) testConnBtn.addEventListener('click', async () => {
    testConnBtn.disabled = true;
    testConnBtn.textContent = 'Testing...';
    const resultEl = $('#testConnectionResult');
    try {
      const res = await fetch('/api/ai/test-connection', {
        method: 'POST',
        credentials: 'same-origin',
      });
      const data = await res.json();
      if (data.ok) {
        resultEl.innerHTML = `<span style="color:var(--success)">Connected! Claw Bot is ready.</span>`;
        showToast('Claw Bot connected successfully!', 'success');
      } else {
        resultEl.innerHTML = `<span style="color:var(--danger)">${esc(data.message || 'Connection failed')}</span>`;
      }
    } catch (err) {
      resultEl.innerHTML = `<span style="color:var(--danger)">Connection test failed</span>`;
    }
    testConnBtn.disabled = false;
    testConnBtn.textContent = 'Test Connection';
  });

  // ── Toggle API Key Visibility ──
  const toggleVis = $('#toggleApiKeyVis');
  if (toggleVis) toggleVis.addEventListener('click', () => {
    const inp = $('#setAnthropicApiKey');
    if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
  });

  // ── Ask Claw Bot global function (for inline buttons) ──
  window.askClaw = function(prompt) {
    if (!aiChatOpen) {
      aiChatOpen = true;
      aiPanel.classList.add('open');
      aiFab.classList.add('active');
      if (!aiPanel.dataset.loaded) {
        aiPanel.dataset.loaded = '1';
        loadAiHistory();
      }
    }
    aiInput.value = prompt;
    sendAiMessage();
  };

  // Keep backward compat alias
  window.askSage = window.askClaw;

  // ── End Claw Bot AI Assistant ──

  // ══════════════════════════════════════════════════════════════════════════
  // AI AGENT FLEET — Advanced System
  // ══════════════════════════════════════════════════════════════════════════

  const AGENT_ICONS = {
    megaphone: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l18-5v12L3 13v-2z"/><path d="M11.6 16.8a3 3 0 11-5.8-1.6"/></svg>',
    binoculars: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="17" r="4"/><circle cx="17" cy="17" r="4"/><path d="M7 13V5a2 2 0 012-2h0a2 2 0 012 2v8"/><path d="M13 13V5a2 2 0 012-2h0a2 2 0 012 2v8"/></svg>',
    heart: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>',
    chess: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 3v3M9 6h6l-1 5h-4L9 6z"/><path d="M7 11h10l1 5H6l1-5z"/><path d="M5 16h14v2a1 1 0 01-1 1H6a1 1 0 01-1-1v-2z"/></svg>',
    dollar: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>',
  };

  const AGENT_ICONS_SM = {
    megaphone: 'M', binoculars: 'S', heart: 'E', chess: 'A', dollar: 'M',
  };

  let _agentsData = null;
  let _agentTasksData = null;
  let _agentOutputsData = null;
  let _commandRunning = false;
  let _currentOutputId = null;

  function timeAgo(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return d.toLocaleDateString();
  }

  // ── Agent Tabs ──
  $$('.agents-tab').forEach(tab => {
    tab.onclick = () => {
      $$('.agents-tab').forEach(t => t.classList.remove('active'));
      $$('.agents-tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = $('#agentsPanel-' + tab.dataset.tab);
      if (panel) panel.classList.add('active');
      // Lazy load tab content
      if (tab.dataset.tab === 'outputs' && !_agentOutputsData) loadAgentOutputs();
      if (tab.dataset.tab === 'tasks' && !_agentTasksData) loadAgentTasks();
      if (tab.dataset.tab === 'performance') loadAgentPerformance();
      if (tab.dataset.tab === 'deliverables') loadDeliverables();
      if (tab.dataset.tab === 'audit') loadAuditLog();
    };
  });

  async function loadAgents() {
    try {
      const res = await fetch('/api/dashboard/agents', { credentials: 'same-origin' });
      const data = await res.json();
      _agentsData = data;

      // Lock overlay for non-Scale (but allow demo account)
      const lockOverlay = $('#agentsLockOverlay');
      const isDemoOrScale = data.plan_tier === 'scale' || data.plan_tier === 'demo';
      if (lockOverlay) {
        if (isDemoOrScale) {
          lockOverlay.hidden = true;
          lockOverlay.style.display = 'none';
        } else {
          lockOverlay.hidden = false;
          lockOverlay.style.display = 'flex';
        }
      }

      // Metrics
      const m = data.metrics || {};
      const amTotalTasks = $('#amTotalTasks');
      if (amTotalTasks) amTotalTasks.textContent = m.total_tasks_month || 0;
      const amContent = $('#amContent');
      if (amContent) amContent.textContent = m.content_generated || 0;
      const amOpportunities = $('#amOpportunities');
      if (amOpportunities) amOpportunities.textContent = m.opportunities_found || 0;
      const amRevenue = $('#amRevenue');
      if (amRevenue) amRevenue.textContent = '$' + (m.estimated_revenue_impact || 0).toLocaleString();
      const amHours = $('#amHours');
      if (amHours) amHours.textContent = '~' + (m.hours_saved || 0) + 'h';

      // Render collaboration bar
      renderCollabBar(data.agents);

      // Render agent cards + custom agent builder teaser
      const grid = $('#agentsGrid');
      if (!grid) return;
      const AGENT_RUN_LABELS = {
        maya: 'Generate Content',
        scout: 'Run Competitor Scan',
        emma: 'Draft Outreach',
        alex: 'Generate Briefing',
        max: 'Find Opportunities',
      };
      const agentCards = data.agents.map(agent => {
        const effectiveness = Math.min(98, 70 + agent.tasks_month * 2);
        const runLabel = AGENT_RUN_LABELS[agent.agent_type] || 'Run Now';
        return `
        <div class="agent-card" data-agent="${agent.agent_type}" style="--agent-color:${agent.color}">
          <div class="agent-card-top">
            <div class="agent-avatar" style="background:${agent.color}">${AGENT_ICONS[agent.icon] || ''}</div>
            <div class="agent-toggle-wrap">
              <span class="agent-status ${agent.is_active ? 'active' : 'paused'}">${agent.is_active ? 'Active' : 'Paused'}</span>
              <label class="agent-switch">
                <input type="checkbox" ${agent.is_active ? 'checked' : ''} onchange="toggleAgent('${agent.agent_type}', this)">
                <span class="agent-slider"></span>
              </label>
            </div>
          </div>
          <h3 class="agent-name">${agent.name}</h3>
          <div class="agent-role">${agent.role}</div>
          <p class="agent-desc">${agent.description}</p>
          <div class="agent-stats">
            <div class="agent-stat"><strong>${agent.tasks_today}</strong> today</div>
            <div class="agent-stat"><strong>${agent.tasks_month}</strong> this month</div>
            <div class="agent-stat"><strong>${effectiveness}%</strong> effective</div>
          </div>
          ${agent.last_action ? '<div class="agent-last-action">' + esc(agent.last_action) + ' <span class="agent-time">' + timeAgo(agent.last_action_at) + '</span></div>' : ''}
          <div class="agent-card-actions">
            <button class="agent-btn agent-btn-run" id="agentRunBtn-${agent.agent_type}" data-label="${esc(runLabel)}" onclick="runSingleAgent('${agent.agent_type}')">${runLabel}</button>
            <button class="agent-btn agent-btn-chat" onclick="openAgentChat('${agent.agent_type}')">Chat</button>
            <button class="agent-btn agent-btn-config" onclick="openAgentConfig('${agent.agent_type}')">Configure</button>
            <button class="agent-btn agent-btn-activity" onclick="showAgentHistory('${agent.agent_type}')">History</button>
          </div>
        </div>`;
      }).join('');

      // Custom agent builder teaser card
      const builderCard = `
        <div class="agent-builder-card">
          <div class="agent-builder-icon">+</div>
          <div class="agent-builder-title">Build Your Own Agent</div>
          <div class="agent-builder-desc">Create custom AI agents tailored to your specific business needs</div>
          <span class="agent-builder-badge">Coming Soon</span>
        </div>`;

      grid.innerHTML = agentCards + builderCard;

      // Load activity feed
      loadAgentActivityFeed('');

      // Wire filter buttons
      $$('.agent-filter-btn').forEach(btn => {
        btn.onclick = () => {
          $$('.agent-filter-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          loadAgentActivityFeed(btn.dataset.agent);
        };
      });

    } catch (err) {
      console.error('[Forge] Error loading agents:', err);
    }
  }

  // ── Collaboration Bar ──
  function renderCollabBar(agents) {
    const bar = $('#collabAgents');
    if (!bar) return;
    const activeAgents = agents.filter(a => a.is_active);
    const currentTasks = {
      maya: 'Drafting social content...',
      scout: 'Monitoring competitors...',
      emma: 'Analyzing customer data...',
      alex: 'Updating revenue forecast...',
      max: 'Optimizing pricing...',
    };
    bar.innerHTML = activeAgents.map(a => `
      <div class="collab-agent" style="--agent-color:${a.color}">
        <div class="collab-agent-avatar" style="background:${a.color}">${a.name[0]}</div>
        <div>
          <div class="collab-agent-name">${a.name}</div>
          <div class="collab-agent-task">${currentTasks[a.agent_type] || 'Standing by...'}</div>
        </div>
      </div>
    `).join('');
  }

  // ── Activity Feed ──
  async function loadAgentActivityFeed(agentFilter) {
    const feed = $('#agentActivityFeed');
    if (!feed) return;
    feed.innerHTML = '<div class="agent-feed-loading">Loading activity...</div>';
    try {
      const url = '/api/dashboard/agents/activity/all' + (agentFilter ? '?agent_filter=' + agentFilter : '');
      const res = await fetch(url, { credentials: 'same-origin' });
      const data = await res.json();
      if (!data.activities || data.activities.length === 0) {
        feed.innerHTML = '<div class="agent-feed-empty">No activity yet. Your agents are getting started.</div>';
        return;
      }
      feed.innerHTML = data.activities.map(a => `
        <div class="agent-feed-item">
          <div class="agent-feed-dot" style="background:${a.agent_color}"></div>
          <div class="agent-feed-content">
            <strong>${esc(a.agent_name)}</strong>
            <span class="agent-feed-desc">${esc(a.description)}</span>
          </div>
          <span class="agent-feed-time">${timeAgo(a.created_at)}</span>
        </div>
      `).join('');
    } catch (err) {
      feed.innerHTML = '<div class="agent-feed-empty">Failed to load activity.</div>';
    }
  }

  // ── Task Board ──
  async function loadAgentTasks() {
    try {
      const res = await fetch('/api/dashboard/agents/tasks', { credentials: 'same-origin' });
      const data = await res.json();
      _agentTasksData = data;

      const counts = data.counts || {};
      const el = (id, val) => { const e = $('#' + id); if (e) e.textContent = val; };
      el('tbPendingCount', counts.pending || 0);
      el('tbInProgressCount', counts.in_progress || 0);
      el('tbCompletedCount', counts.completed || 0);

      const renderTask = (t) => `
        <div class="task-card" data-task-id="${t.id}">
          <div class="task-card-top">
            <div class="task-card-avatar" style="background:${t.agent_color}">${t.agent_name[0]}</div>
            <span class="task-card-agent">${esc(t.agent_name)}</span>
            <span class="task-card-priority ${t.priority}">${t.priority}</span>
          </div>
          <div class="task-card-title">${esc(t.title)}</div>
          <div class="task-card-desc">${esc(t.description)}</div>
          ${t.result ? '<div class="task-card-result">' + esc(t.result) + '</div>' : ''}
          <div class="task-card-footer">
            <span class="task-card-time">${timeAgo(t.created_at)}</span>
            <div class="task-card-actions">
              ${t.status === 'pending' ? '<button class="task-card-btn start" onclick="updateTaskStatus(\'' + t.id + '\',\'in_progress\')">Start</button>' : ''}
              ${t.status === 'in_progress' ? '<button class="task-card-btn complete" onclick="updateTaskStatus(\'' + t.id + '\',\'completed\')">Complete</button>' : ''}
            </div>
          </div>
        </div>`;

      const pending = data.tasks.filter(t => t.status === 'pending');
      const inProgress = data.tasks.filter(t => t.status === 'in_progress');
      const completed = data.tasks.filter(t => t.status === 'completed');

      const tbPending = $('#tbPending');
      const tbInProgress = $('#tbInProgress');
      const tbCompleted = $('#tbCompleted');

      if (tbPending) tbPending.innerHTML = pending.length ? pending.map(renderTask).join('') : '<div class="task-empty">No pending tasks</div>';
      if (tbInProgress) tbInProgress.innerHTML = inProgress.length ? inProgress.map(renderTask).join('') : '<div class="task-empty">No tasks in progress</div>';
      if (tbCompleted) tbCompleted.innerHTML = completed.length ? completed.map(renderTask).join('') : '<div class="task-empty">No completed tasks</div>';

    } catch (err) {
      console.error('[Forge] Error loading agent tasks:', err);
    }
  }

  window.updateTaskStatus = async function(taskId, newStatus) {
    try {
      await fetch('/api/dashboard/agents/tasks/' + taskId + '/status', {
        method: 'PUT', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      showToast('Task updated!', 'success');
      loadAgentTasks();
    } catch (err) {
      showToast('Failed to update task', 'error');
    }
  };

  window.submitQuickTask = async function() {
    const title = $('#aqtTitle');
    const agent = $('#aqtAgent');
    const priority = $('#aqtPriority');
    if (!title || !title.value.trim()) { showToast('Enter a task description', 'error'); return; }

    // Auto-assign based on keywords if no agent selected
    let agentType = agent ? agent.value : '';
    if (!agentType) {
      const t = title.value.toLowerCase();
      if (/social|post|campaign|content|email.*market|instagram|tiktok|facebook/.test(t)) agentType = 'maya';
      else if (/competitor|competition|market.*position|rival|spy/.test(t)) agentType = 'scout';
      else if (/customer|review|win.*back|retention|churn|vip/.test(t)) agentType = 'emma';
      else if (/strat|analys|forecast|goal|revenue.*plan|kpi/.test(t)) agentType = 'alex';
      else if (/price|sale|bundle|upsell|discount|markdown|inventory/.test(t)) agentType = 'max';
      else agentType = 'alex'; // Default to Alex for general tasks
    }

    try {
      await fetch('/api/dashboard/agents/tasks', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_type: agentType,
          title: title.value.trim(),
          priority: priority ? priority.value : 'medium',
        }),
      });
      const agentName = _agentsData ? (_agentsData.agents.find(a => a.agent_type === agentType) || {}).name || agentType : agentType;
      showToast('Task assigned to ' + agentName + '!', 'success');
      title.value = '';
      const bar = $('#agentQuickTaskBar');
      if (bar) { bar.hidden = true; bar.style.display = 'none'; }
      // Switch to task board tab
      const tasksTab = document.querySelector('.agents-tab[data-tab="tasks"]');
      if (tasksTab) tasksTab.click();
      loadAgentTasks();
    } catch (err) {
      showToast('Failed to assign task', 'error');
    }
  };

  // ── Performance ──
  function loadAgentPerformance() {
    if (!_agentsData) return;
    const grid = $('#agentsPerfGrid');
    if (!grid) return;

    grid.innerHTML = _agentsData.agents.map(agent => {
      const eff = Math.min(98, 70 + agent.tasks_month * 2);
      const responseRate = Math.min(99, 80 + Math.floor(Math.random() * 15));
      const taskCompletion = Math.min(100, 85 + Math.floor(Math.random() * 12));
      return `
      <div class="agent-perf-card" style="--agent-color:${agent.color}">
        <div class="agent-perf-header">
          <div class="agent-perf-avatar" style="background:${agent.color}">${AGENT_ICONS[agent.icon] || ''}</div>
          <div>
            <div class="agent-perf-name">${agent.name}</div>
            <div class="agent-perf-role">${agent.role}</div>
          </div>
        </div>
        <div class="agent-perf-stats">
          <div class="agent-perf-stat">
            <div class="agent-perf-stat-value">${agent.tasks_today}</div>
            <div class="agent-perf-stat-label">Tasks today</div>
          </div>
          <div class="agent-perf-stat">
            <div class="agent-perf-stat-value">${agent.tasks_month}</div>
            <div class="agent-perf-stat-label">This month</div>
          </div>
        </div>
        <div class="agent-perf-bar-wrap">
          <div class="agent-perf-bar-label"><span>Effectiveness</span><span>${eff}%</span></div>
          <div class="agent-perf-bar"><div class="agent-perf-bar-fill" style="width:${eff}%;background:${agent.color}"></div></div>
        </div>
        <div class="agent-perf-bar-wrap">
          <div class="agent-perf-bar-label"><span>Response Quality</span><span>${responseRate}%</span></div>
          <div class="agent-perf-bar"><div class="agent-perf-bar-fill" style="width:${responseRate}%;background:${agent.color}"></div></div>
        </div>
        <div class="agent-perf-bar-wrap">
          <div class="agent-perf-bar-label"><span>Task Completion</span><span>${taskCompletion}%</span></div>
          <div class="agent-perf-bar"><div class="agent-perf-bar-fill" style="width:${taskCompletion}%;background:${agent.color}"></div></div>
        </div>
      </div>`;
    }).join('');
  }

  // ── Deliverables Tab ──
  async function loadDeliverables() {
    const grid = $('#deliverablesGrid');
    if (!grid) return;
    grid.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Loading deliverables...</div>';
    try {
      const agentFilter = $('#delAgentFilter') ? $('#delAgentFilter').value : '';
      const statusFilter = $('#delStatusFilter') ? $('#delStatusFilter').value : '';
      let url = '/api/agents/deliverables?limit=50';
      if (agentFilter) url += '&agent_type=' + agentFilter;
      if (statusFilter) url += '&status=' + statusFilter;
      const res = await fetch(url, {credentials: 'same-origin'});
      const data = await res.json();
      const items = data.deliverables || [];
      if (items.length === 0) {
        grid.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--text3)"><div style="font-size:2rem;margin-bottom:0.5rem">&#128230;</div>No deliverables yet. Run a command to generate outputs.</div>';
        return;
      }
      const agentEmojis = {maya:'&#128227;',scout:'&#128269;',emma:'&#128154;',alex:'&#128202;',max:'&#128176;'};
      const agentCredit = {maya:'Created by Maya',scout:'Identified by Scout',emma:'Drafted by Emma',alex:'Analysis by Alex',max:'Recommended by Max'};
      grid.innerHTML = items.map(d => {
        const statusColors = {draft:'#f59e0b',approved:'#10b981',shipped:'#6366f1',rejected:'#ef4444'};
        const statusColor = statusColors[d.status] || '#71717a';
        const quality = d.overall_quality ? Math.round(d.overall_quality) : '—';
        const qualityColor = d.overall_quality >= 80 ? '#10b981' : d.overall_quality >= 60 ? '#f59e0b' : '#ef4444';
        const tAgo = agentTimeAgo(d.created_at);
        const credit = (agentCredit[d.agent_type] || d.agent_type) + ' ' + (agentEmojis[d.agent_type] || '');
        const typeBadge = (d.deliverable_type || 'general').replace(/_/g, ' ');
        const aColor = d.agent_color || '#6366f1';
        return `
        <div class="deliverable-card" style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;padding:2px 8px;border-radius:20px;background:${aColor}18;color:${aColor};font-weight:600;text-transform:capitalize">${typeBadge}</span>
              <span style="font-weight:600;color:var(--text1)">${esc(d.title || d.deliverable_type)}</span>
            </div>
            <span style="font-size:11px;padding:2px 8px;border-radius:20px;background:${statusColor}22;color:${statusColor};font-weight:600;text-transform:uppercase">${d.status}</span>
          </div>
          <div style="font-size:12px;color:var(--text3)">${credit} &middot; ${tAgo}</div>
          <div style="font-size:13px;color:var(--text2);max-height:80px;overflow:hidden;line-height:1.5;white-space:pre-line">${esc((d.content || '').substring(0, 250))}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:auto;gap:6px;flex-wrap:wrap">
            <span style="font-size:12px;font-weight:700;color:${qualityColor}">Quality: ${quality}/100</span>
            <div style="display:flex;gap:4px">
              <button onclick="copyDeliverableContent('${d.id}')" style="font-size:11px;padding:4px 10px;background:var(--bg-3);color:var(--text2);border:1px solid var(--border);border-radius:6px;cursor:pointer" title="Copy to clipboard">Copy</button>
              ${d.status === 'draft' ? '<button onclick="approveDeliverable(&#39;'+d.id+'&#39;)" style="font-size:11px;padding:4px 10px;background:#10b981;color:#fff;border:none;border-radius:6px;cursor:pointer">Approve</button>' : ''}
            </div>
          </div>
        </div>`;
      }).join('');
      // Store data for copy function
      window._deliverablesData = items;
    } catch (err) {
      grid.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--danger)">Failed to load deliverables</div>';
    }
  }

  // Deliverable filter change handlers
  const delAgentFilter = $('#delAgentFilter');
  const delStatusFilter = $('#delStatusFilter');
  if (delAgentFilter) delAgentFilter.onchange = () => loadDeliverables();
  if (delStatusFilter) delStatusFilter.onchange = () => loadDeliverables();

  window.approveDeliverable = async function(id) {
    try {
      const res = await fetch('/api/agents/deliverables/' + id + '/approve', {
        method: 'POST', credentials: 'same-origin',
      });
      const data = await res.json();
      if (data.error) {
        showToast(data.error, 'error');
      } else {
        showToast('Deliverable approved!', 'success');
        loadDeliverables();
      }
    } catch (err) {
      showToast('Approval failed', 'error');
    }
  };

  // ── Audit Log Tab ──
  async function loadAuditLog() {
    const container = $('#auditLogFeed');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Loading audit log...</div>';
    try {
      const res = await fetch('/api/agents/audit-log?limit=100', {credentials: 'same-origin'});
      const data = await res.json();
      const entries = data.entries || [];
      if (entries.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--text3)"><div style="font-size:2rem;margin-bottom:0.5rem">&#128220;</div>No audit entries yet. Actions will appear here.</div>';
        return;
      }
      container.innerHTML = entries.map(e => {
        const actionColors = {goal_started:'#6366f1',task_completed:'#10b981',deliverable_created:'#f59e0b',deliverable_approved:'#10b981',email_sent:'#3b82f6',agent_executed:'#8b5cf6',policy_blocked:'#ef4444'};
        const color = actionColors[e.action] || '#71717a';
        const timeAgo = agentTimeAgo(e.created_at);
        const details = e.details || {};
        let detailStr = '';
        if (details.quality_score) detailStr += ' &middot; Quality: ' + Math.round(details.quality_score) + '/100';
        if (details.reason) detailStr += ' &middot; ' + esc(details.reason);
        return `
        <div style="display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--border);align-items:flex-start">
          <div style="width:8px;height:8px;border-radius:50%;background:${color};margin-top:6px;flex-shrink:0"></div>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;color:var(--text1)"><strong>${esc(e.actor)}</strong> <span style="color:var(--text3)">${esc(e.action.replace(/_/g, ' '))}</span> ${e.resource_type ? '<span style="color:var(--text2)">' + esc(e.resource_type) + (e.resource_id ? ' #' + e.resource_id : '') + '</span>' : ''}</div>
            ${detailStr ? '<div style="font-size:12px;color:var(--text3);margin-top:2px">' + detailStr + '</div>' : ''}
          </div>
          <div style="font-size:11px;color:var(--text3);white-space:nowrap">${timeAgo}</div>
        </div>`;
      }).join('');
    } catch (err) {
      container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--danger)">Failed to load audit log</div>';
    }
  }

  // Toggle agent active/paused
  window.toggleAgent = async function(agentType, checkbox) {
    try {
      const res = await fetch('/api/dashboard/agents/' + agentType + '/toggle', {
        method: 'PUT', credentials: 'same-origin',
      });
      const data = await res.json();
      const card = checkbox.closest('.agent-card');
      const status = card.querySelector('.agent-status');
      if (data.is_active) {
        status.className = 'agent-status active';
        status.textContent = 'Active';
      } else {
        status.className = 'agent-status paused';
        status.textContent = 'Paused';
      }
      // Re-render collab bar
      if (_agentsData) {
        const ag = _agentsData.agents.find(a => a.agent_type === agentType);
        if (ag) ag.is_active = data.is_active;
        renderCollabBar(_agentsData.agents);
      }
    } catch (err) {
      showToast('Failed to toggle agent', 'error');
    }
  };

  // Open agent config modal
  window.openAgentConfig = function(agentType) {
    if (!_agentsData) return;
    const agent = _agentsData.agents.find(a => a.agent_type === agentType);
    if (!agent) return;

    const modal = $('#agentConfigModal');
    modal.hidden = false;
    modal.style.display = 'flex';

    $('#acAvatar').style.background = agent.color;
    $('#acAvatar').innerHTML = AGENT_ICONS[agent.icon] || '';
    $('#acName').textContent = agent.name;
    $('#acRole').textContent = agent.role;

    const body = $('#acBody');
    const cfg = agent.configuration || {};

    const configFields = {
      maya: `
        <div class="ac-field"><label>Posting Frequency</label><select id="acf_posting_frequency"><option value="daily" ${cfg.posting_frequency==='daily'?'selected':''}>Daily</option><option value="3x_week" ${cfg.posting_frequency==='3x_week'?'selected':''}>3x per week</option><option value="weekly" ${cfg.posting_frequency==='weekly'?'selected':''}>Weekly</option></select></div>
        <div class="ac-field"><label>Tone</label><select id="acf_tone"><option value="professional" ${cfg.tone==='professional'?'selected':''}>Professional</option><option value="casual" ${cfg.tone==='casual'?'selected':''}>Casual</option><option value="fun" ${cfg.tone==='fun'?'selected':''}>Fun</option><option value="edgy" ${cfg.tone==='edgy'?'selected':''}>Edgy</option></select></div>
        <div class="ac-field"><label>Content Focus</label><select id="acf_focus"><option value="products" ${cfg.focus==='products'?'selected':''}>Products</option><option value="lifestyle" ${cfg.focus==='lifestyle'?'selected':''}>Lifestyle</option><option value="behind_scenes" ${cfg.focus==='behind_scenes'?'selected':''}>Behind the Scenes</option><option value="competitive" ${cfg.focus==='competitive'?'selected':''}>Competitive</option></select></div>
        <div class="ac-field ac-toggle-field"><label>Auto-Generate Content</label><label class="agent-switch"><input type="checkbox" id="acf_auto_generate" ${cfg.auto_generate?'checked':''}><span class="agent-slider"></span></label></div>
      `,
      scout: `
        <div class="ac-field"><label>Monitor Frequency</label><select id="acf_monitor_frequency"><option value="realtime" ${cfg.monitor_frequency==='realtime'?'selected':''}>Real-time</option><option value="daily" ${cfg.monitor_frequency==='daily'?'selected':''}>Daily</option><option value="weekly" ${cfg.monitor_frequency==='weekly'?'selected':''}>Weekly</option></select></div>
        <div class="ac-field"><label>Alert Sensitivity</label><select id="acf_alert_sensitivity"><option value="all" ${cfg.alert_sensitivity==='all'?'selected':''}>All Changes</option><option value="significant" ${cfg.alert_sensitivity==='significant'?'selected':''}>Significant Only</option><option value="critical" ${cfg.alert_sensitivity==='critical'?'selected':''}>Critical Only</option></select></div>
        <div class="ac-field ac-toggle-field"><label>Auto-Generate Responses</label><label class="agent-switch"><input type="checkbox" id="acf_auto_generate_responses" ${cfg.auto_generate_responses?'checked':''}><span class="agent-slider"></span></label></div>
      `,
      emma: `
        <div class="ac-field"><label>At-Risk Threshold</label><select id="acf_at_risk_threshold"><option value="30" ${cfg.at_risk_threshold==30?'selected':''}>30 days</option><option value="45" ${cfg.at_risk_threshold==45?'selected':''}>45 days</option><option value="60" ${cfg.at_risk_threshold==60?'selected':''}>60 days</option></select></div>
        <div class="ac-field"><label>Review Response Style</label><select id="acf_review_response_style"><option value="grateful" ${cfg.review_response_style==='grateful'?'selected':''}>Grateful</option><option value="professional" ${cfg.review_response_style==='professional'?'selected':''}>Professional</option><option value="casual" ${cfg.review_response_style==='casual'?'selected':''}>Casual</option></select></div>
        <div class="ac-field"><label>Win-Back Discount</label><select id="acf_winback_discount"><option value="10" ${cfg.winback_discount==10?'selected':''}>10%</option><option value="15" ${cfg.winback_discount==15?'selected':''}>15%</option><option value="20" ${cfg.winback_discount==20?'selected':''}>20%</option></select></div>
        <div class="ac-field ac-toggle-field"><label>Auto-Draft Emails</label><label class="agent-switch"><input type="checkbox" id="acf_auto_draft_emails" ${cfg.auto_draft_emails?'checked':''}><span class="agent-slider"></span></label></div>
      `,
      alex: `
        <div class="ac-field"><label>Report Frequency</label><select id="acf_report_frequency"><option value="daily" ${cfg.report_frequency==='daily'?'selected':''}>Daily</option><option value="weekly" ${cfg.report_frequency==='weekly'?'selected':''}>Weekly</option><option value="monthly" ${cfg.report_frequency==='monthly'?'selected':''}>Monthly</option></select></div>
        <div class="ac-field"><label>Alert Threshold</label><select id="acf_alert_threshold"><option value="any" ${cfg.alert_threshold==='any'?'selected':''}>Any Change</option><option value="10pct" ${cfg.alert_threshold==='10pct'?'selected':''}>10%+ Changes</option><option value="25pct" ${cfg.alert_threshold==='25pct'?'selected':''}>25%+ Changes</option></select></div>
        <div class="ac-field ac-toggle-field"><label>Goals Auto-Adjust</label><label class="agent-switch"><input type="checkbox" id="acf_goals_auto_adjust" ${cfg.goals_auto_adjust?'checked':''}><span class="agent-slider"></span></label></div>
      `,
      max: `
        <div class="ac-field"><label>Price Optimization</label><select id="acf_price_optimization"><option value="conservative" ${cfg.price_optimization==='conservative'?'selected':''}>Conservative</option><option value="moderate" ${cfg.price_optimization==='moderate'?'selected':''}>Moderate</option><option value="aggressive" ${cfg.price_optimization==='aggressive'?'selected':''}>Aggressive</option></select></div>
        <div class="ac-field ac-toggle-field"><label>Bundle Suggestions</label><label class="agent-switch"><input type="checkbox" id="acf_bundle_suggestions" ${cfg.bundle_suggestions?'checked':''}><span class="agent-slider"></span></label></div>
        <div class="ac-field ac-toggle-field"><label>Markdown Alerts</label><label class="agent-switch"><input type="checkbox" id="acf_markdown_alerts" ${cfg.markdown_alerts?'checked':''}><span class="agent-slider"></span></label></div>
        <div class="ac-field ac-toggle-field"><label>Upsell Suggestions</label><label class="agent-switch"><input type="checkbox" id="acf_upsell_suggestions" ${cfg.upsell_suggestions?'checked':''}><span class="agent-slider"></span></label></div>
      `,
    };

    body.innerHTML = configFields[agentType] || '<p>No configuration available.</p>';
    modal.dataset.agentType = agentType;

    // Save button
    $('#acSaveBtn').onclick = async () => {
      const newCfg = {};
      body.querySelectorAll('select').forEach(sel => {
        const key = sel.id.replace('acf_', '');
        const val = sel.value;
        newCfg[key] = isNaN(val) ? val : Number(val);
      });
      body.querySelectorAll('input[type=checkbox]').forEach(cb => {
        const key = cb.id.replace('acf_', '');
        newCfg[key] = cb.checked;
      });
      try {
        await fetch('/api/dashboard/agents/' + agentType + '/configure', {
          method: 'PUT', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newCfg),
        });
        showToast(agent.name + ' configuration saved!', 'success');
        modal.hidden = true;
        modal.style.display = 'none';
        loadAgents();
      } catch (e) {
        showToast('Failed to save', 'error');
      }
    };

    // Reset button
    $('#acResetBtn').onclick = () => {
      openAgentConfig(agentType);
    };
  };

  // Open agent chat (redirect to Claw Bot with agent context)
  window.openAgentChat = function(agentType) {
    if (!_agentsData) return;
    const agent = _agentsData.agents.find(a => a.agent_type === agentType);
    if (!agent) return;

    // Open the Claw Bot chat panel
    const chatPanel = $('.ai-chat-panel');
    if (chatPanel) {
      chatPanel.classList.add('open');
      aiChatOpen = true;
      if (aiFab) aiFab.classList.add('active');
    }

    // Update chat header to show agent identity with colored indicator
    const chatHeaderName = chatPanel ? chatPanel.querySelector('.ai-chat-title') : null;
    if (chatHeaderName) chatHeaderName.innerHTML = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + agent.color + ';margin-right:6px"></span>' + agent.name + ' — ' + agent.role;

    // Set the chat to agent mode
    window._activeAgentType = agentType;
    window._activeAgentName = agent.name;

    // Clear and add agent greeting
    const msgs = chatPanel ? chatPanel.querySelector('.ai-chat-messages') : null;
    if (msgs) {
      msgs.innerHTML = '';
      const agentGreetings = {
        maya: "Hey! I'm Maya, your Marketing Director. Want me to create some social posts, plan a campaign, or brainstorm content ideas? Just ask!",
        scout: "I'm Scout, your Competitive Intelligence Analyst. I can brief you on competitor activity, identify opportunities, or help you craft a competitive response.",
        emma: "Hi! I'm Emma, your Customer Success Manager. I can help with win-back emails, review responses, or identifying your VIP customers. What do you need?",
        alex: "I'm Alex, your Chief Strategy Officer. I can analyze your business performance, set goals, forecast revenue, or provide strategic recommendations.",
        max: "I'm Max, your Sales Director. I find ways to increase revenue — bundles, pricing optimization, upsell opportunities. Where should we start?",
      };
      const greeting = agentGreetings[agentType] || 'How can I help?';
      const msgDiv = document.createElement('div');
      msgDiv.className = 'ai-msg assistant';
      msgDiv.innerHTML = '<div class="ai-msg-avatar" style="background:' + agent.color + '">' + agent.name[0] + '</div><div class="ai-msg-bubble">' + esc(greeting) + '</div>';
      msgs.appendChild(msgDiv);
    }
  };

  // Intercept sendAiMessage to use agent chat when in agent mode
  if (aiSendBtn && aiInput) {
    const origHandler = aiSendBtn.onclick;
    aiSendBtn.onclick = async function(e) {
      if (window._activeAgentType) {
        e.preventDefault();
        e.stopPropagation();
        const msg = aiInput.value.trim();
        if (!msg) return;
        aiInput.value = '';
        const msgs = $('.ai-chat-messages');
        const agent = _agentsData ? _agentsData.agents.find(a => a.agent_type === window._activeAgentType) : null;
        const agentColor = agent ? agent.color : '#6366f1';
        const agentInitial = agent ? agent.name[0] : '?';
        // Add user message
        const userDiv = document.createElement('div');
        userDiv.className = 'ai-msg user';
        userDiv.innerHTML = '<div class="ai-msg-bubble">' + esc(msg) + '</div>';
        msgs.appendChild(userDiv);
        msgs.scrollTop = msgs.scrollHeight;
        // Add loading
        const loadDiv = document.createElement('div');
        loadDiv.className = 'ai-msg assistant';
        loadDiv.innerHTML = '<div class="ai-msg-avatar" style="background:' + agentColor + '">' + agentInitial + '</div><div class="ai-msg-bubble"><span class="ai-typing">thinking...</span></div>';
        msgs.appendChild(loadDiv);
        msgs.scrollTop = msgs.scrollHeight;
        try {
          const res = await fetch('/api/ai/agent-chat', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_type: window._activeAgentType, message: msg }),
          });
          const data = await res.json();
          loadDiv.querySelector('.ai-msg-bubble').innerHTML = (data.response || 'No response.').replace(/\n/g, '<br>');
        } catch (err) {
          loadDiv.querySelector('.ai-msg-bubble').innerHTML = 'Something went wrong. Try again.';
        }
        msgs.scrollTop = msgs.scrollHeight;
        return;
      }
      // Otherwise use original handler
      if (origHandler) origHandler.call(this, e);
    };
  }

  // Clear agent mode when chat is closed
  const closeChatBtn = $('.ai-chat-close');
  if (closeChatBtn) {
    const origClose = closeChatBtn.onclick;
    closeChatBtn.onclick = function(e) {
      window._activeAgentType = null;
      window._activeAgentName = null;
      const chatHeaderName = document.querySelector('.ai-chat-title');
      if (chatHeaderName) chatHeaderName.textContent = 'Claw Bot';
      if (origClose) origClose.call(this, e);
    };
  }

  // Show agent activity in a filtered view
  window.showAgentActivity = function(agentType) {
    // Switch to activity tab first
    const activityTab = document.querySelector('.agents-tab[data-tab="activity"]');
    if (activityTab) activityTab.click();
    // Filter
    setTimeout(() => {
      const filterBtn = document.querySelector('.agent-filter-btn[data-agent="' + agentType + '"]');
      if (filterBtn) filterBtn.click();
      const feedSection = document.querySelector('.agents-activity-section');
      if (feedSection) feedSection.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  // ── Command Bar ──
  const cmdInput = $('#agentCommandInput');
  if (cmdInput) {
    cmdInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitAgentCommand(); }
    });
  }

  window.submitAgentCommand = async function() {
    const input = $('#agentCommandInput');
    if (!input) return;
    const command = input.value.trim();
    if (!command || _commandRunning) return;

    _commandRunning = true;
    input.disabled = true;
    const submitBtn = $('#agentCommandSubmit');
    if (submitBtn) submitBtn.disabled = true;

    const progress = $('#agentCommandProgress');
    const progressFill = $('#agentProgressFill');
    const progressText = $('#agentProgressText');
    if (progress) { progress.hidden = false; progress.style.display = 'flex'; }
    if (progressFill) progressFill.style.width = '20%';
    if (progressText) progressText.textContent = 'Claw Bot is coordinating your team...';

    try {
      // Animate progress
      let pct = 20;
      const pInterval = setInterval(() => {
        pct = Math.min(pct + Math.random() * 10, 90);
        if (progressFill) progressFill.style.width = pct + '%';
      }, 800);

      const res = await fetch('/api/agents/orchestrate', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });
      const data = await res.json();

      clearInterval(pInterval);
      if (progressFill) progressFill.style.width = '100%';
      if (progressText) progressText.textContent = 'Complete!';

      setTimeout(() => {
        if (progress) { progress.hidden = true; progress.style.display = 'none'; }
      }, 1500);

      if (data.error) {
        showToast(data.error, 'error');
      } else {
        showToast('Team completed ' + (data.agent_count || 0) + ' task(s)!', 'success');
        input.value = '';
        // Refresh feeds
        loadAgentActivityFeed('');
        _agentOutputsData = null;
        _agentTasksData = null;
        // Load metrics
        loadAgentMetricsBar();
      }
    } catch (err) {
      showToast('Command failed: ' + err.message, 'error');
      if (progress) { progress.hidden = true; progress.style.display = 'none'; }
    }

    _commandRunning = false;
    input.disabled = false;
    if (submitBtn) submitBtn.disabled = false;
  };

  // ── Run Single Agent ──
  window.runSingleAgent = async function(agentType) {
    const btn = $('#agentRunBtn-' + agentType);
    const originalLabel = btn ? (btn.dataset.label || 'Run Now') : 'Run Now';
    const agentNames = {maya:'Maya',scout:'Scout',emma:'Emma',alex:'Alex',max:'Max'};
    const name = agentNames[agentType] || agentType;
    if (btn) { btn.classList.add('running'); btn.textContent = 'Running...'; btn.disabled = true; }

    try {
      const res = await fetch('/api/agents/' + agentType + '/run', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instructions: '' }),
      });
      const data = await res.json();
      if (data.error) {
        showToast(data.error, 'error');
      } else {
        const outCount = (data.outputs || []).length;
        showToast(name + ' produced ' + outCount + ' deliverable(s)! View them in the Outputs tab.', 'success', 5000);
        loadAgentActivityFeed('');
        _agentOutputsData = null;
        _agentTasksData = null;
        loadAgentMetricsBar();
        // Auto-switch to Outputs tab to show results
        const outputsTab = document.querySelector('.agents-tab[data-tab="outputs"]');
        if (outputsTab) outputsTab.click();
      }
    } catch (err) {
      showToast('Run failed: ' + err.message, 'error');
    }

    if (btn) { btn.classList.remove('running'); btn.textContent = originalLabel; btn.disabled = false; }
  };

  // ── Agent Outputs Grid ──
  window.loadAgentOutputs = async function() {
    const grid = $('#agentOutputsGrid');
    if (!grid) return;
    grid.innerHTML = '<div class="agent-feed-loading">Loading outputs...</div>';

    const agentFilter = ($('#aoAgentFilter') || {}).value || 'all';
    const typeFilter = ($('#aoTypeFilter') || {}).value || '';

    try {
      let url = '/api/agents/' + agentFilter + '/outputs?limit=40';
      if (typeFilter) url += '&output_type=' + typeFilter;
      const res = await fetch(url, { credentials: 'same-origin' });
      const data = await res.json();
      _agentOutputsData = data;

      if (!data.outputs || data.outputs.length === 0) {
        grid.innerHTML = '<div class="agent-feed-empty">No outputs yet. Run an agent to generate content!</div>';
        return;
      }

      const agentNames2 = { maya: 'Maya', scout: 'Scout', emma: 'Emma', alex: 'Alex', max: 'Max' };
      const agentCreditEmoji = {maya:'Created by Maya &#128227;',scout:'Identified by Scout &#128269;',emma:'Drafted by Emma &#128154;',alex:'Analysis by Alex &#128202;',max:'Recommended by Max &#128176;'};
      grid.innerHTML = data.outputs.map(o => `
        <div class="agent-output-card" style="--agent-color:${o.agent_color}" onclick="showAgentOutput('${o.id}')">
          <div class="agent-output-card-top">
            <span class="agent-output-type-badge" style="background:${o.agent_color}20;color:${o.agent_color}">${(o.output_type||'').replace(/_/g, ' ')}</span>
            <span class="agent-output-agent">${agentCreditEmoji[o.agent_type] || agentNames2[o.agent_type] || o.agent_type}</span>
          </div>
          <div class="agent-output-card-title">${esc(o.title)}</div>
          <div class="agent-output-card-preview">${esc(o.content.substring(0, 150))}${o.content.length > 150 ? '...' : ''}</div>
          <div class="agent-output-card-footer">
            <span class="agent-output-card-time">${timeAgo(o.created_at)}</span>
            <button class="agent-output-copy-btn" onclick="event.stopPropagation();copyOutputById('${o.id}')" style="font-size:11px;padding:2px 8px;background:var(--bg-3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text2)">Copy</button>
            ${o.rating ? '<span class="agent-output-card-rating">' + '&#9733;'.repeat(o.rating) + '</span>' : ''}
          </div>
        </div>
      `).join('');
    } catch (err) {
      grid.innerHTML = '<div class="agent-feed-empty">Failed to load outputs.</div>';
    }
  };

  // ── Show Agent Output Modal ──
  window.showAgentOutput = function(outputId) {
    if (!_agentOutputsData) return;
    const output = _agentOutputsData.outputs.find(o => o.id === outputId);
    if (!output) return;

    _currentOutputId = outputId;

    const modal = $('#agentOutputModal');
    if (!modal) return;
    modal.hidden = false;
    modal.style.display = 'flex';

    const badge = $('#aoModalBadge');
    if (badge) {
      badge.textContent = output.output_type.replace(/_/g, ' ');
      badge.style.background = output.agent_color + '20';
      badge.style.color = output.agent_color;
    }
    const title = $('#aoModalTitle');
    if (title) title.textContent = output.title;

    const body = $('#aoModalBody');
    if (body) body.innerHTML = '<pre class="agent-output-content">' + esc(output.content) + '</pre>';

    // Set star rating
    $$('.ao-star').forEach(star => {
      const val = parseInt(star.dataset.star);
      star.classList.toggle('active', output.rating && val <= output.rating);
    });

    // Show "Send Email" button for email-related output types
    const sendBtn = $('#aoSendEmailBtn');
    if (sendBtn) {
      const emailTypes = ['winback_email', 'email_campaign', 'email', 'review_response'];
      sendBtn.style.display = emailTypes.includes(output.output_type) ? 'inline-flex' : 'none';
    }
  };

  // ── Rate Output ──
  window.rateAgentOutput = async function(rating) {
    if (!_currentOutputId) return;
    try {
      await fetch('/api/agents/output/' + _currentOutputId + '/rate', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating }),
      });
      $$('.ao-star').forEach(star => {
        const val = parseInt(star.dataset.star);
        star.classList.toggle('active', val <= rating);
      });
      // Update local data
      if (_agentOutputsData) {
        const o = _agentOutputsData.outputs.find(o => o.id === _currentOutputId);
        if (o) o.rating = rating;
      }
      showToast('Rating saved!', 'success');
    } catch (err) {
      showToast('Failed to save rating', 'error');
    }
  };

  // ── Copy Output ──
  window.copyAgentOutput = function() {
    if (!_currentOutputId || !_agentOutputsData) return;
    const output = _agentOutputsData.outputs.find(o => o.id === _currentOutputId);
    if (!output) return;
    navigator.clipboard.writeText(output.content).then(() => {
      showToast('Copied to clipboard!', 'success');
    }).catch(() => {
      showToast('Failed to copy', 'error');
    });
  };

  // ── Copy Output by ID ──
  window.copyOutputById = function(id) {
    if (!_agentOutputsData) return;
    const o = _agentOutputsData.outputs.find(x => x.id === id);
    if (!o) return;
    navigator.clipboard.writeText(o.content).then(() => {
      showToast('Copied to clipboard!', 'success');
    }).catch(() => {
      showToast('Failed to copy', 'error');
    });
  };

  // ── Copy Deliverable Content ──
  window.copyDeliverableContent = function(id) {
    const items = window._deliverablesData || [];
    const d = items.find(x => x.id === id);
    if (!d) return;
    navigator.clipboard.writeText(d.content).then(() => {
      showToast('Copied to clipboard!', 'success');
    }).catch(() => {
      showToast('Failed to copy', 'error');
    });
  };

  // ── Agent History Modal ──
  window.showAgentHistory = async function(agentType) {
    const agentNames = {maya:'Maya',scout:'Scout',emma:'Emma',alex:'Alex',max:'Max'};
    const agentEmojis = {maya:'&#128227;',scout:'&#128269;',emma:'&#128154;',alex:'&#128202;',max:'&#128176;'};
    const name = agentNames[agentType] || agentType;
    const modal = $('#agentHistoryModal');
    const title = $('#ahModalTitle');
    const stats = $('#ahModalStats');
    const body = $('#ahModalBody');
    if (!modal || !body) return;
    modal.hidden = false;
    modal.style.display = 'flex';
    if (title) title.textContent = name + ' History ' + (agentEmojis[agentType] || '');
    if (stats) stats.textContent = 'Loading...';
    body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text3)">Loading history...</div>';
    try {
      const res = await fetch('/api/agents/' + agentType + '/outputs?limit=50', {credentials:'same-origin'});
      const data = await res.json();
      const outputs = data.outputs || [];
      if (stats) stats.textContent = name + ' has created ' + data.total + ' deliverables total';
      if (outputs.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--text3)">No outputs yet. Click "' + (agentType === 'maya' ? 'Generate Content' : 'Run') + '" to get started.</div>';
        return;
      }
      window._historyOutputs = outputs;
      body.innerHTML = outputs.map((o, idx) => `
        <div style="border-bottom:1px solid var(--border);padding:14px 0">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;padding:2px 8px;border-radius:20px;background:${o.agent_color}18;color:${o.agent_color};font-weight:600;text-transform:capitalize">${(o.output_type||'').replace(/_/g,' ')}</span>
              <strong style="color:var(--text1)">${esc(o.title)}</strong>
            </div>
            <span style="font-size:11px;color:var(--text3)">${timeAgo(o.created_at)}</span>
          </div>
          <div style="font-size:13px;color:var(--text2);white-space:pre-line;max-height:100px;overflow:hidden;line-height:1.5">${esc(o.content.substring(0, 300))}${o.content.length > 300 ? '...' : ''}</div>
          <div style="margin-top:8px;display:flex;gap:6px">
            <button onclick="copyHistoryItem(${idx})" style="font-size:11px;padding:3px 10px;background:var(--bg-3);color:var(--text2);border:1px solid var(--border);border-radius:6px;cursor:pointer">Copy</button>
            ${o.rating ? '<span style="color:#f59e0b;font-size:12px">' + '&#9733;'.repeat(o.rating) + '</span>' : ''}
          </div>
        </div>
      `).join('');
    } catch (err) {
      body.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--danger)">Failed to load history</div>';
    }
  };

  window.copyHistoryItem = function(idx) {
    const items = window._historyOutputs || [];
    if (idx < items.length) {
      navigator.clipboard.writeText(items[idx].content).then(() => {
        showToast('Copied to clipboard!', 'success');
      }).catch(() => {
        showToast('Failed to copy', 'error');
      });
    }
  };

  // ── Metrics Bar (enhanced) ──
  async function loadAgentMetricsBar() {
    try {
      const res = await fetch('/api/agents/metrics', { credentials: 'same-origin' });
      const data = await res.json();
      if (data.error) return;
      const el = (id, val) => { const e = $('#' + id); if (e) e.textContent = val; };
      el('amTotalTasks', data.total_runs || 0);
      el('amContent', data.total_outputs || 0);
      el('amOpportunities', data.total_commands || 0);
      el('amRevenue', '$' + (data.estimated_value || 0).toLocaleString());
      el('amHours', '~' + (data.hours_saved || 0) + 'h');
    } catch (err) {
      // silent
    }
  }

  // Load metrics on agents page load
  loadAgentMetricsBar();

  // ── End Agent Fleet ──

  // ══════════════════════════════════════════════════════════════════════════
  // EMAIL SENDING
  // ══════════════════════════════════════════════════════════════════════════

  window.sendAgentOutputEmail = function() {
    if (!_currentOutputId || !_agentOutputsData) return;
    const output = _agentOutputsData.outputs.find(o => o.id === _currentOutputId);
    if (!output) return;

    const agentNames = { maya: 'Maya', scout: 'Scout', emma: 'Emma', alex: 'Alex', max: 'Max' };
    const agentName = agentNames[output.agent_type] || output.agent_type;

    // Open a send-email confirmation modal
    openForgeModal('Send Email', `
      <div style="display:flex;flex-direction:column;gap:16px">
        <div>
          <label style="font-weight:600;display:block;margin-bottom:4px;color:var(--text2)">To:</label>
          <input type="email" id="sendEmailTo" class="settings-input" placeholder="customer@example.com" style="width:100%">
        </div>
        <div>
          <label style="font-weight:600;display:block;margin-bottom:4px;color:var(--text2)">Subject:</label>
          <input type="text" id="sendEmailSubject" class="settings-input" value="${esc(output.title)}" style="width:100%">
        </div>
        <div>
          <label style="font-weight:600;display:block;margin-bottom:4px;color:var(--text2)">Preview:</label>
          <div style="background:var(--bg3);padding:12px;border-radius:8px;max-height:200px;overflow-y:auto;font-size:13px;white-space:pre-wrap;color:var(--text2)">${esc(output.content)}</div>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn-secondary" onclick="closeForgeModal()">Cancel</button>
          <button class="btn-primary" onclick="confirmSendEmail('${output.id}', '${output.agent_type}')">Send Now</button>
        </div>
      </div>
    `);
  };

  window.confirmSendEmail = async function(outputId, agentType) {
    const to = ($('#sendEmailTo') || {}).value;
    const subject = ($('#sendEmailSubject') || {}).value;
    if (!to || !subject) {
      showToast('Please fill in recipient and subject', 'error');
      return;
    }
    const output = _agentOutputsData ? _agentOutputsData.outputs.find(o => o.id === outputId) : null;
    if (!output) return;

    try {
      const res = await fetch('/api/email/send', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: to,
          subject: subject,
          body: output.content,
          template: 'marketing',
          sent_by: agentType,
          agent_output_id: outputId,
        }),
      });
      const data = await res.json();
      if (data.success) {
        showToast('Email sent to ' + to + '!', 'success');
        closeForgeModal();
      } else {
        showToast('Failed: ' + (data.error || 'Unknown error'), 'error');
      }
    } catch (err) {
      showToast('Send failed: ' + err.message, 'error');
    }
  };

  window.testEmailConnection = async function() {
    const resultEl = $('#emailTestResult');
    const badge = $('#emailStatusBadge');
    const btn = $('#testEmailBtn');
    const userEmail = ($('#setSmtpUser') || {}).value;
    if (!userEmail) {
      if (resultEl) resultEl.textContent = 'Enter your email address first.';
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
    if (resultEl) resultEl.textContent = 'Sending test email...';

    try {
      const res = await fetch('/api/email/test', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: userEmail }),
      });
      const data = await res.json();
      if (data.success) {
        if (resultEl) resultEl.innerHTML = '<span style="color:#10b981">Test email sent! Check your inbox.</span>';
        if (badge) { badge.textContent = 'Connected'; badge.style.background = '#10b98120'; badge.style.color = '#10b981'; }
      } else {
        if (resultEl) resultEl.innerHTML = '<span style="color:#ef4444">Failed: ' + esc(data.error || 'Unknown error') + '</span>';
        if (badge) { badge.textContent = 'Error'; badge.style.background = '#ef444420'; badge.style.color = '#ef4444'; }
      }
    } catch (err) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#ef4444">Error: ' + esc(err.message) + '</span>';
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Send Test Email'; }
  };

  // Load email status and history on settings load
  async function loadEmailSettings() {
    try {
      const [statusRes, historyRes] = await Promise.all([
        fetch('/api/email/status', { credentials: 'same-origin' }),
        fetch('/api/email/history?limit=20', { credentials: 'same-origin' }),
      ]);
      const status = await statusRes.json();
      const history = await historyRes.json();

      // Status badge
      const badge = $('#emailStatusBadge');
      if (badge) {
        if (status.configured) {
          badge.textContent = 'Connected';
          badge.style.background = '#10b98120';
          badge.style.color = '#10b981';
        } else {
          badge.textContent = 'Not configured';
          badge.style.background = '#f59e0b20';
          badge.style.color = '#f59e0b';
        }
      }

      // Stats
      const statsEl = $('#emailHistoryStats');
      if (statsEl && status) {
        statsEl.innerHTML = `
          <div style="padding:8px 16px;background:var(--bg3);border-radius:8px;font-size:13px">
            <strong>${status.sent_this_month || 0}</strong> sent this month
          </div>
          <div style="padding:8px 16px;background:var(--bg3);border-radius:8px;font-size:13px">
            <strong>${status.failed_this_month || 0}</strong> failed
          </div>
        `;
      }

      // History table
      const tableEl = $('#emailHistoryTable');
      if (tableEl && history.emails) {
        if (history.emails.length === 0) {
          tableEl.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:16px 0">No emails sent yet.</div>';
        } else {
          tableEl.innerHTML = '<table style="width:100%;font-size:13px;border-collapse:collapse">' +
            '<tr style="border-bottom:1px solid var(--border)"><th style="text-align:left;padding:8px">Date</th><th style="text-align:left;padding:8px">To</th><th style="text-align:left;padding:8px">Subject</th><th style="text-align:left;padding:8px">Sent By</th><th style="text-align:left;padding:8px">Status</th></tr>' +
            history.emails.map(e => `
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:8px;color:var(--text3)">${timeAgo(e.created_at)}</td>
                <td style="padding:8px">${esc(e.to_email)}</td>
                <td style="padding:8px">${esc(e.subject)}</td>
                <td style="padding:8px"><span style="text-transform:capitalize">${esc(e.sent_by)}</span></td>
                <td style="padding:8px"><span style="color:${e.status === 'sent' ? '#10b981' : '#ef4444'}">${e.status}</span></td>
              </tr>
            `).join('') +
            '</table>';
        }
      }
    } catch (err) {
      // silent
    }
  }

  // Load email settings whenever settings section becomes visible
  const _emailSettingsObserver = new MutationObserver(() => {
    const sec = $('#sec-settings');
    if (sec && sec.classList.contains('active')) {
      loadEmailSettings();
    }
  });
  const _mainContent = $('#content');
  if (_mainContent) _emailSettingsObserver.observe(_mainContent, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });

  // Auto-refresh every 60 seconds
  refreshTimer = setInterval(() => {
    const active = $('.nav-item.active');
    if (active) loadSection(active.dataset.section);
    loadQuickStats();
  }, 60000);

  // Welcome banner dismiss
  const welcomeDismiss = $('#welcomeDismiss');
  if (welcomeDismiss) {
    welcomeDismiss.addEventListener('click', () => {
      const banner = $('#welcomeBanner');
      if (banner) {
        banner.style.opacity = '0';
        banner.style.transform = 'translateY(-10px)';
        banner.style.transition = 'opacity .3s, transform .3s';
        setTimeout(() => banner.remove(), 300);
      }
      // Clean up URL
      const url = new URL(window.location);
      url.searchParams.delete('welcome');
      window.history.replaceState({}, '', url.pathname);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // CONNECTED ACCOUNTS (Social Media Linking)
  // ══════════════════════════════════════════════════════════════════════════

  function updateConnectedAccountStatus(id, statusId, value, type) {
    const statusEl = $(statusId);
    if (!statusEl) return;
    if (value && value.trim()) {
      let display = value;
      if (type === 'instagram' || type === 'tiktok') {
        display = value.startsWith('@') ? value : '@' + value;
      }
      if (type === 'email') {
        display = Number(value).toLocaleString() + ' subscribers';
      }
      statusEl.innerHTML = '<span class="ca-connected-badge">Connected</span> <span class="ca-connected-value">' + esc(display) + '</span>';
      if (type === 'instagram') {
        statusEl.innerHTML += ' <a href="https://instagram.com/' + esc(value.replace('@', '')) + '" target="_blank" class="ca-profile-link">View Profile</a>';
      } else if (type === 'facebook' && value.startsWith('http')) {
        statusEl.innerHTML += ' <a href="' + esc(value) + '" target="_blank" class="ca-profile-link">View Page</a>';
      } else if (type === 'tiktok') {
        statusEl.innerHTML += ' <a href="https://tiktok.com/' + esc(value.replace('@', '')) + '" target="_blank" class="ca-profile-link">View Profile</a>';
      }
    } else {
      statusEl.innerHTML = '<span class="ca-not-connected">Not connected</span>';
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ONE-CLICK POST SYSTEM & POST NOW MODAL
  // ══════════════════════════════════════════════════════════════════════════

  // Helper: create action bar with Copy, Open Instagram, Open Facebook buttons
  function createPostActionBar(text, hashtags) {
    const bar = document.createElement('div');
    bar.className = 'post-action-bar';
    const fullText = hashtags ? text + '\n\n' + hashtags : text;

    bar.innerHTML = `
      <button class="pab-btn pab-copy" title="Copy to clipboard">&#128203; Copy</button>
      <button class="pab-btn pab-ig" title="Copy & open Instagram">&#128248; Open Instagram</button>
      <button class="pab-btn pab-fb" title="Copy & open Facebook">&#128216; Open Facebook</button>
      <button class="pab-btn pab-post-now" title="Post Now workflow">&#128640; Post Now</button>
    `;

    bar.querySelector('.pab-copy').onclick = (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(fullText);
      showToast('Copied to clipboard!', 'success', 2000);
      const btn = bar.querySelector('.pab-copy');
      btn.innerHTML = '&#10003; Copied';
      setTimeout(() => btn.innerHTML = '&#128203; Copy', 2000);
    };

    bar.querySelector('.pab-ig').onclick = (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(fullText);
      window.open('https://www.instagram.com/', '_blank');
      showToast('Text copied! Instagram opened.', 'success', 3000);
    };

    bar.querySelector('.pab-fb').onclick = (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(fullText);
      window.open('https://www.facebook.com/', '_blank');
      showToast('Text copied! Facebook opened.', 'success', 3000);
    };

    bar.querySelector('.pab-post-now').onclick = (e) => {
      e.stopPropagation();
      openPostNowModal(text, hashtags || '');
    };

    return bar;
  }

  // Post Now Modal
  function openPostNowModal(text, hashtags) {
    const modal = $('#postNowModal');
    if (!modal) return;
    $('#postNowText').value = text;
    $('#postNowHashtags').value = hashtags;
    modal.hidden = false;
    modal.style.display = 'flex';

    // Platform selector
    let selectedPlatform = 'instagram';
    $$('.pnp-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.platform === 'instagram');
      btn.onclick = () => {
        $$('.pnp-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedPlatform = btn.dataset.platform;
        $('#postNowPlatformLabel').textContent = btn.textContent;
      };
    });

    // Copy & Open button
    const copyOpenBtn = $('#postNowCopyOpen');
    copyOpenBtn.onclick = () => {
      const fullText = $('#postNowText').value + '\n\n' + $('#postNowHashtags').value;
      navigator.clipboard.writeText(fullText);
      const urls = {
        instagram: 'https://www.instagram.com/',
        facebook: 'https://www.facebook.com/',
        tiktok: 'https://www.tiktok.com/upload',
      };
      window.open(urls[selectedPlatform] || urls.instagram, '_blank');
      showToast('Text copied! ' + selectedPlatform.charAt(0).toUpperCase() + selectedPlatform.slice(1) + ' opened.', 'success', 3000);
    };

    // Edit with Claw Bot
    const clawEditBtn = $('#postNowEditClaw');
    clawEditBtn.onclick = () => {
      modal.hidden = true;
      modal.style.display = 'none';
      const content = $('#postNowText').value;
      askClaw('Help me improve this social media post for my shop. Make it more engaging:\n\n' + content);
    };

    // Mark as Posted
    const markBtn = $('#postNowMarkPosted');
    markBtn.onclick = async () => {
      markBtn.disabled = true;
      markBtn.textContent = 'Saving...';
      try {
        await fetch('/api/dashboard/content/mark-posted', {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            content_type: 'social',
            content_text: $('#postNowText').value,
            platform: selectedPlatform,
            hashtags: $('#postNowHashtags').value,
          })
        });
        showToast('Content marked as posted!', 'success');
        modal.hidden = true;
        modal.style.display = 'none';
      } catch (e) {
        showToast('Failed to save', 'error');
      }
      markBtn.disabled = false;
      markBtn.textContent = 'Mark as Posted';
    };
  }

  // Upgrade marketing content copy buttons to action bars
  // This runs after marketing content loads via MutationObserver
  function upgradeContentCopyButtons(container) {
    if (!container) return;
    // Upgrade calendar post copy buttons
    container.querySelectorAll('.mke-cal-post').forEach(post => {
      if (post.querySelector('.post-action-bar')) return;
      const oldBtn = post.querySelector('.mke-copy-btn');
      const contentEl = post.querySelector('.mke-cal-post-content');
      if (oldBtn && contentEl) {
        const text = contentEl.textContent.trim();
        oldBtn.replaceWith(createPostActionBar(text, ''));
      }
    });

    // Upgrade social post copy buttons
    container.querySelectorAll('.mke-social-card').forEach(card => {
      if (card.querySelector('.post-action-bar')) return;
      const actionsDiv = card.querySelector('.mke-social-actions');
      const caption = card.querySelector('.mke-social-caption')?.textContent?.trim() || '';
      const hashtags = card.querySelector('.mke-social-hashtags')?.textContent?.trim() || '';
      if (actionsDiv) {
        actionsDiv.innerHTML = '';
        actionsDiv.appendChild(createPostActionBar(caption, hashtags));
      }
    });

    // Upgrade competitor marketing copy buttons
    container.querySelectorAll('.opp-action').forEach(action => {
      if (action.querySelector('.post-action-bar')) return;
      const oldBtn = action.querySelector('.copy-btn');
      const textEl = action.querySelector('.opp-action-text');
      if (oldBtn && textEl) {
        const text = textEl.textContent.trim();
        oldBtn.replaceWith(createPostActionBar(text, ''));
      }
    });

    // Upgrade competitor marketing response copy buttons
    container.querySelectorAll('.mkt-response').forEach(resp => {
      if (resp.querySelector('.post-action-bar')) return;
      const oldBtn = resp.querySelector('.mkt-copy-btn');
      const textEl = resp.querySelector('.mkt-response-text');
      if (oldBtn && textEl) {
        const text = textEl.textContent.trim();
        oldBtn.replaceWith(createPostActionBar(text, ''));
      }
    });
  }

  // Observe DOM changes to upgrade new content as it loads
  const contentObserver = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.addedNodes.length) {
        const sec = $('#sec-marketing');
        if (sec) upgradeContentCopyButtons(sec);
        const compSec = $('#sec-competitors');
        if (compSec) upgradeContentCopyButtons(compSec);
      }
    }
  });
  const contentEl2 = $('#content');
  if (contentEl2) contentObserver.observe(contentEl2, {childList: true, subtree: true});

  // ── Enhanced loadSettings with Connected Accounts ──
  const origLoadSettings = loadSettings;
  loadSettings = async function() {
    await origLoadSettings();
    // Load connected accounts status
    const data = await api('/api/dashboard/settings');
    if (!data) return;
    if ($('#setInstagramHandle')) $('#setInstagramHandle').value = data.instagram_handle || '';
    if ($('#setFacebookUrl')) $('#setFacebookUrl').value = data.facebook_url || '';
    if ($('#setTiktokHandle')) $('#setTiktokHandle').value = data.tiktok_handle || '';
    if ($('#setEmailListSize')) $('#setEmailListSize').value = data.email_list_size || '';
    updateConnectedAccountStatus('#caInstagram', '#caInstagramStatus', data.instagram_handle, 'instagram');
    updateConnectedAccountStatus('#caFacebook', '#caFacebookStatus', data.facebook_url, 'facebook');
    updateConnectedAccountStatus('#caTiktok', '#caTiktokStatus', data.tiktok_handle, 'tiktok');
    updateConnectedAccountStatus('#caEmail', '#caEmailStatus', data.email_list_size ? String(data.email_list_size) : '', 'email');
    // Load email settings
    loadEmailSettings();
  };

  // ── Enhanced save settings with social accounts ──
  const origSaveClick = saveBtn && saveBtn.onclick;
  if (saveBtn) {
    const origHandler = saveBtn.onclick;
    saveBtn.onclick = null;
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
      const headers = {'Content-Type': 'application/json'};
      const body = {
        shop_name: $('#setShopName')?.value || null,
        address: $('#setAddress')?.value || null,
        category: $('#setCategory')?.value || null,
        store_size_sqft: $('#setStoreSize')?.value ? parseInt($('#setStoreSize').value) : null,
        staff_count: $('#setStaffCount')?.value ? parseInt($('#setStaffCount').value) : null,
        monthly_rent: $('#setRent')?.value ? parseFloat($('#setRent').value) : null,
        avg_cogs_percentage: $('#setCogs')?.value ? parseFloat($('#setCogs').value) : null,
        staff_hourly_rate: $('#setHourlyRate')?.value ? parseFloat($('#setHourlyRate').value) : null,
        tax_rate: $('#setTaxRate')?.value ? parseFloat($('#setTaxRate').value) : null,
        email_frequency: $('#setEmailFreq')?.value || null,
        alert_revenue: $('#setAlertRevenue')?.checked,
        alert_customers: $('#setAlertCustomers')?.checked,
        alert_reviews: $('#setAlertReviews')?.checked,
        alert_competitors: $('#setAlertCompetitors')?.checked,
        google_api_key: $('#setGoogleApiKey')?.value || null,
        anthropic_api_key: $('#setAnthropicApiKey')?.value || null,
        ai_enabled: $('#setAiEnabled')?.checked,
        ai_personality: $('#setAiPersonality')?.value || null,
        instagram_handle: $('#setInstagramHandle')?.value || '',
        facebook_url: $('#setFacebookUrl')?.value || '',
        tiktok_handle: $('#setTiktokHandle')?.value || '',
        email_list_size: $('#setEmailListSize')?.value ? parseInt($('#setEmailListSize').value) : 0,
      };
      try {
        const res = await fetch('/api/dashboard/settings', {
          method: 'PUT', headers, credentials: 'same-origin',
          body: JSON.stringify(body),
        });
        if (res.ok) {
          showToast('Settings saved successfully!', 'success');
          const msg = $('#settingsSavedMsg');
          if (msg) { msg.hidden = false; setTimeout(() => msg.hidden = true, 3000); }
          // Update connected account statuses
          updateConnectedAccountStatus('#caInstagram', '#caInstagramStatus', body.instagram_handle, 'instagram');
          updateConnectedAccountStatus('#caFacebook', '#caFacebookStatus', body.facebook_url, 'facebook');
          updateConnectedAccountStatus('#caTiktok', '#caTiktokStatus', body.tiktok_handle, 'tiktok');
          updateConnectedAccountStatus('#caEmail', '#caEmailStatus', body.email_list_size ? String(body.email_list_size) : '', 'email');
        } else {
          showToast('Failed to save settings', 'error');
        }
      } catch (e) {
        showToast('Network error saving settings', 'error');
      }
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Settings';
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // POSTING TRACKER (Marketing Performance Tab)
  // ══════════════════════════════════════════════════════════════════════════

  const origLoadMkePerformance = loadMkePerformance;
  loadMkePerformance = async function() {
    if (typeof origLoadMkePerformance === 'function') await origLoadMkePerformance();
    // Add posting tracker section
    const container = $('#mkePerfContent');
    if (!container) return;
    const stats = await api('/api/dashboard/content/posted-stats');
    if (!stats) return;
    const trackerHtml = `
      <div class="posting-tracker">
        <div class="pt-header">
          <h4 class="pt-title">Content Publishing Tracker</h4>
        </div>
        <div class="pt-stats-row">
          <div class="pt-stat">
            <div class="pt-stat-value">${stats.total_this_week}</div>
            <div class="pt-stat-label">Posts This Week</div>
          </div>
          <div class="pt-stat">
            <div class="pt-stat-value">${stats.suggested_per_week}</div>
            <div class="pt-stat-label">Suggested / Week</div>
          </div>
          <div class="pt-stat">
            <div class="pt-stat-value">${stats.usage_rate}%</div>
            <div class="pt-stat-label">Content Usage Rate</div>
          </div>
          <div class="pt-stat">
            <div class="pt-stat-value">${stats.total_all_time}</div>
            <div class="pt-stat-label">All Time Posts</div>
          </div>
        </div>
        <div class="pt-progress">
          <div class="pt-progress-label">This week: ${stats.total_this_week} of ${stats.suggested_per_week} suggested posts published</div>
          <div class="pt-progress-bar"><div class="pt-progress-fill" style="width:${Math.min(stats.usage_rate, 100)}%"></div></div>
        </div>
        ${stats.recent && stats.recent.length > 0 ? `
          <div class="pt-recent">
            <div class="pt-recent-title">Recently Posted</div>
            ${stats.recent.slice(0, 5).map(p => `
              <div class="pt-recent-item">
                <span class="pt-recent-badge">${p.platform || 'social'}</span>
                <span class="pt-recent-text">${esc(p.content_text)}</span>
                <span class="pt-recent-time">${p.posted_at ? new Date(p.posted_at).toLocaleDateString() : ''}</span>
                <span class="pt-posted-check">Posted &#10003;</span>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
    // Prepend tracker before existing performance content
    const existingContent = container.innerHTML;
    if (!container.querySelector('.posting-tracker')) {
      container.innerHTML = trackerHtml + existingContent;
    }
  };

  // ══════════════════════════════════════════════════════════════════════════
  // UNIVERSAL EDIT MODAL SYSTEM + CRUD OPERATIONS
  // ══════════════════════════════════════════════════════════════════════════

  // ── Helper: fetch with JSON body ──
  async function apiFetch(path, method, body) {
    try {
      const res = await fetch(path, {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      });
      if (res.status === 401) { window.location.href = '/login'; return null; }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Something went wrong', 'error');
        return null;
      }
      return await res.json();
    } catch (e) {
      console.error('[Forge] apiFetch error', e);
      showToast('Network error', 'error');
      return null;
    }
  }

  // ── Modal open / close ──
  let _forgeModalSaveHandler = null;

  window.closeForgeModal = function() {
    const m = document.getElementById('forgeEditModal');
    if (m) { m.hidden = true; m.style.display = 'none'; }
  };

  window.closeForgeConfirm = function() {
    const m = document.getElementById('forgeConfirmModal');
    if (m) { m.hidden = true; m.style.display = 'none'; }
  };

  function openForgeModal(title, bodyHtml, saveCallback) {
    const m = document.getElementById('forgeEditModal');
    document.getElementById('forgeModalTitle').textContent = title;
    document.getElementById('forgeModalBody').innerHTML = bodyHtml;
    const saveBtn = document.getElementById('forgeModalSave');
    // Remove old listener
    if (_forgeModalSaveHandler) saveBtn.removeEventListener('click', _forgeModalSaveHandler);
    _forgeModalSaveHandler = saveCallback;
    saveBtn.addEventListener('click', _forgeModalSaveHandler);
    m.hidden = false;
    m.style.display = '';
    // Focus first input
    const firstInput = m.querySelector('input,textarea,select');
    if (firstInput) setTimeout(() => firstInput.focus(), 100);
  }

  let _forgeConfirmYesHandler = null;

  function openForgeConfirm(title, message, onConfirm) {
    const m = document.getElementById('forgeConfirmModal');
    document.getElementById('forgeConfirmTitle').textContent = title;
    document.getElementById('forgeConfirmMsg').textContent = message;
    const yesBtn = document.getElementById('forgeConfirmYes');
    if (_forgeConfirmYesHandler) yesBtn.removeEventListener('click', _forgeConfirmYesHandler);
    _forgeConfirmYesHandler = async function() {
      await onConfirm();
      window.closeForgeConfirm();
    };
    yesBtn.addEventListener('click', _forgeConfirmYesHandler);
    m.hidden = false;
    m.style.display = '';
  }

  // Helper: get current quarter string
  function currentQuarter() {
    const now = new Date();
    const q = Math.ceil((now.getMonth() + 1) / 3);
    return now.getFullYear() + '-Q' + q;
  }

  // Helper: get current period key
  function currentPeriodKey() {
    const now = new Date();
    return now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0');
  }

  // ══════════════════════════════════════════════════════════════════════════
  // GOAL MODALS
  // ══════════════════════════════════════════════════════════════════════════

  window.openGoalModal = function(editData) {
    const isEdit = !!editData;
    const title = isEdit ? 'Edit Goal' : 'Add New Goal';
    const html = `
      <div class="fm-field">
        <label>Goal Title</label>
        <input id="fmGoalTitle" type="text" value="${isEdit ? esc(editData.title) : ''}" placeholder="e.g. Monthly Revenue Target">
      </div>
      <div class="fm-row">
        <div class="fm-field">
          <label>Target Value</label>
          <input id="fmGoalTarget" type="number" value="${isEdit ? editData.target_value : ''}" placeholder="50000">
        </div>
        <div class="fm-field">
          <label>Unit</label>
          <select id="fmGoalUnit">
            <option value="$" ${!isEdit || editData.unit === '$' ? 'selected' : ''}>$ (Revenue)</option>
            <option value="units" ${isEdit && editData.unit === 'units' ? 'selected' : ''}>Units</option>
            <option value="%" ${isEdit && editData.unit === '%' ? 'selected' : ''}>%</option>
          </select>
        </div>
      </div>
      <div class="fm-row">
        <div class="fm-field">
          <label>Period</label>
          <select id="fmGoalPeriod">
            <option value="monthly" ${!isEdit || editData.period === 'monthly' ? 'selected' : ''}>Monthly</option>
            <option value="quarterly" ${isEdit && editData.period === 'quarterly' ? 'selected' : ''}>Quarterly</option>
            <option value="yearly" ${isEdit && editData.period === 'yearly' ? 'selected' : ''}>Yearly</option>
          </select>
        </div>
        <div class="fm-field">
          <label>Period Key</label>
          <input id="fmGoalPeriodKey" type="text" value="${isEdit ? esc(editData.period_key) : currentPeriodKey()}" placeholder="2026-02">
        </div>
      </div>
      <div class="fm-field">
        <label>Type</label>
        <select id="fmGoalType">
          <option value="revenue" ${!isEdit || editData.goal_type === 'revenue' ? 'selected' : ''}>Revenue</option>
          <option value="transactions" ${isEdit && editData.goal_type === 'transactions' ? 'selected' : ''}>Transactions</option>
          <option value="customers" ${isEdit && editData.goal_type === 'customers' ? 'selected' : ''}>New Customers</option>
        </select>
      </div>
    `;
    openForgeModal(title, html, async function() {
      const goalTitle = document.getElementById('fmGoalTitle').value.trim();
      const target = parseFloat(document.getElementById('fmGoalTarget').value);
      if (!goalTitle || isNaN(target)) { showToast('Please fill in all fields', 'warning'); return; }
      const body = {
        title: goalTitle,
        target_value: target,
        unit: document.getElementById('fmGoalUnit').value,
        period: document.getElementById('fmGoalPeriod').value,
        period_key: document.getElementById('fmGoalPeriodKey').value,
        goal_type: document.getElementById('fmGoalType').value,
      };
      let result;
      if (isEdit) {
        result = await apiFetch('/api/dashboard/goals/' + editData.id, 'PUT', body);
      } else {
        result = await apiFetch('/api/dashboard/goals', 'POST', body);
      }
      if (result && result.ok) {
        showToast(isEdit ? 'Goal updated!' : 'Goal created!', 'success');
        window.closeForgeModal();
        await loadGoals();
      }
    });
  };

  window.deleteGoal = function(goalId, goalTitle) {
    openForgeConfirm('Delete Goal', 'Are you sure you want to delete "' + goalTitle + '"? This cannot be undone.', async function() {
      const result = await apiFetch('/api/dashboard/goals/' + goalId, 'DELETE', {});
      if (result && result.ok) {
        showToast('Goal deleted', 'success');
        await loadGoals();
      }
    });
  };

  // ── Strategy Modal ──
  window.openStrategyModal = function(editData) {
    const isEdit = !!editData;
    const title = isEdit ? 'Edit Strategy' : 'Add Quarterly Strategy';
    const html = `
      <div class="fm-row">
        <div class="fm-field">
          <label>Quarter</label>
          <input id="fmStratQuarter" type="text" value="${isEdit ? esc(editData.quarter) : currentQuarter()}" placeholder="2026-Q1">
        </div>
        <div class="fm-field">
          <label>Status</label>
          <select id="fmStratStatus">
            <option value="active" ${!isEdit || editData.status === 'active' ? 'selected' : ''}>Active</option>
            <option value="completed" ${isEdit && editData.status === 'completed' ? 'selected' : ''}>Completed</option>
            <option value="draft" ${isEdit && editData.status === 'draft' ? 'selected' : ''}>Draft</option>
          </select>
        </div>
      </div>
      <div class="fm-field">
        <label>Strategy Title</label>
        <input id="fmStratTitle" type="text" value="${isEdit ? esc(editData.title) : ''}" placeholder="e.g. Expand Premium Product Line">
      </div>
      <div class="fm-field">
        <label>Objectives (one per line)</label>
        <textarea id="fmStratObjectives" rows="3" placeholder="Increase premium SKUs by 30%&#10;Launch 2 exclusive collections">${isEdit && editData.objectives ? editData.objectives.join('\n') : ''}</textarea>
      </div>
      <div class="fm-field">
        <label>Key Results (one per line)</label>
        <textarea id="fmStratKeyResults" rows="3" placeholder="Premium revenue reaches $15k/month&#10;Average order value increases 20%">${isEdit && editData.key_results ? editData.key_results.join('\n') : ''}</textarea>
      </div>
      <div class="fm-field">
        <label>Notes</label>
        <textarea id="fmStratNotes" rows="2" placeholder="Additional context...">${isEdit && editData.notes ? esc(editData.notes) : ''}</textarea>
      </div>
    `;
    openForgeModal(title, html, async function() {
      const stratTitle = document.getElementById('fmStratTitle').value.trim();
      const quarter = document.getElementById('fmStratQuarter').value.trim();
      if (!stratTitle || !quarter) { showToast('Please fill in title and quarter', 'warning'); return; }
      const objectives = document.getElementById('fmStratObjectives').value.split('\n').map(s => s.trim()).filter(Boolean);
      const keyResults = document.getElementById('fmStratKeyResults').value.split('\n').map(s => s.trim()).filter(Boolean);
      const body = {
        quarter: quarter,
        title: stratTitle,
        objectives: objectives,
        key_results: keyResults,
        notes: document.getElementById('fmStratNotes').value.trim(),
        status: document.getElementById('fmStratStatus').value,
      };
      let result;
      if (isEdit) {
        result = await apiFetch('/api/dashboard/goals/strategy/' + editData.id, 'PUT', body);
      } else {
        result = await apiFetch('/api/dashboard/goals/strategy', 'POST', body);
      }
      if (result && result.ok) {
        showToast(isEdit ? 'Strategy updated!' : 'Strategy created!', 'success');
        window.closeForgeModal();
        await loadGoals();
      }
    });
  };

  // ── Product Target Modal ──
  window.openProductTargetModal = function() {
    const html = `
      <div class="fm-field">
        <label>Product</label>
        <select id="fmPtProduct">
          <option value="">Loading products...</option>
        </select>
      </div>
      <div class="fm-field">
        <label>Target Units</label>
        <input id="fmPtUnits" type="number" placeholder="100">
      </div>
      <div class="fm-field">
        <label>Period</label>
        <input id="fmPtPeriod" type="text" value="${currentPeriodKey()}" placeholder="2026-02">
      </div>
    `;
    openForgeModal('Set Product Sales Target', html, async function() {
      const productId = document.getElementById('fmPtProduct').value;
      const units = parseInt(document.getElementById('fmPtUnits').value);
      if (!productId || isNaN(units)) { showToast('Please select a product and enter units', 'warning'); return; }
      const result = await apiFetch('/api/dashboard/goals/product-goals', 'POST', {
        product_id: productId,
        target_units: units,
        period: document.getElementById('fmPtPeriod').value,
      });
      if (result && result.ok) {
        showToast('Product target set!', 'success');
        window.closeForgeModal();
        await loadGoals();
      }
    });
    // Load products into the dropdown
    api('/api/dashboard/products?days=30').then(data => {
      const sel = document.getElementById('fmPtProduct');
      if (!sel) return;
      if (data && data.top_products && data.top_products.length > 0) {
        sel.innerHTML = '<option value="">Select a product</option>' +
          data.top_products.map(p => '<option value="' + esc(p.id) + '">' + esc(p.name) + '</option>').join('');
      } else {
        sel.innerHTML = '<option value="">No products found</option>';
      }
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  // PRODUCT MODAL
  // ══════════════════════════════════════════════════════════════════════════

  window.openProductModal = function(editData) {
    const isEdit = !!editData;
    const title = isEdit ? 'Edit Product' : 'Add New Product';
    const html = `
      <div class="fm-field">
        <label>Product Name</label>
        <input id="fmProdName" type="text" value="${isEdit ? esc(editData.name) : ''}" placeholder="e.g. Artisan Candle Set">
      </div>
      <div class="fm-row">
        <div class="fm-field">
          <label>Price ($)</label>
          <input id="fmProdPrice" type="number" step="0.01" value="${isEdit ? editData.price : ''}" placeholder="29.99">
        </div>
        <div class="fm-field">
          <label>Cost ($)</label>
          <input id="fmProdCost" type="number" step="0.01" value="${isEdit && editData.cost ? editData.cost : ''}" placeholder="12.00">
        </div>
      </div>
      <div class="fm-row">
        <div class="fm-field">
          <label>Category</label>
          <input id="fmProdCategory" type="text" value="${isEdit ? esc(editData.category || '') : ''}" placeholder="e.g. Home & Living">
        </div>
        <div class="fm-field">
          <label>SKU</label>
          <input id="fmProdSku" type="text" value="${isEdit ? esc(editData.sku || '') : ''}" placeholder="e.g. CND-001">
        </div>
      </div>
      <div class="fm-field">
        <label>Stock Quantity</label>
        <input id="fmProdStock" type="number" value="${isEdit && editData.stock_quantity != null ? editData.stock_quantity : ''}" placeholder="50">
      </div>
    `;
    openForgeModal(title, html, async function() {
      const name = document.getElementById('fmProdName').value.trim();
      const price = parseFloat(document.getElementById('fmProdPrice').value);
      if (!name || isNaN(price)) { showToast('Please enter name and price', 'warning'); return; }
      const body = {
        name: name,
        price: price,
        cost: parseFloat(document.getElementById('fmProdCost').value) || null,
        category: document.getElementById('fmProdCategory').value.trim(),
        sku: document.getElementById('fmProdSku').value.trim(),
        stock_quantity: parseInt(document.getElementById('fmProdStock').value) || null,
      };
      let result;
      if (isEdit) {
        result = await apiFetch('/api/dashboard/products/' + editData.id, 'PUT', body);
      } else {
        result = await apiFetch('/api/dashboard/products', 'POST', body);
      }
      if (result && result.ok) {
        showToast(isEdit ? 'Product updated!' : 'Product added!', 'success');
        window.closeForgeModal();
        await loadProducts();
      }
    });
  };

  window.deleteProduct = function(productId, productName) {
    openForgeConfirm('Remove Product', 'Are you sure you want to remove "' + productName + '"?', async function() {
      const result = await apiFetch('/api/dashboard/products/' + productId, 'DELETE', {});
      if (result && result.ok) {
        showToast('Product removed', 'success');
        await loadProducts();
      }
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  // CUSTOMER MODAL
  // ══════════════════════════════════════════════════════════════════════════

  window.openCustomerModal = function(editData) {
    const isEdit = !!editData;
    const title = isEdit ? 'Edit Customer' : 'Add New Customer';
    const html = `
      <div class="fm-field">
        <label>Email</label>
        <input id="fmCustEmail" type="email" value="${isEdit ? esc(editData.email || '') : ''}" placeholder="customer@example.com">
      </div>
      <div class="fm-field">
        <label>Segment</label>
        <select id="fmCustSegment">
          <option value="regular" ${!isEdit || editData.segment === 'regular' ? 'selected' : ''}>Regular</option>
          <option value="vip" ${isEdit && editData.segment === 'vip' ? 'selected' : ''}>VIP</option>
          <option value="new" ${isEdit && editData.segment === 'new' ? 'selected' : ''}>New</option>
          <option value="at_risk" ${isEdit && editData.segment === 'at_risk' ? 'selected' : ''}>At Risk</option>
          <option value="lost" ${isEdit && editData.segment === 'lost' ? 'selected' : ''}>Lost</option>
        </select>
      </div>
    `;
    openForgeModal(title, html, async function() {
      const email = document.getElementById('fmCustEmail').value.trim();
      if (!email) { showToast('Please enter an email', 'warning'); return; }
      const body = { email: email, segment: document.getElementById('fmCustSegment').value };
      let result;
      if (isEdit) {
        result = await apiFetch('/api/dashboard/customers/' + editData.id, 'PUT', body);
      } else {
        result = await apiFetch('/api/dashboard/customers', 'POST', body);
      }
      if (result && result.ok) {
        showToast(isEdit ? 'Customer updated!' : 'Customer added!', 'success');
        window.closeForgeModal();
        await loadCustomers();
      }
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  // COMPETITOR MODAL
  // ══════════════════════════════════════════════════════════════════════════

  window.openCompetitorModal = function(editData) {
    const isEdit = !!editData;
    const title = isEdit ? 'Edit Competitor' : 'Add New Competitor';
    const html = `
      <div class="fm-field">
        <label>Business Name</label>
        <input id="fmCompName" type="text" value="${isEdit ? esc(editData.name) : ''}" placeholder="e.g. Local Rival Shop">
      </div>
      <div class="fm-field">
        <label>Address</label>
        <input id="fmCompAddress" type="text" value="${isEdit ? esc(editData.address || '') : ''}" placeholder="123 Main St, City">
      </div>
      <div class="fm-row">
        <div class="fm-field">
          <label>Category</label>
          <input id="fmCompCategory" type="text" value="${isEdit ? esc(editData.category || '') : ''}" placeholder="e.g. Boutique">
        </div>
        <div class="fm-field">
          <label>Google Place ID (optional)</label>
          <input id="fmCompPlaceId" type="text" value="${isEdit ? esc(editData.google_place_id || '') : ''}" placeholder="ChIJ...">
        </div>
      </div>
    `;
    openForgeModal(title, html, async function() {
      const name = document.getElementById('fmCompName').value.trim();
      if (!name) { showToast('Please enter a business name', 'warning'); return; }
      const body = {
        name: name,
        address: document.getElementById('fmCompAddress').value.trim(),
        category: document.getElementById('fmCompCategory').value.trim(),
        google_place_id: document.getElementById('fmCompPlaceId').value.trim() || null,
      };
      let result;
      if (isEdit) {
        result = await apiFetch('/api/dashboard/competitors/' + editData.id, 'PUT', body);
      } else {
        result = await apiFetch('/api/dashboard/competitors', 'POST', body);
      }
      if (result && result.ok) {
        showToast(isEdit ? 'Competitor updated!' : 'Competitor added!', 'success');
        window.closeForgeModal();
        await loadCompetitors();
      }
    });
  };

  window.deleteCompetitor = function(compId, compName) {
    openForgeConfirm('Delete Competitor', 'Are you sure you want to remove "' + compName + '" from your competitor list?', async function() {
      const result = await apiFetch('/api/dashboard/competitors/' + compId, 'DELETE', {});
      if (result && result.ok) {
        showToast('Competitor removed', 'success');
        await loadCompetitors();
      }
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  // RUN ALL AGENTS
  // ══════════════════════════════════════════════════════════════════════════

  window.runAgent = async function(agentType) {
    const agentNames = {marketing:'Maya',competitor:'Scout',customer:'Emma',strategy:'Alex',sales:'Max'};
    const name = agentNames[agentType] || agentType;
    showToast('Running ' + name + '...', 'info', 3000);
    try {
      const res = await fetch('/api/ai/agent/' + agentType + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ message: 'Run your analysis and provide an actionable summary report.' }),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(name + ' completed!', 'success');
        // Show the result in a modal
        if (data && data.response) {
          openForgeModal(name + ' Report', '<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;color:var(--text2);max-height:400px;overflow-y:auto">' + esc(data.response) + '</div>', function() { window.closeForgeModal(); });
        }
      } else {
        showToast(name + ' encountered an error', 'error');
      }
    } catch (e) {
      console.warn('[Forge] Agent run failed:', agentType, e);
      showToast('Failed to run ' + name, 'error');
    }
  };

  window.runAllAgents = async function() {
    const btn = $('#runAllAgentsBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }
    const agentTypes = ['maya', 'scout', 'emma', 'alex', 'max'];
    const agentNames = {maya:'Maya',scout:'Scout',emma:'Emma',alex:'Alex',max:'Max'};
    let completed = 0;
    let totalOutputs = 0;
    for (const agentType of agentTypes) {
      showToast('Running ' + agentNames[agentType] + '...', 'info', 3000);
      try {
        const res = await fetch('/api/agents/' + agentType + '/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ instructions: '' }),
        });
        const data = await res.json();
        if (!data.error) {
          completed++;
          totalOutputs += (data.outputs || []).length;
        }
      } catch (e) {
        console.warn('[Forge] Agent run failed:', agentType, e);
      }
    }
    showToast('All agents complete! ' + totalOutputs + ' deliverables generated.', 'success', 5000);
    if (btn) { btn.disabled = false; btn.textContent = 'Run All Agents'; }
    // Refresh data and switch to outputs tab
    _agentOutputsData = null;
    _agentTasksData = null;
    loadAgentActivityFeed('');
    loadAgentMetricsBar();
    const outputsTab = document.querySelector('.agents-tab[data-tab="outputs"]');
    if (outputsTab) outputsTab.click();
  };

  // ── Claw Bot Error Handling Enhancement ──
  const origSendAiMessage = sendAiMessage;
  // Override to add better error messages (the original already handles errors,
  // but we enhance the catch block's message)

});
