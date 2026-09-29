// Care Gap Worklist -- plain JS, no build step.
// UX decisions not nailed down by the API contract are called out in comments
// (also summarized in the handoff report).

const state = {
  me: null,            // {id, name, role}
  filters: { specialty: '', task_type: '' },
  expanded: {},          // taskId -> 'complete' | 'decline' | null (which inline form is open)
};

const PROGRAM_LABELS = {
  primary_care_wellness: 'Primary Care Wellness',
  diabetes_management: 'Diabetes Management',
};

function titleCase(snake) {
  return snake.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// ---------- fetch helper ----------
// Every call includes credentials:'include' per the cookie-session contract.
// A 401 anywhere bounces back to login. A network failure shows a plain banner
// instead of failing silently.
async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      ...options,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
  } catch (err) {
    showError('Could not reach the server. Check your connection and try again.');
    throw err;
  }
  if (res.status === 401) {
    showLogin();
    throw new Error('unauthorized');
  }
  return res;
}

function showError(msg) {
  const el = document.getElementById('error-banner');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(showError._t);
  showError._t = setTimeout(() => el.classList.add('hidden'), 6000);
}

// ---------- screens ----------
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  document.getElementById(id).classList.remove('hidden');
}

async function showLogin() {
  showScreen('login-screen');
  state.me = null;
  try {
    const res = await api('/api/users');
    const users = await res.json();
    renderLoginUsers(users);
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Could not load the user list.');
  }
}

function renderLoginUsers(users) {
  const wrap = document.getElementById('login-users');
  wrap.innerHTML = users.map(u => `
    <div class="login-user-card" data-user-id="${u.id}">
      <span class="login-user-name">${escapeHtml(u.name)}</span>
      <span class="role-badge ${u.role}">${u.role === 'clinical' ? 'Clinical' : 'Scheduler'}</span>
    </div>
  `).join('');
  wrap.querySelectorAll('.login-user-card').forEach(card => {
    card.addEventListener('click', () => login(card.dataset.userId));
  });
}

async function login(userId) {
  try {
    const res = await api('/api/login', { method: 'POST', body: JSON.stringify({ user_id: userId }) });
    if (!res.ok) { showError('Login failed. Please try again.'); return; }
    state.me = await res.json();
    await showWorklist();
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Login failed. Please try again.');
  }
}

async function logout() {
  try { await api('/api/logout', { method: 'POST' }); } catch (e) { /* ignore, we're leaving anyway */ }
  showLogin();
}

async function showWorklist() {
  showScreen('worklist-screen');
  const chip = document.getElementById('user-chip');
  chip.textContent = `${state.me.name} · ${state.me.role === 'clinical' ? 'Clinical' : 'Scheduler'}`;
  // Task-type filter only matters for clinical (scheduler only ever gets scheduling tasks back).
  document.getElementById('task-type-field').classList.toggle('hidden', state.me.role !== 'clinical');
  if (state.me.role !== 'clinical') state.filters.task_type = '';
  await loadPatients();
}

// ---------- worklist ----------
async function loadPatients() {
  const params = new URLSearchParams();
  if (state.filters.specialty) params.set('specialty', state.filters.specialty);
  if (state.filters.task_type) params.set('task_type', state.filters.task_type);
  try {
    const res = await api('/api/patients?' + params.toString());
    if (!res.ok) { showError('Could not load the worklist.'); return; }
    const patients = await res.json();
    renderPatients(patients);
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Could not load the worklist.');
  }
}

async function refreshWorklist() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';
  try {
    const res = await api('/api/admin/recompute', { method: 'POST' });
    if (!res.ok) showError('Refresh failed.');
    await loadPatients();
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Refresh failed.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh worklist';
  }
}

// Design decision: patients with zero tasks visible to this role are hidden
// entirely (not shown collapsed) -- keeps the worklist focused on actionable
// items, per the "recommended" option in the spec.
function renderPatients(patients) {
  const visible = patients.filter(p => p.tasks && p.tasks.length > 0);
  const container = document.getElementById('patients-container');
  document.getElementById('empty-state').classList.toggle('hidden', visible.length > 0);
  container.innerHTML = visible.map(renderPatientCard).join('');
  wireUpPatientEvents(container, visible);
}

function tierBadges(enrollments) {
  return (enrollments || []).map(e =>
    `<span class="tier-badge">${PROGRAM_LABELS[e.program_id] || titleCase(e.program_id)}: ${titleCase(e.tier)}</span>`
  ).join('');
}

function assignedName(name) {
  // assigned_to comes back from the API as the user's display name (not their
  // id) -- confirmed against the live backend. "you" is nicer than echoing
  // your own name back at you.
  if (!name) return '';
  if (state.me && name === state.me.name) return 'you';
  return name;
}

function taskRow(task) {
  const isMine = task.status === 'in_progress' && task.assigned_to === state.me.name;
  const overdue = task.status === 'open' && task.due_date && task.due_date < todayISO();
  const typeBadge = task.task_type === 'referral'
    ? '<span class="badge badge-referral">Needs Review</span>'
    : '<span class="badge badge-scheduling">Scheduling</span>';
  const statusLabels = { open: 'Open', in_progress: 'In Progress', completed: 'Completed', declined: 'Declined' };
  const statusLabel = statusLabels[task.status] || titleCase(task.status || 'unknown');
  const claimedNote = (task.status === 'in_progress' && task.assigned_to)
    ? ` <span class="due-date">(claimed by ${escapeHtml(assignedName(task.assigned_to))})</span>` : '';

  let controls = '';
  if (isMine) {
    controls = `
      <div class="task-controls">
        <button class="btn btn-ghost btn-small" data-action="toggle-complete" data-task-id="${task.task_id}">Complete</button>
        <button class="btn btn-ghost btn-small" data-action="toggle-decline" data-task-id="${task.task_id}">Decline</button>
      </div>`;
  }

  let form = '';
  const mode = state.expanded[task.task_id];
  if (isMine && mode === 'complete') {
    const options = task.task_type === 'referral'
      ? [['referral_approved', 'Referral approved'], ['referral_not_indicated', 'Referral not needed']]
      : [['booked', 'Booked the appointment']];
    form = `
      <div class="inline-form">
        <select data-role="resolution-select" data-task-id="${task.task_id}">
          ${options.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}
        </select>
        <button class="btn btn-navy btn-small" data-action="confirm-complete" data-task-id="${task.task_id}">Confirm</button>
        <button class="btn btn-ghost btn-small" data-action="toggle-complete" data-task-id="${task.task_id}">Cancel</button>
      </div>`;
  } else if (isMine && mode === 'decline') {
    form = `
      <div class="inline-form">
        <input type="text" placeholder="Reason" data-role="decline-reason" data-task-id="${task.task_id}">
        <label>Check back in
          <input type="number" min="1" value="7" data-role="decline-snooze" data-task-id="${task.task_id}">
          days
        </label>
        <button class="btn btn-navy btn-small" data-action="confirm-decline" data-task-id="${task.task_id}">Confirm</button>
        <button class="btn btn-ghost btn-small" data-action="toggle-decline" data-task-id="${task.task_id}">Cancel</button>
      </div>`;
  }

  return `
    <div class="task-row">
      <div class="task-row-main">
        <span class="task-specialty">${escapeHtml(task.specialty)}</span>
        ${typeBadge}
        <span class="badge badge-status-${task.status}">${statusLabel}</span>
        <span class="due-date ${overdue ? 'overdue' : ''}">${task.due_date ? (overdue ? 'Overdue - due ' : 'Due ') + task.due_date : 'No due date'}</span>
        ${claimedNote}
      </div>
      ${controls}
      ${form}
    </div>`;
}

function renderPatientCard(p) {
  const hasOpenTask = p.tasks.some(t => t.status === 'open');
  const myClaimedTasks = p.tasks.filter(t => t.status === 'in_progress' && t.assigned_to === (state.me && state.me.name));
  const claimNote = myClaimedTasks.length > 0
    ? `<div class="claim-note">In progress -- claimed by you</div>` : '';

  return `
    <div class="patient-card" data-patient-id="${p.patient_id}">
      <div class="patient-top">
        <div class="patient-identity">
          <h2>${escapeHtml(p.first_name)} ${escapeHtml(p.last_name)}</h2>
          <div class="patient-meta">Age ${p.age} &middot; PCP: ${escapeHtml(p.pcp_provider_name || 'Unassigned')}</div>
          <a class="patient-phone" href="tel:${escapeHtml(p.phone)}">${escapeHtml(p.phone)}</a>
          <div class="tier-badges">${tierBadges(p.enrollments)}</div>
          ${claimNote}
        </div>
        <div class="patient-actions">
          ${hasOpenTask ? `<button class="btn btn-red" data-action="claim" data-patient-id="${p.patient_id}">Claim</button>` : ''}
        </div>
      </div>
      <div class="task-list">
        ${p.tasks.map(taskRow).join('')}
      </div>
    </div>`;
}

function wireUpPatientEvents(container) {
  container.querySelectorAll('[data-action="claim"]').forEach(btn =>
    btn.addEventListener('click', () => claimPatient(btn.dataset.patientId)));

  container.querySelectorAll('[data-action="toggle-complete"]').forEach(btn =>
    btn.addEventListener('click', () => {
      const id = btn.dataset.taskId;
      state.expanded[id] = state.expanded[id] === 'complete' ? null : 'complete';
      loadPatients();
    }));

  container.querySelectorAll('[data-action="toggle-decline"]').forEach(btn =>
    btn.addEventListener('click', () => {
      const id = btn.dataset.taskId;
      state.expanded[id] = state.expanded[id] === 'decline' ? null : 'decline';
      loadPatients();
    }));

  container.querySelectorAll('[data-action="confirm-complete"]').forEach(btn =>
    btn.addEventListener('click', () => {
      const id = btn.dataset.taskId;
      const select = container.querySelector(`[data-role="resolution-select"][data-task-id="${id}"]`);
      completeTask(id, select.value);
    }));

  container.querySelectorAll('[data-action="confirm-decline"]').forEach(btn =>
    btn.addEventListener('click', () => {
      const id = btn.dataset.taskId;
      const reason = container.querySelector(`[data-role="decline-reason"][data-task-id="${id}"]`).value.trim();
      const snooze = parseInt(container.querySelector(`[data-role="decline-snooze"][data-task-id="${id}"]`).value, 10) || 7;
      if (!reason) { showError('Please enter a reason before declining.'); return; }
      declineTask(id, reason, snooze);
    }));
}

async function claimPatient(patientId) {
  try {
    const res = await api(`/api/patients/${patientId}/claim`, { method: 'POST' });
    if (res.status === 409) {
      const body = await res.json().catch(() => ({}));
      showError(body.detail || "Someone already claimed this patient's tasks -- refreshing");
      await loadPatients();
      return;
    }
    if (!res.ok) { showError('Could not claim this patient.'); return; }
    await loadPatients();
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Could not claim this patient.');
  }
}

async function completeTask(taskId, resolution) {
  try {
    const res = await api(`/api/tasks/${taskId}/complete`, { method: 'POST', body: JSON.stringify({ resolution }) });
    if (res.status === 403) { showError('This task was claimed by someone else -- refreshing.'); await loadPatients(); return; }
    if (!res.ok) { showError('Could not complete this task.'); return; }
    delete state.expanded[taskId];
    await loadPatients();
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Could not complete this task.');
  }
}

async function declineTask(taskId, reason, snoozeDays) {
  try {
    const res = await api(`/api/tasks/${taskId}/decline`, {
      method: 'POST',
      body: JSON.stringify({ reason, snooze_days: snoozeDays }),
    });
    if (res.status === 403) { showError('This task was claimed by someone else -- refreshing.'); await loadPatients(); return; }
    if (!res.ok) { showError('Could not decline this task.'); return; }
    delete state.expanded[taskId];
    await loadPatients();
  } catch (e) {
    if (e.message !== 'unauthorized') showError('Could not decline this task.');
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// ---------- boot ----------
async function init() {
  document.getElementById('logout-btn').addEventListener('click', logout);
  document.getElementById('refresh-btn').addEventListener('click', refreshWorklist);
  document.getElementById('specialty-filter').addEventListener('change', e => {
    state.filters.specialty = e.target.value;
    loadPatients();
  });
  document.getElementById('task-type-filter').addEventListener('change', e => {
    state.filters.task_type = e.target.value;
    loadPatients();
  });

  try {
    const res = await api('/api/me');
    if (res.ok) {
      state.me = await res.json();
      await showWorklist();
    } else {
      await showLogin();
    }
  } catch (e) {
    if (e.message === 'unauthorized') { /* showLogin already called by api() */ }
    else showError('Could not reach the server.');
  }
}

init();
