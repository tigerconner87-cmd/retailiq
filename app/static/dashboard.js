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
      $('#pageTitle').textContent = item.textContent.trim();
      $('#sidebar').classList.remove('open');
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
    const res = await fetch(path, {headers, credentials: 'same-origin'});
    if (res.status === 401) {
      window.location.href = '/login';
      return null;
    }
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
    if (section === 'overview') await loadOverview();
    else if (section === 'sales') await loadSales();
    else if (section === 'products') await loadProducts();
    else if (section === 'customers') await loadCustomers();
    else if (section === 'competitors') await loadCompetitors();
    else if (section === 'reviews') await loadReviews();
    else if (section === 'alerts') await loadAlerts();
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

    if (summary) {
      $('#kpiRevenue').textContent = fmt(summary.revenue_today);
      $('#kpiTransactions').textContent = fmtInt(summary.transactions_today);
      $('#kpiAov').textContent = fmt(summary.avg_order_value);
      $('#kpiRepeat').textContent = summary.repeat_customer_rate + '%';

      const dod = summary.revenue_change_dod;
      const dodEl = $('#kpiRevenueDod');
      dodEl.textContent = (dod >= 0 ? '+' : '') + dod + '% vs yesterday';
      dodEl.className = 'kpi-change ' + (dod >= 0 ? 'up' : 'down');
    }

    if (sales && sales.daily) renderRevenueChart(sales.daily);
    if (peakHours) renderHeatmap(peakHours);

    if (products && products.top_products) {
      const tbody = $('#productsTableOverview tbody');
      tbody.innerHTML = products.top_products.slice(0, 5).map(p =>
        `<tr><td>${esc(p.name)}</td><td>${fmt(p.revenue)}</td><td>${fmtInt(p.units_sold)}</td></tr>`
      ).join('');
    }

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

    renderAiActions(aiActions);
  }

  async function loadSales() {
    showRefresh();
    const data = await api('/api/dashboard/sales?days=60');
    hideRefresh();
    if (!data) return;

    renderSalesChartFull(data.daily);

    const wTbody = $('#weeklyTable tbody');
    wTbody.innerHTML = data.weekly_totals.map(w =>
      `<tr><td>${w.week_start}</td><td>${fmt(w.revenue)}</td><td>${fmtInt(w.transactions)}</td></tr>`
    ).join('');

    const mTbody = $('#monthlyTable tbody');
    mTbody.innerHTML = data.monthly_totals.map(m =>
      `<tr><td>${m.month}</td><td>${fmt(m.revenue)}</td><td>${fmtInt(m.transactions)}</td></tr>`
    ).join('');
  }

  async function loadProducts() {
    showRefresh();
    const data = await api('/api/dashboard/products?days=30');
    hideRefresh();
    if (!data) return;

    const tbody = $('#productsTableFull tbody');
    tbody.innerHTML = data.top_products.map((p, i) =>
      `<tr><td>${i + 1}</td><td>${esc(p.name)}</td><td>${esc(p.category || '-')}</td><td>${fmt(p.revenue)}</td><td>${fmtInt(p.units_sold)}</td><td>${fmt(p.avg_price)}</td><td>${p.margin != null ? p.margin + '%' : '-'}</td></tr>`
    ).join('');
  }

  async function loadCustomers() {
    showRefresh();
    const data = await api('/api/dashboard/customers');
    hideRefresh();
    if (!data) return;

    $('#custTotal').textContent = fmtInt(data.total_customers);
    $('#custRepeat').textContent = data.repeat_rate + '%';
    $('#custNew').textContent = fmtInt(data.new_customers_30d);
    $('#custAvgRev').textContent = fmt(data.avg_revenue_per_customer);

    const tbody = $('#topCustomersTable tbody');
    tbody.innerHTML = data.top_customers.map((c, i) =>
      `<tr><td>${i + 1}</td><td>Customer ${c.id.slice(0, 8)}</td><td>${c.visit_count}</td><td>${fmt(c.total_spent)}</td><td>${c.last_seen ? c.last_seen.split('T')[0] : '-'}</td></tr>`
    ).join('');
  }

  async function loadCompetitors() {
    showRefresh();
    const data = await api('/api/dashboard/competitors');
    hideRefresh();
    if (!data) return;

    $('#ownRating').textContent = data.own_rating ? data.own_rating + ' / 5' : '--';
    $('#ownReviewCount').textContent = fmtInt(data.own_review_count);

    const tbody = $('#competitorTable tbody');
    tbody.innerHTML = data.competitors.map(c => {
      const change = c.rating_change;
      const changeStr = change != null ? `<span class="${change >= 0 ? 'kpi-change up' : 'kpi-change down'}">${change >= 0 ? '+' : ''}${change}</span>` : '-';
      return `<tr><td>${esc(c.name)}</td><td>${esc(c.address || '-')}</td><td>${c.rating || '-'}</td><td>${fmtInt(c.review_count)}</td><td>${changeStr}</td></tr>`;
    }).join('');
  }

  async function loadReviews() {
    showRefresh();
    const data = await api('/api/dashboard/reviews');
    hideRefresh();
    if (!data) return;

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

    let html = '<div class="heatmap-header">';
    hours.forEach(h => html += `<span>${h > 12 ? (h-12)+'p' : h+'a'}</span>`);
    html += '</div>';

    days.forEach((day, di) => {
      html += `<div class="heatmap-row"><span class="heatmap-label">${day}</span>`;
      hours.forEach(h => {
        const val = grid[`${di}-${h}`] || 0;
        const intensity = maxVal > 0 ? val / maxVal : 0;
        const bg = `rgba(99,102,241,${0.05 + intensity * 0.85})`;
        html += `<div class="heatmap-cell" style="background:${bg}" data-tip="${day} ${h}:00 — ${fmt(val)}"></div>`;
      });
      html += '</div>';
    });

    container.innerHTML = html;
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

  // ── Init ──
  loadOverview();

  // Auto-refresh every 60 seconds
  refreshTimer = setInterval(() => {
    const active = $('.nav-item.active');
    if (active) loadSection(active.dataset.section);
  }, 60000);

});
