/**
 * app.js – UI-Initialisierung, Tab-Navigation, Status-Polling & Steuerung
 */
let currentChannels = [];
let currentFilter = 'all';
let pollInterval = null;

function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.innerText = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3500);
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  const targetPane = document.getElementById('tab-' + tabId);
  if (targetPane) targetPane.classList.add('active');
  const targetBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
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
    const data = await res.json();
    
    // Connection badge
    const badge = document.getElementById('connBadge');
    if (data.connected) {
      badge.className = 'badge connected';
      badge.innerText = '● Verbunden (' + data.ip + ')';
    } else {
      badge.className = 'badge disconnected';
      badge.innerText = '● Getrennt';
    }

    // Signal Gauges (0-100%)
    const rawStr = data.signal.strength || 0;
    const rawQual = data.signal.quality || 0;
    const agc = Math.min(100, Math.max(0, Math.round(rawStr <= 100 ? rawStr : (rawStr * 100 / 255))));
    const snr = Math.min(100, Math.max(0, Math.round(rawQual <= 100 ? rawQual : (rawQual * 100 / 255))));
    document.getElementById('gaugeAgc').style.width = agc + '%';
    document.getElementById('valAgc').innerText = agc + '%';
    document.getElementById('gaugeSnr').style.width = snr + '%';
    document.getElementById('valSnr').innerText = snr + '%';

    const lockBadge = document.getElementById('gaugeLock');
    if (data.signal.locked) {
      lockBadge.className = 'badge connected';
      lockBadge.innerText = '🔒 Gelockt';
    } else {
      lockBadge.className = 'badge';
      lockBadge.innerText = '❌ Kein Lock';
    }

    // Streaming metrics
    if (data.streaming && data.streaming.is_streaming) {
      const kb = Math.round(data.streaming.kbps || 0);
      const mbit = (kb * 8 / 1024).toFixed(1);
      document.getElementById('metricBitrate').innerText = kb + ' KB/s (' + mbit + ' Mbit/s)';
      document.getElementById('metricBytes').innerText = (data.streaming.bytes / 1048576).toFixed(1) + ' MB';
      const dur = Math.round(data.streaming.elapsed || data.streaming.elapsed_seconds || 0);
      const m = String(Math.floor(dur / 60)).padStart(2, '0');
      const s = String(dur % 60).padStart(2, '0');
      document.getElementById('metricDuration').innerText = m + ':' + s;
    }

    // Recording button state
    const recBtn = document.getElementById('btnRecPlayer');
    if (data.recording && data.recording.active) {
      recBtn.className = 'danger';
      recBtn.innerText = '⏹️ Aufnahme stoppen (' + Math.round(data.recording.seconds) + 's)';
    } else {
      recBtn.className = 'secondary';
      recBtn.innerText = '🔴 Aufnahme';
    }

    // Scan progress
    if (data.scan && data.scan.in_progress) {
      document.getElementById('scanBox').style.display = 'block';
      document.getElementById('scanProgressBar').style.width = data.scan.progress + '%';
      document.getElementById('scanProgressText').innerText = data.scan.progress + '%';
      document.getElementById('scanTvCount').innerText = data.scan.tv_count;
      document.getElementById('scanRadioCount').innerText = data.scan.radio_count;
    }
  } catch (err) {}
}

async function connectDongle() {
  const ip = document.getElementById('dongleIpInput').value.trim();
  showToast('Verbinde mit ' + ip + ' …');
  const res = await fetch('/api/connect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ ip })
  });
  const data = await res.json();
  showToast(data.message);
  loadChannels();
  pollStatus();
}

async function discoverDongle() {
  showToast('Suche WISI Dongle im Netzwerk …');
  try {
    const res = await fetch('/api/discover', { method: 'POST' });
    const data = await res.json();
    if (data.devices && data.devices.length > 0) {
      const foundIp = data.devices[0].ip;
      document.getElementById('dongleIpInput').value = foundIp;
      showToast('Dongle gefunden: ' + foundIp);
    } else {
      showToast('Kein Dongle gefunden – prüfe Verbindung.');
    }
  } catch (err) {
    showToast('Fehler bei der Gerätesuche: ' + err);
  }
}

async function loadChannels() {
  try {
    const res = await fetch('/api/channels');
    const data = await res.json();
    currentChannels = data.channels || [];
    renderChannels();
  } catch (e) {
    console.error(e);
  }
}

async function refreshChannels() {
  showToast('Lade Kanalliste frisch vom Dongle…');
  const res = await fetch('/api/channels/refresh', { method: 'POST' });
  const data = await res.json();
  showToast(data.message);
  loadChannels();
}

function setFilter(filt, el) {
  currentFilter = filt;
  document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  renderChannels();
}

function renderChannels() {
  const q = document.getElementById('channelSearch').value.toLowerCase().trim();
  const tbody = document.getElementById('channelsTableBody');
  const filtered = currentChannels.filter(c => {
    if (currentFilter === 'tv' && c.is_radio) return false;
    if (currentFilter === 'radio' && !c.is_radio) return false;
    if (currentFilter === 'fta' && !c.fta) return false;
    if (currentFilter === 'enc' && c.fta) return false;
    if (q) {
      const matchName = c.name.toLowerCase().includes(q);
      const matchLcn = String(c.lcn).includes(q);
      const matchSid = String(c.service_id).includes(q);
      return matchName || matchLcn || matchSid;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Keine Sender gefunden.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(c => `
    <tr>
      <td><strong style="color:var(--text);">${c.lcn || '-'}</strong></td>
      <td>
        <div class="ch-name">${c.name}</div>
        <div class="ch-epg">${c.current_show ? '▶ ' + c.current_show : 'SID ' + c.service_id}</div>
      </td>
      <td><span class="tag ${c.is_radio ? 'radio' : 'tv'}">${c.is_radio ? 'Radio' : 'TV'}</span></td>
      <td>${c.freq} MHz ${c.pol}</td>
      <td><span class="tag ${c.fta ? 'fta' : 'enc'}">${c.fta ? 'FTA' : '🔒 Verschlüsselt'}</span></td>
      <td>
        <button onclick="playChannel(${c.prog_idx}, '${c.name.replace(/'/g, "\\'")}', ${c.fta})">▶ Play</button>
      </td>
    </tr>
  `).join('');
}

async function loadInfo() {
  const res = await fetch('/api/info');
  const data = await res.json();
  const div = document.getElementById('infoTable');
  const info = data.info || {};
  const val = (v) => (v !== undefined && v !== null && v !== '' ? v : '-');
  const hw = (info.hw_version_str !== undefined && info.hw_version_str !== '') ? info.hw_version_str : info.hw_version;
  const sw = (info.sw_version_str !== undefined && info.sw_version_str !== '') ? info.sw_version_str : info.sw_version;
  const ldr = (info.loader_version_str !== undefined && info.loader_version_str !== '') ? info.loader_version_str : info.loader_version;
  div.innerHTML = `
    <table style="max-width:600px;">
      <tr><td>Modellname:</td><td><strong>${val(info.model_name)}</strong></td></tr>
      <tr><td>Tuner-Typ:</td><td>${info.tuner_name || 'DVB-S2'} (${val(info.tuner_type)})</td></tr>
      <tr><td>SVN-Revision:</td><td>${val(info.svn_revision)}</td></tr>
      <tr><td>Hardware-Version:</td><td>${val(hw)}</td></tr>
      <tr><td>Software-Version:</td><td>${val(sw)}</td></tr>
      <tr><td>Loader-Version:</td><td>${val(ldr)}</td></tr>
      <tr><td>Dongle MAC-Adresse:</td><td>${val(info.dongle_mac)}</td></tr>
      <tr><td>Dongle IP-Adresse:</td><td>${val(info.dongle_ip)}</td></tr>
      <tr><td>Client IP-Adresse:</td><td>${val(info.client_ip)}</td></tr>
      <tr><td>CAS-Typ:</td><td>${val(info.cas_type)}</td></tr>
      <tr><td>Seriennummer:</td><td><code>${val(info.serial_id)}</code></td></tr>
      <tr><td>Chip-ID:</td><td><code>${val(info.chip_id)}</code></td></tr>
    </table>
  `;
}

async function loadEpg() {
  const res = await fetch('/api/epg');
  const data = await res.json();
  const grid = document.getElementById('epgGrid');
  const epg = data.epg || {};
  const sids = Object.keys(epg);
  if (sids.length === 0) {
    grid.innerHTML = '<p style="color:var(--text-muted);">Keine EPG-Daten im Speicher. Klicke auf "EPG vom Dongle laden".</p>';
    return;
  }
  grid.innerHTML = sids.map(sid => {
    const events = epg[sid] || [];
    const ch = currentChannels.find(c => c.service_id == sid) || { name: 'SID ' + sid };
    return `
      <div class="epg-card">
        <h3>${ch.name} <span class="tag fta">SID ${sid}</span></h3>
        ${events.slice(0, 4).map(ev => `
          <div class="epg-event-item" style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
            <div>
              <div class="epg-time">${ev.date} ${ev.time} (${ev.duration})</div>
              <div style="font-weight:600; color:#fff;">${ev.title}</div>
            </div>
            <button class="secondary" style="font-size:0.75rem; padding:4px 8px; white-space:nowrap;" onclick="scheduleFromEpg(${sid}, '${ch.name.replace(/'/g, "\\'")}', '${ev.title.replace(/'/g, "\\'")}', '${ev.date}', '${ev.time}', '${ev.duration}')">⏰ Aufnehmen</button>
          </div>
        `).join('')}
      </div>
    `;
  }).join('');
}

async function refreshEpg() {
  showToast('Lade EPG vom Dongle…');
  const res = await fetch('/api/epg/refresh', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ limit: 25 })
  });
  const data = await res.json();
  showToast(data.message);
  loadEpg();
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

// Page Visibility API: 0% CPU wenn Tab im Hintergrund oder minimiert ist
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopPolling();
  } else {
    startPolling();
  }
});

// Init
window.addEventListener('DOMContentLoaded', () => {
  loadChannels();
  startPolling();
});
