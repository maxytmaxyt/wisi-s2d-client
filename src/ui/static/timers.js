/**
 * timers.js – Verwaltung von Aufnahmen, Timern & Entschlüsselung
 */

async function loadRecordings() {
  const res = await fetch('/api/recordings');
  const data = await res.json();
  const div = document.getElementById('recordingsList');
  if (!div) return;
  if (!data.recordings || data.recordings.length === 0) {
    div.innerHTML = '<p style="color:var(--text-muted);">Keine Aufnahmen vorhanden.</p>';
    return;
  }
  div.innerHTML = data.recordings.map(r => `
    <div style="background:#1e293b; padding:12px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
      <div>
        <div style="font-weight:600; color:#fff;">
          ${r.is_mp4 ? '🎬 <span class="tag fta" style="font-size:0.7rem; padding:2px 6px;">MP4</span>' : '📼 <span class="tag" style="background:#64748b; font-size:0.7rem; padding:2px 6px;">TS</span>'} ${r.filename}
        </div>
        <div style="font-size:0.75rem; color:var(--text-muted);">${r.size_mb} MB • ${r.created}</div>
      </div>
      <div style="display:flex; gap:6px; flex-wrap:wrap;">
        <button class="primary" style="font-size:0.75rem; padding:4px 8px;" onclick="playRecordedFile('${r.filename.replace(/'/g, "\\'")}')">▶️ Abspielen</button>
        ${!r.is_mp4 ? `<button class="secondary" style="font-size:0.75rem; padding:4px 8px;" onclick="convertRecordingToMp4('${r.filename.replace(/'/g, "\\'")}')">⚡ In MP4 wandeln</button>` : ''}
        <a href="/api/recordings/${encodeURIComponent(r.filename)}" download>
          <button class="secondary" style="font-size:0.75rem; padding:4px 8px;">📥 Download</button>
        </a>
        <button class="danger" style="font-size:0.75rem; padding:4px 8px;" onclick="deleteRecording('${r.filename.replace(/'/g, "\\'")}')">🗑️ Löschen</button>
      </div>
    </div>
  `).join('');
}

async function convertRecordingToMp4(filename) {
  showToast('Konvertiere ' + filename + ' nach MP4…');
  try {
    const res = await fetch('/api/recordings/convert', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ filename: filename })
    });
    const data = await res.json();
    showToast(data.message);
    loadRecordings();
  } catch (e) {
    showToast('Fehler bei Konvertierung: ' + e);
  }
}

async function deleteRecording(filename) {
  if (!confirm('Aufnahme wirklich löschen: ' + filename + '?')) return;
  const res = await fetch('/api/recordings/' + encodeURIComponent(filename), { method: 'DELETE' });
  const data = await res.json();
  showToast(data.message);
  loadRecordings();
}

async function loadTimers() {
  const res = await fetch('/api/timers');
  const data = await res.json();
  const div = document.getElementById('timersList');
  if (!div) return;
  if (!data.timers || data.timers.length === 0) {
    div.innerHTML = '<p style="color:var(--text-muted); font-size:0.85rem;">Keine programmierten Timer vorhanden.</p>';
    return;
  }
  div.innerHTML = data.timers.map(t => {
    let statusBadge = '<span class="tag" style="background:#3b82f6;">Geplant</span>';
    if (t.status === 'recording') statusBadge = '<span class="tag" style="background:#ef4444; animation:pulse 1s infinite;">🔴 Nimmt auf</span>';
    if (t.status === 'completed') statusBadge = '<span class="tag fta">Beendet</span>';
    if (t.status === 'failed') statusBadge = '<span class="tag enc">Fehler</span>';
    if (t.status === 'expired') statusBadge = '<span class="tag" style="background:#6b7280;">Abgelaufen</span>';

    return `
      <div style="background:#1e293b; padding:10px 12px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <div style="font-weight:600; color:#fff; display:flex; align-items:center; gap:8px;">
            ${t.title} ${statusBadge}
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
            ${t.channel_name} • Start: ${t.start_str} • ${t.duration_minutes} Min
          </div>
        </div>
        <div>
          <button class="danger" style="font-size:0.75rem; padding:4px 8px;" onclick="deleteTimer('${t.id}')">🗑️ Löschen</button>
        </div>
      </div>
    `;
  }).join('');
}

function populateTimerChannels() {
  const sel = document.getElementById('timerChannelSelect');
  if (!sel) return;
  if (currentChannels.length === 0) {
    sel.innerHTML = '<option value="">Keine Sender geladen (erst Senderliste laden)</option>';
    return;
  }
  sel.innerHTML = currentChannels.map(c => `
    <option value="${c.prog_idx}">${c.name} (${c.is_radio ? 'Radio' : 'TV'}, ${c.fta ? 'FTA' : 'Pay-TV'})</option>
  `).join('');

  const startInp = document.getElementById('timerStartInput');
  if (startInp && !startInp.value) {
    const inFiveMins = new Date(Date.now() + 5 * 60 * 1000);
    inFiveMins.setSeconds(0, 0);
    const tzOffset = inFiveMins.getTimezoneOffset() * 60000;
    const localISOTime = (new Date(inFiveMins - tzOffset)).toISOString().slice(0, 16);
    startInp.value = localISOTime;
  }
}

async function createTimer() {
  const progIdx = parseInt(document.getElementById('timerChannelSelect').value, 10);
  const title = document.getElementById('timerTitleInput').value.trim();
  const startVal = document.getElementById('timerStartInput').value;
  const dur = parseInt(document.getElementById('timerDurationInput').value, 10) || 60;

  if (!progIdx) { showToast('Bitte einen Sender auswählen.'); return; }
  if (!startVal) { showToast('Bitte eine Startzeit angeben.'); return; }

  const startTs = new Date(startVal).getTime() / 1000;
  if (isNaN(startTs)) { showToast('Ungültiges Datum'); return; }

  const res = await fetch('/api/timers', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      prog_idx: progIdx,
      title: title || 'Aufnahme',
      start_time: startTs,
      duration_minutes: dur
    })
  });
  const data = await res.json();
  showToast(data.message);
  if (data.success) {
    document.getElementById('timerTitleInput').value = '';
    loadTimers();
  }
}

async function deleteTimer(timerId) {
  if (!confirm('Diesen Timer wirklich löschen?')) return;
  const res = await fetch('/api/timers/' + encodeURIComponent(timerId), { method: 'DELETE' });
  const data = await res.json();
  showToast(data.message);
  loadTimers();
}

async function scheduleFromEpg(sid, chName, title, dateStr, timeStr, durStr) {
  const ch = currentChannels.find(c => c.service_id == sid);
  const progIdx = ch ? ch.prog_idx : 0;
  if (!progIdx) {
    showToast('Kanal nicht gefunden (Senderliste laden).');
    return;
  }
  let startTs = 0;
  try {
    const dt = new Date(`${dateStr}T${timeStr}:00`);
    if (!isNaN(dt.getTime())) {
      startTs = dt.getTime() / 1000;
    }
  } catch (e) {}
  if (!startTs || startTs < Date.now() / 1000) {
    startTs = Math.floor(Date.now() / 1000);
  }
  let durationMins = 60;
  if (durStr && durStr.includes(':')) {
    const parts = durStr.split(':');
    durationMins = (parseInt(parts[0], 10) * 60) + parseInt(parts[1], 10);
  }
  showToast('Programmiere Timer für ' + title + '…');
  const res = await fetch('/api/timers', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      prog_idx: progIdx,
      title: title || (chName + ' Sendung'),
      start_time: startTs,
      duration_minutes: durationMins
    })
  });
  const data = await res.json();
  showToast(data.message);
}
