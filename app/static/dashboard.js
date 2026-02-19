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
      if (section === 'overview') await loadOverview();
      else if (section === 'sales') await loadSales();
      else if (section === 'products') await loadProducts();
      else if (section === 'customers') await loadCustomers();
      else if (section === 'competitors') await loadCompetitors();
      else if (section === 'goals') await loadGoals();
      else if (section === 'reviews') await loadReviews();
      else if (section === 'alerts') await loadAlerts();
    } catch (err) {
      console.error('[RetailIQ] Error loading section:', section, err);
      hideRefresh();
    }
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

  // Auto-refresh every 60 seconds
  refreshTimer = setInterval(() => {
    const active = $('.nav-item.active');
    if (active) loadSection(active.dataset.section);
  }, 60000);

});
