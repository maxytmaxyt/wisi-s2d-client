/**
 * player.js – Video Player & Streaming-Steuerung (mpegts.js + Timeshift)
 */
let activeProgIdx = null;
let activeChannelName = '';
let activeChannelFta = true;
let player = null;

function setStandbyVisible(visible) {
  const standby = document.getElementById('videoStandby');
  if (standby) {
    standby.classList.toggle('hidden', !visible);
  }
}

function setTimeshiftEnabled(enabled) {
  const bar = document.getElementById('timeshiftBar');
  if (bar) {
    bar.classList.toggle('disabled-bar', !enabled);
  }
}

function destroyMpegtsPlayer() {
  if (player) {
    try {
      player.pause();
      player.unload();
      player.detachMediaElement();
      player.destroy();
    } catch (e) {
      console.debug('[Player] cleanup:', e);
    }
    player = null;
  }
}

function buildStreamUrl(progIdx) {
  const mode = document.getElementById('streamModeSelect')?.value || 'auto';
  const base = `${window.location.origin}/api/stream/${progIdx}`;
  if (mode === 'raw') return `${base}?raw=1`;
  if (mode === '1') return `${base}?transcode=1`;
  return base;
}

function playChannel(progIdx, name, fta) {
  activeProgIdx = progIdx;
  activeChannelName = name;
  activeChannelFta = Boolean(fta);

  document.getElementById('playerChannelName').textContent = name;
  const ftaBadge = document.getElementById('playerFtaBadge');
  ftaBadge.className = 'tag ' + (fta ? 'fta' : 'enc');
  ftaBadge.textContent = fta ? 'FTA' : 'Pay-TV';

  const ch = currentChannels.find(c => c.prog_idx === progIdx);
  const nowEl = document.getElementById('playerNowPlaying');
  if (nowEl) {
    nowEl.textContent = ch && ch.current_show
      ? `Aktuell: ${ch.current_show}${ch.current_time ? ' · ' + ch.current_time : ''}`
      : 'Live-Signal wird geladen…';
  }

  const videoElement = document.getElementById('videoElement');
  const streamUrl = buildStreamUrl(progIdx);

  destroyMpegtsPlayer();
  if (videoElement) {
    videoElement.removeAttribute('src');
    videoElement.load();
  }

  setStandbyVisible(false);
  setTimeshiftEnabled(true);
  renderChannels();

  if (typeof mpegts !== 'undefined' && mpegts.getFeatureList().mseLivePlayback) {
    player = mpegts.createPlayer({
      type: 'mse',
      isLive: true,
      url: streamUrl
    }, {
      enableWorker: true,
      lazyLoad: false,
      enableStashBuffer: true,
      stashInitialSize: 256 * 1024,
      liveBufferLatencyChasing: false,
      autoCleanupSourceBuffer: false,
      autoCleanupMaxBackwardDuration: 7200,
      autoCleanupMinBackwardDuration: 3600,
    });

    player.on(mpegts.Events.ERROR, (type, detail, info) => {
      console.warn('[Player] mpegts error:', type, detail, info);
      if (type === mpegts.ErrorTypes.MEDIA_ERROR || (detail && String(detail).includes('codec'))) {
        showToast('Codec-Hinweis: Teste "Transcode (H.264)" im Modus-Menü oder "In VLC öffnen".', 'error');
      }
    });

    player.attachMediaElement(videoElement);
    player.load();
    player.play().catch(e => console.log('Autoplay:', e));
  } else {
    videoElement.src = streamUrl;
    videoElement.play().catch(e => console.log('Autoplay:', e));
  }
  showToast('Kanal gewählt: ' + name);
}

function onStreamModeChange() {
  if (activeProgIdx && activeProgIdx > 0) {
    playChannel(activeProgIdx, activeChannelName, activeChannelFta);
  }
}

async function stopStream() {
  destroyMpegtsPlayer();
  const videoElement = document.getElementById('videoElement');
  if (videoElement) {
    videoElement.pause();
    videoElement.removeAttribute('src');
    videoElement.load();
  }
  activeProgIdx = null;
  activeChannelName = '';

  try {
    await fetch('/api/stream/stop', { method: 'POST' });
  } catch (e) {}

  document.getElementById('playerChannelName').textContent = 'Kein Kanal aktiv';
  const ftaBadge = document.getElementById('playerFtaBadge');
  ftaBadge.className = 'tag neutral';
  ftaBadge.textContent = 'Bereit';
  const nowEl = document.getElementById('playerNowPlaying');
  if (nowEl) nowEl.textContent = 'Kein aktiver Stream';

  document.getElementById('metricBitrate').textContent = '0 KB/s';
  document.getElementById('metricBytes').textContent = '0.0 MB';
  document.getElementById('metricDuration').textContent = '00:00';

  setStandbyVisible(true);
  setTimeshiftEnabled(false);
  updateTimeshiftUI();
  renderChannels();
  showToast('Stream gestoppt.');
}

async function copyStreamUrl() {
  if (!activeProgIdx || activeProgIdx <= 0) {
    showToast('Erst Live-Kanal auswählen.', 'error');
    return;
  }
  const url = buildStreamUrl(activeProgIdx);
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(url);
    } else {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    showToast('Stream-URL kopiert: ' + url, 'success');
  } catch (err) {
    showToast('Stream-URL: ' + url);
  }
}

function openInVlc() {
  if (!activeProgIdx || activeProgIdx <= 0) {
    showToast('Erst Live-Kanal auswählen.', 'error');
    return;
  }
  const url = `${window.location.origin}/api/stream/${activeProgIdx}?raw=1`;
  window.location.href = 'vlc://' + url;
  showToast('Öffne VLC mit: ' + url);
}

async function toggleRecording() {
  try {
    const res = await fetch('/api/status');
    const st = await res.json();
    if (st.recording && st.recording.active) {
      const r = await fetch('/api/record/stop', { method: 'POST' });
      const d = await r.json();
      showToast(d.message, d.success ? 'success' : 'error');
      if (typeof loadRecordings === 'function') loadRecordings();
    } else {
      if (!activeProgIdx || activeProgIdx <= 0) {
        showToast('Bitte erst einen Live-Kanal auswählen.', 'error');
        return;
      }
      const r = await fetch('/api/record/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ prog_idx: activeProgIdx })
      });
      const d = await r.json();
      showToast(d.message, d.success ? 'success' : 'error');
    }
    if (typeof pollStatus === 'function') pollStatus();
  } catch (err) {
    showToast('Aufnahme-Fehler: ' + err, 'error');
  }
}

function playRecordedFile(filename) {
  destroyMpegtsPlayer();
  activeProgIdx = 0;
  activeChannelName = filename;
  document.getElementById('playerChannelName').textContent = 'Aufnahme: ' + filename;
  const ftaBadge = document.getElementById('playerFtaBadge');
  ftaBadge.className = 'tag fta';
  ftaBadge.textContent = 'Aufnahme';
  const nowEl = document.getElementById('playerNowPlaying');
  if (nowEl) nowEl.textContent = 'Wiedergabe einer gespeicherten Aufnahme';

  const videoElement = document.getElementById('videoElement');
  const isMp4 = filename.toLowerCase().endsWith('.mp4');
  const playUrl = isMp4
    ? `${window.location.origin}/api/recordings/${encodeURIComponent(filename)}`
    : `${window.location.origin}/api/recordings/stream/${encodeURIComponent(filename)}`;

  setStandbyVisible(false);
  setTimeshiftEnabled(false);
  videoElement.src = playUrl;
  videoElement.controls = true;
  videoElement.play().catch(e => console.log('Wiedergabe:', e));

  renderChannels();
  switchTab('tv');
  showToast('Spiele Aufnahme: ' + filename);
}

function timeshiftSeek(secondsDelta) {
  const videoElement = document.getElementById('videoElement');
  if (!videoElement || videoElement.buffered.length === 0) return;
  const bufStart = videoElement.buffered.start(0);
  const bufEnd = videoElement.buffered.end(videoElement.buffered.length - 1);
  let target = videoElement.currentTime + secondsDelta;
  if (target < bufStart) target = bufStart;
  if (target > bufEnd) target = bufEnd;
  videoElement.currentTime = target;
  updateTimeshiftUI();
}

function timeshiftTogglePause() {
  const videoElement = document.getElementById('videoElement');
  if (!videoElement || !activeProgIdx) return;
  if (videoElement.paused) {
    videoElement.play().catch(() => {});
  } else {
    videoElement.pause();
  }
  updateTimeshiftUI();
}

function timeshiftJumpToLive() {
  const videoElement = document.getElementById('videoElement');
  if (!videoElement || videoElement.buffered.length === 0) return;
  const bufStart = videoElement.buffered.start(0);
  const liveEdge = videoElement.buffered.end(videoElement.buffered.length - 1);
  videoElement.currentTime = Math.max(bufStart, liveEdge - 0.5);
  if (videoElement.paused) {
    videoElement.play().catch(() => {});
  }
  updateTimeshiftUI();
  showToast('Zurück auf Live-Signal');
}

function onTimeshiftSliderChange(val) {
  const videoElement = document.getElementById('videoElement');
  if (!videoElement || videoElement.buffered.length === 0) return;
  const bufStart = videoElement.buffered.start(0);
  const bufEnd = videoElement.buffered.end(videoElement.buffered.length - 1);
  const duration = bufEnd - bufStart;
  if (duration <= 0) return;
  videoElement.currentTime = bufStart + (duration * (val / 100));
  updateTimeshiftUI();
}

function updateTimeshiftUI() {
  const videoElement = document.getElementById('videoElement');
  const badge = document.getElementById('timeshiftBadge');
  const slider = document.getElementById('timeshiftSlider');
  const delayText = document.getElementById('timeshiftDelayText');
  const btnPause = document.getElementById('btnTimeshiftPause');

  if (!videoElement || !badge) return;

  if (btnPause) {
    btnPause.textContent = videoElement.paused ? 'Weiter' : 'Pause';
  }

  if (activeProgIdx === 0) {
    badge.textContent = 'WIEDERGABE';
    badge.className = 'tag tv';
    if (delayText) delayText.textContent = 'Aufnahme';
    return;
  }

  if (!activeProgIdx || videoElement.buffered.length === 0) {
    badge.textContent = 'LIVE';
    badge.className = 'tag fta';
    if (delayText) delayText.textContent = activeProgIdx ? 'Live' : 'Bereit';
    if (slider) slider.value = 100;
    return;
  }

  const bufStart = videoElement.buffered.start(0);
  const bufEnd = videoElement.buffered.end(videoElement.buffered.length - 1);
  const cur = videoElement.currentTime;
  const delay = Math.max(0, bufEnd - cur);

  if (slider && !slider.matches(':active')) {
    const total = bufEnd - bufStart;
    if (total > 0) {
      slider.value = Math.min(100, Math.max(0, Math.round(((cur - bufStart) / total) * 100)));
    }
  }

  if (delay <= 3.0) {
    badge.textContent = 'LIVE';
    badge.className = 'tag fta';
    if (delayText) delayText.textContent = 'Live';
  } else {
    const m = String(Math.floor(delay / 60)).padStart(2, '0');
    const s = String(Math.floor(delay % 60)).padStart(2, '0');
    badge.textContent = `TIMESHIFT (-${m}:${s})`;
    badge.className = 'tag enc';
    if (delayText) delayText.textContent = `-${m}:${s} Min`;
  }
}

async function saveTimeshiftRecording() {
  showToast('Speichere Timeshift als Aufnahme…');
  try {
    const res = await fetch('/api/timeshift/save', { method: 'POST' });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    if (typeof loadRecordings === 'function') loadRecordings();
  } catch (e) {
    showToast('Fehler beim Speichern: ' + e, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const videoElement = document.getElementById('videoElement');
  if (videoElement) {
    videoElement.addEventListener('timeupdate', () => {
      if (activeProgIdx === 0 && !isNaN(videoElement.currentTime)) {
        const cur = Math.round(videoElement.currentTime);
        const m = String(Math.floor(cur / 60)).padStart(2, '0');
        const s = String(cur % 60).padStart(2, '0');
        if (!isNaN(videoElement.duration) && isFinite(videoElement.duration) && videoElement.duration > 0) {
          const tot = Math.round(videoElement.duration);
          const tm = String(Math.floor(tot / 60)).padStart(2, '0');
          const ts = String(tot % 60).padStart(2, '0');
          document.getElementById('metricDuration').textContent = `${m}:${s} / ${tm}:${ts}`;
        } else {
          document.getElementById('metricDuration').textContent = `${m}:${s}`;
        }
      } else if (activeProgIdx && activeProgIdx > 0) {
        updateTimeshiftUI();
      }
    });
  }
});
