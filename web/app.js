const state = { data: null, index: 1, events: [], showBoxes: true };
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));
const label = {
  in_progress: '施工中',
  unclear: '无法确认',
  completed: '已完成',
  done: '已完成',
  not_started: '未开工',
};
const fmtDate = d => d?.length === 7 ? d.replace('-', '年') + '月' : (d || '');

function showNotice(text, error = false) {
  const n = $('#notice');
  n.textContent = text;
  n.className = 'notice' + (error ? ' error' : '');
}

function hideNotice() {
  $('#notice').className = 'notice hidden';
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  let body = {};
  try { body = await r.json(); } catch {}
  if (!r.ok) throw new Error(body.detail || '请求失败');
  return body;
}

async function loadDemo() {
  try {
    state.data = await api('/api/demo');
    state.index = Math.max(0, state.data.history.length - 1);
    render();
    loadJobs();
  } catch (e) {
    showNotice(e.message, true);
  }
}

function render() {
  const d = state.data;
  if (!d) return;
  const projectName = d.project_name || '当前工程';
  $('#projectTitle').textContent = projectName;
  if ($('#metaProject')) $('#metaProject').textContent = projectName;
  if ($('#metaType')) $('#metaType').textContent = d.context?.dam_type || '未指定';
  const live = d.source === 'live';
  $('#sourceBadge').textContent = live ? '本次识别' : `${d.history.length} 期历史分析`;
  $('#sourceBadge').className = 'badge ' + (live ? 'live' : 'historical');

  const dates = d.history.map(h => h.date).filter(Boolean);
  if ($('#dateRange')) {
    $('#dateRange').textContent = dates.length > 1
      ? `${fmtDate(dates[0])} — ${fmtDate(dates[dates.length - 1])}`
      : (dates[0] ? fmtDate(dates[0]) : '等待更多照片');
  }

  renderTrend(d);
  $('#timeline').innerHTML = d.history.map((h, i) => `
    <button class="timeline-item ${i === state.index ? 'active' : ''}" data-index="${i}" type="button">
      <div class="timeline-date">${esc(fmtDate(h.date))}</div>
      <div class="timeline-meta">${i ? '与上期对比' : '基准影像'}</div>
    </button>
  `).join('');

  document.querySelectorAll('.timeline-item').forEach(x => {
    x.onclick = () => {
      state.index = +x.dataset.index;
      render();
    };
  });

  const h = d.history[state.index];
  const prev = d.history[state.index - 1];
  renderComparison(h, prev);
  renderSummary(h);
  renderStages(h);
  updateMetrics(h);
}

function updateMetrics(h) {
  const o = overview(h).overall;
  const rows = overview(h).rows;
  const total = o.project_progress_pct ?? o.total_estimate_pct ?? o.display_progress_pct;
  const active = rows.filter(s => ['in_progress', 'done', 'completed'].includes(s.status)).length;
  const stateText = o.construction_state_label || '—';
  if ($('#metricPeriod')) $('#metricPeriod').textContent = fmtDate(h.date);
  if ($('#metricProgress')) $('#metricProgress').textContent = total == null ? '—' : `${Number(total).toFixed(0)}%`;
  if ($('#metricCoverage')) $('#metricCoverage').textContent = `${Number(o.status_coverage_pct ?? 0).toFixed(0)}%`;
  if ($('#metricStatus')) $('#metricStatus').textContent = active ? `${active}/${rows.length} 部位施工中` : stateText;
}

function renderTrend(d) {
  const items = d.trend || d.history.map(h => ({
    date: h.date,
    progress_pct: h.construction_overview?.overall?.display_progress_pct,
  }));
  if (!$('#trend')) return;
  $('#trend').innerHTML = items.map((x, i) => {
    const value = Number(x.progress_pct ?? 0);
    return `
      <button class="trend-item ${i === state.index ? 'active' : ''}" data-index="${i}" type="button">
        <div class="trend-bar"><i style="height:${Math.max(4, Math.min(100, value))}%"></i></div>
        <strong>${value.toFixed(0)}%</strong>
        <span>${esc(fmtDate(x.date))}</span>
      </button>
    `;
  }).join('');
  document.querySelectorAll('.trend-item').forEach(x => {
    x.onclick = () => {
      state.index = +x.dataset.index;
      render();
    };
  });
}

function renderComparison(h, prev) {
  const events = h.temporal_changes || [];
  state.events = events;
  const stageBoxes = overview(h).rows.map((s, i) => stageBox(s, i)).filter(Boolean).join('');
  const currentWrap = `
    <div class="image-wrap">
      <img src="${h.image_url}" alt="${esc(h.date)}现场照片">
      <span class="image-label">${esc(fmtDate(h.date))} · ${prev ? '本期原图' : '首期原图'}</span>
      ${stageBoxes}
      ${events.map((e, i) => box(e, i)).join('')}
    </div>
  `;
  const gridHtml = prev
    ? `<div class="image-grid">
         <div class="image-wrap">
           <img src="${prev.image_url}" alt="${esc(prev.date)}现场照片">
           <span class="image-label">${esc(fmtDate(prev.date))} · 上期原图</span>
         </div>
         ${currentWrap}
       </div>`
    : `<div class="image-grid single-grid">${currentWrap}</div>`;

  $('#comparison').innerHTML = `
    <div class="compare-head">
      <h3>${prev ? '前后期现场影像对比' : '首期基准影像'}</h3>
      <span>${prev ? (events.length ? `${events.length} 处通过筛选的变化` : '本期暂未检出通过筛选的同区域变化') : '首期建立观察基准'}</span>
    </div>
    <div class="${state.showBoxes ? '' : 'hide-boxes'}">${gridHtml}</div>
    ${events.length ? `
      <div class="event-list">
        ${events.map((e, i) => `
          <div class="event-card" data-event="${i}">
            <span class="event-pin">↗</span>
            <div>
              <strong>${esc(stageName(e.stage_id, h))} · ${e.direction === 'advanced' ? '可见范围扩大' : '发生变化'}</strong>
              <p>${esc(e.what || e.where || '同一区域存在可见变化。')}</p>
            </div>
            <span class="confidence">${Math.round((e.confidence || 0) * 100)}%</span>
          </div>
        `).join('')}
      </div>` : ''}
  `;

  document.querySelectorAll('.event-card').forEach(x => {
    x.onclick = () => {
      document.querySelectorAll('.event-card').forEach(y => y.classList.remove('selected'));
      x.classList.add('selected');
      document.querySelectorAll('.box').forEach(y => y.classList.remove('selected'));
      document.querySelector(`.box[data-box="${x.dataset.event}"]`)?.classList.add('selected');
    };
  });
}

function box(e, i) {
  const b = e.bbox_xyxy || [0, 0, 0, 0];
  return `<span class="box" data-box="${i}" style="left:${b[0] * 100}%;top:${b[1] * 100}%;width:${(b[2] - b[0]) * 100}%;height:${(b[3] - b[1]) * 100}%"></span>`;
}

function stageBox(s, i) {
  const b = s.observation?.bbox_xyxy;
  if (!Array.isArray(b) || b.length !== 4 || b.some(v => typeof v !== 'number' || v < 0 || v > 1) || b[2] <= b[0] || b[3] <= b[1]) {
    return '';
  }
  return `<span class="box stage-box" data-stage="${esc(s.id)}" title="${esc(s.name || s.id)}" style="left:${b[0] * 100}%;top:${b[1] * 100}%;width:${(b[2] - b[0]) * 100}%;height:${(b[3] - b[1]) * 100}%"><em>${i + 1}</em></span>`;
}

function stageName(e, h) {
  return (h.stages || []).find(s => s.id === e)?.name || e;
}

function overview(h) {
  const view = h.construction_overview || {};
  const overall = view.overall || {};
  const rows = view.parts || h.stages || [];
  const legacy = h.overall || {};
  return {
    overall: {
      ...legacy,
      ...overall,
      project_progress_pct: overall.display_progress_pct ?? overall.progress_pct ?? legacy.project_progress_pct,
      current_coverage_pct: overall.coverage_pct ?? legacy.current_coverage_pct,
      total_possible_range_pct: overall.range_pct ?? legacy.total_possible_range_pct,
      project_progress_method: overall.method ?? legacy.project_progress_method,
    },
    rows,
  };
}

function renderSummary(h) {
  const data = overview(h);
  const o = data.overall;
  const rows = data.rows;
  const total = o.project_progress_pct ?? o.total_estimate_pct;
  const counts = o.status_counts || {};
  const activeCount = (counts.in_progress || 0) + (counts.done || 0) + (counts.completed || 0);
  const unclear = counts.unclear ?? rows.filter(s => s.status === 'unclear').length;
  const events = (h.temporal_changes || []).length;
  const methods = {
    insufficient_evidence: '状态估算',
    status_fallback_weighted: '状态加权估算',
    direct_stage_weighted: '分项估算加权',
    all_stage_weighted: '按分项权重汇总',
    model_overall: '模型整体估算',
    coverage_extrapolation: '按覆盖率外推',
  };
  const method = methods[o.project_progress_method] || '视觉估算';
  const stateLabel = o.construction_state_label || (activeCount ? '可见部位正在施工' : '当前照片无法判断施工状态');
  const statusCoverage = Number(o.status_coverage_pct ?? 0);
  const activeWeight = Number(o.active_stage_weight_pct ?? 0);
  const basis = o.basis || o.project_progress_basis;
  const percentText = total == null ? '—' : `${Number(total).toFixed(0)}%`;

  $('#summary').innerHTML = `
    <div class="overall-status-banner">
      <div class="status-pulse"></div>
      <div>
        <strong>${esc(stateLabel)}</strong>
        <p>已识别 ${activeCount}/${rows.length} 个部位有明确可见状态，${unclear} 个部位暂无法确认。</p>
      </div>
    </div>
    <div class="meter-label"><span>状态证据覆盖（按分项权重）</span><b>${statusCoverage.toFixed(0)}%</b></div>
    <div class="meter"><i style="width:${Math.max(0, Math.min(100, statusCoverage))}%"></i></div>
    <div class="summary-grid">
      <div><b>${activeCount}</b><span>可见施工部位</span></div>
      <div><b>${unclear}</b><span>暂无法确认</span></div>
      <div><b>${events}</b><span>本期变化区域</span></div>
    </div>
    <div class="metric-row"><span>施工中分项权重</span><b>${activeWeight.toFixed(0)}%</b></div>
    <div class="metric-row"><span>工程百分比（${esc(method)}）</span><b>${esc(percentText)}</b></div>
    <div class="metric-row"><span>百分比证据覆盖率</span><b>${(o.current_coverage_pct ?? 0).toFixed(0)}%</b></div>
    <div class="metric-row"><span>整体证据范围</span><b>${range(o.total_possible_range_pct)}</b></div>
    ${h.summary ? `<div class="overall-evidence"><span>本期现场概况</span><p>${esc(h.summary)}</p></div>` : ''}
    ${basis ? `<p class="summary-basis">${esc(basis)}</p>` : ''}
  `;
}

function range(v) {
  return Array.isArray(v) ? `${Number(v[0]).toFixed(0)}–${Number(v[1]).toFixed(0)}%` : '未知';
}

function renderStages(h) {
  const rows = overview(h).rows;
  const events = h.temporal_changes || [];
  $('#stageCount').textContent = `${rows.length} 个部位`;
  $('#stages').innerHTML = rows.map((s, i) => {
    const estimate = s.progress_estimate;
    const percent = estimate && typeof estimate === 'object' ? estimate.percent : estimate ?? s.display_progress_pct;
    const bounds = estimate && typeof estimate === 'object' ? estimate.range_pct : null;
    const estimateText = `${Number(percent ?? 0).toFixed(0)}%${Array.isArray(bounds) ? `（${range(bounds)}）` : ''}`;
    const confidence = typeof s.confidence === 'number' ? `${Math.round(s.confidence * 100)}%` : '';
    const changes = events.filter(e => e.stage_id === s.id);
    const status = label[s.status] || s.status || '未知';
    const labelClass = s.status === 'unclear'
      ? 'unclear-label'
      : (['done', 'completed'].includes(s.status) ? 'done-label' : '');

    return `
      <article class="stage-card" data-stage="${esc(s.id)}" data-status="${esc(s.status)}">
        <div class="stage-card-head">
          <span class="stage-index">${i + 1}</span>
          <div class="stage-name">${esc(s.name || s.id)}<small>权重 ${esc(s.weight ?? '—')}%</small></div>
          <span class="stage-label ${labelClass}">${esc(status)}</span>
        </div>
        <div class="stage-detail">
          <div class="stage-result"><span>本期结论</span><b>${esc(estimateText)}</b></div>
          ${confidence ? `<div class="stage-confidence"><span>置信度</span><b>${confidence}</b></div>` : ''}
          ${s.source === 'historical_only' ? '<span class="stage-change">沿用历史判断</span>' : ''}
          ${changes.length ? `<span class="stage-change">${changes.length} 处时序变化</span>` : ''}
        </div>
        <p class="stage-evidence">${esc(s.evidence || '当前照片没有足够证据确认该部位。')}</p>
      </article>
    `;
  }).join('');

  document.querySelectorAll('.stage-card').forEach(x => {
    x.onclick = () => {
      document.querySelectorAll('.stage-card').forEach(y => y.classList.remove('selected'));
      x.classList.add('selected');
      document.querySelectorAll('.stage-box').forEach(y => y.classList.remove('selected'));
      const targetBox = document.querySelector(`.stage-box[data-stage="${x.dataset.stage}"]`);
      if (targetBox) {
        targetBox.classList.add('selected');
        if (!state.showBoxes) {
          state.showBoxes = true;
          $('#toggleBoxes').textContent = '隐藏框线';
          $('#toggleBoxes').setAttribute('aria-pressed', 'true');
          $('#comparison .hide-boxes')?.classList.remove('hide-boxes');
        }
        $('#comparison').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    };
  });
}

function loadJobs() {
  api('/api/jobs').then(jobs => {
    $('#jobs').innerHTML = jobs.length ? jobs.slice(0, 8).map(jobRow).join('') : '<div class="empty">还没有新的上传任务。</div>';
    jobs.filter(j => ['queued', 'running'].includes(j.status)).forEach(j => poll(j.id));
  }).catch(() => {});
}

function jobRow(j) {
  const text = { queued: '排队中', running: '识别中', succeeded: '已完成', failed: '失败' }[j.status] || j.status;
  const progressText = j.status === 'running'
    ? `正在处理 ${esc(j.current_date || '照片')} · ${j.completed}/${j.total}`
    : `${j.completed}/${j.total} 张照片`;
  return `
    <div class="job-row">
      <div class="job-top">
        <div class="job-name">${esc(j.project_name)}</div>
        <span class="job-state ${j.status}">${text}</span>
      </div>
      <div class="job-progress">${progressText}</div>
      ${j.status === 'failed' ? `<div class="job-error">${esc(j.error || '')}</div>` : ''}
      ${(j.status === 'failed' || j.status === 'succeeded') ? `
        <div class="job-actions">
          ${j.status === 'failed' ? `<button class="button ghost tiny" data-retry="${j.id}" type="button">重试</button>` : ''}
          ${j.status === 'succeeded' ? `<button class="button ghost tiny" data-result="${j.id}" type="button">查看结果</button>` : ''}
        </div>` : ''}
    </div>
  `;
}

function poll(id) {
  api('/api/jobs/' + id).then(async j => {
    if (['queued', 'running'].includes(j.status)) {
      setTimeout(() => poll(id), 1100);
    } else {
      loadJobs();
      if (j.status === 'succeeded') {
        try {
          state.data = await api('/api/jobs/' + id + '/result');
          state.index = state.data.history.length - 1;
          hideNotice();
          render();
        } catch (e) {
          showNotice(e.message, true);
        }
      } else {
        showNotice(j.error || '任务失败', true);
      }
    }
  }).catch(() => setTimeout(() => poll(id), 1800));
}

function setupUpload() {
  const dialog = $('#uploadDialog');
  const input = $('#photos');
  const rows = $('#photoRows');
  const error = $('#formError');
  const drop = $('#dropzone');

  $('#openUpload').onclick = () => dialog.showModal();
  ['#closeUpload', '#cancelUpload'].forEach(s => $(s).onclick = () => dialog.close());

  input.onchange = () => {
    rows.innerHTML = '';
    error.className = 'form-error hidden';
    [...input.files].forEach(f => {
      const u = URL.createObjectURL(f);
      rows.insertAdjacentHTML('beforeend', `
        <div class="photo-row">
          <img src="${u}" alt="">
          <span title="${esc(f.name)}">${esc(f.name)}</span>
          <input type="date" data-date required>
        </div>
      `);
    });
    if (input.files.length > 8) {
      error.textContent = '最多上传 8 张照片。';
      error.className = 'form-error';
    }
  };

  ['dragenter', 'dragover'].forEach(x => drop.addEventListener(x, e => {
    e.preventDefault();
    drop.classList.add('drag');
  }));
  ['dragleave', 'drop'].forEach(x => drop.addEventListener(x, e => {
    e.preventDefault();
    drop.classList.remove('drag');
  }));
  drop.addEventListener('drop', e => {
    input.files = e.dataTransfer.files;
    input.dispatchEvent(new Event('change'));
  });

  $('#uploadForm').onsubmit = async e => {
    e.preventDefault();
    error.className = 'form-error hidden';
    if (input.files.length < 2 || input.files.length > 8) {
      error.textContent = '请选择 2–8 张照片。';
      error.className = 'form-error';
      return;
    }
    const dates = [...rows.querySelectorAll('[data-date]')].map(x => x.value);
    if (dates.some(x => !x)) {
      error.textContent = '请填写每张照片的日期。';
      error.className = 'form-error';
      return;
    }
    const fd = new FormData(e.target);
    fd.delete('photos');
    [...input.files].forEach(f => fd.append('photos', f));
    fd.set('dates', JSON.stringify(dates));
    const btn = $('#submitUpload');
    btn.disabled = true;
    btn.textContent = '正在提交…';
    try {
      const j = await api('/api/jobs', { method: 'POST', body: fd });
      dialog.close();
      showNotice('已进入识别队列，页面会自动更新任务状态。');
      loadJobs();
      poll(j.id);
    } catch (err) {
      error.textContent = err.message;
      error.className = 'form-error';
    } finally {
      btn.disabled = false;
      btn.textContent = '开始识别';
    }
  };
}

$('#toggleBoxes').onclick = () => {
  state.showBoxes = !state.showBoxes;
  const btn = $('#toggleBoxes');
  btn.textContent = state.showBoxes ? '隐藏框线' : '显示框线';
  btn.setAttribute('aria-pressed', state.showBoxes ? 'true' : 'false');
  const gridContainer = $('#comparison .image-grid')?.parentElement;
  if (gridContainer) gridContainer.classList.toggle('hide-boxes', !state.showBoxes);
};

document.addEventListener('click', e => {
  const retry = e.target.closest('[data-retry]');
  if (retry) {
    api('/api/jobs/' + retry.dataset.retry + '/retry', { method: 'POST' })
      .then(() => {
        showNotice('已重新排队。');
        loadJobs();
        poll(retry.dataset.retry);
      })
      .catch(err => showNotice(err.message, true));
  }
  const result = e.target.closest('[data-result]');
  if (result) {
    api('/api/jobs/' + result.dataset.result + '/result')
      .then(d => {
        state.data = d;
        state.index = d.history.length - 1;
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .catch(err => showNotice(err.message, true));
  }
});

$('#refreshJobs').onclick = loadJobs;
setupUpload();
loadDemo();
