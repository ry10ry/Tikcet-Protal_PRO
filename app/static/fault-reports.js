function renderFaultReports(container) {
  container.insertAdjacentHTML('afterbegin', `
    <section class="panel fault-report-panel">
      <h2>Monthly Fault Ticket Trend</h2>
      <p>Fault Tickets created each month, including Public and Internal (SGT).</p>
      <div data-trend aria-live="polite">Loading monthly trend…</div>
    </section>
    <section class="panel fault-report-panel">
      <h2>Ticket Intake</h2>
      <div class="fault-report-actions">
        <button type="button" data-calculate>Intake</button>
        <button type="button" class="secondary" data-download hidden>Download CSV</button>
      </div>
      <p data-intake-status role="status" hidden></p>
      <div class="fault-report-scroll" data-intake></div>
    </section>`);

  const trend = container.querySelector('[data-trend]');
  api('/report/fault-trend').then(data => drawFaultTrend(trend, data))
    .catch(error => { trend.textContent = error.message; });

  const calculate = container.querySelector('[data-calculate]');
  const download = container.querySelector('[data-download]');
  const status = container.querySelector('[data-intake-status]');
  const intake = container.querySelector('[data-intake]');
  let report;
  calculate.onclick = async () => {
    calculate.disabled = true;
    status.hidden = false;
    status.textContent = 'Calculating Engineer intake…';
    try {
      report = await api('/report/engineer-intake');
      intake.innerHTML = `<table>
        <caption>Fault Ticket intake for ${escape(report.month)} (SGT)</caption>
        <thead><tr><th scope="col">Engineer</th><th scope="col">This month</th><th scope="col">All time</th></tr></thead>
        <tbody>${report.rows.map(row => `<tr><th scope="row">${escape(row.name)}</th><td>${row.month}</td><td>${row.total}</td></tr>`).join('')}</tbody>
        <tfoot><tr><th scope="row">Total</th><td>${report.totals.month}</td><td>${report.totals.total}</td></tr></tfoot>
      </table>`;
      status.textContent = '';
      status.hidden = true;
      download.hidden = false;
    } catch (error) {
      status.textContent = report ? `${error.message} Showing the last successful result.` : error.message;
    } finally {
      calculate.disabled = false;
    }
  };
  download.onclick = () => downloadFaultIntake(report);
}

function drawFaultTrend(element, report) {
  element.innerHTML = `
    <p>Last 12 months · Current month through ${escape(report.as_of)} (SGT)</p>
    <div class="fault-report-scroll"><canvas width="840" height="250" aria-hidden="true"></canvas></div>
    <p data-month-detail aria-live="polite"></p>
    <details><summary>Monthly counts</summary>
      <div class="fault-report-scroll"><table>
        <thead><tr><th scope="col">Month</th><th scope="col">Total</th><th scope="col">Public</th><th scope="col">Internal</th></tr></thead>
        <tbody>${report.months.map(row => `<tr><th scope="row">${escape(row.month)}</th><td>${row.total}</td><td>${row.public}</td><td>${row.internal}</td></tr>`).join('')}</tbody>
      </table></div>
    </details>`;

  const canvas = element.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const detail = element.querySelector('[data-month-detail]');
  const showMonth = row => {
    detail.textContent = `${row.month} · ${row.total} total · ${row.public} Public · ${row.internal} Internal`;
  };
  showMonth(report.months.at(-1));
  if (!ctx) return;

  const left = 54;
  const right = canvas.width - 32;
  const top = 28;
  const bottom = canvas.height - 42;
  const step = Math.max(1, Math.ceil(Math.max(...report.months.map(row => row.total)) / 4));
  const spacing = (right - left) / (report.months.length - 1);
  const points = report.months.map((row, i) => ({
    x: left + i * spacing, y: bottom - row.total * (bottom - top) / (4 * step)
  }));

  ctx.font = '14px Segoe UI, sans-serif';
  ctx.fillStyle = '#405475';
  ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const y = bottom - i * (bottom - top) / 4;
    ctx.strokeStyle = '#dce4f2';
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
    ctx.fillText(String(i * step), left - 8, y + 5);
  }
  ctx.textAlign = 'center';
  points.forEach((point, i) => ctx.fillText(report.months[i].month.slice(2), point.x, bottom + 25));

  ctx.strokeStyle = '#2357d8';
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, i) => {
    if (i === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();
  ctx.fillStyle = '#2357d8';
  for (const point of points) {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 4, 0, 2 * Math.PI);
    ctx.fill();
  }
  canvas.addEventListener('pointermove', event => {
    const x = (event.clientX - canvas.getBoundingClientRect().left) * canvas.width / canvas.clientWidth;
    const index = Math.max(0, Math.min(points.length - 1, Math.round((x - left) / spacing)));
    if (canvas.dataset.month !== String(index)) {
      canvas.dataset.month = index;
      showMonth(report.months[index]);
    }
  });
}

function downloadFaultIntake(report) {
  const csvCell = value => {
    const text = String(value);
    const safe = /^[\s]*[=+@-]/.test(text) ? "'" + text : text;
    return '"' + safe.replaceAll('"', '""') + '"';
  };
  const rows = [
    ['Engineer', `This month (${report.month}, SGT)`, 'All time'],
    ...report.rows.map(row => [row.name, row.month, row.total]),
    ['Total', report.totals.month, report.totals.total]
  ];
  if (report.unmatched_legacy_entries) {
    rows.push(['Older records without a unique account', '', report.unmatched_legacy_entries]);
  }
  const csv = rows.map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
  const url = URL.createObjectURL(new Blob(['\ufeff', csv], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = `MOMCC-engineer-intake-${report.month}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
