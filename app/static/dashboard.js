/* =============================================
   RetailIQ Dashboard — Client-Side Logic
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
  const stored = localStorage.getItem('retailiq-theme');
  if (stored) html.setAttribute('data-theme', stored);

  $('#themeToggle').addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('retailiq-theme', next);
    updateChartColors();
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
      $(`#sec-${section}`).classList.add('active');
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
    await fetch('/api/auth/logout', {method: 'POST'});
    localStorage.removeItem('retailiq_token');
    window.location.href = '/login';
  });

  // ── API helper ──
  async function api(path) {
    const token = localStorage.getItem('retailiq_token');
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    try {
      const res = await fetch(path, {headers, credentials: 'same-origin'});
      if (res.status === 401) {
        console.warn('[RetailIQ] 401 on', path, '— redirecting to login');
        window.location.href = '/login';
        return null;
      }
      if (!res.ok) {
        console.warn('[RetailIQ] API error', res.status, 'on', path);
        return null;
      }
      return res.json();
    } catch (err) {
      console.error('[RetailIQ] Network error on', path, err);
      return null;
    }
  }

  async function apiPost(path) {
    const token = localStorage.getItem('retailiq_token');
    const headers = {'Content-Type': 'application/json'};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(path, {method: 'POST', headers, credentials: 'same-origin'});
    if (!res.ok) return null;
    return res.json();
  }

  async function apiPatch(path) {
    const token = localStorage.getItem('retailiq_token');
    const headers = {'Content-Type': 'application/json'};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(path, {method: 'PATCH', headers, credentials: 'same-origin'});
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

  async function loadSection(section) {
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
    } catch (err) {
      console.error('[RetailIQ] Error loading section:', section, err);
      hideRefresh();
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

    // Detect empty shop (truly no data — no customers and no revenue at all)
    const isEmpty = summary && summary.has_data === false;

    lastUpdateTime = Date.now();
    updateLastUpdated();

    if (summary) {
      animateValue($('#kpiRevenue'), summary.revenue_today, 800, '$');
      animateValue($('#kpiTransactions'), summary.transactions_today, 800);
      animateValue($('#kpiAov'), summary.avg_order_value, 600, '$');
      animateValue($('#kpiRepeat'), summary.repeat_customer_rate, 600, '', '%');

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
    tbody.innerHTML = data.top_products.map((p, i) =>
      `<tr><td>${i + 1}</td><td>${esc(p.name)}</td><td>${esc(p.category || '-')}</td><td>${fmt(p.revenue)}</td><td>${fmtInt(p.units_sold)}</td><td>${fmt(p.avg_price)}</td><td>${p.margin != null ? p.margin + '%' : '-'}</td></tr>`
    ).join('');

    loadProductRecommendations();
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
    tbody.innerHTML = data.top_customers.map((c, i) =>
      `<tr><td>${i + 1}</td><td>Customer ${c.id.slice(0, 8)}</td><td>${c.visit_count}</td><td>${fmt(c.total_spent)}</td><td>${c.last_seen ? c.last_seen.split('T')[0] : '-'}</td></tr>`
    ).join('');
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
      compDataLoaded[tab] = true;
    } catch (err) {
      console.error('[RetailIQ] Error loading competitor tab:', tab, err);
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
            ${!c.is_own ? `<span class="threat-badge ${(c.threat_level || '').toLowerCase()}">${esc(c.threat_level)}</span>` : ''}
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
      if (goals.goals.length === 0) {
        grid.innerHTML = '<div class="empty-state"><p>No active goals. Set goals to track your progress!</p></div>';
      } else {
        grid.innerHTML = goals.goals.map(g => {
          const valueStr = g.unit === '$' ? fmt(g.current_value) : fmtInt(g.current_value);
          const targetStr = g.unit === '$' ? fmt(g.target_value) : fmtInt(g.target_value);
          return `
            <div class="goal-card">
              <div class="goal-card-header">
                <div class="goal-card-title">${esc(g.title)}</div>
                <span class="goal-pacing ${g.pacing}">${g.pacing === 'on_track' ? 'On Track' : g.pacing === 'behind' ? 'Behind' : 'At Risk'}</span>
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
      if (strategy.strategies.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No quarterly strategies set yet.</p></div>';
      } else {
        container.innerHTML = strategy.strategies.map(s => `
          <div class="strategy-card">
            <div class="strategy-quarter">${esc(s.quarter)} <span class="strategy-status ${s.status}">${s.status}</span></div>
            <div class="strategy-title">${esc(s.title)}</div>
            ${s.objectives && s.objectives.length > 0 ? `
              <div class="strategy-section">
                <div class="strategy-section-label">Objectives</div>
                <ul class="strategy-list">${s.objectives.map(o => `<li>${esc(o)}</li>`).join('')}</ul>
              </div>
            ` : ''}
            ${s.key_results && s.key_results.length > 0 ? `
              <div class="strategy-section">
                <div class="strategy-section-label">Key Results</div>
                <ul class="strategy-list">${s.key_results.map(kr => `<li>${esc(kr)}</li>`).join('')}</ul>
              </div>
            ` : ''}
            ${s.notes ? `<div class="strategy-section"><div class="strategy-section-label">Notes</div><p style="font-size:13px;color:var(--text2);line-height:1.6;">${esc(s.notes)}</p></div>` : ''}
          </div>
        `).join('');
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
      mkeDataLoaded[tab] = true;
    } catch (err) {
      console.error('[RetailIQ] Error loading marketing tab:', tab, err);
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
    animateValue($('#brfRevenue'), 0, n.yesterday_revenue, 800, fmt);
    animateValue($('#brfTransactions'), 0, n.yesterday_transactions, 800, fmtInt);
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

  function animateValue(el, start, end, duration, formatter) {
    if (!el) return;
    const range = end - start;
    if (range === 0) { el.textContent = formatter(end); return; }
    const startTime = performance.now();
    function step(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
      const current = start + range * eased;
      el.textContent = formatter(current);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

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
        <td><span style="color:${c.days_since_visit > 60 ? 'var(--danger)' : 'var(--warning)};font-weight:600">${c.days_since_visit}d</span></td>
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
  // NOTIFICATION BELL
  // ══════════════════════════════════════════════════════════════════════════

  const notifBellBtn = $('#notifBellBtn');
  const notifDropdown = $('#notifDropdown');
  const notifBellWrap = $('#notifBellWrap');

  if (notifBellBtn && notifDropdown) {
    notifBellBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const isOpen = notifDropdown.classList.contains('show');
      if (isOpen) {
        notifDropdown.classList.remove('show');
      } else {
        notifDropdown.classList.add('show');
        loadNotifications();
      }
    });

    document.addEventListener('click', (e) => {
      // Close dropdown if clicking outside the entire bell area
      if (notifBellWrap && !notifBellWrap.contains(e.target)) {
        notifDropdown.classList.remove('show');
      }
    });

    // Mark all read
    const markAllBtn = $('#notifMarkAll');
    if (markAllBtn) {
      markAllBtn.addEventListener('click', async () => {
        markAllBtn.textContent = 'Marking...';
        await apiPost('/api/dashboard/notifications/read-all');
        markAllBtn.textContent = 'Done!';
        const badge = $('#notifBadge');
        if (badge) { badge.textContent = '0'; badge.hidden = true; }
        $$('.notif-item.unread', notifDropdown).forEach(el => el.classList.remove('unread'));
        // Also update sidebar badge
        const sidebarBadge = $('#alertBadge');
        if (sidebarBadge) { sidebarBadge.textContent = '0'; sidebarBadge.hidden = true; }
        setTimeout(() => markAllBtn.textContent = 'Mark All Read', 2000);
      });
    }

    // View All link
    const viewAllLink = $('#notifViewAll');
    if (viewAllLink) {
      viewAllLink.addEventListener('click', (e) => {
        e.preventDefault();
        notifDropdown.classList.remove('show');
        const navItem = $(`.nav-item[data-section="alerts"]`);
        if (navItem) navItem.click();
      });
    }

    // Load initial badge count
    loadNotifBadge();
  }

  async function loadNotifBadge() {
    const data = await api('/api/dashboard/notifications');
    if (data) {
      const badge = $('#notifBadge');
      if (badge) {
        if (data.unread_count > 0) {
          badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
          badge.hidden = false;
        } else {
          badge.hidden = true;
        }
      }
    }
  }

  async function loadNotifications() {
    const body = $('#notifDropdownBody');
    body.innerHTML = '<div class="ai-loading">Loading...</div>';
    const data = await api('/api/dashboard/notifications');
    if (!data || !data.notifications || data.notifications.length === 0) {
      body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text3);font-size:13px;">No notifications</div>';
      return;
    }

    body.innerHTML = data.notifications.map(n => `
      <div class="notif-item ${n.is_read ? '' : 'unread'}">
        <div class="notif-item-icon">${n.icon}</div>
        <div class="notif-item-content">
          <div class="notif-item-title">${esc(n.title)}</div>
          <div class="notif-item-msg">${esc(n.message)}</div>
        </div>
        <div class="notif-item-time">${esc(n.time_ago)}</div>
      </div>
    `).join('');

    // Update badge
    const badge = $('#notifBadge');
    if (badge) {
      if (data.unread_count > 0) {
        badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // END NOTIFICATION BELL
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
    'b': 'briefing', 'o': 'overview', 's': 'sales', 'p': 'products',
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
  console.log('[RetailIQ] Init section:', initSection, '| Sub:', window.__SUB_SECTION || 'none');
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
      console.warn('[RetailIQ] Quick stats error:', e);
    }
  }
  loadQuickStats();

  // ── Export helper ──
  async function exportCSV(type) {
    const token = localStorage.getItem('retailiq_token');
    const headers = {'Content-Type': 'application/json'};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    try {
      const res = await fetch('/api/dashboard/export', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
        body: JSON.stringify({export_type: type}),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `retailiq_${type}_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('[RetailIQ] Export error:', e);
    }
  }

  // Attach export buttons (they use onclick="exportCSV('type')")
  window.exportCSV = exportCSV;

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

});
