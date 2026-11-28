/**
 * timers.js – Verwaltung von Aufnahmen, Timern & Entschlüsselung
 */

async function loadRecordings() {
  const div = document.getElementById('recordingsList');
  if (!div) return;
  try {
    const res = await fetch('/api/recordings');
    const data = await res.json();
    if (!data.recordings || data.recordings.length === 0) {
      div.innerHTML = '<p class="empty-msg">Keine Aufnahmen vorhanden.</p>';
      return;
    }
    div.innerHTML = data.recordings.map(r => `
      <div class="item-row">
        <div style="min-width:0;">
          <div class="item-row-title">
            <span class="tag ${r.is_mp4 ? 'fta' : 'neutral'}">${r.is_mp4 ? 'MP4' : 'TS'}</span>
            <span>${escapeHtml(r.filename)}</span>
          </div>
          <div class="item-row-sub">${escapeHtml(r.size_mb)} MB · ${escapeHtml(r.created)}</div>
        </div>
        <div class="item-row-actions">
          <button class="primary sm" data-rec-action="play" data-filename="${escapeHtml(r.filename)}">Abspielen</button>
          ${!r.is_mp4 && ffmpegAvailable ? `<button class="secondary sm" data-rec-action="convert" data-filename="${escapeHtml(r.filename)}">In MP4 wandeln</button>` : ''}
          ${!r.is_mp4 ? `<button class="secondary sm" data-rec-action="decrypt" data-filename="${escapeHtml(r.filename)}">Entschlüsseln</button>` : ''}
          <a href="/api/recordings/${encodeURIComponent(r.filename)}" download style="text-decoration:none;">
            <button type="button" class="secondary sm">Download</button>
          </a>
          <button class="danger sm" data-rec-action="delete" data-filename="${escapeHtml(r.filename)}">Löschen</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    div.innerHTML = `<p class="empty-msg">Fehler beim Laden: ${escapeHtml(err)}</p>`;
  }
}

async function convertRecordingToMp4(filename, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = 'Konvertiere…';
  }
  showToast('Konvertiere ' + filename + ' nach MP4…');
  try {
    const res = await fetch('/api/recordings/convert', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ filename })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    loadRecordings();
  } catch (e) {
    showToast('Fehler bei Konvertierung: ' + e, 'error');
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = 'In MP4 wandeln';
    }
  }
}

async function decryptRecording(filename, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = 'Entschlüssele…';
  }
  showToast('Entschlüssele ' + filename + '…');
  try {
    const res = await fetch('/api/recordings/decrypt', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ filename })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    loadRecordings();
  } catch (e) {
    showToast('Fehler bei Entschlüsselung: ' + e, 'error');
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = 'Entschlüsseln';
    }
  }
}

async function deleteRecording(filename) {
  if (!confirm('Aufnahme wirklich löschen: ' + filename + '?')) return;
  try {
    const res = await fetch('/api/recordings/' + encodeURIComponent(filename), { method: 'DELETE' });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    loadRecordings();
  } catch (err) {
    showToast('Fehler beim Löschen: ' + err, 'error');
  }
}

async function loadTimers() {
  const div = document.getElementById('timersList');
  if (!div) return;
  try {
    const res = await fetch('/api/timers');
    const data = await res.json();
    if (!data.timers || data.timers.length === 0) {
      div.innerHTML = '<p class="empty-msg">Keine programmierten Timer vorhanden.</p>';
      return;
    }
    div.innerHTML = data.timers.map(t => {
      let badgeCls = 'scheduled';
      let badgeText = 'Geplant';
      if (t.status === 'recording') { badgeCls = 'enc'; badgeText = 'Nimmt auf'; }
      else if (t.status === 'completed') { badgeCls = 'fta'; badgeText = 'Beendet'; }
      else if (t.status === 'failed') { badgeCls = 'enc'; badgeText = 'Fehler'; }
      else if (t.status === 'expired') { badgeCls = 'neutral'; badgeText = 'Abgelaufen'; }

      return `
        <div class="item-row">
          <div>
            <div class="item-row-title">
              <span>${escapeHtml(t.title)}</span>
              <span class="tag ${badgeCls}">${badgeText}</span>
            </div>
            <div class="item-row-sub">
              ${escapeHtml(t.channel_name)} · Start: ${escapeHtml(t.start_str)} · ${escapeHtml(t.duration_minutes)} Min
            </div>
          </div>
          <div class="item-row-actions">
            <button class="danger sm" onclick="deleteTimer('${escapeHtml(t.id)}')">Löschen</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    div.innerHTML = `<p class="empty-msg">Fehler beim Laden: ${escapeHtml(err)}</p>`;
  }
}

function populateTimerChannels() {
  const sel = document.getElementById('timerChannelSelect');
  if (!sel) return;
  if (currentChannels.length === 0) {
    sel.innerHTML = '<option value="">Keine Sender geladen (erst Senderliste laden)</option>';
    return;
  }
  const prevVal = sel.value;
  sel.innerHTML = currentChannels.map(c => `
    <option value="${c.prog_idx}">${escapeHtml(c.name)} (${c.is_radio ? 'Radio' : 'TV'}, ${c.fta ? 'FTA' : 'Pay-TV'})</option>
  `).join('');
  if (prevVal) sel.value = prevVal;

  const startInp = document.getElementById('timerStartInput');
  if (startInp && !startInp.value) {
    const inFiveMins = new Date(Date.now() + 5 * 60 * 1000);
    inFiveMins.setSeconds(0, 0);
    const tzOffset = inFiveMins.getTimezoneOffset() * 60000;
    startInp.value = (new Date(inFiveMins - tzOffset)).toISOString().slice(0, 16);
  }
}

async function createTimer() {
  const progIdx = parseInt(document.getElementById('timerChannelSelect').value, 10);
  const title = document.getElementById('timerTitleInput').value.trim();
  const startVal = document.getElementById('timerStartInput').value;
  const dur = parseInt(document.getElementById('timerDurationInput').value, 10) || 60;

  if (isNaN(progIdx)) { showToast('Bitte einen Sender auswählen.', 'error'); return; }
  if (!startVal) { showToast('Bitte eine Startzeit angeben.', 'error'); return; }

  const startTs = new Date(startVal).getTime() / 1000;
  if (isNaN(startTs)) { showToast('Ungültiges Datum', 'error'); return; }

  try {
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
    showToast(data.message, data.success ? 'success' : 'error');
    if (data.success) {
      document.getElementById('timerTitleInput').value = '';
      loadTimers();
    }
  } catch (err) {
    showToast('Timer-Fehler: ' + err, 'error');
  }
}

async function deleteTimer(timerId) {
  if (!confirm('Diesen Timer wirklich löschen?')) return;
  try {
    const res = await fetch('/api/timers/' + encodeURIComponent(timerId), { method: 'DELETE' });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    loadTimers();
  } catch (err) {
    showToast('Fehler beim Löschen: ' + err, 'error');
  }
}

function scheduleFromEpgButton(btn) {
  const sid = btn.getAttribute('data-epg-sid');
  const chName = btn.getAttribute('data-epg-ch') || '';
  const title = btn.getAttribute('data-epg-title') || '';
  const dateStr = btn.getAttribute('data-epg-date') || '';
  const timeStr = btn.getAttribute('data-epg-time') || '';
  const durStr = btn.getAttribute('data-epg-dur') || '';
  scheduleFromEpg(sid, chName, title, dateStr, timeStr, durStr);
}

async function scheduleFromEpg(sid, chName, title, dateStr, timeStr, durStr) {
  const ch = currentChannels.find(c => String(c.service_id) === String(sid));
  const progIdx = ch ? ch.prog_idx : 0;
  if (!progIdx) {
    showToast('Kanal nicht gefunden (Senderliste laden).', 'error');
    return;
  }
  let startTs = parseEpgDateTime(dateStr, timeStr);
  const nowSec = Math.floor(Date.now() / 1000);
  if (!startTs || startTs < nowSec) {
    startTs = nowSec;
  }
  let durationMins = 60;
  if (durStr && durStr.includes(':')) {
    const parts = durStr.split(':');
    const parsed = (parseInt(parts[0], 10) * 60) + parseInt(parts[1], 10);
    if (!isNaN(parsed) && parsed > 0) durationMins = parsed;
  }
  showToast('Programmiere Timer für ' + title + '…');
  try {
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
    showToast(data.message, data.success ? 'success' : 'error');
    if (data.success && typeof loadTimers === 'function') loadTimers();
  } catch (err) {
    showToast('Timer-Fehler: ' + err, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const recList = document.getElementById('recordingsList');
  if (recList) {
    recList.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-rec-action]');
      if (!btn) return;
      const action = btn.getAttribute('data-rec-action');
      const filename = btn.getAttribute('data-filename');
      if (!filename) return;
      if (action === 'play') playRecordedFile(filename);
      else if (action === 'convert') convertRecordingToMp4(filename, btn);
      else if (action === 'decrypt') decryptRecording(filename, btn);
      else if (action === 'delete') deleteRecording(filename);
    });
  }
});
