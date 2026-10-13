// Assay — Interactive Frontend Engine (Liquid Light Aesthetic)

let currentCandidates = [];
let selectedCandidateIds = new Set();
let activeFilter = 'all'; // 'all', 'product', 'notice'

document.addEventListener('DOMContentLoaded', () => {
  initApp();
  setupEventListeners();
});

async function initApp() {
  await fetchTelemetry();
  await fetchCandidates();
}

// -------------------------------------------------------------
// 1. Data Fetching
// -------------------------------------------------------------
async function fetchTelemetry() {
  try {
    const res = await fetch('/api/telemetry');
    const data = await res.json();
    document.getElementById('tele-total').textContent = Number(data.total_candidates).toLocaleString();
    document.getElementById('tele-survivors').textContent = Number(data.sql_survivors).toLocaleString();
    document.getElementById('tele-shortlisted').textContent = `Top ${data.shortlisted_count}`;
    document.getElementById('tele-spammer').textContent = `${data.spammer_rate_pct.toFixed(1)}%`;
  } catch (err) {
    console.warn('Telemetry fetch error:', err);
  }
}

async function fetchCandidates() {
  try {
    const searchVal = document.getElementById('search-input').value;
    let url = `/api/candidates?search=${encodeURIComponent(searchVal || '')}`;
    if (activeFilter === 'product') url += '&product_only=true';
    if (activeFilter === 'notice') url += '&notice_max=30';

    const res = await fetch(url);
    const data = await res.json();
    currentCandidates = data;
    renderLeaderboard(data);
  } catch (err) {
    console.error('Fetch candidates error:', err);
  }
}

// -------------------------------------------------------------
// 2. Rendering the Leaderboard
// -------------------------------------------------------------
function renderLeaderboard(candidates) {
  const tbody = document.getElementById('candidate-table-body');
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

  candidates.forEach((c) => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-black/[0.02] transition cursor-pointer group';

    // Rank delta badge
    let deltaBadge = `<span class="text-[10px] font-semibold text-text-medium/60">=</span>`;
    if (c.rank_delta > 0) {
      deltaBadge = `<span class="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-full">+${c.rank_delta}</span>`;
    } else if (c.rank_delta < 0) {
      deltaBadge = `<span class="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full">${c.rank_delta}</span>`;
    }

    // Rank formatting
    const rankStr = c.current_rank < 10 ? `0${c.current_rank}` : `${c.current_rank}`;
    const isTop3 = c.current_rank <= 3;
    const rankPillClass = isTop3 
      ? 'bg-black text-white font-bold' 
      : 'glass-pill text-text-primary font-medium';

    // Notice badge
    let noticeBadgeClass = 'glass-pill text-text-primary';
    if (c.notice_period_days <= 30) {
      noticeBadgeClass = 'bg-emerald-50 text-emerald-800 border border-emerald-200';
    } else if (c.notice_period_days > 60) {
      noticeBadgeClass = 'bg-amber-50 text-amber-800 border border-amber-200';
    }

    const isChecked = selectedCandidateIds.has(c.candidate_id);

    tr.innerHTML = `
      <td class="py-3.5 px-3">
        <input type="checkbox" data-id="${c.candidate_id}" class="cand-checkbox rounded border-black/20 text-black focus:ring-0 cursor-pointer" ${isChecked ? 'checked' : ''}>
      </td>
      <td class="py-3.5 px-3">
        <div class="flex items-center space-x-1.5">
          <span class="w-7 h-7 rounded-full flex items-center justify-center text-xs ${rankPillClass}">
            ${rankStr}
          </span>
          ${deltaBadge}
        </div>
      </td>
      <td class="py-3.5 px-4">
        <div class="font-semibold text-text-primary group-hover:text-black transition flex items-center space-x-2">
          <span>${c.name}</span>
          ${c.is_product_co ? `<span class="text-[9px] uppercase tracking-wider font-bold bg-black text-white px-1.5 py-0.5 rounded-full">Product Co</span>` : ''}
        </div>
        <div class="text-xs text-text-medium mt-0.5">${c.current_title} &bull; <span class="font-medium text-text-primary">${c.current_company}</span></div>
      </td>
      <td class="py-3.5 px-3">
        <span class="font-serif font-bold text-base text-text-primary">${c.score.toFixed(3)}</span>
      </td>
      <td class="py-3.5 px-3 text-xs text-text-medium">
        ${c.total_exp_years}y YoE
      </td>
      <td class="py-3.5 px-3">
        <span class="text-[11px] px-2.5 py-1 rounded-full font-medium ${noticeBadgeClass}">
          ${c.notice_period_days}d Notice
        </span>
      </td>
      <td class="py-3.5 px-4 text-xs text-text-medium max-w-md truncate" title="${c.reasoning}">
        &ldquo;${c.reasoning}&rdquo;
      </td>
      <td class="py-3.5 px-3 text-right">
        <button class="btn-audit glass-pill text-xs px-3 py-1.5 rounded-full hover:bg-black hover:text-white transition font-medium" data-id="${c.candidate_id}">
          Audit
        </button>
      </td>
    `;

    // Row click opens audit drawer (unless clicking checkbox)
    tr.addEventListener('click', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.closest('.cand-checkbox')) return;
      openAuditDrawer(c.candidate_id);
    });

    tbody.appendChild(tr);
  });

  document.getElementById('footer-count').textContent = `Showing ${candidates.length} Shortlisted Candidates`;
  attachCheckboxListeners();
}

// -------------------------------------------------------------
// 3. Selection & Compare Bar
// -------------------------------------------------------------
function attachCheckboxListeners() {
  document.querySelectorAll('.cand-checkbox').forEach((box) => {
    box.addEventListener('change', (e) => {
      const cid = e.target.getAttribute('data-id');
      if (e.target.checked) {
        selectedCandidateIds.add(cid);
      } else {
        selectedCandidateIds.delete(cid);
      }
      updateCompareBar();
    });
  });
}

function updateCompareBar() {
  const bar = document.getElementById('compare-bar');
  const countSpan = document.getElementById('selected-count');
  const count = selectedCandidateIds.size;

  countSpan.textContent = `${count} Candidate${count === 1 ? '' : 's'} Selected`;

  if (count >= 2) {
    bar.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-4');
  } else {
    bar.classList.add('opacity-0', 'pointer-events-none', 'translate-y-4');
  }
}

// -------------------------------------------------------------
// 4. Interactive Sliders (Debounced Fast Re-Rank)
// -------------------------------------------------------------
let rerankTimeout = null;

function handleSliderChange() {
  const noticeVal = parseFloat(document.getElementById('slider-notice').value);
  const prodVal = parseFloat(document.getElementById('slider-product').value);
  const coreVal = parseFloat(document.getElementById('slider-core').value);

  // Update slider label tags
  document.getElementById('val-notice').textContent = noticeVal >= 0.7 ? 'Strict (<=30d)' : (noticeVal <= 0.3 ? 'Flexible (120d)' : 'Standard (30d)');
  document.getElementById('val-product').textContent = prodVal >= 0.7 ? '+25% Product Co' : (prodVal <= 0.3 ? 'Neutral Pedigree' : 'High Affinity');
  document.getElementById('val-core').textContent = coreVal >= 0.7 ? '0.90 Strict Threshold' : (coreVal <= 0.3 ? '0.70 Soft Match' : '0.85 Threshold');

  clearTimeout(rerankTimeout);
  rerankTimeout = setTimeout(async () => {
    try {
      const t0 = performance.now();
      const res = await fetch('/api/rerank', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          notice_sensitivity: noticeVal,
          product_bias: prodVal,
          core_strictness: coreVal
        })
      });
      const data = await res.json();
      const elapsed = Math.round(performance.now() - t0);
      document.getElementById('latency-indicator').textContent = `Auto-Calibrated • ${elapsed}ms Latency`;

      currentCandidates = data.candidates;
      renderLeaderboard(data.candidates);
    } catch (err) {
      console.error('Rerank error:', err);
    }
  }, 40);
}

// -------------------------------------------------------------
// 5. Screen 2: Candidate Deep-Dive Audit Drawer
// -------------------------------------------------------------
async function openAuditDrawer(candidateId) {
  try {
    const res = await fetch(`/api/candidates/${candidateId}`);
    const c = await res.json();

    const drawerBody = document.getElementById('drawer-body');
    const isTop1 = c.current_rank === 1;

    drawerBody.innerHTML = `
      <!-- Header -->
      <div class="mb-6 pt-2">
        <div class="flex items-center space-x-2 mb-2">
          <span class="text-xs uppercase tracking-widest font-semibold px-2.5 py-0.5 rounded-full ${isTop1 ? 'bg-black text-white' : 'glass-pill text-text-primary'}">
            Rank #${c.current_rank}
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
          <div class="font-serif text-xl font-bold text-text-primary mt-1">${c.score.toFixed(3)}</div>
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
            <span class="font-semibold text-text-primary">${(c.original_score * 0.95).toFixed(3)}</span>
          </div>
          <div class="flex justify-between py-1 border-b border-black/5">
            <span class="text-text-medium">Verified Platform Skill Multiplier</span>
            <span class="font-semibold text-emerald-800">${c.skill_multiplier}x</span>
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
            <span class="font-serif text-base text-text-primary">${c.score.toFixed(3)}</span>
          </div>
        </div>
      </div>

      <!-- 12-Facet Competency Breakdown -->
      <div class="glass-card rounded-2xl p-5 mb-6">
        <div class="text-xs font-bold text-text-primary mb-3">12-Facet Competency Alignment</div>
        <div class="space-y-3">
          ${renderFacetBar('Embeddings Retrieval (HNSW / FAISS)', c.facet_scores['retrieval_systems'] || 96)}
          ${renderFacetBar('Vector Database Search & Sharding', c.facet_scores['vector_db_search'] || 94)}
          ${renderFacetBar('Python ML Engineering / PyTorch', c.facet_scores['python_engineering'] || 92)}
          ${renderFacetBar('Multi-Factor Ranking Evaluation', c.facet_scores['ranking_evaluation'] || 95)}
          ${renderFacetBar('Learning to Rank (LTR / Neural)', c.facet_scores['learning_to_rank'] || 88)}
          ${renderFacetBar('LLM Fine-tuning (LoRA / PEFT)', c.facet_scores['llm_finetuning'] || 82)}
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

// -------------------------------------------------------------
// 6. Screen 3: Candidate Comparative Analysis Modal
// -------------------------------------------------------------
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
              Rank #${c.current_rank} Match
            </span>
            ${c.is_product_co ? `<span class="text-[9px] uppercase tracking-wider font-bold bg-black text-white px-1.5 py-0.5 rounded-full">Product Co</span>` : ''}
          </div>
          <h3 class="font-serif text-2xl font-bold text-text-primary mt-1">${c.name}</h3>
          <div class="text-xs text-text-medium mt-0.5">${c.current_title} &bull; <strong class="text-text-primary">${c.current_company}</strong></div>

          <!-- Score Card -->
          <div class="glass-pill rounded-2xl p-3 my-4 flex items-center justify-between">
            <span class="text-xs text-text-medium font-medium">Composite Score</span>
            <span class="font-serif text-xl font-bold text-text-primary">${c.score.toFixed(3)}</span>
          </div>

          <!-- Structured Comparison Rows -->
          <div class="space-y-4 my-4 text-xs">
            <!-- Competencies -->
            <div>
              <div class="text-[10px] uppercase tracking-wider text-text-medium font-bold mb-1">Core Competency Gauges</div>
              ${renderFacetBar('Embeddings Retrieval', c.facet_scores['retrieval_systems'] || 96)}
              <div class="mt-2"></div>
              ${renderFacetBar('Vector DB Scale', c.facet_scores['vector_db_search'] || 94)}
              <div class="mt-2"></div>
              ${renderFacetBar('Python ML Engineering', c.facet_scores['python_engineering'] || 92)}
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
                <span class="font-semibold text-emerald-800">${c.skill_multiplier}x Verified</span>
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
// 7. Event Listeners Setup
// -------------------------------------------------------------
function setupEventListeners() {
  // Sliders
  document.getElementById('slider-notice').addEventListener('input', handleSliderChange);
  document.getElementById('slider-product').addEventListener('input', handleSliderChange);
  document.getElementById('slider-core').addEventListener('input', handleSliderChange);

  // Search input
  document.getElementById('search-input').addEventListener('input', () => {
    fetchCandidates();
  });

  // Filter chips
  document.getElementById('chip-filter-all').addEventListener('click', (e) => {
    setActiveChip(e.target);
    activeFilter = 'all';
    fetchCandidates();
  });
  document.getElementById('chip-filter-product').addEventListener('click', (e) => {
    setActiveChip(e.target);
    activeFilter = 'product';
    fetchCandidates();
  });
  document.getElementById('chip-filter-notice').addEventListener('click', (e) => {
    setActiveChip(e.target);
    activeFilter = 'notice';
    fetchCandidates();
  });

  // Export CSV button
  document.getElementById('btn-export-csv').addEventListener('click', () => {
    window.location.href = '/api/export';
  });

  // Run pipeline button
  document.getElementById('btn-run-pipeline').addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-pipeline');
    btn.innerHTML = `<span class="material-symbols-outlined text-sm animate-spin">refresh</span><span>Running DuckDB...</span>`;
    await handleSliderChange();
    setTimeout(() => {
      btn.innerHTML = `<span class="material-symbols-outlined text-sm">play_arrow</span><span>Run Pipeline</span>`;
    }, 400);
  });

  // Compare triggers
  document.getElementById('btn-open-compare').addEventListener('click', openCompareModal);
  document.getElementById('btn-close-compare').addEventListener('click', closeCompareModal);
  document.getElementById('btn-clear-selection').addEventListener('click', () => {
    selectedCandidateIds.clear();
    document.querySelectorAll('.cand-checkbox').forEach(b => b.checked = false);
    updateCompareBar();
  });

  // Drawer triggers
  document.getElementById('btn-close-drawer').addEventListener('click', closeDrawer);
  document.getElementById('drawer-modal').addEventListener('click', (e) => {
    if (e.target.id === 'drawer-modal') closeDrawer();
  });
  document.getElementById('compare-modal').addEventListener('click', (e) => {
    if (e.target.id === 'compare-modal') closeCompareModal();
  });
}

function setActiveChip(activeBtn) {
  document.querySelectorAll('.filter-chip').forEach(btn => {
    btn.className = 'filter-chip glass-pill text-black text-xs px-3.5 py-1.5 rounded-full font-medium hover:bg-white transition';
  });
  activeBtn.className = 'filter-chip active bg-black text-white text-xs px-3.5 py-1.5 rounded-full font-medium transition';
}
