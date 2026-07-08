// Suffet topo editor — SPA. Fetches /api/boulders, lets the user edit, then
// PUTs the whole shape back. Line drawing is inlined here rather than reusing
// the standalone annotator's HTML, because we want the same in-page flow for
// adding + editing.

// "Project" was previously a grade string; it's now a separate checkbox on
// the row so a project can carry its own *proposed* grade if the climber has
// one in mind. See the `.p-project` input in the template + save handler.
const GRADES = [
    '',
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
    // Cluster-letter → user-provided name. Missing / empty means the cluster
    // falls back to the generic "Cluster A" label in the PDF.
    clusterNames: {},
    // Getting-there prose per language, edited in the Getting There tab.
    gettingThere: { en: '', fr: '' },
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
    tabs: document.querySelectorAll('.tab-bar .tab'),
    tabPanels: document.querySelectorAll('.tab-panel'),
    addGallery: $('#add-gallery'),
    galleryInput: $('#gallery-input'),
    galleryList: $('#gallery-list'),
    galleryEmpty: $('#gallery-empty'),
    sidebarTabs: document.querySelectorAll('.sidebar-tab'),
    sidebarPanels: document.querySelectorAll('.sidebar-panel'),
    clusterList: $('#cluster-list'),
    gtEn: $('#gt-en'),
    gtFr: $('#gt-fr'),
    gtAddGallery: $('#gt-add-gallery'),
    gtGalleryInput: $('#gt-gallery-input'),
    gtGalleryList: $('#gt-gallery-list'),
    gtGalleryEmpty: $('#gt-gallery-empty'),
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
    state.clusterNames = bRes.clusterNames && typeof bRes.clusterNames === 'object'
        ? { ...bRes.clusterNames }
        : {};
    state.gettingThere = bRes.gettingThere && typeof bRes.gettingThere === 'object'
        ? { en: '', fr: '', ...bRes.gettingThere }
        : { en: '', fr: '' };
    els.gtEn.value = state.gettingThere.en || '';
    els.gtFr.value = state.gettingThere.fr || '';
    if (!Array.isArray(state.gettingThere.gallery)) state.gettingThere.gallery = [];
    renderGettingThereGallery();
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
                project: !!p.project,
                notes: p.notes || '',
                notes_fr: p.notes_fr || '',
                line: p.line || '',
            })),
            gallery: Array.isArray(b.gallery) ? b.gallery.filter(Boolean) : [],
            cluster: typeof b.cluster === 'string' ? b.cluster : '',
        })),
        clusterNames: state.clusterNames || {},
        gettingThere: state.gettingThere || {},
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
    const { removed = [], renamed = [], renamedGallery = [] } =
        await res.json().catch(() => ({}));

    // Server may have renamed photos on disk to match new boulder names.
    // Apply those to state so the displayed image URL uses the new file.
    if (renamed.length) {
        const map = new Map(renamed.map((r) => [r.from, r.to]));
        for (const b of state.boulders) {
            if (b.photo && map.has(b.photo)) b.photo = map.get(b.photo);
        }
        state.photos = state.photos.map((p) => (map.has(p) ? map.get(p) : p));
    }
    if (renamedGallery.length) {
        const gmap = new Map(renamedGallery.map((r) => [r.from, r.to]));
        for (const b of state.boulders) {
            if (!Array.isArray(b.gallery)) continue;
            b.gallery = b.gallery.map((f) => (gmap.has(f) ? gmap.get(f) : f));
        }
    }
    if (renamed.length || renamedGallery.length) {
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

// 4-bucket grade → colour map, mirrored from topo/data.py:grade_color.
//   3, 3+, 4, 5, 6A          → green
//   6A+, 6B, 6B+, 6C         → yellow
//   6C+, 7A, 7A+, 7B         → red
//   7B+ and above            → near-black
function gradeColor(grade) {
    if (!grade) return null;
    const g = String(grade).trim().toUpperCase();
    if (g === 'PROJECT' || g === '–' || g === '-') return null;
    const m = /^(\d+)([A-C])?(\+)?/.exec(g);
    if (!m) return null;
    const num = parseInt(m[1], 10);
    const letter = m[2] || 'A';
    const plus = m[3] === '+' ? 1 : 0;
    const idx = [num, letter.charCodeAt(0) - 65, plus];
    const le = (a, b) => (a[0] !== b[0] ? a[0] < b[0]
                        : a[1] !== b[1] ? a[1] < b[1]
                        : a[2] <= b[2]);
    if (le(idx, [6, 0, 0])) return '#2f9e44';
    if (le(idx, [6, 2, 0])) return '#f59f00';
    if (le(idx, [7, 1, 0])) return '#e03131';
    return '#212529';
}

// The colour we use for a problem's line / marker / card border. Projects
// always render in black; everything else uses the grade bucket, falling
// back to LINE_PALETTE-by-number for ungraded problems.
function accentColor(p) {
    if (p.project) return '#000000';
    return gradeColor(p.grade) || colorFor(p.no);
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

    // GPS badge over the photo. Three flavours share the pill:
    //   * no GPS at all — amber warning, can't be placed on the map
    //   * fix present but loose (≥ flag threshold) — amber warning
    //   * fix present and tight — neutral info readout so climbers can see
    //     the number without having to click through
    const acc = b.gpsAccuracy;
    const noGps = b.hasGps === false;
    const flagged = typeof acc === 'number' && acc >= GPS_ACCURACY_FLAG_M;
    const showInfo = !noGps && !flagged && typeof acc === 'number';
    els.gpsWarning.hidden = !(noGps || flagged || showInfo);
    els.gpsWarning.classList.toggle('ok', showInfo);
    if (noGps) {
        els.gpsWarning.textContent = '⚠ No GPS data in photo — add coordinates or replace the image';
    } else if (flagged) {
        els.gpsWarning.textContent = `⚠ GPS ±${Math.round(acc)} m`;
    } else if (showInfo) {
        els.gpsWarning.textContent = `GPS ±${Math.round(acc)} m`;
    }

    // Rebuild the problems list. Simpler than surgical DOM updates and cheap
    // even for 30+ problems.
    els.problemList.innerHTML = '';
    for (const p of b.problems) {
        els.problemList.append(buildProblemRow(p));
    }
    updateDrawingIndicators();
    renderGallery();
}

function renderGallery() {
    const b = selectedBoulder();
    els.galleryList.innerHTML = '';
    if (!b) return;
    const files = Array.isArray(b.gallery) ? b.gallery : [];
    els.galleryEmpty.hidden = files.length > 0;
    for (const filename of files) {
        const item = document.createElement('div');
        item.className = 'gallery-item';
        item.draggable = true;
        item.dataset.filename = filename;
        item.style.backgroundImage = `url('/gallery/${encodeURIComponent(filename)}')`;

        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'del';
        del.setAttribute('aria-label', 'Remove from gallery');
        del.textContent = '×';
        del.addEventListener('click', () => {
            b.gallery = files.filter((f) => f !== filename);
            markDirty();
            renderGallery();
        });
        // Mouseup on the delete button shouldn't trigger drag on the parent.
        del.addEventListener('mousedown', (e) => e.stopPropagation());
        item.append(del);

        // Drag-drop reordering — live shuffle under the cursor; commit
        // b.gallery from the DOM order on drop.
        item.addEventListener('dragstart', (e) => {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', filename);
            requestAnimationFrame(() => item.classList.add('dragging'));
        });
        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            commitGalleryOrderFromDom();
        });
        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const dragging = els.galleryList.querySelector('.dragging');
            if (!dragging || dragging === item) return;
            const rect = item.getBoundingClientRect();
            // 2-D grid — decide by pointer position relative to the item's
            // centre; horizontal wins because rows can be short.
            const beforeX = e.clientX < rect.left + rect.width / 2;
            const beforeY = e.clientY < rect.top + rect.height / 2;
            const before = beforeY || (Math.abs(e.clientY - (rect.top + rect.height / 2)) < 4 && beforeX);
            els.galleryList.insertBefore(dragging, before ? item : item.nextSibling);
        });

        els.galleryList.append(item);
    }
}

// Read the current DOM order of gallery items back into the boulder's
// gallery array — called on dragend.
function commitGalleryOrderFromDom() {
    const b = selectedBoulder();
    if (!b) return;
    const order = [...els.galleryList.querySelectorAll('.gallery-item')].map(
        (el) => el.dataset.filename
    );
    const same = order.length === (b.gallery || []).length
        && order.every((f, i) => f === b.gallery[i]);
    if (!same) {
        b.gallery = order;
        markDirty();
    }
}

function activateTab(name) {
    for (const t of els.tabs) {
        const on = t.dataset.tab === name;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
    }
    for (const p of els.tabPanels) {
        p.hidden = p.dataset.tab !== name;
    }
}

for (const t of els.tabs) {
    t.addEventListener('click', () => activateTab(t.dataset.tab));
}

// -----------------------------------------------------------------------------
// Sidebar tabs — Boulders / Clusters
// -----------------------------------------------------------------------------

function activateSidebarTab(name) {
    for (const t of els.sidebarTabs) {
        const on = t.dataset.tab === name;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
    }
    for (const p of els.sidebarPanels) {
        p.hidden = p.dataset.tab !== name;
    }
    if (name === 'clusters') renderClusters();
}

for (const t of els.sidebarTabs) {
    t.addEventListener('click', () => activateSidebarTab(t.dataset.tab));
}

// Getting-there textareas — write into state and mark dirty on every
// keystroke so Save picks it up.
els.gtEn.addEventListener('input', () => {
    state.gettingThere = { ...(state.gettingThere || {}), en: els.gtEn.value };
    markDirty();
});
els.gtFr.addEventListener('input', () => {
    state.gettingThere = { ...(state.gettingThere || {}), fr: els.gtFr.value };
    markDirty();
});

// -----------------------------------------------------------------------------
// Getting-there gallery — mirrors the per-boulder gallery, but the array
// lives on state.gettingThere.gallery instead of a boulder object.
// -----------------------------------------------------------------------------
function gettingThereFiles() {
    if (!state.gettingThere) state.gettingThere = { en: '', fr: '', gallery: [] };
    if (!Array.isArray(state.gettingThere.gallery)) state.gettingThere.gallery = [];
    return state.gettingThere.gallery;
}

function renderGettingThereGallery() {
    els.gtGalleryList.innerHTML = '';
    const files = gettingThereFiles();
    els.gtGalleryEmpty.hidden = files.length > 0;
    for (const filename of files) {
        const item = document.createElement('div');
        item.className = 'gallery-item';
        item.draggable = true;
        item.dataset.filename = filename;
        item.style.backgroundImage = `url('/gallery/${encodeURIComponent(filename)}')`;

        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'del';
        del.setAttribute('aria-label', 'Remove');
        del.textContent = '×';
        del.addEventListener('mousedown', (e) => e.stopPropagation());
        del.addEventListener('click', () => {
            state.gettingThere.gallery = files.filter((f) => f !== filename);
            markDirty();
            renderGettingThereGallery();
        });
        item.append(del);

        item.addEventListener('dragstart', (e) => {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', filename);
            requestAnimationFrame(() => item.classList.add('dragging'));
        });
        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            const order = [...els.gtGalleryList.querySelectorAll('.gallery-item')].map(
                (el) => el.dataset.filename
            );
            const same = order.length === files.length && order.every((f, i) => f === files[i]);
            if (!same) {
                state.gettingThere.gallery = order;
                markDirty();
            }
        });
        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const dragging = els.gtGalleryList.querySelector('.dragging');
            if (!dragging || dragging === item) return;
            const rect = item.getBoundingClientRect();
            const beforeX = e.clientX < rect.left + rect.width / 2;
            const beforeY = e.clientY < rect.top + rect.height / 2;
            const before = beforeY || (Math.abs(e.clientY - (rect.top + rect.height / 2)) < 4 && beforeX);
            els.gtGalleryList.insertBefore(dragging, before ? item : item.nextSibling);
        });

        els.gtGalleryList.append(item);
    }
}

els.gtAddGallery.addEventListener('click', () => els.gtGalleryInput.click());
els.gtGalleryInput.addEventListener('change', async () => {
    const files = [...els.gtGalleryInput.files];
    els.gtGalleryInput.value = '';
    if (!files.length) return;
    els.gtAddGallery.disabled = true;
    try {
        for (const file of files) {
            const fd = new FormData();
            fd.append('photo', file);
            fd.append('boulderName', 'getting-there');
            const res = await fetch('/api/gallery', { method: 'POST', body: fd });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                setStatus(`Upload failed: ${err.error || res.status}`);
                continue;
            }
            const { filename } = await res.json();
            state.gettingThere.gallery = [...gettingThereFiles(), filename];
            renderGettingThereGallery();
            markDirty();
        }
        setStatus(`Uploaded ${files.length}`);
        setTimeout(() => setStatus(''), 2000);
    } finally {
        els.gtAddGallery.disabled = false;
    }
});

// Cluster the GPS-having boulders west→east by the two largest longitude
// gaps (same algorithm as topo/data.py:cluster_by_lon_gap). Returns
// [[boulder, ...], ...] ordered by longitude.
// Cluster boulders into `n` groups. If any boulder has a `cluster` letter
// set, all boulders are grouped by that letter (west→east within each
// group). Otherwise falls back to the same longitude-gap algorithm the
// Python side uses.
function clusterByLonGap(boulders, n = 3) {
    const withGps = boulders.filter((b) => typeof b.lon === 'number' && !isNaN(b.lon));
    withGps.sort((a, b) => a.lon - b.lon);
    const letters = 'ABCDEFGHIJKL'.slice(0, n).split('');
    const anyManual = withGps.some((b) => typeof b.cluster === 'string' && b.cluster.trim());
    if (anyManual) {
        const groups = Object.fromEntries(letters.map((L) => [L, []]));
        const unassigned = [];
        for (const b of withGps) {
            const L = (b.cluster || '').trim().toUpperCase();
            if (L in groups) groups[L].push(b);
            else unassigned.push(b);
        }
        // Snap un-assigned boulders to the nearest cluster by mean longitude.
        for (const b of unassigned) {
            const nonEmpty = letters.filter((L) => groups[L].length);
            const nearest = nonEmpty.length
                ? nonEmpty.reduce((best, L) => {
                      const mean = groups[L].reduce((s, x) => s + x.lon, 0) / groups[L].length;
                      const dist = Math.abs(b.lon - mean);
                      return dist < best.dist ? { L, dist } : best;
                  }, { L: nonEmpty[0], dist: Infinity }).L
                : 'A';
            groups[nearest].push(b);
        }
        return letters.map((L) => groups[L].sort((a, b) => a.lon - b.lon));
    }
    if (withGps.length <= n) return withGps.map((b) => [b]).concat(
        Array.from({ length: Math.max(0, n - withGps.length) }, () => [])
    );
    const gaps = [];
    for (let k = 0; k < withGps.length - 1; k++) {
        gaps.push({ gap: withGps[k + 1].lon - withGps[k].lon, k });
    }
    gaps.sort((a, b) => b.gap - a.gap);
    const splits = gaps.slice(0, n - 1).map((g) => g.k).sort((a, b) => a - b);
    const clusters = [];
    let start = 0;
    for (const k of splits) {
        clusters.push(withGps.slice(start, k + 1));
        start = k + 1;
    }
    clusters.push(withGps.slice(start));
    return clusters;
}

// Called from the drag handler before we apply the user's move. Walks the
// currently displayed clusters and writes the corresponding letter onto
// each boulder so the manual-mode code path in clusterByLonGap keeps
// everyone else where they were.
function freezeCurrentClusters() {
    const clusters = clusterByLonGap(state.boulders, 3);
    const letters = 'ABCDEFGH';
    clusters.forEach((cluster, i) => {
        const letter = letters[i];
        for (const b of cluster) {
            if (!b.cluster) b.cluster = letter;
        }
    });
}


function renderClusters() {
    const clusters = clusterByLonGap(state.boulders, 3);
    els.clusterList.innerHTML = '';
    const letters = 'ABCDEFGH';
    clusters.forEach((cluster, i) => {
        const letter = letters[i];
        const li = document.createElement('li');
        li.className = 'cluster-item';
        li.dataset.letter = letter;

        const badge = document.createElement('div');
        badge.className = 'letter';
        badge.textContent = letter;

        const body = document.createElement('div');
        body.className = 'body';
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = `Cluster ${letter}`;
        input.value = state.clusterNames[letter] || '';
        input.addEventListener('input', () => {
            state.clusterNames[letter] = input.value;
            markDirty();
        });

        // Boulder chips — draggable; drop into another cluster's chip row
        // reassigns b.cluster and re-renders the whole tab.
        const chips = document.createElement('div');
        chips.className = 'chips';
        if (cluster.length) {
            for (const b of cluster) {
                const chip = document.createElement('span');
                chip.className = 'chip';
                chip.draggable = true;
                chip.dataset.boulderId = b._id;
                const idx = document.createElement('span');
                idx.className = 'idx';
                idx.textContent = String(b.id ?? '');
                const name = document.createElement('span');
                name.textContent = b.name || '(unnamed)';
                chip.append(idx, name);
                chip.addEventListener('dragstart', (e) => {
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', b._id);
                    requestAnimationFrame(() => chip.classList.add('dragging'));
                });
                chip.addEventListener('dragend', () => chip.classList.remove('dragging'));
                chips.append(chip);
            }
        } else {
            const empty = document.createElement('span');
            empty.className = 'empty';
            empty.textContent = '(drop boulders here)';
            chips.append(empty);
        }

        li.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            li.classList.add('drop-target');
        });
        li.addEventListener('dragleave', () => li.classList.remove('drop-target'));
        li.addEventListener('drop', (e) => {
            e.preventDefault();
            li.classList.remove('drop-target');
            const bid = e.dataTransfer.getData('text/plain');
            const b = state.boulders.find((x) => x._id === bid);
            if (!b || b.cluster === letter) return;
            // Freeze the CURRENT arrangement onto every boulder before we
            // apply the user's move — otherwise the "snap to nearest"
            // fallback in clusterByLonGap pulls all un-assigned boulders
            // into whichever cluster the newly-moved one just landed in.
            freezeCurrentClusters();
            b.cluster = letter;
            markDirty();
            renderClusters();
        });

        body.append(input, chips);
        li.append(badge, body);
        els.clusterList.append(li);
    });
}

// Gallery upload — mirrors the boulder-photo upload flow but posts to
// /api/gallery. Multiple files are accepted; each pushes onto the
// current boulder's gallery array.
els.addGallery.addEventListener('click', () => els.galleryInput.click());
els.galleryInput.addEventListener('change', async () => {
    const b = selectedBoulder();
    const files = [...els.galleryInput.files];
    els.galleryInput.value = '';
    if (!b || !files.length) return;
    els.addGallery.disabled = true;
    try {
        for (const file of files) {
            const fd = new FormData();
            fd.append('photo', file);
            fd.append('boulderName', b.name || '');
            const res = await fetch('/api/gallery', { method: 'POST', body: fd });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                setStatus(`Upload failed: ${err.error || res.status}`);
                continue;
            }
            const { filename } = await res.json();
            b.gallery = [...(b.gallery || []), filename];
            renderGallery();
            markDirty();
        }
        setStatus(`Uploaded ${files.length} to gallery`);
        setTimeout(() => setStatus(''), 2000);
    } finally {
        els.addGallery.disabled = false;
    }
});

function buildProblemRow(p) {
    const node = els.tpl.content.firstElementChild.cloneNode(true);
    node.dataset.pid = p._id;
    // The whole row is only draggable while the dedicated handle is grabbed —
    // that way clicking a text input, button or the row background never
    // kicks off a drag.
    node.draggable = false;

    // Drag handle — sits at the front of `.row-first`. It toggles the row's
    // draggable attribute on mousedown / dragend.
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'p-drag-handle';
    handle.setAttribute('aria-label', 'Drag to reorder');
    handle.setAttribute('title', 'Drag to reorder');
    handle.textContent = '⋮⋮';
    handle.addEventListener('mousedown', () => {
        node.draggable = true;
    });
    // Clicking the handle without dragging still needs a reset so a
    // subsequent click on any other row control doesn't start a drag.
    handle.addEventListener('mouseup', () => {
        node.draggable = false;
    });
    const rowFirst = node.querySelector('.row-first');
    rowFirst.prepend(handle);

    node.addEventListener('dragstart', (e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', p._id);
        requestAnimationFrame(() => node.classList.add('dragging'));
    });
    node.addEventListener('dragend', () => {
        node.classList.remove('dragging');
        node.draggable = false;
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

    const nInput = node.querySelector('.p-no');
    const nameInput = node.querySelector('.p-name');
    const gradeSel = node.querySelector('.p-grade');
    const projectCheck = node.querySelector('.p-project');
    const notes = node.querySelector('.p-notes');
    const notesFr = node.querySelector('.p-notes-fr');

    // Colour the whole card's border (and the active pencil button) to match
    // this problem's line — visual hook so the card and its drawn line share
    // the same identity. --accent is picked up by CSS.
    node.style.setProperty('--accent', accentColor(p));
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
    projectCheck.checked = !!p.project;

    nInput.addEventListener('input', () => {
        p.no = parseInt(nInput.value) || 0;
        node.style.setProperty('--accent', accentColor(p));
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
        node.style.setProperty('--accent', accentColor(p));
        renderOverlay();
        markDirty();
    });
    projectCheck.addEventListener('change', () => {
        p.project = projectCheck.checked;
        node.style.setProperty('--accent', accentColor(p));
        renderOverlay();
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
    const color = accentColor(p);

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
        if (p.project) line.setAttribute('stroke-dasharray', '6 5');
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
    marker.setAttribute('fill', color);
    marker.setAttribute('stroke', color);
    marker.setAttribute('stroke-width', 0);
    els.overlay.append(marker);

    const label = noPointer(document.createElementNS(SVG_NS, 'text'));
    label.setAttribute('x', first.x);
    label.setAttribute('y', first.y);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('dominant-baseline', 'central');
    label.setAttribute('font-family', 'Helvetica, Arial, sans-serif');
    label.setAttribute('font-weight', 'bold');
    label.setAttribute('font-size', '2.5');
    label.setAttribute('fill', '#ffffff');
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
    const b = { _id: uid(), name: 'New boulder', photo: '', problems: [], gallery: [] };
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
        project: false,
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
