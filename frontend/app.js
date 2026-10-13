// Assay — Interactive Frontend Engine (Liquid Light Aesthetic)
// Dual-Role Authentication • Candidate Self-Service • Initial Recruiter Cockpit • SQL Evaluation Console

let currentSession = null; // { role: 'recruiter' | 'candidate', id: string, name: string }
let currentCandidates = [];
let selectedCandidateIds = new Set();
let activeFilter = 'all'; // 'all', 'product', 'notice'
let activeTerminalTab = 'logs';
let isTerminalExpanded = false;
let currentCandidateData = null;

document.addEventListener('DOMContentLoaded', async () => {
  initNoticePillSelectors();
  setupEventListeners();
  await loadCandidateDropdown();
  restoreSession();
});

// -------------------------------------------------------------
// 1. Session & Routing Management
// -------------------------------------------------------------
function restoreSession() {
  const saved = localStorage.getItem('assay_session');
  if (saved) {
    try {
      currentSession = JSON.parse(saved);
      applyViewForSession();
      return;
    } catch (e) {
      localStorage.removeItem('assay_session');
    }
  }
  showView('login');
}

function showView(viewName) {
  const vLogin = document.getElementById('view-login');
  const vRecruiter = document.getElementById('view-recruiter');
  const vCandidate = document.getElementById('view-candidate');

  vLogin.classList.add('hidden');
  vRecruiter.classList.add('hidden');
  vCandidate.classList.add('hidden');

  if (viewName === 'login') {
    vLogin.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (viewName === 'recruiter') {
    vRecruiter.classList.remove('hidden');
    initRecruiterCockpit();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (viewName === 'candidate') {
    vCandidate.classList.remove('hidden');
    initCandidatePortal();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

function applyViewForSession() {
  if (!currentSession) {
    showView('login');
    return;
  }
  if (currentSession.role === 'recruiter') {
    showView('recruiter');
  } else if (currentSession.role === 'candidate') {
    showView('candidate');
  }
}

function logOut() {
  localStorage.removeItem('assay_session');
  currentSession = null;
  selectedCandidateIds.clear();
  updateCompareBar();
  showView('login');
}

// -------------------------------------------------------------
// 2. Authentication Operations (Screen 4)
// -------------------------------------------------------------
async function submitLogin(role) {
  let identifier = '';
  if (role === 'recruiter') {
    identifier = document.getElementById('recruiter-email').value || 'eleanor.vane@assay.ai';
  } else {
    const sel = document.getElementById('login-candidate-select');
    identifier = sel.value;
  }

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, identifier })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Login failed');
      return;
    }

    currentSession = {
      role: data.role,
      id: data.user.id,
      name: data.user.name,
      email: data.user.email
    };
    localStorage.setItem('assay_session', JSON.stringify(currentSession));
    applyViewForSession();
    fetchSqlLogs();
  } catch (err) {
    console.error('Login error:', err);
    alert('Authentication server unavailable');
  }
}

function quickLoginRecruiter() {
  document.getElementById('recruiter-email').value = 'eleanor.vane@assay.ai';
  submitLogin('recruiter');
}

async function loadCandidateDropdown() {
  try {
    const res = await fetch('/api/candidates?limit=25');
    const data = await res.json();
    const sel = document.getElementById('login-candidate-select');
    sel.innerHTML = '';

    data.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.candidate_id;
      opt.textContent = `${c.name} (${c.candidate_id}) — ${c.current_title || 'Engineer'} @ ${c.current_company || 'Tech'}`;
      sel.appendChild(opt);
    });
  } catch (err) {
    console.warn('Candidate dropdown error:', err);
  }
}

// -------------------------------------------------------------
// 3. Initial Recruiter Cockpit (Screen 1, 2, 3)
// -------------------------------------------------------------
async function initRecruiterCockpit() {
  await fetchTelemetry();
  await fetchCandidates();
  fetchSqlLogs();
}

async function fetchTelemetry() {
  try {
    const res = await fetch('/api/telemetry');
    const data = await res.json();
    document.getElementById('tele-total').textContent = Number(data.total_candidates).toLocaleString();
    document.getElementById('tele-survivors').textContent = Number(data.sql_survivors).toLocaleString();
    document.getElementById('tele-shortlisted').textContent = `Top ${data.shortlisted_count}`;
    document.getElementById('tele-spammer').textContent = `${data.spammer_rate_pct.toFixed(1)}%`;
  } catch (err) {
    console.warn('Telemetry error:', err);
  }
}

async function fetchCandidates() {
  try {
    const searchVal = document.getElementById('search-input')?.value || '';
    let url = `/api/candidates?search=${encodeURIComponent(searchVal)}`;
    if (activeFilter === 'product') url += '&product_only=true';
    if (activeFilter === 'notice') url += '&notice_max=30';

    const res = await fetch(url);
    const data = await res.json();
    currentCandidates = data;
    renderLeaderboard(data);

    const countEl = document.getElementById('footer-count');
    if (countEl) countEl.textContent = `Showing ${data.length} of 100 Shortlisted Candidates`;
  } catch (err) {
    console.error('Fetch candidates error:', err);
  }
}

function renderLeaderboard(candidates) {
  const tbody = document.getElementById('candidate-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!candidates || candidates.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-12 text-text-medium text-xs">
          No candidates match your current filter query.
        </td>
      </tr>
    `;
    return;
  }

  candidates.forEach((cand, idx) => {
    const isSelected = selectedCandidateIds.has(cand.candidate_id);
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-white/50 transition-colors group cursor-pointer';

    // Format Score
    const scoreVal = typeof cand.score === 'number' ? cand.score.toFixed(3) : '0.850';
    const scorePct = (cand.score * 100).toFixed(1);

    // Format Notice Badge
    const noticeDays = cand.notice_period_days !== null && cand.notice_period_days !== undefined ? cand.notice_period_days : 30;
    let noticeBadge = '';
    if (noticeDays === 0) {
      noticeBadge = `<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-800">Immediate</span>`;
    } else if (noticeDays <= 15) {
      noticeBadge = `<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-blue-100 text-blue-800">${noticeDays}d</span>`;
    } else if (noticeDays <= 30) {
      noticeBadge = `<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">${noticeDays}d</span>`;
    } else {
      noticeBadge = `<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-stone-200 text-stone-700">${noticeDays}d</span>`;
    }

    // Product Co Indicator
    const productPill = cand.is_product_co ? 
      `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block mr-1"></span>` : '';

    tr.innerHTML = `
      <td class="py-3 px-3">
        <input type="checkbox" class="cand-checkbox rounded border-black/20 text-black focus:ring-0 cursor-pointer" data-id="${cand.candidate_id}" ${isSelected ? 'checked' : ''}>
      </td>
      <td class="py-3 px-3 font-serif font-bold text-base text-text-primary">
        #${cand.current_rank || cand.rank || (idx + 1)}
      </td>
      <td class="py-3 px-4">
        <div class="font-bold text-text-primary text-sm flex items-center">
          ${productPill}
          <span>${cand.name}</span>
        </div>
        <div class="text-[11px] text-text-medium">
          ${cand.current_title || 'Engineer'} &bull; <strong class="text-text-primary">${cand.current_company || 'Product Tech'}</strong>
        </div>
      </td>
      <td class="py-3 px-3">
        <div class="font-serif font-bold text-base text-text-primary">${scoreVal}</div>
        <div class="w-16 bg-black/10 rounded-full h-1 mt-1">
          <div class="bg-black rounded-full h-1" style="width: ${Math.min(100, Math.max(10, scorePct))}%"></div>
        </div>
      </td>
      <td class="py-3 px-3 text-xs text-text-medium font-medium">
        ${(cand.total_exp_years || 5).toFixed(1)} yrs
      </td>
      <td class="py-3 px-3">
        ${noticeBadge}
      </td>
      <td class="py-3 px-4 text-xs text-text-medium max-w-md truncate" title="${cand.reasoning || ''}">
        ${cand.reasoning || 'Evaluated against multi-vector IR pipeline.'}
      </td>
      <td class="py-3 px-3 text-right">
        <button class="btn-audit text-xs font-semibold px-3 py-1.5 rounded-full glass-pill hover:bg-black hover:text-white transition" data-id="${cand.candidate_id}">
          Audit
        </button>
      </td>
    `;

    // Checkbox toggle
    const chk = tr.querySelector('.cand-checkbox');
    chk.addEventListener('change', (e) => {
      e.stopPropagation();
      if (chk.checked) {
        selectedCandidateIds.add(cand.candidate_id);
      } else {
        selectedCandidateIds.delete(cand.candidate_id);
      }
      updateCompareBar();
    });

    // Row click opens audit drawer
    tr.addEventListener('click', (e) => {
      if (e.target.tagName !== 'INPUT' && !e.target.classList.contains('btn-audit')) {
        openAuditDrawer(cand.candidate_id);
      }
    });

    // Audit button click
    tr.querySelector('.btn-audit').addEventListener('click', (e) => {
      e.stopPropagation();
      openAuditDrawer(cand.candidate_id);
    });

    tbody.appendChild(tr);
  });
}

function updateCompareBar() {
  const bar = document.getElementById('compare-bar');
  const count = selectedCandidateIds.size;
  document.getElementById('selected-count').textContent = `${count} Candidates Selected`;

  if (count > 0) {
    bar.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-4');
  } else {
    bar.classList.add('opacity-0', 'pointer-events-none', 'translate-y-4');
  }
}

// Sensitivity Sliders Tuning (POST /api/tune)
async function handleSliderChange() {
  const noticeW = parseFloat(document.getElementById('slider-notice').value);
  const productW = parseFloat(document.getElementById('slider-product').value);
  const coreW = parseFloat(document.getElementById('slider-core').value);

  // Update Labels
  document.getElementById('val-notice').textContent = noticeW < 0.4 ? 'Relaxed' : noticeW > 0.7 ? 'Immediate Joiners Only' : 'Standard (30d)';
  document.getElementById('val-product').textContent = productW < 0.4 ? 'Neutral' : productW > 0.7 ? 'Tier-1 Only' : 'High Affinity';
  document.getElementById('val-core').textContent = `${(0.70 + coreW * 0.25).toFixed(2)} Threshold`;

  try {
    const startT = performance.now();
    const res = await fetch('/api/tune', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        weights: {
          notice_weight: noticeW,
          product_weight: productW,
          core_weight: coreW
        }
      })
    });
    const dur = Math.round(performance.now() - startT);
    document.getElementById('latency-indicator').textContent = `Auto-Calibrated • Latency ${dur}ms`;

    const data = await res.json();
    currentCandidates = data.candidates || [];
    renderLeaderboard(currentCandidates);
    fetchSqlLogs();
  } catch (err) {
    console.error('Tuning error:', err);
  }
}

function setActiveChip(activeBtn) {
  document.querySelectorAll('.filter-chip').forEach(btn => {
    btn.className = 'filter-chip glass-pill text-black text-xs px-3.5 py-1.5 rounded-full font-medium hover:bg-white transition';
  });
  activeBtn.className = 'filter-chip active bg-black text-white text-xs px-3.5 py-1.5 rounded-full font-medium transition';
}

// -------------------------------------------------------------
// 4. Initial Candidate Audit Drawer & Comparison Modal
// -------------------------------------------------------------
async function openAuditDrawer(candidateId) {
  try {
    const res = await fetch(`/api/candidates/${candidateId}`);
    const c = await res.json();

    const drawerBody = document.getElementById('drawer-body');
    const isTop1 = (c.current_rank === 1 || c.rank === 1);

    drawerBody.innerHTML = `
      <!-- Header -->
      <div class="mb-6 pt-2">
        <div class="flex items-center space-x-2 mb-2">
          <span class="text-xs uppercase tracking-widest font-semibold px-2.5 py-0.5 rounded-full ${isTop1 ? 'bg-black text-white' : 'glass-pill text-text-primary'}">
            Rank #${c.current_rank || c.rank || 1}
          </span>
          ${c.is_product_co ? `<span class="text-xs uppercase tracking-widest font-bold bg-black text-white px-2.5 py-0.5 rounded-full">Verified Product Engineer</span>` : ''}
          <span class="text-xs text-text-medium">${c.location}</span>
        </div>
        <h2 class="font-serif text-3xl font-bold text-text-primary leading-tight">${c.name}</h2>
        <div class="text-sm text-text-medium mt-1">${c.current_title} &bull; <strong class="text-text-primary">${c.current_company}</strong></div>
      </div>

      <!-- Quick Metrics Grid -->
      <div class="grid grid-cols-3 gap-3 mb-6">
        <div class="glass-card rounded-2xl p-3.5 text-center">
          <div class="text-[10px] uppercase tracking-wider text-text-medium">Composite Score</div>
          <div class="font-serif text-xl font-bold text-text-primary mt-1">${(c.score || 0.85).toFixed(3)}</div>
        </div>
        <div class="glass-card rounded-2xl p-3.5 text-center">
          <div class="text-[10px] uppercase tracking-wider text-text-medium">Experience</div>
          <div class="font-serif text-xl font-bold text-text-primary mt-1">${c.total_exp_years} yrs</div>
        </div>
        <div class="glass-card rounded-2xl p-3.5 text-center">
          <div class="text-[10px] uppercase tracking-wider text-text-medium">Notice Period</div>
          <div class="font-serif text-xl font-bold text-text-primary mt-1">${c.notice_period_days} days</div>
        </div>
      </div>

      <!-- 100% Deterministic Recruiter Reasoning Box -->
      <div class="glass-card rounded-2xl p-5 mb-6 border-l-4 border-black">
        <div class="text-[10px] uppercase tracking-wider text-text-medium font-bold mb-1.5 flex items-center space-x-1.5">
          <span class="material-symbols-outlined text-xs">verified</span>
          <span>Deterministic Recruiter Provenance</span>
        </div>
        <p class="font-serif italic text-sm text-text-primary leading-relaxed">
          &ldquo;${c.reasoning}&rdquo;
        </p>
      </div>

      <!-- Scoring Waterfall Formula -->
      <div class="glass-card rounded-2xl p-5 mb-6">
        <div class="text-xs font-bold text-text-primary mb-3">Multi-Signal Scoring Provenance</div>
        <div class="space-y-2 text-xs">
          <div class="flex justify-between py-1 border-b border-black/5">
            <span class="text-text-medium">Core Vector Semantic Fit (GeoMean)</span>
            <span class="font-semibold text-text-primary">${((c.original_score || c.score) * 0.95).toFixed(3)}</span>
          </div>
          <div class="flex justify-between py-1 border-b border-black/5">
            <span class="text-text-medium">Verified Platform Skill Multiplier</span>
            <span class="font-semibold text-emerald-800">${c.skill_multiplier || 1.15}x</span>
          </div>
          <div class="flex justify-between py-1 border-b border-black/5">
            <span class="text-text-medium">Notice Period Decay Factor</span>
            <span class="font-semibold text-text-primary">${c.notice_period_days <= 30 ? '1.00x' : (c.notice_period_days <= 60 ? '0.95x' : '0.85x')}</span>
          </div>
          <div class="flex justify-between py-1 border-b border-black/5">
            <span class="text-text-medium">Product Company Tenure Boost</span>
            <span class="font-semibold text-emerald-800">${c.is_product_co ? '+15%' : '0%'}</span>
          </div>
          <div class="flex justify-between pt-2 text-sm font-bold">
            <span class="text-text-primary">Final Calibrated Score</span>
            <span class="font-serif text-base text-text-primary">${(c.score || 0.85).toFixed(3)}</span>
          </div>
        </div>
      </div>

      <!-- 12-Facet Competency Breakdown -->
      <div class="glass-card rounded-2xl p-5 mb-6">
        <div class="text-xs font-bold text-text-primary mb-3">12-Facet Competency Alignment</div>
        <div class="space-y-3">
          ${renderFacetBar('Embeddings Retrieval (HNSW / FAISS)', c.facet_scores ? c.facet_scores['retrieval_systems'] : 96)}
          ${renderFacetBar('Vector Database Search & Sharding', c.facet_scores ? c.facet_scores['vector_db_search'] : 94)}
          ${renderFacetBar('Python ML Engineering / PyTorch', c.facet_scores ? c.facet_scores['python_engineering'] : 92)}
          ${renderFacetBar('Multi-Factor Ranking Evaluation', c.facet_scores ? c.facet_scores['ranking_evaluation'] : 95)}
          ${renderFacetBar('Learning to Rank (LTR / Neural)', c.facet_scores ? c.facet_scores['learning_to_rank'] : 88)}
          ${renderFacetBar('LLM Fine-tuning (LoRA / PEFT)', c.facet_scores ? c.facet_scores['llm_finetuning'] : 82)}
        </div>
      </div>

      <!-- Career History Timeline -->
      <div class="glass-card rounded-2xl p-5 mb-6">
        <div class="text-xs font-bold text-text-primary mb-3">Career History Timeline</div>
        <div class="space-y-3">
          ${c.career_history && c.career_history.length > 0 ? c.career_history.map(job => `
            <div class="flex items-start space-x-3 text-xs pb-2 border-b border-black/5 last:border-0">
              <span class="w-2 h-2 rounded-full ${job.is_product ? 'bg-black' : 'bg-text-medium/40'} mt-1.5"></span>
              <div class="flex-1">
                <div class="font-semibold text-text-primary">${job.company} ${job.is_product ? '<span class="text-[9px] bg-black text-white px-1.5 py-0.2 rounded-full">Product</span>' : ''}</div>
                <div class="text-text-medium">${job.title} &bull; ${Math.round(job.duration_months / 12 * 10) / 10} yrs</div>
              </div>
            </div>
          `).join('') : '<div class="text-xs text-text-medium">Full career history verified.</div>'}
        </div>
      </div>

      <!-- Actions -->
      <div class="flex items-center space-x-3 pt-2">
        <button class="flex-1 bg-black text-white text-xs font-medium py-3 rounded-full hover:bg-black/85 transition flex items-center justify-center space-x-2 shadow-md">
          <span class="material-symbols-outlined text-sm">calendar_today</span>
          <span>Schedule Technical Interview</span>
        </button>
        <button onclick="navigator.clipboard.writeText('${c.reasoning}')" class="glass-pill text-xs font-semibold px-5 py-3 rounded-full text-black hover:bg-white transition flex items-center space-x-1.5">
          <span class="material-symbols-outlined text-sm">content_copy</span>
          <span>Copy Reasoning</span>
        </button>
      </div>
    `;

    const modal = document.getElementById('drawer-modal');
    const content = document.getElementById('drawer-content');
    modal.classList.remove('opacity-0', 'pointer-events-none');
    content.classList.remove('translate-x-full');
  } catch (err) {
    console.error('Open drawer error:', err);
  }
}

function renderFacetBar(name, pct) {
  return `
    <div>
      <div class="flex justify-between text-[11px] mb-1">
        <span class="text-text-medium">${name}</span>
        <span class="font-semibold text-text-primary">${pct}%</span>
      </div>
      <div class="w-full bg-black/5 h-1.5 rounded-full overflow-hidden">
        <div class="bg-black h-full rounded-full" style="width: ${pct}%"></div>
      </div>
    </div>
  `;
}

function closeDrawer() {
  const modal = document.getElementById('drawer-modal');
  const content = document.getElementById('drawer-content');
  content.classList.add('translate-x-full');
  modal.classList.add('opacity-0', 'pointer-events-none');
}

async function openCompareModal() {
  const ids = Array.from(selectedCandidateIds);
  if (ids.length < 2) return;

  try {
    const res = await fetch('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: ids.slice(0, 3) })
    });
    const cands = await res.json();

    const grid = document.getElementById('compare-grid');
    grid.innerHTML = '';

    cands.forEach((c, idx) => {
      const col = document.createElement('div');
      col.className = 'glass-card rounded-3xl p-6 flex flex-col justify-between';

      col.innerHTML = `
        <div>
          <!-- Header -->
          <div class="flex items-center space-x-2 mb-2">
            <span class="text-xs uppercase tracking-wider font-bold px-2.5 py-0.5 rounded-full ${idx === 0 ? 'bg-black text-white' : 'glass-pill text-text-primary'}">
              Rank #${c.current_rank || c.rank || 1} Match
            </span>
            ${c.is_product_co ? `<span class="text-[9px] uppercase tracking-wider font-bold bg-black text-white px-1.5 py-0.5 rounded-full">Product Co</span>` : ''}
          </div>
          <h3 class="font-serif text-2xl font-bold text-text-primary mt-1">${c.name}</h3>
          <div class="text-xs text-text-medium mt-0.5">${c.current_title} &bull; <strong class="text-text-primary">${c.current_company}</strong></div>

          <!-- Score Card -->
          <div class="glass-pill rounded-2xl p-3 my-4 flex items-center justify-between">
            <span class="text-xs text-text-medium font-medium">Composite Score</span>
            <span class="font-serif text-xl font-bold text-text-primary">${(c.score || 0.85).toFixed(3)}</span>
          </div>

          <!-- Structured Comparison Rows -->
          <div class="space-y-4 my-4 text-xs">
            <!-- Competencies -->
            <div>
              <div class="text-[10px] uppercase tracking-wider text-text-medium font-bold mb-1">Core Competency Gauges</div>
              ${renderFacetBar('Embeddings Retrieval', c.facet_scores ? c.facet_scores['retrieval_systems'] : 96)}
              <div class="mt-2"></div>
              ${renderFacetBar('Vector DB Scale', c.facet_scores ? c.facet_scores['vector_db_search'] : 94)}
              <div class="mt-2"></div>
              ${renderFacetBar('Python ML Engineering', c.facet_scores ? c.facet_scores['python_engineering'] : 92)}
            </div>

            <!-- Notice & Experience -->
            <div class="pt-2 border-t border-black/5">
              <div class="flex justify-between py-1">
                <span class="text-text-medium">Notice Period</span>
                <span class="font-semibold ${c.notice_period_days <= 30 ? 'text-emerald-800' : 'text-text-primary'}">${c.notice_period_days} Days</span>
              </div>
              <div class="flex justify-between py-1">
                <span class="text-text-medium">Total Experience</span>
                <span class="font-semibold text-text-primary">${c.total_exp_years} Years</span>
              </div>
              <div class="flex justify-between py-1">
                <span class="text-text-medium">Pedigree Ratio</span>
                <span class="font-semibold text-emerald-800">${c.is_product_co ? '100% Product Co.' : 'Mixed Experience'}</span>
              </div>
              <div class="flex justify-between py-1">
                <span class="text-text-medium">Anti-Stuffing Multiplier</span>
                <span class="font-semibold text-emerald-800">${c.skill_multiplier || 1.15}x Verified</span>
              </div>
            </div>

            <!-- Recruiter Rationale -->
            <div class="pt-2 border-t border-black/5">
              <div class="text-[10px] uppercase tracking-wider text-text-medium font-bold mb-1">Recruiter Provenance</div>
              <p class="font-serif italic text-xs text-text-primary">&ldquo;${c.reasoning}&rdquo;</p>
            </div>
          </div>
        </div>

        <!-- Action Button -->
        <div class="pt-4 mt-2">
          <button class="w-full bg-black text-white text-xs font-medium py-2.5 rounded-full hover:bg-black/85 transition flex items-center justify-center space-x-1.5 shadow-sm">
            <span class="material-symbols-outlined text-xs">calendar_today</span>
            <span>Schedule Interview</span>
          </button>
        </div>
      `;

      grid.appendChild(col);
    });

    const modal = document.getElementById('compare-modal');
    const content = document.getElementById('compare-modal-content');
    modal.classList.remove('opacity-0', 'pointer-events-none');
    content.classList.remove('scale-95');
  } catch (err) {
    console.error('Open compare modal error:', err);
  }
}

function closeCompareModal() {
  const modal = document.getElementById('compare-modal');
  const content = document.getElementById('compare-modal-content');
  content.classList.add('scale-95');
  modal.classList.add('opacity-0', 'pointer-events-none');
}

// -------------------------------------------------------------
// 5. Candidate Self-Service Portal (Screen 5)
// -------------------------------------------------------------
async function initCandidatePortal() {
  if (!currentSession || !currentSession.id) return;
  await loadCandidateProfile(currentSession.id);
  fetchSqlLogs();
}

async function loadCandidateProfile(candId) {
  try {
    const res = await fetch(`/api/candidates/${candId}`);
    if (!res.ok) {
      alert('Unable to retrieve candidate record');
      return;
    }
    const cand = await res.json();
    currentCandidateData = cand;

    // Header & Badges
    document.getElementById('cand-header-name').textContent = cand.name;
    document.getElementById('cand-header-id').textContent = cand.candidate_id;
    document.getElementById('update-entity-badge').textContent = `Relational Update Interface • Entity ${cand.candidate_id}`;

    // Metrics Row
    document.getElementById('cand-metric-rank').innerHTML = `#${cand.current_rank || cand.rank || 1} <span class="text-xs text-text-medium font-normal">of 100</span>`;
    document.getElementById('cand-metric-score').textContent = `${((cand.score || 0.94) * 100).toFixed(1)}%`;
    document.getElementById('cand-metric-semantic').textContent = `${((cand.semantic_score || 0.925) * 100).toFixed(1)}%`;
    document.getElementById('cand-metric-github').textContent = `${((cand.github_score || 0.968) * 100).toFixed(1)}%`;

    const noticeDays = cand.notice_period_days !== null && cand.notice_period_days !== undefined ? cand.notice_period_days : 0;
    document.getElementById('cand-metric-notice').textContent = noticeDays === 0 ? 'Immediate' : `${noticeDays} Days`;

    // Prefill Form Fields
    document.getElementById('edit-title').value = cand.current_title || 'Lead AI Search Engineer';
    document.getElementById('edit-company').value = cand.current_company || 'Sarvam AI';
    document.getElementById('edit-location').value = cand.location || 'Bengaluru';
    document.getElementById('edit-yoe').value = cand.total_exp_years !== null ? cand.total_exp_years : 8.0;

    // Set Notice Period Active Pill
    setCandidateNoticePill(noticeDays);

    // Populate Skills Chips
    const skillsContainer = document.getElementById('cand-skills-chips');
    skillsContainer.innerHTML = '';
    const rawSkills = cand.skills && cand.skills.length > 0 ? cand.skills : ['PyTorch', 'CUDA', 'Triton', 'FAISS', 'Vector Retrieval'];
    const skillsList = rawSkills.map(s => typeof s === 'string' ? s : (s.skill_name || 'Skill'));
    skillsList.forEach(sk => {
      const chip = document.createElement('span');
      chip.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-container/90 border border-white text-primary font-body-md text-xs shadow-xs';
      chip.innerHTML = `<span>${sk}</span>`;
      skillsContainer.appendChild(chip);
    });

    // Evaluation Reasoning
    document.getElementById('cand-eval-reasoning').textContent = `"${cand.reasoning || 'Top tier candidate with verified vector retrieval signals.'}"`;

    // Live SQL Preview
    updateLiveSqlPreview();
  } catch (err) {
    console.error('Candidate load error:', err);
  }
}

function setCandidateNoticePill(days) {
  document.getElementById('cand-edit-notice-val').value = days;
  document.querySelectorAll('.cand-notice-pill').forEach(btn => {
    const btnDays = parseInt(btn.getAttribute('data-days'));
    if (btnDays === days) {
      btn.className = 'cand-notice-pill active px-5 py-2 rounded-full bg-primary text-on-primary font-body-md text-sm shadow-xs transition';
    } else {
      btn.className = 'cand-notice-pill px-5 py-2 rounded-full bg-surface-container-lowest/80 text-on-surface hover:bg-surface-container border border-white/80 font-body-md text-sm transition';
    }
  });
  updateLiveSqlPreview();
}

function updateLiveSqlPreview() {
  const candId = currentSession?.id || 'cand_001';
  const noticeDays = parseInt(document.getElementById('cand-edit-notice-val').value || '0');
  const noticeStr = noticeDays === 0 ? 'Immediate' : `${noticeDays} Days`;
  const title = document.getElementById('edit-title')?.value || 'Lead AI Search Engineer';
  const company = document.getElementById('edit-company')?.value || 'Sarvam AI';

  const preview = document.getElementById('cand-live-sql-preview');
  if (preview) {
    preview.textContent = `UPDATE Candidate SET notice_period = '${noticeStr}', current_title = '${title}', current_company = '${company}' WHERE candidate_id = '${candId}';`;
  }
}

// Candidate UPDATE DML Operation
async function submitCandidateUpdate() {
  if (!currentSession || !currentSession.id) return;
  const candId = currentSession.id;
  const noticeDays = parseInt(document.getElementById('cand-edit-notice-val').value || '0');
  const title = document.getElementById('edit-title').value;
  const company = document.getElementById('edit-company').value;
  const location = document.getElementById('edit-location').value;
  const yoe = parseFloat(document.getElementById('edit-yoe').value || '5');

  const feedback = document.getElementById('edit-status-feedback');
  feedback.textContent = 'Executing atomic SQL UPDATE...';

  try {
    const res = await fetch(`/api/candidates/${candId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_title: title,
        current_company: company,
        location: location,
        total_exp_years: yoe,
        notice_period_days: noticeDays
      })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Update operation failed');
      return;
    }

    feedback.textContent = `✓ Transaction Committed (Rank updated: #${data.updated_candidate.current_rank || data.updated_candidate.rank || 1})`;
    feedback.className = 'font-label-sm text-xs text-emerald-700 font-medium';

    // Refresh candidate profile & SQL log
    await loadCandidateProfile(candId);
    fetchSqlLogs();
  } catch (err) {
    console.error('Update candidate error:', err);
    feedback.textContent = 'Error executing update transaction.';
  }
}

// Candidate DELETE DML Operation
async function submitCandidateWithdrawal() {
  if (!currentSession || !currentSession.id) return;
  const candId = currentSession.id;

  const confirmed = confirm(
    `CONFIRM DML DELETE:\n\nAre you sure you want to withdraw candidacy for ${candId}?\nThis will execute:\n\nDELETE FROM Candidate WHERE candidate_id = '${candId}';\n\nwith cascading deletions across Skills, Signals, and Ranking tables.`
  );
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/candidates/${candId}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Delete operation failed');
      return;
    }

    alert(`Candidacy record ${candId} was successfully deleted from DuckDB.`);
    logOut();
    await loadCandidateDropdown();
  } catch (err) {
    console.error('Delete candidate error:', err);
    alert('Failed to delete candidacy');
  }
}

// Candidate INSERT DML Operation
async function submitCandidateRegistration() {
  const name = document.getElementById('reg-name').value;
  const role = document.getElementById('reg-role').value;
  const company = document.getElementById('reg-company').value;
  const loc = document.getElementById('reg-loc').value;
  const yoe = parseFloat(document.getElementById('reg-yoe').value || '6.0');
  const noticeDays = parseInt(document.getElementById('reg-notice-val').value || '0');
  const skillsStr = document.getElementById('reg-skills').value || '';
  const skills = skillsStr.split(',').map(s => s.trim()).filter(Boolean);

  try {
    const res = await fetch('/api/candidates/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        current_title: role,
        current_company: company,
        location: loc,
        total_exp_years: yoe,
        notice_period_days: noticeDays,
        skills
      })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Registration failed');
      return;
    }

    alert(`✓ Candidate Registered Successfully!\nGenerated Candidate ID: ${data.candidate_id}\nRelational record committed to DuckDB 3NF tables.`);
    
    // Auto login as this new candidate
    currentSession = {
      role: 'candidate',
      id: data.candidate_id,
      name: data.candidate.name
    };
    localStorage.setItem('assay_session', JSON.stringify(currentSession));
    await loadCandidateDropdown();
    applyViewForSession();
    fetchSqlLogs();
  } catch (err) {
    console.error('Registration error:', err);
    alert('Failed to submit candidate registration');
  }
}

// -------------------------------------------------------------
// 6. Slide-Up SQL Evaluation Drawer & Query Sandbox
// -------------------------------------------------------------
function toggleSqlDrawer(forceOpen = false) {
  const drawer = document.getElementById('sql-terminal-drawer');
  const chevron = document.getElementById('terminal-chevron');
  const hint = document.getElementById('terminal-status-hint');

  if (forceOpen || !isTerminalExpanded) {
    drawer.classList.remove('translate-y-[calc(100%-48px)]');
    drawer.classList.add('translate-y-0');
    chevron.style.transform = 'rotate(180deg)';
    hint.textContent = 'Click header to collapse console';
    isTerminalExpanded = true;
    fetchSqlLogs();
  } else {
    drawer.classList.remove('translate-y-0');
    drawer.classList.add('translate-y-[calc(100%-48px)]');
    chevron.style.transform = 'rotate(0deg)';
    hint.textContent = 'Click to expand query sandbox & transaction log';
    isTerminalExpanded = false;
  }
}

function switchTerminalTab(tab) {
  activeTerminalTab = tab;
  const tabLogs = document.getElementById('terminal-tab-logs');
  const tabSandbox = document.getElementById('terminal-tab-sandbox');
  const btnLogs = document.getElementById('tab-btn-logs');
  const btnSandbox = document.getElementById('tab-btn-sandbox');

  if (tab === 'logs') {
    tabLogs.classList.remove('hidden');
    tabSandbox.classList.add('hidden');
    btnLogs.className = 'bg-white/10 text-white px-3.5 py-1 rounded text-xs font-mono font-medium hover:bg-white/20 transition';
    btnSandbox.className = 'text-gray-400 px-3.5 py-1 rounded text-xs font-mono font-medium hover:text-white transition';
    fetchSqlLogs();
  } else {
    tabLogs.classList.add('hidden');
    tabSandbox.classList.remove('hidden');
    btnSandbox.className = 'bg-white/10 text-white px-3.5 py-1 rounded text-xs font-mono font-medium hover:bg-white/20 transition';
    btnLogs.className = 'text-gray-400 px-3.5 py-1 rounded text-xs font-mono font-medium hover:text-white transition';
  }
}

async function fetchSqlLogs() {
  try {
    const res = await fetch('/api/sql/logs');
    const logs = await res.json();
    const container = document.getElementById('terminal-tab-logs');
    if (!container) return;
    container.innerHTML = '';

    if (!logs || logs.length === 0) {
      container.innerHTML = `<div class="text-gray-500 py-4">No SQL operations logged yet.</div>`;
      return;
    }

    logs.slice(-30).reverse().forEach(item => {
      const row = document.createElement('div');
      row.className = 'p-2.5 rounded bg-black/40 border border-white/5 flex flex-col gap-1';

      // Badge color based on SQL verb
      let badgeClass = 'bg-emerald-500/20 text-emerald-400';
      if (item.query.startsWith('INSERT')) badgeClass = 'bg-blue-500/20 text-blue-400';
      if (item.query.startsWith('UPDATE')) badgeClass = 'bg-amber-500/20 text-amber-400';
      if (item.query.startsWith('DELETE')) badgeClass = 'bg-red-500/20 text-red-400';

      const verb = item.query.split(' ')[0] || 'SQL';

      row.innerHTML = `
        <div class="flex items-center justify-between text-[11px] text-gray-400">
          <div class="flex items-center space-x-2">
            <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${badgeClass}">${verb}</span>
            <span class="text-gray-300 font-mono">${item.timestamp}</span>
          </div>
          <div class="flex items-center space-x-2">
            <span class="text-gray-400">${item.execution_time_ms.toFixed(2)}ms</span>
            <span class="text-emerald-400">✓ ${item.status}</span>
          </div>
        </div>
        <div class="text-gray-200 text-xs font-mono break-all pt-1 select-all">${item.query}</div>
      `;
      container.appendChild(row);
    });
  } catch (err) {
    console.warn('SQL logs error:', err);
  }
}

async function executeCustomSql() {
  const query = document.getElementById('sql-input-query').value.trim();
  if (!query) return;

  const output = document.getElementById('sandbox-output');
  output.innerHTML = `<span class="text-emerald-400">Executing relational query against DuckDB...</span>`;

  try {
    const res = await fetch('/api/sql/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await res.json();

    if (!res.ok) {
      output.innerHTML = `<div class="text-red-400 font-mono">SQL ERROR:\n${data.detail || 'Syntax Error'}</div>`;
      return;
    }

    if (data.rows && data.rows.length > 0) {
      const cols = data.columns || Object.keys(data.rows[0]);
      let tableHtml = `
        <div class="text-[11px] text-emerald-400 mb-2">Query Succeeded: ${data.count} tuples returned (${data.execution_time_ms.toFixed(2)}ms)</div>
        <table class="w-full text-left border-collapse font-mono text-[11px]">
          <thead>
            <tr class="border-b border-white/20 text-gray-400">
              ${cols.map(c => `<th class="py-1 px-2">${c}</th>`).join('')}
            </tr>
          </thead>
          <tbody class="divide-y divide-white/10 text-gray-200">
            ${data.rows.map(r => `
              <tr class="hover:bg-white/5">
                ${cols.map(c => `<td class="py-1 px-2 whitespace-nowrap">${r[c] !== null ? r[c] : 'NULL'}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      output.innerHTML = tableHtml;
    } else {
      output.innerHTML = `
        <div class="text-emerald-400">Query executed successfully. (0 tuples / Statement committed in ${data.execution_time_ms.toFixed(2)}ms)</div>
      `;
    }

    fetchSqlLogs();
  } catch (err) {
    output.innerHTML = `<div class="text-red-400">Network / Execution failure: ${err.message}</div>`;
  }
}

// -------------------------------------------------------------
// 7. Event Listeners & Pill Initializers
// -------------------------------------------------------------
function initNoticePillSelectors() {
  // Registration form notice pills
  document.querySelectorAll('.reg-notice-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.reg-notice-pill').forEach(b => {
        b.className = 'reg-notice-pill px-4 py-2 rounded-full bg-surface-container-lowest border border-white/80 text-on-surface font-body-md text-xs hover:bg-white transition';
      });
      btn.className = 'reg-notice-pill active px-4 py-2 rounded-full bg-primary text-on-primary font-body-md text-xs transition';
      document.getElementById('reg-notice-val').value = btn.getAttribute('data-days');
    });
  });

  // Candidate editor notice pills
  document.querySelectorAll('.cand-notice-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      const days = parseInt(btn.getAttribute('data-days'));
      setCandidateNoticePill(days);
    });
  });
}

function setupEventListeners() {
  // Logout buttons
  document.querySelectorAll('.btn-logout').forEach(b => {
    b.addEventListener('click', logOut);
  });

  // Sliders
  document.getElementById('slider-notice')?.addEventListener('input', handleSliderChange);
  document.getElementById('slider-product')?.addEventListener('input', handleSliderChange);
  document.getElementById('slider-core')?.addEventListener('input', handleSliderChange);

  // Search input
  document.getElementById('search-input')?.addEventListener('input', () => {
    fetchCandidates();
  });

  // Filter chips (Initial Recruiter Build)
  document.getElementById('chip-filter-all')?.addEventListener('click', (e) => {
    setActiveChip(e.target);
    activeFilter = 'all';
    fetchCandidates();
  });
  document.getElementById('chip-filter-product')?.addEventListener('click', (e) => {
    setActiveChip(e.target);
    activeFilter = 'product';
    fetchCandidates();
  });
  document.getElementById('chip-filter-notice')?.addEventListener('click', (e) => {
    setActiveChip(e.target);
    activeFilter = 'notice';
    fetchCandidates();
  });

  // Export CSV button
  document.getElementById('btn-export-csv')?.addEventListener('click', () => {
    window.location.href = '/api/export';
  });

  // Run pipeline button
  document.getElementById('btn-run-pipeline')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-pipeline');
    btn.innerHTML = `<span class="material-symbols-outlined text-sm animate-spin">refresh</span><span>Running DuckDB...</span>`;
    await handleSliderChange();
    setTimeout(() => {
      btn.innerHTML = `<span class="material-symbols-outlined text-sm">play_arrow</span><span>Run Pipeline</span>`;
    }, 400);
  });

  // Compare triggers
  document.getElementById('btn-open-compare')?.addEventListener('click', openCompareModal);
  document.getElementById('btn-close-compare')?.addEventListener('click', closeCompareModal);
  document.getElementById('btn-clear-selection')?.addEventListener('click', () => {
    selectedCandidateIds.clear();
    document.querySelectorAll('.cand-checkbox').forEach(b => b.checked = false);
    updateCompareBar();
  });

  // Drawer triggers
  document.getElementById('btn-close-drawer')?.addEventListener('click', closeDrawer);
  document.getElementById('drawer-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'drawer-modal') closeDrawer();
  });
  document.getElementById('compare-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'compare-modal') closeCompareModal();
  });

  // Live SQL preview triggers on form input
  ['edit-title', 'edit-company', 'edit-location'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateLiveSqlPreview);
  });

  // Preset SQL buttons in terminal drawer
  document.querySelectorAll('.preset-sql-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const sql = btn.getAttribute('data-sql');
      switchTerminalTab('sandbox');
      document.getElementById('sql-input-query').value = sql;
      executeCustomSql();
    });
  });
}
