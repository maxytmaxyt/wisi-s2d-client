/**
 * tuner.js – Transponder-Tuning, Suchlauf & Diagnose-Tools
 */

async function tuneTransponder() {
  const freq = document.getElementById('tuneFreq').value;
  const pol = document.getElementById('tunePol').value;
  const sym = document.getElementById('tuneSr').value;
  const sat_lon = document.getElementById('tuneSat').value;
  showToast('Stelle Transponder ein…');
  const res = await fetch('/api/tuner/tune', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ freq, pol, sym, sat_lon })
  });
  const data = await res.json();
  showToast(data.message);
}

async function startScan() {
  const scan_type = document.getElementById('scanMode').value;
  const search_range = document.getElementById('scanFilter').value;
  showToast('Starte Sendersuchlauf…');
  const res = await fetch('/api/tuner/scan/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ scan_type, search_range, network_scan: scan_type == '2' })
  });
  const data = await res.json();
  showToast(data.message);
  document.getElementById('scanBox').style.display = 'block';
}

async function stopScan() {
  const res = await fetch('/api/tuner/scan/stop', { method: 'POST' });
  const data = await res.json();
  showToast(data.message);
}
