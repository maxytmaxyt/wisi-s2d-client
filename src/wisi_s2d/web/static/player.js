/**
 * player.js – Video Player & Streaming-Steuerung (mpegts.js)
 */
let activeProgIdx = null;
let player = null;

function playChannel(progIdx, name, fta) {
  activeProgIdx = progIdx;
  document.getElementById('playerChannelName').innerText = name;
  const ftaBadge = document.getElementById('playerFtaBadge');
  ftaBadge.className = 'tag ' + (fta ? 'fta' : 'enc');
  ftaBadge.innerText = fta ? 'FTA' : '🔒 Pay-TV';

  const videoElement = document.getElementById('videoElement');
  const streamUrl = window.location.origin + '/api/stream/' + progIdx;

  if (typeof mpegts !== 'undefined' && mpegts.getFeatureList().mseLivePlayback) {
    if (player) {
      player.pause();
      player.unload();
      player.detachMediaElement();
      player.destroy();
      player = null;
    }

    player = mpegts.createPlayer({
      type: 'mse',
      isLive: true,
      url: streamUrl
    }, {
      enableWorker: true,
      lazyLoad: false,
      enableStashBuffer: true,
      stashInitialSize: 256 * 1024,        // 256 KB Puffer (~1s) gegen Ruckler
      liveBufferLatencyChasing: false,     // Timeshift: Erlaubt Pausieren & Zurückspulen
      autoCleanupSourceBuffer: false,       // Timeshift: Löscht bisheriges Video nicht
      autoCleanupMaxBackwardDuration: 7200, // Bis zu 2 Stunden Puffer
      autoCleanupMinBackwardDuration: 3600,
    });

    player.on(mpegts.Events.ERROR, (type, detail, info) => {
      console.warn('[Player] mpegts error:', type, detail, info);
      if (type === mpegts.ErrorTypes.MEDIA_ERROR || (detail && detail.includes('codec'))) {
        showToast('ℹ️ SD-Sender (MPEG-2): Klicke auf "🎬 In VLC öffnen" oder teste einen HD-Sender (z. B. ZDF HD).');
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

async function stopStream() {
  if (player) {
    player.pause();
    player.unload();
  }
  await fetch('/api/stream/stop', { method: 'POST' });
  document.getElementById('playerChannelName').innerText = 'Kein Kanal aktiv';
  showToast('Stream gestoppt.');
}

function copyStreamUrl() {
  if (!activeProgIdx) { showToast('Erst Kanal auswählen.'); return; }
  const url = window.location.origin + '/api/stream/' + activeProgIdx;
  navigator.clipboard.writeText(url);
  showToast('Stream-URL in Zwischenablage kopiert: ' + url);
}

function openInVlc() {
  if (!activeProgIdx) { showToast('Erst Kanal auswählen.'); return; }
  const url = window.location.origin + '/api/stream/' + activeProgIdx + '?raw=1';
  window.location.href = 'vlc://' + url;
  showToast('Öffne VLC mit: ' + url);
}

async function toggleRecording() {
  const res = await fetch('/api/status');
  const st = await res.json();
  if (st.recording && st.recording.active) {
    const r = await fetch('/api/record/stop', { method: 'POST' });
    const d = await r.json();
    showToast(d.message);
  } else {
    const r = await fetch('/api/record/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ prog_idx: activeProgIdx })
    });
    const d = await r.json();
    showToast(d.message);
  }
}

function playRecordedFile(filename) {
  if (player) {
    player.pause();
    player.unload();
    player.detachMediaElement();
    player.destroy();
    player = null;
  }
  activeProgIdx = 0;
  document.getElementById('playerChannelName').innerText = '📼 Aufnahme: ' + filename;
  const ftaBadge = document.getElementById('playerFtaBadge');
  ftaBadge.className = 'tag fta';
  ftaBadge.innerText = 'Aufnahme';

  const videoElement = document.getElementById('videoElement');
  const isMp4 = filename.toLowerCase().endsWith('.mp4');
  const playUrl = isMp4
    ? window.location.origin + '/api/recordings/' + encodeURIComponent(filename)
    : window.location.origin + '/api/recordings/stream/' + encodeURIComponent(filename);

  videoElement.src = playUrl;
  videoElement.controls = true;
  videoElement.play().catch(e => console.log('Wiedergabe:', e));

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
  if (!videoElement) return;
  if (videoElement.paused) {
    videoElement.play();
  } else {
    videoElement.pause();
  }
  updateTimeshiftUI();
}

function timeshiftJumpToLive() {
  const videoElement = document.getElementById('videoElement');
  if (!videoElement || videoElement.buffered.length === 0) return;
  const liveEdge = videoElement.buffered.end(videoElement.buffered.length - 1);
  videoElement.currentTime = Math.max(0, liveEdge - 0.5);
  if (videoElement.paused) {
    videoElement.play();
  }
  updateTimeshiftUI();
  showToast('🔴 Zurück auf Live-Signal');
}

function onTimeshiftSliderChange(val) {
  const videoElement = document.getElementById('videoElement');
  if (!videoElement || videoElement.buffered.length === 0) return;
  const bufStart = videoElement.buffered.start(0);
  const bufEnd = videoElement.buffered.end(videoElement.buffered.length - 1);
  const duration = bufEnd - bufStart;
  if (duration <= 0) return;
  const target = bufStart + (duration * (val / 100));
  videoElement.currentTime = target;
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
    btnPause.innerText = videoElement.paused ? '▶️ Weiter' : '⏸️ Pause';
  }

  if (videoElement.buffered.length === 0) {
    badge.innerText = '🔴 LIVE';
    badge.className = 'tag fta';
    if (delayText) delayText.innerText = 'Live';
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
    badge.innerText = '🔴 LIVE';
    badge.className = 'tag fta';
    if (delayText) delayText.innerText = 'Live';
  } else {
    const m = String(Math.floor(delay / 60)).padStart(2, '0');
    const s = String(Math.floor(delay % 60)).padStart(2, '0');
    badge.innerText = `⏳ TIMESHIFT (-${m}:${s})`;
    badge.className = 'tag enc';
    if (delayText) delayText.innerText = `-${m}:${s} Min`;
  }
}

async function saveTimeshiftRecording() {
  showToast('💾 Speichere Timeshift als Aufnahme…');
  try {
    const res = await fetch('/api/timeshift/save', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
    if (typeof loadRecordings === 'function') loadRecordings();
  } catch (e) {
    showToast('Fehler beim Speichern: ' + e);
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
          document.getElementById('metricDuration').innerText = `${m}:${s} / ${tm}:${ts}`;
        } else {
          document.getElementById('metricDuration').innerText = `${m}:${s}`;
        }
      } else if (activeProgIdx && activeProgIdx > 0) {
        updateTimeshiftUI();
      }
    });
  }
});
