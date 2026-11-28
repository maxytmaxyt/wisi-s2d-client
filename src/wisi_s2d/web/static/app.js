/**
 * app.js – UI-Initialisierung, Tab-Navigation, Status-Polling, EPG & Diagnose
 */
let currentChannels = [];
let currentFilter = 'all';
let cachedEpgData = {};
let pollInterval = null;
let toastTimer = null;
let wasConnected = false;
let wasScanning = false;
let ffmpegAvailable = true;

function escapeHtml(val) {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showToast(msg, variant = 'info') {
  const t = document.getElementById('toast');
  if (!t) return;
  if (toastTimer) {
    clearTimeout(toastTimer);
    toastTimer = null;
  }
  t.textContent = msg;
  t.className = variant === 'error' ? 'toast-error' : (variant === 'success' ? 'toast-success' : '');
  t.style.display = 'block';
  toastTimer = setTimeout(() => {
    t.style.display = 'none';
    toastTimer = null;
  }, 3800);
}

/**
 * Konvertiert DVB Modified Julian Date (z. B. "61358"), ISO ("2026-11-14")
 * oder "DD/MM/YYYY" in { iso: "YYYY-MM-DD", display: "DD.MM.YYYY" }.
 */
function parseEpgDateParts(rawDate) {
  const s = String(rawDate || '').trim();
  if (/^\d{5}$/.test(s)) {
    const mjd = parseInt(s, 10);
    if (mjd >= 40000 && mjd <= 99999) {
      const utcMs = Date.UTC(1858, 10, 17) + mjd * 86400000;
      const d = new Date(utcMs);
      const yyyy = d.getUTCFullYear();
      const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
      const dd = String(d.getUTCDate()).padStart(2, '0');
      return { iso: `${yyyy}-${mm}-${dd}`, display: `${dd}.${mm}.${yyyy}` };
    }
  }
  const isoMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) {
    return { iso: s, display: `${isoMatch[3]}.${isoMatch[2]}.${isoMatch[1]}` };
  }
  const slashMatch = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (slashMatch) {
    return {
      iso: `${slashMatch[3]}-${slashMatch[2]}-${slashMatch[1]}`,
      display: `${slashMatch[1]}.${slashMatch[2]}.${slashMatch[3]}`,
    };
  }
  return { iso: '', display: s };
}

function parseEpgDateTime(rawDate, timeStr) {
  const parts = parseEpgDateParts(rawDate);
  const t = String(timeStr || '').trim();
  if (!parts.iso || !/^\d{1,2}:\d{2}$/.test(t)) return 0;
  const hhmm = t.length === 4 ? '0' + t : t;
  const dt = new Date(`${parts.iso}T${hhmm}:00`);
  return isNaN(dt.getTime()) ? 0 : Math.floor(dt.getTime() / 1000);
}

function computeEndTime(timeStr, durStr) {
  const tm = String(timeStr || '').match(/^(\d{1,2}):(\d{2})$/);
  const dm = String(durStr || '').match(/^(\d{1,2}):(\d{2})$/);
  if (!tm || !dm) return '';
  const totalMins = parseInt(tm[1], 10) * 60 + parseInt(tm[2], 10) + parseInt(dm[1], 10) * 60 + parseInt(dm[2], 10);
  const endH = String(Math.floor((totalMins / 60) % 24)).padStart(2, '0');
  const endM = String(totalMins % 60).padStart(2, '0');
  return `${endH}:${endM}`;
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  const targetPane = document.getElementById('tab-' + tabId);
  if (targetPane) targetPane.classList.add('active');
  const targetBtn = document.querySelector(`.tab-btn[data-tab="tab-${tabId}"]`);
  if (targetBtn) targetBtn.classList.add('active');
  if (tabId === 'recordings') {
    loadRecordings();
    loadTimers();
    populateTimerChannels();
  }
  if (tabId === 'info') loadInfo();
  if (tabId === 'epg') loadEpg();
}

async function pollStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();

    if (typeof data.ffmpeg_available === 'boolean') {
      ffmpegAvailable = data.ffmpeg_available;
    }

    // Connection badge & button
    const badge = document.getElementById('connBadge');
    const btnConn = document.getElementById('btnConnect');
    wasConnected = Boolean(data.connected);
    if (data.connected) {
      badge.className = 'badge connected';
      badge.textContent = 'Verbunden (' + data.ip + ')';
      if (btnConn) {
        btnConn.textContent = 'Trennen';
        btnConn.className = 'secondary';
      }
    } else {
      badge.className = 'badge disconnected';
      badge.textContent = 'Getrennt';
      if (btnConn) {
        btnConn.textContent = 'Verbinden';
        btnConn.className = 'primary';
      }
    }

    // Signal Gauges (0-100%)
    const rawStr = data.signal.strength || 0;
    const rawQual = data.signal.quality || 0;
    const agc = Math.min(100, Math.max(0, Math.round(rawStr <= 100 ? rawStr : (rawStr * 100 / 255))));
    const snr = Math.min(100, Math.max(0, Math.round(rawQual <= 100 ? rawQual : (rawQual * 100 / 255))));
    document.getElementById('gaugeAgc').style.width = agc + '%';
    document.getElementById('valAgc').textContent = agc + '%';
    document.getElementById('gaugeSnr').style.width = snr + '%';
    document.getElementById('valSnr').textContent = snr + '%';

    const lockBadge = document.getElementById('gaugeLock');
    if (data.signal.locked) {
      lockBadge.className = 'badge connected';
      lockBadge.textContent = 'Gelockt';
    } else {
      lockBadge.className = 'badge';
      lockBadge.textContent = 'Kein Lock';
    }

    // Tab counters
    const epgBadge = document.getElementById('tabCountEpg');
    if (epgBadge && typeof data.epg_count === 'number') {
      epgBadge.textContent = String(data.epg_count);
    }

    // Streaming metrics
    if (data.streaming && data.streaming.is_streaming) {
      const kb = Math.round(data.streaming.kbps || 0);
      const mbit = (kb * 8 / 1024).toFixed(1);
      document.getElementById('metricBitrate').textContent = `${kb} KB/s (${mbit} Mbit/s)`;
      document.getElementById('metricBytes').textContent = `${(data.streaming.bytes / 1048576).toFixed(1)} MB`;
      const dur = Math.round(data.streaming.elapsed || data.streaming.elapsed_seconds || 0);
      const m = String(Math.floor(dur / 60)).padStart(2, '0');
      const s = String(dur % 60).padStart(2, '0');
      document.getElementById('metricDuration').textContent = `${m}:${s}`;
    } else if (activeProgIdx === null) {
      document.getElementById('metricBitrate').textContent = '0 KB/s';
      document.getElementById('metricBytes').textContent = '0.0 MB';
      document.getElementById('metricDuration').textContent = '00:00';
    }

    // Recording state
    const recBtn = document.getElementById('btnRecPlayer');
    const tabRecBadge = document.getElementById('tabRecBadge');
    const recBanner = document.getElementById('activeRecBanner');
    if (data.recording && data.recording.active) {
      const recSec = Math.round(data.recording.seconds || 0);
      const recMb = ((data.recording.bytes || 0) / 1048576).toFixed(1);
      if (recBtn) {
        recBtn.className = 'danger';
        recBtn.textContent = `Aufnahme stoppen (${recSec}s)`;
      }
      if (tabRecBadge) {
        tabRecBadge.style.display = 'inline-flex';
        tabRecBadge.className = 'tab-count rec-dot';
        tabRecBadge.textContent = `${recSec}s`;
      }
      if (recBanner) {
        recBanner.classList.add('visible');
        document.getElementById('activeRecTitle').textContent = 'Aufnahme läuft: ' + (data.recording.path || '');
        document.getElementById('activeRecMeta').textContent = `${recMb} MB • ${recSec} s`;
      }
    } else {
      if (recBtn) {
        recBtn.className = 'secondary';
        recBtn.textContent = 'Aufnahme';
      }
      if (tabRecBadge) {
        tabRecBadge.style.display = 'none';
      }
      if (recBanner) {
        recBanner.classList.remove('visible');
      }
    }

    // Scan progress & completion
    const scanBox = document.getElementById('scanBox');
    if (data.scan && data.scan.in_progress) {
      wasScanning = true;
      if (scanBox) scanBox.style.display = 'block';
      document.getElementById('scanStatusLabel').textContent = 'Suchlauf läuft…';
      document.getElementById('scanProgressBar').style.width = (data.scan.progress || 0) + '%';
      document.getElementById('scanProgressText').textContent = (data.scan.progress || 0) + '%';
      document.getElementById('scanTvCount').textContent = data.scan.tv_count || 0;
      document.getElementById('scanRadioCount').textContent = data.scan.radio_count || 0;
      const freqEl = document.getElementById('scanFreqText');
      if (freqEl && data.scan.freq) {
        freqEl.textContent = `${data.scan.freq} kHz (${data.scan.symbol_rate || 0} kS/s)`;
      }
    } else if (wasScanning) {
      wasScanning = false;
      document.getElementById('scanStatusLabel').textContent = 'Suchlauf abgeschlossen';
      document.getElementById('scanProgressBar').style.width = '100%';
      document.getElementById('scanProgressText').textContent = '100%';
      showToast('Sendersuchlauf abgeschlossen – Senderliste aktualisiert.', 'success');
      loadChannels();
    }
  } catch (err) {
    // Polling error silently ignored during transient server restarts
  }
}

async function connectOrDisconnectDongle() {
  if (wasConnected) {
    await disconnectDongle();
  } else {
    await connectDongle();
  }
}

async function connectDongle() {
  const ip = document.getElementById('dongleIpInput').value.trim();
  showToast('Verbinde mit ' + ip + ' …');
  try {
    const res = await fetch('/api/connect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ ip })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    await loadChannels();
    await pollStatus();
  } catch (err) {
    showToast('Verbindungsfehler: ' + err, 'error');
  }
}

async function disconnectDongle() {
  try {
    const res = await fetch('/api/disconnect', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
    await pollStatus();
  } catch (err) {
    showToast('Fehler beim Trennen: ' + err, 'error');
  }
}

async function discoverDongle() {
  showToast('Suche WISI Dongle im Netzwerk …');
  try {
    const res = await fetch('/api/discover', { method: 'POST' });
    const data = await res.json();
    if (data.devices && data.devices.length > 0) {
      const foundIp = data.devices[0].ip;
      document.getElementById('dongleIpInput').value = foundIp;
      showToast('Dongle gefunden: ' + foundIp, 'success');
    } else {
      showToast('Kein Dongle gefunden – prüfe Verbindung.', 'error');
    }
  } catch (err) {
    showToast('Fehler bei der Gerätesuche: ' + err, 'error');
  }
}

async function loadChannels() {
  try {
    const res = await fetch('/api/channels');
    if (!res.ok) return;
    const data = await res.json();
    currentChannels = data.channels || [];
    const chBadge = document.getElementById('tabCountChannels');
    if (chBadge) chBadge.textContent = String(currentChannels.length);
    updateFilterCounts();
    renderChannels();
  } catch (e) {
    console.error(e);
  }
}

function updateFilterCounts() {
  const counts = {
    all: currentChannels.length,
    tv: currentChannels.filter(c => !c.is_radio).length,
    radio: currentChannels.filter(c => c.is_radio).length,
    fta: currentChannels.filter(c => c.fta).length,
    enc: currentChannels.filter(c => !c.fta).length,
  };
  const labels = { all: 'Alle', tv: 'TV', radio: 'Radio', fta: 'Frei (FTA)', enc: 'Pay-TV' };
  document.querySelectorAll('.filter-pill[data-filter]').forEach(p => {
    const key = p.getAttribute('data-filter');
    if (key && labels[key]) {
      p.textContent = `${labels[key]} (${counts[key] ?? 0})`;
    }
  });
}

async function refreshChannels() {
  showToast('Lade Kanalliste frisch vom Dongle…');
  try {
    const res = await fetch('/api/channels/refresh', { method: 'POST' });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    await loadChannels();
  } catch (err) {
    showToast('Fehler beim Laden der Senderliste: ' + err, 'error');
  }
}

function setFilter(filt, el) {
  currentFilter = filt;
  document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  renderChannels();
}

function clearChannelSearch() {
  const inp = document.getElementById('channelSearch');
  if (inp) {
    inp.value = '';
    renderChannels();
    inp.focus();
  }
}

function renderChannels() {
  const inp = document.getElementById('channelSearch');
  const clearBtn = document.getElementById('channelSearchClear');
  const q = inp ? inp.value.toLowerCase().trim() : '';
  if (clearBtn) clearBtn.style.display = q ? 'block' : 'none';

  const tbody = document.getElementById('channelsTableBody');
  const filtered = currentChannels.filter(c => {
    if (currentFilter === 'tv' && c.is_radio) return false;
    if (currentFilter === 'radio' && !c.is_radio) return false;
    if (currentFilter === 'fta' && !c.fta) return false;
    if (currentFilter === 'enc' && c.fta) return false;
    if (q) {
      const matchName = (c.name || '').toLowerCase().includes(q);
      const matchLcn = String(c.lcn).includes(q);
      const matchSid = String(c.service_id).includes(q);
      const matchShow = (c.current_show || '').toLowerCase().includes(q);
      return matchName || matchLcn || matchSid || matchShow;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:24px;">Keine Sender gefunden.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(c => {
    const isPlaying = activeProgIdx === c.prog_idx;
    const epgText = c.current_show
      ? `▶ ${c.current_show}${c.current_time ? ' · ' + c.current_time : ''}`
      : `SID ${c.service_id}`;
    return `
      <tr class="${isPlaying ? 'channel-active' : ''}" data-prog-idx="${c.prog_idx}">
        <td class="ch-lcn">${escapeHtml(c.lcn || '-')}</td>
        <td>
          <div class="ch-name">${escapeHtml(c.name)}</div>
          <div class="ch-epg" title="${escapeHtml(epgText)}">${escapeHtml(epgText)}</div>
        </td>
        <td><span class="tag ${c.is_radio ? 'radio' : 'tv'}">${c.is_radio ? 'Radio' : 'TV'}</span></td>
        <td class="ch-freq">${escapeHtml(c.freq)} ${escapeHtml(c.pol)}</td>
        <td><span class="tag ${c.fta ? 'fta' : 'enc'}">${c.fta ? 'FTA' : 'Pay-TV'}</span></td>
        <td>
          <button class="sm ${isPlaying ? 'success' : 'primary'}" data-action="play" data-prog-idx="${c.prog_idx}">${isPlaying ? 'Aktiv' : 'Play'}</button>
        </td>
      </tr>
    `;
  }).join('');
}

async function loadInfo() {
  const div = document.getElementById('infoTable');
  try {
    const res = await fetch('/api/info');
    const data = await res.json();
    const info = data.info || {};
    const val = (v) => (v !== undefined && v !== null && v !== '' ? escapeHtml(v) : '-');
    const hw = (info.hw_version_str !== undefined && info.hw_version_str !== '') ? info.hw_version_str : info.hw_version;
    const sw = (info.sw_version_str !== undefined && info.sw_version_str !== '') ? info.sw_version_str : info.sw_version;
    const ldr = (info.loader_version_str !== undefined && info.loader_version_str !== '') ? info.loader_version_str : info.loader_version;

    const specs = [
      { label: 'Modellname', value: val(info.model_name) },
      { label: 'Tuner-Typ', value: `${val(info.tuner_name || 'DVB-S2')} (${val(info.tuner_type)})` },
      { label: 'SVN-Revision', value: val(info.svn_revision), mono: true },
      { label: 'Hardware-Version', value: val(hw), mono: true },
      { label: 'Software-Version', value: val(sw), mono: true },
      { label: 'Loader-Version', value: val(ldr), mono: true },
      { label: 'Dongle MAC-Adresse', value: val(info.dongle_mac), mono: true },
      { label: 'Dongle IP-Adresse', value: val(info.dongle_ip), mono: true },
      { label: 'Client IP-Adresse', value: val(info.client_ip), mono: true },
      { label: 'CAS-Typ', value: val(info.cas_type), mono: true },
      { label: 'Seriennummer', value: val(info.serial_id), mono: true },
      { label: 'Chip-ID', value: val(info.chip_id), mono: true },
    ];

    div.innerHTML = `<div class="info-grid">${specs.map(s => `
      <div class="info-tile">
        <div class="info-tile-label">${escapeHtml(s.label)}</div>
        <div class="info-tile-val ${s.mono ? 'mono' : ''}">${s.value}</div>
      </div>
    `).join('')}</div>`;
  } catch (err) {
    div.innerHTML = `<p class="empty-msg">Fehler beim Laden: ${escapeHtml(err)}</p>`;
  }
}

async function runOpcodeProbe() {
  const op = document.getElementById('probeOpcodeInput').value.trim();
  const out = document.getElementById('probeOutput');
  out.classList.add('visible');
  out.textContent = 'Sende Opcode ' + op + '…';
  try {
    const res = await fetch('/api/probe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ opcode: op })
    });
    const data = await res.json();
    out.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    out.textContent = 'Fehler: ' + err;
  }
}

async function runPcapAnalyze() {
  const pathVal = document.getElementById('pcapPathInput').value.trim();
  const out = document.getElementById('pcapOutput');
  if (!pathVal) {
    showToast('Bitte Pfad zur PCAP-Datei eingeben.', 'error');
    return;
  }
  out.classList.add('visible');
  out.textContent = 'Analysiere PCAP…';
  try {
    const res = await fetch('/api/pcap/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ path: pathVal })
    });
    const data = await res.json();
    out.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    out.textContent = 'Fehler: ' + err;
  }
}

async function loadEpg() {
  try {
    const res = await fetch('/api/epg');
    const data = await res.json();
    cachedEpgData = data.epg || {};
    renderEpg();
  } catch (err) {
    document.getElementById('epgGrid').innerHTML = `<p class="empty-msg">EPG konnte nicht geladen werden: ${escapeHtml(err)}</p>`;
  }
}

function renderEpg() {
  const grid = document.getElementById('epgGrid');
  const q = (document.getElementById('epgSearch')?.value || '').toLowerCase().trim();
  const sids = Object.keys(cachedEpgData);

  if (sids.length === 0) {
    grid.innerHTML = '<p class="empty-msg">Keine EPG-Daten im Speicher. Klicke auf "EPG vom Dongle laden".</p>';
    return;
  }

  const cards = [];
  for (const sid of sids) {
    const events = cachedEpgData[sid] || [];
    const ch = currentChannels.find(c => String(c.service_id) === String(sid)) || { name: 'SID ' + sid };
    const matchedEvents = q
      ? events.filter(ev =>
          (ch.name || '').toLowerCase().includes(q) ||
          (ev.title || '').toLowerCase().includes(q)
        )
      : events;
    if (matchedEvents.length === 0) continue;

    cards.push(`
      <div class="epg-card">
        <div class="epg-card-header">
          <h4>${escapeHtml(ch.name)}</h4>
          <span class="tag neutral">SID ${escapeHtml(sid)}</span>
        </div>
        ${matchedEvents.slice(0, 5).map((ev, idx) => {
          const dateFmt = parseEpgDateParts(ev.date);
          const endTime = computeEndTime(ev.time, ev.duration);
          const timeRange = endTime ? `${ev.time}–${endTime}` : ev.time;
          return `
            <div class="epg-event-item ${idx === 0 ? 'is-first' : ''}">
              <div style="min-width:0;">
                <div class="epg-time">${escapeHtml(dateFmt.display)} · ${escapeHtml(timeRange)} (${escapeHtml(ev.duration)})</div>
                <div class="epg-title">${escapeHtml(ev.title)}</div>
              </div>
              <button class="secondary sm"
                data-epg-sid="${escapeHtml(sid)}"
                data-epg-ch="${escapeHtml(ch.name)}"
                data-epg-title="${escapeHtml(ev.title)}"
                data-epg-date="${escapeHtml(ev.date)}"
                data-epg-time="${escapeHtml(ev.time)}"
                data-epg-dur="${escapeHtml(ev.duration)}"
                onclick="scheduleFromEpgButton(this)">
                Aufnehmen
              </button>
            </div>
          `;
        }).join('')}
      </div>
    `);
  }

  grid.innerHTML = cards.length > 0
    ? cards.join('')
    : '<p class="empty-msg">Keine passenden Sendungen gefunden.</p>';
}

async function refreshEpg() {
  const btn = document.getElementById('btnRefreshEpg');
  if (btn) btn.disabled = true;
  showToast('Lade EPG vom Dongle…');
  try {
    const res = await fetch('/api/epg/refresh', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ limit: 30 })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    await loadEpg();
    await loadChannels();
  } catch (err) {
    showToast('EPG-Aktualisierung fehlgeschlagen: ' + err, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function startPolling() {
  if (!pollInterval) {
    pollStatus();
    pollInterval = setInterval(pollStatus, 2500);
  }
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopPolling();
  } else {
    startPolling();
  }
});

window.addEventListener('DOMContentLoaded', () => {
  const tbody = document.getElementById('channelsTableBody');
  if (tbody) {
    tbody.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action="play"]');
      if (!btn) return;
      const progIdx = parseInt(btn.getAttribute('data-prog-idx'), 10);
      const ch = currentChannels.find(c => c.prog_idx === progIdx);
      if (ch) playChannel(ch.prog_idx, ch.name, ch.fta);
    });
  }
  loadChannels();
  startPolling();
});
