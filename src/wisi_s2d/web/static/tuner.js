/**
 * tuner.js – Transponder-Tuning & Sendersuchlauf
 */

function applyTransponderPreset(freq, pol, sr, sat) {
  document.getElementById('tuneFreq').value = freq;
  document.getElementById('tunePol').value = pol;
  document.getElementById('tuneSr').value = sr;
  document.getElementById('tuneSat').value = sat;
  showToast(`Preset geladen: ${freq} MHz ${pol} ${sr} kS/s`);
}

async function tuneTransponder() {
  const freq = document.getElementById('tuneFreq').value;
  const pol = document.getElementById('tunePol').value;
  const sym = document.getElementById('tuneSr').value;
  const sat_lon = document.getElementById('tuneSat').value;
  showToast('Stelle Transponder ein…');
  try {
    const res = await fetch('/api/tuner/tune', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ freq, pol, sym, sat_lon })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
  } catch (err) {
    showToast('Tuner-Fehler: ' + err, 'error');
  }
}

async function startScan() {
  const scan_type = parseInt(document.getElementById('scanMode').value, 10) || 0;
  const search_range = parseInt(document.getElementById('scanFilter').value, 10) || 0;
  showToast('Starte Sendersuchlauf…');
  try {
    const res = await fetch('/api/tuner/scan/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        scan_type,
        search_range,
        network_scan: scan_type === 2
      })
    });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
    if (data.success) {
      document.getElementById('scanBox').style.display = 'block';
    }
  } catch (err) {
    showToast('Suchlauf-Fehler: ' + err, 'error');
  }
}

async function stopScan() {
  try {
    const res = await fetch('/api/tuner/scan/stop', { method: 'POST' });
    const data = await res.json();
    showToast(data.message, data.success ? 'success' : 'error');
  } catch (err) {
    showToast('Fehler beim Abbrechen: ' + err, 'error');
  }
}
