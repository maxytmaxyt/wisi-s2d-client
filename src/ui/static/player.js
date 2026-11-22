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
      liveBufferLatencyChasing: true,
      liveBufferLatencyMaxLatency: 2.5,
      liveBufferLatencyMinRemain: 0.8,
      autoCleanupSourceBuffer: true,
      autoCleanupMaxBackwardDuration: 30,
      autoCleanupMinBackwardDuration: 10,
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
  const fileUrl = window.location.origin + '/api/recordings/' + encodeURIComponent(filename);

  if (typeof mpegts !== 'undefined' && mpegts.isSupported()) {
    player = mpegts.createPlayer({
      type: 'mse',
      isLive: false,
      url: fileUrl
    }, {
      enableWorker: true,
      lazyLoad: false
    });
    player.attachMediaElement(videoElement);
    player.load();
    player.play().catch(e => console.log('Wiedergabe:', e));
  } else {
    videoElement.src = fileUrl;
    videoElement.play().catch(e => console.log('Wiedergabe:', e));
  }
  switchTab('tv');
  showToast('Spiele Aufnahme: ' + filename);
}
