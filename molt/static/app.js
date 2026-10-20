'use strict';
const $ = (id) => document.getElementById(id);
const state = {csrf: '', initialized: true, view: 'radar', classification: '', offset: 0, limit: 15, total: 0, dashboard: null, settings: null, listRequest: 0, sourceKey: '', detail: null};
const labels = {open: 'Vigente según fuente', review: 'Por verificar', historical: 'Histórica'};
const docLabels = {pending: 'Pendiente', read: 'Texto revisado', partial: 'Lectura parcial', manual: 'Revisión manual', error: 'Error de acceso'};
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = (value) => {try {const u = new URL(value); return u.protocol === 'https:' ? esc(u.href) : '#';} catch {return '#';}};
const number = (n) => new Intl.NumberFormat('es-PE').format(n || 0);
const date = (value, withTime = false) => {if (!value) return 'No publicada'; const d = new Date(value); if (Number.isNaN(d.valueOf())) return 'Por confirmar'; return new Intl.DateTimeFormat('es-PE', {timeZone: 'America/Lima', day: '2-digit', month: 'short', year: 'numeric', ...(withTime ? {hour: '2-digit', minute: '2-digit'} : {})}).format(d);};
const money = (amount, currency) => {if (amount === null || amount === undefined) return 'Monto no publicado'; if (!currency) return number(amount) + ' · moneda no publicada'; try {return new Intl.NumberFormat('es-PE', {style:'currency', currency, maximumFractionDigits: 2}).format(amount);} catch {return number(amount) + ' ' + currency;}};
let toastTimer, searchTimer;
function toast(message, error = false) {clearTimeout(toastTimer); $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').hidden = false; toastTimer = setTimeout(() => {$('toast').hidden = true;}, error ? 9000 : 5000);}

async function api(path, options = {}) {
  const headers = {'Content-Type': 'application/json', ...options.headers};
  if (state.csrf) headers['X-CSRF-Token'] = state.csrf;
  const response = await fetch('/api' + path, {...options, headers, credentials: 'same-origin'});
  let data;
  try {data = await response.json();} catch {throw new Error('No se pudo leer la respuesta del servidor.');}
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) showAuth(true);
    const detail = Array.isArray(data.detail) ? data.detail.map((x) => x.msg).join(' · ') : data.detail;
    throw new Error(detail || 'No se pudo completar la operación.');
  }
  return data;
}

function showAuth(initialized) {
  state.initialized = initialized; state.csrf = '';
  $('application').hidden = true; $('auth-screen').hidden = false; $('initial-loading').hidden = true;
  $('setup-field').hidden = initialized; $('setup-code').required = !initialized;
  $('auth-title').innerHTML = initialized ? 'Un buen negocio<br>empieza por aquí.' : 'Tu espacio privado.<br>Tu primera conexión.';
  $('auth-description').textContent = initialized ? 'Ingresa a tu espacio de oportunidades.' : 'Crea tu único usuario. Usa una contraseña de al menos 12 caracteres.';
  $('auth-submit').innerHTML = initialized ? 'Entrar a mi radar <span>↗</span>' : 'Crear mi acceso privado <span>↗</span>';
  $('password').minLength = initialized ? 1 : 12; $('password').autocomplete = initialized ? 'current-password' : 'new-password';
  if (!initialized) $('username').value = 'admin';
}

async function enterApplication(user) {
  state.csrf = user.csrf; $('account-name').textContent = user.username;
  $('auth-screen').hidden = true; $('initial-loading').hidden = true; $('application').hidden = false;
  $('password').value = ''; $('setup-code').value = ''; $('auth-error').textContent = '';
  await refreshDashboard();
  await setView('radar');
}

$('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault(); $('auth-error').textContent = ''; $('auth-submit').disabled = true;
  try {
    const body = {username: $('username').value.trim(), password: $('password').value};
    if (!state.initialized) body.code = $('setup-code').value.trim();
    const user = await api(state.initialized ? '/auth/login' : '/auth/setup', {method:'POST', body:JSON.stringify(body)});
    await enterApplication(user);
  } catch (error) {$('auth-error').textContent = error.message;}
  finally {$('auth-submit').disabled = false;}
});

$('logout').addEventListener('click', async () => {try {await api('/auth/logout', {method:'POST'}); showAuth(true);} catch (error) {toast(error.message, true);}});
$('mobile-logout').addEventListener('click', () => $('logout').click());

async function setView(view) {
  state.view = view;
  document.querySelectorAll('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  $('radar-view').hidden = !['radar', 'followup'].includes(view); $('mail-view').hidden = view !== 'mail'; $('settings-view').hidden = view !== 'settings';
  const names = {radar:'Radar de oportunidades', followup:'Mi seguimiento', mail:'Resúmenes por correo', settings:'Preferencias'};
  $('breadcrumb').textContent = names[view];
  if (view === 'radar' || view === 'followup') {
    $('page-title').innerHTML = view === 'radar' ? 'Tu próximo evento empieza aquí<span>.</span>' : 'Cada oportunidad, un paso más<span>.</span>';
    $('page-description').textContent = view === 'radar' ? 'Encuentra oportunidades que conectan con lo que mejor sabes hacer.' : 'Tus procesos en revisión, cotización o presentación, en un solo lugar.';
    $('list-title').firstChild.textContent = view === 'radar' ? 'Oportunidades para tu negocio ' : 'Oportunidades en seguimiento ';
    state.offset = 0; await loadItems();
  } else if (view === 'settings') {await loadSettings();}
  else {await loadMail();}
}

document.addEventListener('click', async (event) => {
  const nav = event.target.closest('[data-view]');
  if (nav) {try {await setView(nav.dataset.view);} catch (error) {toast(error.message, true);} return;}
  const tab = event.target.closest('[data-class]');
  if (tab) {state.classification = tab.dataset.class; state.offset = 0; updateTabs(); await loadItems(); return;}
  const detail = event.target.closest('[data-detail]');
  if (detail) {await openDetail(detail.dataset.detail); return;}
  const refresh = event.target.closest('[data-action="sync"]');
  if (refresh) $('sync-button').click();
});

function updateTabs() {document.querySelectorAll('.tab').forEach((tab) => {const active = tab.dataset.class === state.classification; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active));});}

function queryParams() {
  const params = new URLSearchParams();
  const values = {q:$('search').value.trim(), city:$('city-filter').value, family:$('family-filter').value, stage:$('stage-filter').value, sort:$('sort-filter').value, classification:state.classification};
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  if ($('include-unknown').checked) params.set('include_unknown', 'true');
  if (state.view === 'followup') params.set('followup', 'true');
  return params;
}

function automationLabel(automation) {
  if (automation?.web_worker) return 'En el servidor · cada ' + automation.interval_hours + ' h';
  if (!automation?.started) return 'Recolector externo pendiente de conectar';
  const last = new Date(automation.started);
  const stale = !Number.isFinite(last.valueOf()) || Date.now() - last.valueOf() > 3 * 3600000;
  const status = stale ? 'Sin señal reciente' : automation.status === 'error' ? 'Última ejecución con error' : automation.status === 'running' ? 'En ejecución' : 'Recolector externo';
  return status + ' · ' + date(automation.started, true);
}

async function refreshDashboard() {
  if (!state.csrf) return;
  const data = await api('/dashboard'); state.dashboard = data;
  const stats = data.stats;
  $('city-chips').innerHTML = data.selected_cities.map((c) => `<span>${esc(c)}</span>`).join('');
  for (const key of ['total', 'open', 'review', 'historical', 'integral']) $('stat-' + key).textContent = number(stats[key]);
  $('followup-count').textContent = number(stats.saved); $('tab-open').textContent = number(stats.open);
  const familyFilter = $('family-filter');
  if (familyFilter.options.length === 1) for (const [key, label] of Object.entries(data.families)) familyFilter.add(new Option(label, key));
  const source = data.source;
  const names = {never:'Sin consultar', running:'Consultando', complete:'Consulta completa', partial:'Parcial', error:'Error de fuente', interrupted:'Interrumpida'};
  $('sync-status-pill').textContent = source.running ? 'Consultando' : names[source.status] || source.status;
  $('sync-status-pill').className = 'badge ' + (source.status === 'error' ? 'error' : source.status === 'complete' ? 'open' : 'neutral');
  $('source-message').textContent = source.message || (source.running ? 'Consultando registros oficiales. Las coincidencias aparecerán durante la lectura.' : 'Puedes consultar la fuente sin salir de tu panel.');
  $('source-last').textContent = source.last_complete ? date(source.last_complete, true) : 'Aún sin consulta completa';
  $('source-window').textContent = source.window_start ? date(source.window_start + 'T12:00:00-05:00') + ' — ' + date(source.window_end + 'T12:00:00-05:00') : 'Últimos 90 días';
  $('source-latest').textContent = date(source.source_latest, true);
  $('source-automation').textContent = automationLabel(source.automation);
  $('source-scanned').textContent = number(source.scanned);
  $('sync-button').disabled = !!source.running;
  $('sync-button').innerHTML = source.running ? '<span class="spinner"></span> Consultando…' : '<span class="sync-icon">↻</span> Actualizar radar';
  $('source-progress').hidden = !source.running;
  $('source-progress-label').textContent = number(source.pages) + ' páginas · ' + number(source.matched) + ' coincidencias nacionales';
  const docs = source.documents || {};
  $('docs-read').textContent = number((docs.read || 0) + (docs.partial || 0));
  $('docs-pending').textContent = number(docs.pending); $('docs-manual').textContent = number((docs.manual || 0) + (docs.error || 0));
  $('document-summary').textContent = source.documents_paused ? source.documents_message : 'Cola nacional de contratos candidatos. Un PDF escaneado o ZIP necesita revisión manual.';
  $('process-documents').disabled = !(docs.pending > 0 || docs.error > 0);
  return data;
}

function renderCard(item) {
  const familyNames = state.dashboard?.families || {};
  const tags = item.families.slice(0, 2).map((f) => `<span class="tag">${esc(familyNames[f] || f)}</span>`).join('');
  const documentMatch = item.evidence.some((e) => e.origin === 'Documento oficial');
  const location = !item.city ? 'Sin ubicación' : (item.location_basis.startsWith('Domicilio') ? 'Entidad: ' : 'Servicio: ') + item.city;
  return `<article class="opportunity"><div class="opportunity-top"><span class="buyer-line" title="${esc(item.buyer)}">${esc(item.buyer)}</span><span class="badge ${esc(item.classification)}">${esc(labels[item.classification])}</span></div><button class="opportunity-title-button" data-detail="${esc(item.ocid)}"><h3>${esc(item.title)}</h3></button><div class="opportunity-meta"><span title="${esc(item.location_basis)}">⌖ ${esc(location)}</span><span class="amount">${esc(money(item.amount, item.currency))}</span><span>${item.classification === 'historical' ? 'Cierre publicado' : 'Cierre'}: ${esc(date(item.deadline))}</span></div><p class="scope-line"><span class="small-arrow">↗</span>${esc(item.scope)}${item.stage !== 'Pendiente' ? ' · ' + esc(item.stage) : ''}</p><div class="opportunity-bottom"><div class="tags">${tags}${documentMatch ? '<span class="tag doc">Hallazgo en documento</span>' : ''}</div><button class="text-button card-action" data-detail="${esc(item.ocid)}">Ver oportunidad <span>↗</span></button></div></article>`;
}

async function loadItems() {
  if (!state.csrf) return;
  const request = ++state.listRequest;
  $('list-loading').hidden = false;
  try {
    const params = queryParams(); $('export-button').href = '/api/export.xlsx?' + params.toString();
    params.set('offset', state.offset); params.set('limit', state.limit);
    const data = await api('/opportunities?' + params.toString());
    if (request !== state.listRequest) return;
    state.total = data.total; $('result-count').textContent = number(data.total);
    if (data.items.length) $('opportunities-list').innerHTML = data.items.map(renderCard).join('');
    else {
      const never = !state.dashboard?.source.last_complete;
      const title = state.view === 'followup' ? 'Dale seguimiento a tu siguiente conexión.' : 'Aún no hay coincidencias con estos filtros.';
      const text = state.view === 'followup' ? 'Abre una oportunidad y guárdala como Revisar, Cotizar o Presentada para encontrarla aquí.' : never ? 'Consulta el radar y espera a que finalice la lectura de la fuente. Los resultados se mostrarán con su estado real.' : 'Prueba otra familia o zona. La ausencia de resultados en esta ventana no significa que no existan contrataciones en otras fuentes o períodos.';
      $('opportunities-list').innerHTML = `<div class="empty-state"><span class="empty-icon">↗</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${never ? '<button class="button secondary" data-action="sync">Consultar fuente oficial ↗</button>' : ''}</div>`;
    }
    $('pagination-label').textContent = data.total ? `${number(state.offset + 1)}–${number(Math.min(state.offset + state.limit, data.total))} de ${number(data.total)} coincidencias` : 'Sin resultados en este filtro';
    $('previous-page').disabled = state.offset === 0; $('next-page').disabled = state.offset + state.limit >= data.total;
  } catch (error) {toast(error.message, true);} finally {if (request === state.listRequest) $('list-loading').hidden = true;}
}

$('search').addEventListener('input', () => {clearTimeout(searchTimer); searchTimer = setTimeout(() => {state.offset = 0; loadItems();}, 300);});
for (const id of ['city-filter', 'family-filter', 'stage-filter', 'sort-filter', 'include-unknown']) $(id).addEventListener('change', () => {state.offset = 0; loadItems();});
$('more-filters').addEventListener('click', () => {const hidden = !$('advanced-filters').hidden; $('advanced-filters').hidden = hidden; $('more-filters').setAttribute('aria-expanded', String(!hidden));});
$('clear-filters').addEventListener('click', () => {for (const id of ['search', 'city-filter', 'family-filter', 'stage-filter']) $(id).value = ''; $('sort-filter').value = 'recent'; $('include-unknown').checked = false; state.classification = ''; state.offset = 0; updateTabs(); loadItems();});
$('previous-page').addEventListener('click', () => {state.offset = Math.max(0, state.offset - state.limit); loadItems();});
$('next-page').addEventListener('click', () => {state.offset += state.limit; loadItems();});
$('integral-filter').addEventListener('click', () => {$('family-filter').value = 'integral'; $('advanced-filters').hidden = false; $('more-filters').setAttribute('aria-expanded', 'true'); state.classification = ''; state.offset = 0; updateTabs(); loadItems();});
$('sync-button').addEventListener('click', async () => {try {$('sync-button').disabled = true; const result = await api('/sync', {method:'POST'}); toast(result.message); setTimeout(() => refreshDashboard().catch(() => {}), 1000);} catch (error) {toast(error.message, true); $('sync-button').disabled = false;}});
$('process-documents').addEventListener('click', async () => {try {$('process-documents').disabled = true; const result = await api('/documents/process', {method:'POST'}); toast(result.message);} catch (error) {toast(error.message, true);} finally {setTimeout(() => refreshDashboard().catch(() => {}), 1000);}});

async function openDetail(ocid) {
  try {
    const item = await api('/opportunities/' + encodeURIComponent(ocid)); state.detail = item;
    const address = item.buyer_address || {};
    const addressText = [address.streetAddress, address.locality, address.region, address.department].filter(Boolean).join(', ');
    const checkMap = new Map((item.document_checks || []).map((d) => [d.url, d]));
    const documents = item.documents.map((doc) => {const check = checkMap.get(doc.url); return `<div class="document-row"><a href="${safeUrl(doc.url)}" target="_blank" rel="noopener noreferrer">${esc(doc.title)} ↗</a><span class="badge ${check?.status === 'read' ? 'open' : 'neutral'}">${esc(check ? docLabels[check.status] || check.status : 'Sin lectura automática')}</span><small>${esc(check?.detail || 'Revisa el documento oficial para confirmar alcance, equipos, cantidades y requisitos.')}</small></div>`;}).join('');
    $('detail-content').innerHTML = `<span class="badge ${esc(item.classification)}">${esc(labels[item.classification])}</span><p class="detail-buyer">${esc(item.buyer)}</p><h2 class="detail-title">${esc(item.title)}</h2><p class="detail-reference">${esc(item.reference)}</p><div class="notice ${item.classification === 'review' ? 'warning' : ''}">${esc(item.status_reason)}</div><div class="detail-stats"><div class="detail-stat"><small>Monto referencial del proceso completo</small><strong>${esc(money(item.amount, item.currency))}</strong></div><div class="detail-stat"><small>Fecha límite publicada · hora de Perú</small><strong>${esc(date(item.deadline, true))}</strong></div><div class="detail-stat"><small>Zona detectada</small><strong>${esc(item.city || 'Sin confirmar')}</strong></div><div class="detail-stat"><small>Publicación del procedimiento</small><strong>${esc(date(item.published))}</strong></div></div><p class="field-help">${esc(item.location_basis)}${addressText ? '<br>Domicilio publicado de la entidad: ' + esc(addressText) : ''}</p><div class="detail-actions"><a class="button primary" href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">Abrir proceso oficial ↗</a><a class="button secondary" href="${safeUrl(item.raw_url)}" target="_blank" rel="noopener noreferrer">Ver registro de origen ↗</a></div><section class="detail-section"><h3>Por qué aparece en tu radar</h3><p>${esc(item.scope)}. Afinidad orientativa: ${number(item.score)}/100; no representa probabilidad de adjudicación.</p>${item.evidence.map((e) => `<div class="evidence"><strong>${esc(e.label)} · ${esc(e.term)}</strong><p>…${esc(e.snippet)}…</p><small>Origen de la coincidencia: ${esc(e.origin)}</small></div>`).join('')}</section><section class="detail-section"><h3>Documentos y términos de referencia</h3><p>Revisa cantidades, dimensiones, jornadas, personal, requisitos y entregables. La lectura automática detecta palabras; no certifica que puedas atender el contrato completo.</p>${documents || '<div class="notice warning">La fuente no publica adjuntos en este registro. Revisa el procedimiento en SEACE.</div>'}${item.documents.length ? '<div class="button-row"><button id="detail-documents" class="button secondary small">Reintentar documentos pendientes ↗</button></div>' : ''}</section>${item.suppliers.length ? `<section class="detail-section"><h3>Adjudicatarios publicados</h3><ul class="supplier-list">${item.suppliers.map((s) => `<li>${esc(s)}</li>`).join('')}</ul><p>Posibles contactos para investigar como aliados. La adjudicación no implica que exista una posibilidad o autorización de subcontratación.</p></section>` : ''}<form id="followup-form" class="detail-form"><h3>Tu siguiente paso</h3><label for="detail-stage">Etapa comercial</label><select id="detail-stage">${['Pendiente','Revisar','Cotizar','Presentada','Descartada'].map((s) => `<option${s === item.stage ? ' selected' : ''}>${s}</option>`).join('')}</select><label for="detail-notes">Notas privadas</label><textarea id="detail-notes" maxlength="6000" placeholder="Qué puedes atender, aliados, requisitos por revisar…">${esc(item.notes)}</textarea><button type="submit" class="button primary">Guardar seguimiento ↗</button></form><p class="field-help">Registro de origen actualizado: ${esc(date(item.source_updated, true))}. Consultado por MOLT: ${esc(date(item.last_seen, true))}.</p>`;
    if (!$('detail-dialog').open) $('detail-dialog').showModal();
    $('followup-form').addEventListener('submit', async (event) => {event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true; try {await api('/opportunities/' + encodeURIComponent(ocid), {method:'PATCH', body:JSON.stringify({stage:$('detail-stage').value, notes:$('detail-notes').value})}); toast('Seguimiento guardado en tu espacio privado.'); await refreshDashboard(); await loadItems();} catch (error) {toast(error.message, true);} finally {button.disabled = false;}});
    if ($('detail-documents')) $('detail-documents').addEventListener('click', async () => {try {const result = await api('/opportunities/' + encodeURIComponent(ocid) + '/documents', {method:'POST'}); toast(result.message);} catch (error) {toast(error.message, true);}});
  } catch (error) {toast(error.message, true);}
}
$('close-detail').addEventListener('click', () => $('detail-dialog').close());
$('detail-dialog').addEventListener('click', (event) => {if (event.target === $('detail-dialog')) {const r = $('detail-dialog').getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) $('detail-dialog').close();}});

async function loadSettings() {
  const data = await api('/settings'); state.settings = data.settings;
  const settings = data.settings;
  $('settings-cities').innerHTML = ['Lima','Cusco','Trujillo','Arequipa'].map((city) => `<label><input type="checkbox" name="city" value="${esc(city)}"${settings.cities.includes(city) ? ' checked' : ''}>${esc(city)}</label>`).join('');
  for (const [id, value] of Object.entries({'email-to':settings.email_to, 'lookback-days':settings.lookback_days, 'scan-hours':settings.scan_interval_hours})) $(id).value = value;
  $('digest-time').value = String(settings.digest_hour).padStart(2, '0') + ':' + String(settings.digest_minute).padStart(2, '0');
  $('email-enabled').checked = settings.email_enabled; $('include-historical').checked = settings.include_historical;
  $('mail-config-note').className = 'notice' + (data.mail.configured ? '' : ' warning');
  $('mail-config-note').textContent = data.mail.configured ? 'Proveedor configurado. Puedes activar el resumen diario. La entrega se confirma al enviar.' : 'Correos pendientes de activar: configura RESEND_API_KEY y MOLT_MAIL_FROM en los ajustes seguros del servidor. El panel y Excel ya pueden utilizarse.';
  $('worker-state').textContent = automationLabel(data.automation) + '. El recolector externo comprueba el horario aproximadamente cada hora; puede demorarse. OECE determina cuándo publica sus datos.';
}
$('settings-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const button = event.target.querySelector('button[type="submit"]'); button.disabled = true;
  try {
    const [hour, minute] = $('digest-time').value.split(':').map(Number);
    const settings = {cities:[...document.querySelectorAll('#settings-cities input:checked')].map((i) => i.value), email_to:$('email-to').value.trim(), email_enabled:$('email-enabled').checked, digest_hour:hour, digest_minute:minute, include_historical:$('include-historical').checked, lookback_days:Number($('lookback-days').value), scan_interval_hours:Number($('scan-hours').value)};
    const result = await api('/settings', {method:'PUT', body:JSON.stringify(settings)}); state.settings = settings;
    $('city-chips').innerHTML = settings.cities.map((c) => `<span>${esc(c)}</span>`).join('');
    $('settings-message').textContent = result.message; toast(result.message); await refreshDashboard();
  } catch (error) {toast(error.message, true); $('settings-message').textContent = error.message;} finally {button.disabled = false;}
});
$('password-form').addEventListener('submit', async (event) => {event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true; try {const result = await api('/auth/password', {method:'POST', body:JSON.stringify({current_password:$('current-password').value, new_password:$('new-password').value})}); state.csrf = result.csrf; $('current-password').value = ''; $('new-password').value = ''; toast(result.message);} catch (error) {toast(error.message, true);} finally {button.disabled = false;}});

async function loadMail() {
  const data = await api('/settings'); state.settings = data.settings;
  $('mail-destination').textContent = data.settings.email_to ? 'Destino: ' + data.settings.email_to : 'Configura tu correo en Preferencias.';
  $('mail-state').className = 'notice' + (data.mail.configured ? '' : ' warning');
  $('mail-state').textContent = data.mail.configured ? data.settings.email_enabled ? 'Resumen automático activado. Se enviará cuando existan novedades y la fuente esté actualizada.' : 'Proveedor configurado. El envío automático está desactivado; puedes enviar manualmente.' : 'El envío todavía no está activo: falta configurar el proveedor y su remitente autorizado. Puedes revisar el resumen y descargar Excel.';
  const last = data.mail.last_run;
  $('mail-info').innerHTML = `<div><dt>Horario programado · Perú</dt><dd>${String(data.settings.digest_hour).padStart(2,'0')}:${String(data.settings.digest_minute).padStart(2,'0')}</dd></div><div><dt>Último resultado</dt><dd>${last ? esc(date(last.created_at, true) + ' · ' + last.message) : 'Todavía no se ha enviado ningún correo.'}</dd></div>`;
  $('send-mail').disabled = !data.mail.configured;
}
$('preview-mail').addEventListener('click', async () => {try {const data = await api('/mail/preview'); $('mail-preview').hidden = false; $('mail-preview').innerHTML = `<p class="eyebrow">VISTA PREVIA · NO ENVÍA CORREOS</p><h3>${number(data.count)} novedades pendientes</h3><p>Destino: ${esc(data.recipient || 'Sin configurar')}. Las históricas solo se incluyen si activaste esa opción.</p>${data.items.length ? data.items.map((i) => `<div class="preview-item"><span class="badge ${esc(i.classification)}">${esc(labels[i.classification])}</span><h3>${esc(i.title)}</h3><p>${esc(i.buyer)} · ${esc(i.notification_reason)}</p></div>`).join('') : '<div class="notice">No hay novedades para enviar con tus preferencias actuales.</div>'}${data.count > 10 ? '<p>El Excel adjunto incluirá todas las novedades; aquí se muestran las primeras diez.</p>' : ''}`;} catch (error) {toast(error.message, true);}});
$('send-mail').addEventListener('click', async () => {$('send-mail').disabled = true; try {const result = await api('/mail/send', {method:'POST'}); toast(result.message); await loadMail();} catch (error) {toast(error.message, true);} finally {await loadMail().catch(() => {});}});

document.addEventListener('keydown', (event) => {if (event.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) && !['mail','settings'].includes(state.view) && state.csrf) {event.preventDefault(); $('search').focus();}});
$('today-label').textContent = new Intl.DateTimeFormat('es-PE', {timeZone:'America/Lima', day:'numeric', month:'long', year:'numeric'}).format(new Date());

async function poll() {
  if (!state.csrf || document.hidden) return;
  try {
    const data = await refreshDashboard();
    const key = JSON.stringify([data.source.scanned, data.source.status, data.source.documents, data.stats.total]);
    if (key !== state.sourceKey) {state.sourceKey = key; if (['radar','followup'].includes(state.view)) await loadItems();}
  } catch { /* The visible source status is preserved; login/errors are handled by explicit requests. */ }
}

(async () => {try {const status = await api('/auth/status'); if (!status.initialized) {showAuth(false); return;} try {await enterApplication(await api('/auth/me'));} catch {showAuth(true);}} catch (error) {$('initial-loading').hidden = true; showAuth(true); $('auth-error').textContent = error.message;}})();
setInterval(poll, 12000);
