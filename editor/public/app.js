// Suffet topo editor — SPA. Fetches /api/boulders, lets the user edit, then
// PUTs the whole shape back. Line drawing is inlined here rather than reusing
// the standalone annotator's HTML, because we want the same in-page flow for
// adding + editing.

const GRADES = [
    'Project',
    '3', '3+', '4a', '4b', '4c',
    '5a', '5b', '5c',
    '6a', '6a+', '6b', '6b+', '6c', '6c+',
    '7a', '7a+', '7b', '7b+', '7c', '7c+',
    '8a', '8a+', '8b', '8b+', '8c', '8c+',
    '9a',
];

// Same palette as topo/style.py (line_palette). Cycled by (no - 1) mod len.
const LINE_PALETTE = ['#004AAD', '#E4572E', '#6AB0AB', '#A096EF', '#E0A21B'];

// -----------------------------------------------------------------------------
// State
// -----------------------------------------------------------------------------

const state = {
    boulders: [],       // [{ _id, name, photo, problems: [{ _id, no, ... }] }]
    photos: [],
    selectedId: null,   // boulder _id
    drawingPid: null,   // problem _id currently being drawn
    dirty: false,
};

let uidSeq = 0;
const uid = () => `x${++uidSeq}`;

// -----------------------------------------------------------------------------
// Dom refs
// -----------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);
const els = {
    body: document.body,
    status: $('#status'),
    save: $('#save'),
    generate: $('#generate'),
    generateLog: $('#generate-log'),
    generateLogTitle: $('#generate-log-title'),
    generateLogBody: $('#generate-log-body'),
    generateLogClose: $('#generate-log-close'),
    generateFiles: $('#generate-files'),
    generateLoading: $('#generate-loading'),
    addBoulder: $('#add-boulder'),
    list: $('#boulder-list'),
    empty: $('#empty'),
    detail: $('#detail'),
    name: $('#f-name'),
    photo: $('#f-photo'),
    pickPhoto: $('#pick-photo'),
    uploadPhoto: $('#upload-photo'),
    uploadInput: $('#upload-input'),
    canvasWrap: $('#canvas-wrap'),
    img: $('#photo'),
    overlay: $('#overlay'),
    canvasHint: $('#canvas-hint'),
    addProblem: $('#add-problem'),
    problemList: $('#problem-list'),
    tpl: $('#problem-row-tpl'),
};

// -----------------------------------------------------------------------------
// Load / save
// -----------------------------------------------------------------------------

async function loadAll() {
    setStatus('Loading…');
    const [bRes, pRes] = await Promise.all([
        fetch('/api/boulders').then((r) => r.json()),
        fetch('/api/photos').then((r) => r.json()),
    ]);
    state.boulders = (bRes.boulders || []).map((b) => ({
        _id: uid(),
        ...b,
        problems: (b.problems || []).map((p) => ({ _id: uid(), ...p })),
    }));
    state.photos = pRes.photos || [];
    if (state.boulders.length) {
        state.selectedId = state.boulders[0]._id;
    }
    setDirty(false);
    render();
    setStatus(`${state.boulders.length} boulders`);
}

async function saveAll() {
    setStatus('Saving…');
    // Strip internal _id fields before sending back.
    const payload = {
        boulders: state.boulders.map((b) => ({
            name: b.name,
            photo: b.photo,
            problems: b.problems.map((p) => ({
                no: Number(p.no) || 0,
                problem: p.problem || '',
                grade: p.grade || '',
                notes: p.notes || '',
                notes_fr: p.notes_fr || '',
                line: p.line || '',
            })),
        })),
    };
    const res = await fetch('/api/boulders', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setStatus(`Save failed: ${err.error || res.status}`);
        return;
    }
    setDirty(false);
    setStatus('Saved.');
    setTimeout(() => setStatus(''), 2000);
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function setStatus(msg) {
    els.status.textContent = msg;
}

function setDirty(v) {
    state.dirty = v;
    els.body.classList.toggle('dirty', v);
}

function markDirty() {
    setDirty(true);
}

function selectedBoulder() {
    return state.boulders.find((b) => b._id === state.selectedId) || null;
}

function colorFor(no) {
    if (!no || no < 1) return LINE_PALETTE[0];
    return LINE_PALETTE[(no - 1) % LINE_PALETTE.length];
}

// Line strings are stored as "x1,y1 x2,y2 …" where each value is a percent
// (0–100) of the photo's width/height. Same format the annotator writes.
function parseLine(s) {
    if (!s || typeof s !== 'string') return [];
    return s
        .trim()
        .split(/\s+/)
        .map((pair) => {
            const [x, y] = pair.split(',').map(Number);
            return { x, y };
        })
        .filter((pt) => Number.isFinite(pt.x) && Number.isFinite(pt.y));
}
function stringifyLine(pts) {
    return pts.map((p) => `${round2(p.x)},${round2(p.y)}`).join(' ');
}
function round2(n) {
    return Math.round(n * 100) / 100;
}

// -----------------------------------------------------------------------------
// Rendering — sidebar
// -----------------------------------------------------------------------------

function render() {
    renderSidebar();
    renderDetail();
    renderOverlay();
}

function renderSidebar() {
    els.list.innerHTML = '';
    for (const b of state.boulders) {
        const li = document.createElement('li');
        if (b._id === state.selectedId) li.classList.add('active');
        li.dataset.id = b._id;

        const thumb = document.createElement('div');
        thumb.className = 'thumb';
        if (b.photo) thumb.style.backgroundImage = `url('/photos/${encodeURIComponent(b.photo)}')`;

        const meta = document.createElement('div');
        meta.className = 'meta';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = b.name || '(unnamed)';
        const sub = document.createElement('div');
        sub.className = 'sub';
        const n = b.problems.length;
        sub.textContent = `${n} problem${n === 1 ? '' : 's'}  ·  ${b.photo || 'no photo'}`;
        meta.append(title, sub);

        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'row-delete';
        del.title = 'Delete this boulder';
        del.setAttribute('aria-label', 'Delete boulder');
        del.textContent = '×';
        del.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteBoulder(b);
        });

        li.append(thumb, meta, del);
        li.addEventListener('click', () => {
            state.selectedId = b._id;
            state.drawingPid = null;
            render();
        });
        els.list.append(li);
    }
}

function deleteBoulder(b) {
    if (!confirm(`Delete boulder "${b.name || '(unnamed)'}" and its ${b.problems.length} problem(s)?`)) {
        return;
    }
    const idx = state.boulders.findIndex((x) => x._id === b._id);
    state.boulders.splice(idx, 1);
    if (state.selectedId === b._id) {
        state.selectedId = state.boulders[Math.min(idx, state.boulders.length - 1)]?._id || null;
        state.drawingPid = null;
    }
    render();
    markDirty();
}

// -----------------------------------------------------------------------------
// Rendering — detail pane
// -----------------------------------------------------------------------------

function renderDetail() {
    const b = selectedBoulder();
    if (!b) {
        els.empty.hidden = false;
        els.detail.hidden = true;
        return;
    }
    els.empty.hidden = true;
    els.detail.hidden = false;

    els.name.value = b.name || '';
    els.photo.value = b.photo || '';
    els.img.src = b.photo ? `/photos/${encodeURIComponent(b.photo)}` : '';
    els.img.alt = b.photo || '';

    // Rebuild the problems list. Simpler than surgical DOM updates and cheap
    // even for 30+ problems.
    els.problemList.innerHTML = '';
    for (const p of b.problems) {
        els.problemList.append(buildProblemRow(p));
    }
    updateDrawingIndicators();
}

function buildProblemRow(p) {
    const node = els.tpl.content.firstElementChild.cloneNode(true);
    node.dataset.pid = p._id;

    const pin = node.querySelector('.pin');
    pin.style.background = colorFor(p.no);

    const nInput = node.querySelector('.p-no');
    const nameInput = node.querySelector('.p-name');
    const gradeSel = node.querySelector('.p-grade');
    const notes = node.querySelector('.p-notes');
    const notesFr = node.querySelector('.p-notes-fr');

    nInput.value = p.no;
    nameInput.value = p.problem || '';
    for (const g of GRADES) {
        const opt = document.createElement('option');
        opt.value = g;
        opt.textContent = g;
        if ((p.grade || '') === g) opt.selected = true;
        gradeSel.append(opt);
    }
    notes.value = p.notes || '';
    notesFr.value = p.notes_fr || '';

    nInput.addEventListener('input', () => {
        p.no = parseInt(nInput.value) || 0;
        pin.style.background = colorFor(p.no);
        renderOverlay();
        renderSidebar();
        markDirty();
    });
    nameInput.addEventListener('input', () => {
        p.problem = nameInput.value;
        markDirty();
    });
    gradeSel.addEventListener('change', () => {
        p.grade = gradeSel.value;
        markDirty();
    });
    notes.addEventListener('input', () => {
        p.notes = notes.value;
        markDirty();
    });
    notesFr.addEventListener('input', () => {
        p.notes_fr = notesFr.value;
        markDirty();
    });

    node.querySelector('.draw').addEventListener('click', () => {
        state.drawingPid = state.drawingPid === p._id ? null : p._id;
        updateDrawingIndicators();
        renderOverlay();
    });
    node.querySelector('.clear-line').addEventListener('click', () => {
        p.line = '';
        renderOverlay();
        markDirty();
    });
    node.querySelector('.delete').addEventListener('click', () => {
        const b = selectedBoulder();
        b.problems = b.problems.filter((x) => x._id !== p._id);
        if (state.drawingPid === p._id) state.drawingPid = null;
        renderDetail();
        renderOverlay();
        renderSidebar();
        markDirty();
    });

    return node;
}

function updateDrawingIndicators() {
    const drawing = state.drawingPid != null;
    els.canvasWrap.classList.toggle('drawing', drawing);
    els.canvasHint.hidden = !drawing;
    if (drawing) {
        els.canvasHint.textContent =
            'Click to add points · drag handles to nudge · double-click a handle to remove · Enter/Esc to finish';
    }
    for (const row of els.problemList.querySelectorAll('.problem-row')) {
        row.classList.toggle('drawing', row.dataset.pid === state.drawingPid);
    }
}

// -----------------------------------------------------------------------------
// SVG overlay — draws every problem's line, plus editing handles for the
// currently-drawing one.
// -----------------------------------------------------------------------------

const SVG_NS = 'http://www.w3.org/2000/svg';

function renderOverlay() {
    const b = selectedBoulder();
    els.overlay.innerHTML = '';
    if (!b || !els.img.naturalWidth) {
        // If the image hasn't loaded yet, wait for it.
        return;
    }

    // viewBox in image-percent (0-100) simplifies pt <-> screen math: pts are
    // stored as percent already.
    els.overlay.setAttribute('viewBox', '0 0 100 100');
    els.overlay.setAttribute('preserveAspectRatio', 'none');

    // Sort so the currently-drawing line renders on top.
    const ordered = [...b.problems].sort((a, c) => {
        if (a._id === state.drawingPid) return 1;
        if (c._id === state.drawingPid) return -1;
        return a.no - c.no;
    });

    for (const p of ordered) {
        const pts = parseLine(p.line);
        if (pts.length < 1) continue;
        const active = p._id === state.drawingPid;
        drawLine(p, pts, active);
    }
}

// Catmull-Rom → cubic-bezier path. Same smoothing the standalone annotator
// uses (tools/boulder-line-annotator.html → smooth()). Scale-invariant, so
// it works identically in the percent-space viewBox we use here.
function smoothPath(pts) {
    if (pts.length === 0) return '';
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] || pts[i];
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const p3 = pts[i + 2] || p2;
        const c1x = p1.x + (p2.x - p0.x) / 6;
        const c1y = p1.y + (p2.y - p0.y) / 6;
        const c2x = p2.x - (p3.x - p1.x) / 6;
        const c2y = p2.y - (p3.y - p1.y) / 6;
        d += ` C ${c1x} ${c1y} ${c2x} ${c2y} ${p2.x} ${p2.y}`;
    }
    return d;
}

function drawLine(p, pts, active) {
    const color = colorFor(p.no);
    const project = (p.grade || '').toLowerCase() === 'project';

    if (pts.length >= 2) {
        const d = smoothPath(pts);

        // White halo behind the coloured stroke — same visual language as the
        // PDF and annotator preview.
        const halo = document.createElementNS(SVG_NS, 'path');
        halo.setAttribute('d', d);
        halo.setAttribute('fill', 'none');
        halo.setAttribute('stroke', '#ffffff');
        halo.setAttribute('stroke-width', '1.6');
        halo.setAttribute('stroke-linecap', 'round');
        halo.setAttribute('stroke-linejoin', 'round');
        halo.setAttribute('vector-effect', 'non-scaling-stroke');
        // vector-effect + a big literal width so the halo stays visible after
        // the viewBox transform. We drop it back to something sensible via
        // stroke-width in css-pixel units by using pathLength if needed later.
        halo.style.strokeWidth = '6px';
        els.overlay.append(halo);

        const line = document.createElementNS(SVG_NS, 'path');
        line.setAttribute('d', d);
        line.setAttribute('fill', 'none');
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-linecap', 'round');
        line.setAttribute('stroke-linejoin', 'round');
        line.setAttribute('vector-effect', 'non-scaling-stroke');
        if (project) line.setAttribute('stroke-dasharray', '6 5');
        line.style.strokeWidth = '3px';
        els.overlay.append(line);
    }

    // Number marker at the first point (matches PDF / annotator).
    const first = pts[0];
    const r = 2.2;
    const markerHalo = document.createElementNS(SVG_NS, 'circle');
    markerHalo.setAttribute('cx', first.x);
    markerHalo.setAttribute('cy', first.y);
    markerHalo.setAttribute('r', r + 0.6);
    markerHalo.setAttribute('fill', '#ffffff');
    els.overlay.append(markerHalo);

    const marker = document.createElementNS(SVG_NS, 'circle');
    marker.setAttribute('cx', first.x);
    marker.setAttribute('cy', first.y);
    marker.setAttribute('r', r);
    marker.setAttribute('fill', project ? '#ffffff' : color);
    marker.setAttribute('stroke', color);
    marker.setAttribute('stroke-width', project ? 0.6 : 0);
    els.overlay.append(marker);

    const label = document.createElementNS(SVG_NS, 'text');
    label.setAttribute('x', first.x);
    label.setAttribute('y', first.y);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('dominant-baseline', 'central');
    label.setAttribute('font-family', 'Helvetica, Arial, sans-serif');
    label.setAttribute('font-weight', 'bold');
    label.setAttribute('font-size', '2.5');
    label.setAttribute('fill', project ? color : '#ffffff');
    label.textContent = String(p.no);
    els.overlay.append(label);

    // Handles for the currently-drawing line.
    if (active) {
        pts.forEach((pt, idx) => {
            const handle = document.createElementNS(SVG_NS, 'circle');
            handle.setAttribute('cx', pt.x);
            handle.setAttribute('cy', pt.y);
            handle.setAttribute('r', 1.4);
            handle.setAttribute('fill', '#ffffff');
            handle.setAttribute('stroke', color);
            handle.setAttribute('stroke-width', 0.6);
            handle.style.cursor = 'grab';
            handle.dataset.idx = idx;
            handle.addEventListener('mousedown', (e) => startDrag(e, p, idx));
            handle.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                removePoint(p, idx);
            });
            els.overlay.append(handle);
        });
    }
}

// -----------------------------------------------------------------------------
// Drawing interactions
// -----------------------------------------------------------------------------

function svgPoint(evt) {
    const rect = els.overlay.getBoundingClientRect();
    const x = ((evt.clientX - rect.left) / rect.width) * 100;
    const y = ((evt.clientY - rect.top) / rect.height) * 100;
    return { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) };
}

els.overlay.addEventListener('click', (evt) => {
    if (state.drawingPid == null) return;
    // Clicking on a handle already fires that handle's own listener; only
    // treat clicks on empty overlay as "add point".
    if (evt.target !== els.overlay) return;
    const b = selectedBoulder();
    const p = b?.problems.find((x) => x._id === state.drawingPid);
    if (!p) return;
    const pt = svgPoint(evt);
    const pts = parseLine(p.line);
    pts.push(pt);
    p.line = stringifyLine(pts);
    renderOverlay();
    markDirty();
});

function startDrag(evt, p, idx) {
    evt.preventDefault();
    evt.stopPropagation();
    const move = (e) => {
        const pt = svgPoint(e);
        const pts = parseLine(p.line);
        pts[idx] = pt;
        p.line = stringifyLine(pts);
        renderOverlay();
    };
    const up = () => {
        window.removeEventListener('mousemove', move);
        window.removeEventListener('mouseup', up);
        markDirty();
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
}

function removePoint(p, idx) {
    const pts = parseLine(p.line);
    pts.splice(idx, 1);
    p.line = stringifyLine(pts);
    renderOverlay();
    markDirty();
}

// Enter / Esc exit drawing mode.
window.addEventListener('keydown', (e) => {
    if (state.drawingPid == null) return;
    if (e.key === 'Enter' || e.key === 'Escape') {
        state.drawingPid = null;
        updateDrawingIndicators();
        renderOverlay();
    }
});

// Re-render overlay once the photo loads (viewBox depends on nothing, but the
// image needs to be sized so the SVG has real screen dimensions).
els.img.addEventListener('load', () => {
    renderOverlay();
});

// -----------------------------------------------------------------------------
// Header + boulder-level actions
// -----------------------------------------------------------------------------

els.name.addEventListener('input', () => {
    const b = selectedBoulder();
    if (!b) return;
    b.name = els.name.value;
    renderSidebar();
    markDirty();
});

els.addBoulder.addEventListener('click', () => {
    const b = { _id: uid(), name: 'New boulder', photo: '', problems: [] };
    state.boulders.push(b);
    state.selectedId = b._id;
    render();
    markDirty();
    els.name.focus();
    els.name.select();
});

els.addProblem.addEventListener('click', () => {
    const b = selectedBoulder();
    if (!b) return;
    const nextNo = b.problems.reduce((m, p) => Math.max(m, p.no || 0), 0) + 1;
    b.problems.push({
        _id: uid(),
        no: nextNo,
        problem: '',
        grade: '',
        notes: '',
        notes_fr: '',
        line: '',
    });
    renderDetail();
    renderOverlay();
    renderSidebar();
    markDirty();
});

// -----------------------------------------------------------------------------
// Photo picker + upload
// -----------------------------------------------------------------------------

els.pickPhoto.addEventListener('click', async () => {
    const b = selectedBoulder();
    if (!b) return;
    if (!state.photos.length) {
        alert('No photos in data/photos/. Upload one first.');
        return;
    }
    const choice = prompt(
        `Choose a photo:\n\n${state.photos.map((n, i) => `${i + 1}. ${n}`).join('\n')}\n\nEnter filename:`,
        b.photo || state.photos[0],
    );
    if (!choice) return;
    if (!state.photos.includes(choice)) {
        alert(`"${choice}" not found in data/photos/.`);
        return;
    }
    b.photo = choice;
    renderDetail();
    renderSidebar();
    markDirty();
});

els.uploadPhoto.addEventListener('click', () => els.uploadInput.click());

els.uploadInput.addEventListener('change', async () => {
    const file = els.uploadInput.files?.[0];
    if (!file) return;
    // Warn on collisions so the user doesn't silently clobber an existing
    // photo their old CSV rows still reference.
    const safe = file.name.replace(/[/\\]/g, '_').replace(/\s+/g, '_');
    if (state.photos.includes(safe)) {
        const ok = confirm(
            `A file named "${safe}" already exists in data/photos/. Overwrite?`,
        );
        if (!ok) {
            els.uploadInput.value = '';
            return;
        }
    }
    setStatus(`Uploading ${safe}…`);
    const fd = new FormData();
    fd.append('photo', file);
    const res = await fetch('/api/photos', { method: 'POST', body: fd });
    els.uploadInput.value = '';
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setStatus(`Upload failed: ${err.error || res.status}`);
        return;
    }
    const { filename } = await res.json();
    if (!state.photos.includes(filename)) state.photos.push(filename);
    const b = selectedBoulder();
    if (b) {
        b.photo = filename;
        renderDetail();
        renderSidebar();
        markDirty();
    }
    setStatus(`Uploaded ${filename}`);
    setTimeout(() => setStatus(''), 2000);
});

// -----------------------------------------------------------------------------
// Save + unload guard
// -----------------------------------------------------------------------------

els.save.addEventListener('click', saveAll);

// -----------------------------------------------------------------------------
// Generate PDFs — POST /api/generate; blocks the button while running (PDF
// build is ~2–5s, HTML build is longer because of the IGN tile bundle).
// -----------------------------------------------------------------------------

async function generatePdfs() {
    // Save unsaved edits first so what's rendered matches what's on screen.
    if (state.dirty) {
        await saveAll();
        if (state.dirty) return; // save failed — status shows why
    }
    els.generate.disabled = true;
    els.generate.textContent = 'Generating…';
    setStatus('Generating…');

    // Loading state: show only the spinner; hide any previous log/file list.
    els.generateLog.hidden = false;
    els.generateLog.classList.remove('error');
    els.generateLogTitle.textContent = 'Generating PDFs';
    els.generateLoading.hidden = false;
    els.generateLogBody.hidden = true;
    els.generateFiles.hidden = true;
    els.generateFiles.innerHTML = '';

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lang: 'both', includeHtml: false }),
        });
        const data = await res.json();

        els.generateLoading.hidden = true;
        els.generateLogBody.hidden = false;
        els.generateLogBody.textContent = data.log || '(no output)';

        if (!data.ok) {
            els.generateLog.classList.add('error');
            els.generateLogTitle.textContent = 'Generate failed';
            setStatus('Generate failed');
            return;
        }

        els.generateLogTitle.textContent = `Generated in ${data.seconds}s`;
        for (const f of data.files || []) {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = `/output/${encodeURIComponent(f)}`;
            a.textContent = f;
            a.target = '_blank';
            a.rel = 'noopener';
            li.append(a);
            els.generateFiles.append(li);
        }
        els.generateFiles.hidden = !(data.files || []).length;
        setStatus(`Generated in ${data.seconds}s`);
        setTimeout(() => setStatus(''), 4000);
    } catch (e) {
        els.generateLoading.hidden = true;
        els.generateLogBody.hidden = false;
        els.generateLog.classList.add('error');
        els.generateLogTitle.textContent = 'Generate failed';
        els.generateLogBody.textContent = `Request failed: ${e.message}`;
        setStatus('Generate failed');
    } finally {
        els.generate.disabled = false;
        els.generate.textContent = 'Generate PDFs';
    }
}

els.generate.addEventListener('click', generatePdfs);
els.generateLogClose.addEventListener('click', () => {
    els.generateLog.hidden = true;
});

window.addEventListener('beforeunload', (e) => {
    if (!state.dirty) return;
    e.preventDefault();
    e.returnValue = '';
});

loadAll().catch((e) => {
    console.error(e);
    setStatus(`Load failed: ${e.message}`);
});
