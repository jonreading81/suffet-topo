// Suffet topo editor — SPA. Fetches /api/boulders, lets the user edit, then
// PUTs the whole shape back. Line drawing is inlined here rather than reusing
// the standalone annotator's HTML, because we want the same in-page flow for
// adding + editing.

const GRADES = [
    'Project',
    '3', '3+', '4', '5',
    '6A', '6A+', '6B', '6B+', '6C', '6C+',
    '7A', '7A+', '7B', '7B+', '7C', '7C+',
    '8A', '8A+', '8B', '8B+', '8C', '8C+',
    '9A',
];

// Same palette as topo/style.py (line_palette). Cycled by (no - 1) mod len.
const LINE_PALETTE = ['#004AAD', '#E4572E', '#6AB0AB', '#A096EF', '#E0A21B'];

// Metres above which the GPS fix is flagged as "verify on map" — matches
// ACCURACY_FLAG_M in config.yaml on the Python side.
const GPS_ACCURACY_FLAG_M = 15;

// -----------------------------------------------------------------------------
// State
// -----------------------------------------------------------------------------

const state = {
    boulders: [],       // [{ _id, name, photo, problems: [{ _id, no, ... }] }]
    photos: [],
    selectedId: null,   // boulder _id
    drawingPid: null,   // problem _id currently being drawn
    // The "next segment" preview is only shown after the user actively adds a
    // point in this session. That way opening an existing line puts you in
    // edit mode (drag handles freely) without a phantom curve chasing the
    // cursor around; the first click on empty canvas flips this on.
    addingPoints: false,
    hoverPt: null,
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
    nameError: $('#f-name-error'),
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
    uploadPhoto: $('#upload-photo'),
    uploadInput: $('#upload-input'),
    canvasWrap: $('#canvas-wrap'),
    canvasEmpty: $('#canvas-empty'),
    gpsWarning: $('#gps-warning'),
    img: $('#photo'),
    overlay: $('#overlay'),
    canvasHint: $('#canvas-hint'),
    drawingActions: $('#drawing-actions'),
    clearDrawing: $('#clear-drawing'),
    finishDrawing: $('#finish-drawing'),
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
    const { removed = [], renamed = [] } = await res.json().catch(() => ({}));

    // Server may have renamed photos on disk to match new boulder names.
    // Apply those to state so the displayed image URL uses the new file.
    if (renamed.length) {
        const map = new Map(renamed.map((r) => [r.from, r.to]));
        for (const b of state.boulders) {
            if (b.photo && map.has(b.photo)) b.photo = map.get(b.photo);
        }
        state.photos = state.photos.map((p) => (map.has(p) ? map.get(p) : p));
        renderDetail();
        renderSidebar();
    }

    // Drop deleted photos from local state so subsequent uploads don't think
    // the name is still taken.
    if (removed.length) {
        state.photos = state.photos.filter((p) => !removed.includes(p));
    }

    setDirty(false);
    const parts = [];
    if (renamed.length) {
        parts.push(`renamed ${renamed.length} photo${renamed.length === 1 ? '' : 's'}`);
    }
    if (removed.length) {
        parts.push(`removed ${removed.length} orphan${removed.length === 1 ? '' : 's'}`);
    }
    setStatus(parts.length ? `Saved · ${parts.join(', ')}` : 'Saved.');
    setTimeout(() => setStatus(''), 2500);
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

// Normalise boulder names for duplicate detection — trim + lowercase so
// "Big Boulder" and "big boulder " count as the same name.
function normalizedName(s) {
    return (s || '').trim().toLowerCase();
}

// Set of normalised names that appear more than once across state.boulders.
// Empty / whitespace-only names are ignored (they're separately unusable).
function duplicateBoulderNames() {
    const counts = new Map();
    for (const b of state.boulders) {
        const n = normalizedName(b.name);
        if (!n) continue;
        counts.set(n, (counts.get(n) || 0) + 1);
    }
    return new Set([...counts.entries()].filter(([, c]) => c > 1).map(([n]) => n));
}

// Update the name-input error state + the sidebar dupe flag + the Save
// button's enabled state. Call after any change to a boulder name.
function updateValidation() {
    const dupes = duplicateBoulderNames();
    const b = selectedBoulder();
    const currentIsDupe = !!(b && dupes.has(normalizedName(b.name)));
    els.name.classList.toggle('invalid', currentIsDupe);
    els.nameError.hidden = !currentIsDupe;
    els.nameError.textContent = currentIsDupe
        ? 'Another boulder already uses this name.'
        : '';

    for (const li of els.list.querySelectorAll('li')) {
        const bId = li.dataset.id;
        const other = state.boulders.find((x) => x._id === bId);
        li.classList.toggle('dupe', !!(other && dupes.has(normalizedName(other.name))));
    }

    els.save.disabled = dupes.size > 0;
    els.save.title = dupes.size > 0
        ? 'Fix duplicate boulder names before saving.'
        : '';
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
    updateValidation();
}

function renderSidebar() {
    els.list.innerHTML = '';
    for (const b of state.boulders) {
        const li = document.createElement('li');
        if (b._id === state.selectedId) li.classList.add('active');
        li.dataset.id = b._id;
        li.draggable = true;

        const thumb = document.createElement('div');
        thumb.className = 'thumb';
        if (b.photo) {
            const bust = b._photoTs ? `?v=${b._photoTs}` : '';
            thumb.style.backgroundImage = `url('/photos/${encodeURIComponent(b.photo)}${bust}')`;
        }

        const meta = document.createElement('div');
        meta.className = 'meta';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = b.name || '(unnamed)';
        // Flag boulders with no GPS or a loose fix so they stand out in the
        // list without having to click into each one.
        const noGps = b.hasGps === false;
        const looseGps = typeof b.gpsAccuracy === 'number' && b.gpsAccuracy >= GPS_ACCURACY_FLAG_M;
        if (b.photo && (noGps || looseGps)) {
            const warn = document.createElement('span');
            warn.className = 'row-warn';
            warn.textContent = '⚠';
            warn.title = noGps
                ? 'No GPS data in photo'
                : `GPS ±${Math.round(b.gpsAccuracy)} m — low confidence`;
            title.append(' ', warn);
        }
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
        // A mousedown on the delete button shouldn't kick off a drag on the
        // parent li — cancel drag initiation for this button specifically.
        del.addEventListener('mousedown', (e) => e.stopPropagation());

        li.append(thumb, meta, del);
        li.addEventListener('click', () => {
            state.selectedId = b._id;
            state.drawingPid = null;
            render();
        });

        // Drag & drop reordering — live shuffle as the pointer moves, so the
        // list literally reorders under the cursor instead of just showing an
        // insertion line. State catches up on drop.
        li.addEventListener('dragstart', (e) => {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', b._id);
            // The dragged element itself needs a paint frame before we hide
            // it, otherwise the drag ghost is invisible.
            requestAnimationFrame(() => li.classList.add('dragging'));
        });
        li.addEventListener('dragend', () => {
            li.classList.remove('dragging');
            commitSidebarOrderFromDom();
        });
        li.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const dragging = els.list.querySelector('.dragging');
            if (!dragging || dragging === li) return;
            const rect = li.getBoundingClientRect();
            const before = e.clientY < rect.top + rect.height / 2;
            els.list.insertBefore(dragging, before ? li : li.nextSibling);
        });

        els.list.append(li);
    }
}

// Read the sidebar list's current DOM order back into state.boulders. Called
// on dragend so the live-shuffled order becomes the persisted order.
function commitSidebarOrderFromDom() {
    const domOrder = [...els.list.querySelectorAll('li')].map((el) => el.dataset.id);
    const byId = new Map(state.boulders.map((b) => [b._id, b]));
    const next = domOrder.map((id) => byId.get(id)).filter(Boolean);
    // Only touch state if the order actually changed.
    const same = next.length === state.boulders.length &&
        next.every((b, i) => b === state.boulders[i]);
    if (same) return;
    state.boulders = next;
    markDirty();
}

// Read the problem list's current DOM order back into state and renumber
// 1..N so the order sticks through save/reload.
function commitProblemOrderFromDom() {
    const b = selectedBoulder();
    if (!b) return;
    const domOrder = [...els.problemList.querySelectorAll('.problem-row')].map(
        (el) => el.dataset.pid,
    );
    const byId = new Map(b.problems.map((p) => [p._id, p]));
    const next = domOrder.map((id) => byId.get(id)).filter(Boolean);
    const same = next.length === b.problems.length &&
        next.every((p, i) => p === b.problems[i]);
    if (same) return;
    b.problems = next;
    b.problems.forEach((p, i) => { p.no = i + 1; });
    renderDetail();
    renderOverlay();
    renderSidebar();
    markDirty();
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
    // Cache-bust the URL after uploads so the browser refetches even when the
    // filename is unchanged (which is the common case — filename is a slug of
    // the boulder name, so a replacement upload hits the same URL).
    const bust = b._photoTs ? `?v=${b._photoTs}` : '';
    els.img.src = b.photo ? `/photos/${encodeURIComponent(b.photo)}${bust}` : '';
    els.img.alt = b.photo || '';
    els.canvasWrap.classList.toggle('has-photo', !!b.photo);
    els.canvasEmpty.hidden = !!b.photo;

    // GPS warning banner. Two flavours share the pill:
    //   * no GPS in the photo at all — the boulder can't be placed on the map
    //   * a fix exists but the reported accuracy is loose (>= flag threshold)
    // Same visual as the PDF's warning pill on the boulder detail page.
    const acc = b.gpsAccuracy;
    const noGps = b.hasGps === false;
    const flagged = typeof acc === 'number' && acc >= GPS_ACCURACY_FLAG_M;
    els.gpsWarning.hidden = !(noGps || flagged);
    if (noGps) {
        els.gpsWarning.textContent = '⚠ No GPS data in photo — add coordinates or replace the image';
    } else if (flagged) {
        els.gpsWarning.textContent =
            `⚠ GPS ±${Math.round(acc)} m — low confidence, verify on map`;
    }

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
    node.draggable = true;

    // Drag & drop reordering within the problems list — live shuffle under
    // the cursor. State catches up on drop, and numbers auto-renumber 1..N
    // in the new order (both editor server and Python PDF builder sort by
    // `no`, so reorder-without-renumber would revert on reload).
    node.addEventListener('dragstart', (e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', p._id);
        requestAnimationFrame(() => node.classList.add('dragging'));
    });
    node.addEventListener('dragend', () => {
        node.classList.remove('dragging');
        commitProblemOrderFromDom();
    });
    node.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const dragging = els.problemList.querySelector('.dragging');
        if (!dragging || dragging === node) return;
        const rect = node.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        els.problemList.insertBefore(dragging, before ? node : node.nextSibling);
    });

    // Text inputs bubble their mousedown up to the row and would otherwise
    // start a drag when clicking inside them — cancel that.
    for (const el of node.querySelectorAll('input, select, button')) {
        el.addEventListener('mousedown', (e) => e.stopPropagation());
    }

    const nInput = node.querySelector('.p-no');
    const nameInput = node.querySelector('.p-name');
    const gradeSel = node.querySelector('.p-grade');
    const notes = node.querySelector('.p-notes');
    const notesFr = node.querySelector('.p-notes-fr');

    // Colour the whole card's border (and the active pencil button) to match
    // this problem's line — visual hook so the card and its drawn line share
    // the same identity. --accent is picked up by CSS.
    node.style.setProperty('--accent', colorFor(p.no));
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
        node.style.setProperty('--accent', colorFor(p.no));
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

    const drawBtn = node.querySelector('.draw');
    const drawLabel = drawBtn.querySelector('.row-btn-label');
    drawLabel.textContent = p.line ? 'Edit Line' : 'Draw Line';
    drawBtn.addEventListener('click', () => {
        const wasDrawing = state.drawingPid === p._id;
        state.drawingPid = wasDrawing ? null : p._id;
        state.addingPoints = false;
        state.hoverPt = null;
        updateDrawingIndicators();
        renderOverlay();
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
    els.drawingActions.hidden = !drawing;
    if (drawing) {
        els.canvasHint.textContent =
            'Click to add points · drag handles to nudge · double-click a handle to remove';
    }
    const b = selectedBoulder();
    for (const row of els.problemList.querySelectorAll('.problem-row')) {
        const isActive = row.dataset.pid === state.drawingPid;
        row.classList.toggle('drawing', isActive);
        const drawLabel = row.querySelector('.draw .row-btn-label');
        if (!drawLabel) continue;
        if (isActive) {
            drawLabel.textContent = 'Editing…';
        } else {
            const p = b?.problems.find((x) => x._id === row.dataset.pid);
            drawLabel.textContent = p?.line ? 'Edit Line' : 'Draw Line';
        }
    }
}

function finishDrawing() {
    state.drawingPid = null;
    state.addingPoints = false;
    state.hoverPt = null;
    updateDrawingIndicators();
    renderOverlay();
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

    // While drawing this line — AND only after the user has explicitly
    // committed to adding points — append the cursor position so the
    // Catmull-Rom curve extends to it in real time. Opening an existing line
    // starts in "edit only" mode so the curve doesn't chase the cursor while
    // the user is trying to drag a handle.
    const showPreview = active && state.addingPoints && state.hoverPt && pts.length >= 1;
    const renderPts = showPreview ? [...pts, state.hoverPt] : pts;

    // Everything below is decorative — we don't want the coloured line, its
    // halo, or the number marker to swallow clicks that were meant for the
    // canvas underneath (the hover-preview curve chases the cursor, so clicks
    // land on it if it captures pointer events).
    const noPointer = (el) => {
        el.setAttribute('pointer-events', 'none');
        return el;
    };

    if (renderPts.length >= 2) {
        const d = smoothPath(renderPts);

        // White halo behind the coloured stroke — same visual language as the
        // PDF and annotator preview.
        const halo = noPointer(document.createElementNS(SVG_NS, 'path'));
        halo.setAttribute('d', d);
        halo.setAttribute('fill', 'none');
        halo.setAttribute('stroke', '#ffffff');
        halo.setAttribute('stroke-linecap', 'round');
        halo.setAttribute('stroke-linejoin', 'round');
        halo.setAttribute('vector-effect', 'non-scaling-stroke');
        halo.style.strokeWidth = '6px';
        els.overlay.append(halo);

        const line = noPointer(document.createElementNS(SVG_NS, 'path'));
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
    const markerHalo = noPointer(document.createElementNS(SVG_NS, 'circle'));
    markerHalo.setAttribute('cx', first.x);
    markerHalo.setAttribute('cy', first.y);
    markerHalo.setAttribute('r', r + 0.6);
    markerHalo.setAttribute('fill', '#ffffff');
    els.overlay.append(markerHalo);

    const marker = noPointer(document.createElementNS(SVG_NS, 'circle'));
    marker.setAttribute('cx', first.x);
    marker.setAttribute('cy', first.y);
    marker.setAttribute('r', r);
    marker.setAttribute('fill', project ? '#ffffff' : color);
    marker.setAttribute('stroke', color);
    marker.setAttribute('stroke-width', project ? 0.6 : 0);
    els.overlay.append(marker);

    const label = noPointer(document.createElementNS(SVG_NS, 'text'));
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

// A click is treated as "add a point" only if it doesn't land close to an
// existing one. Threshold is in percent-space (the SVG's viewBox), and is
// slightly larger than the handle radius (1.4) so clicks that just miss the
// handle still count as "meant for that handle" — the user was going for the
// grab, not adding a new point on top of it.
const CLICK_ADD_THRESHOLD = 3;

els.overlay.addEventListener('click', (evt) => {
    if (state.drawingPid == null) return;
    // Clicking on a handle already fires that handle's own listener; only
    // treat clicks on empty overlay as candidates for "add point".
    if (evt.target !== els.overlay) return;
    const b = selectedBoulder();
    const p = b?.problems.find((x) => x._id === state.drawingPid);
    if (!p) return;
    const pt = svgPoint(evt);
    const pts = parseLine(p.line);
    const nearExisting = pts.some(
        (q) => Math.hypot(q.x - pt.x, q.y - pt.y) < CLICK_ADD_THRESHOLD,
    );
    if (nearExisting) return;
    pts.push(pt);
    p.line = stringifyLine(pts);
    state.addingPoints = true; // arm the cursor preview from now on
    state.hoverPt = pt;        // keep the preview snapped to the just-placed point
    renderOverlay();
    markDirty();
});

// Live "next segment" preview — track the cursor while drawing so the smooth
// curve extends to it. Cleared on mouseleave so the curve doesn't stay stuck
// pointing off-canvas.
els.overlay.addEventListener('mousemove', (evt) => {
    if (state.drawingPid == null) return;
    state.hoverPt = svgPoint(evt);
    renderOverlay();
});
els.overlay.addEventListener('mouseleave', () => {
    if (state.drawingPid == null) return;
    state.hoverPt = null;
    renderOverlay();
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
        finishDrawing();
    }
});

els.finishDrawing.addEventListener('click', finishDrawing);

els.clearDrawing.addEventListener('click', () => {
    const b = selectedBoulder();
    const p = b?.problems.find((x) => x._id === state.drawingPid);
    if (!p) return;
    p.line = '';
    state.addingPoints = false; // back to "click to start adding" for the empty line
    state.hoverPt = null;
    renderOverlay();
    markDirty();
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
    updateValidation();
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

els.uploadPhoto.addEventListener('click', () => els.uploadInput.click());

els.uploadInput.addEventListener('change', async () => {
    const file = els.uploadInput.files?.[0];
    if (!file) return;
    els.uploadInput.value = ''; // reset early so re-picking the same file fires 'change'
    await uploadPhoto(file, false);
});

async function uploadPhoto(file, overwrite) {
    const b = selectedBoulder();
    const isHeic = /\.(heic|heif)$/i.test(file.name);
    els.uploadPhoto.disabled = true;
    setStatus(isHeic ? 'Converting HEIC & uploading…' : 'Uploading…');
    const fd = new FormData();
    fd.append('photo', file);
    fd.append('boulderName', b?.name || '');
    if (overwrite) fd.append('overwrite', 'true');
    try {
        const res = await fetch('/api/photos', { method: 'POST', body: fd });
        // Server returns 409 when a photo with the target filename already
        // exists — confirm with the user before overwriting.
        if (res.status === 409) {
            const err = await res.json().catch(() => ({}));
            const ok = confirm(
                `${err.error || 'This photo already exists.'}\n\nOverwrite it?`,
            );
            if (ok) {
                els.uploadPhoto.disabled = false; // uploadPhoto re-disables it
                await uploadPhoto(file, true);
            } else {
                setStatus('Upload cancelled');
                setTimeout(() => setStatus(''), 2000);
            }
            return;
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            setStatus(`Upload failed: ${err.error || res.status}`);
            return;
        }
        const { filename, gpsAccuracy, hasGps } = await res.json();
        if (!state.photos.includes(filename)) state.photos.push(filename);
        if (b) {
            b.photo = filename;
            b.gpsAccuracy = gpsAccuracy ?? null;
            b.hasGps = hasGps !== false;
            b._photoTs = Date.now(); // bust the image cache for this boulder
            renderDetail();
            renderSidebar();
            markDirty();
        }
        setStatus(`Uploaded ${filename}`);
        setTimeout(() => setStatus(''), 2500);
    } finally {
        els.uploadPhoto.disabled = false;
    }
}

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
