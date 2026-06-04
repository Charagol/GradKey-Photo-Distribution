/**
 * admin.js — Phase 11: 沉浸式打标工作台
 *
 * 设计原则:
 * - State 驱动渲染: state 对象是唯一数据源，UI 通过 render*() 函数单向更新
 * - 事件委托: 容器级事件监听，避免重新绑定
 * - processingLock: 打标操作防抖，防止并发 API 调用混乱
 * - 自动分流: allImages → unprocessed (tags=[]) + processed (tags>0)
 */

// ==========================================================================
// Global State (single source of truth)
// ==========================================================================
const state = {
    // Auth
    token: null,

    // Navigation
    currentTab: 'workspace',

    // Image data (core)
    allImages: [],           // GET /api/admin/images 全量
    unprocessed: [],         // tags.length === 0
    processed: [],           // tags.length > 0
    currentImageId: null,    // currently selected unprocessed image

    // Tags
    tagGroups: [],           // GET /api/admin/tag-groups (nested tags)

    // Students
    students: [],

    // UI
    processedFilter: 'all',  // 'all' | 'tagged' | 'untagged'
    processingLock: false,   // prevent concurrent applyTag calls
    editingImageId: null,    // image being edited in modal
    modalTagIds: [],         // temp tag IDs in edit modal
};

// ==========================================================================
// Initialization
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    const savedToken = sessionStorage.getItem('admin_token');
    if (savedToken) {
        state.token = savedToken;
        showDashboard();
    } else {
        showLogin();
    }
    bindEvents();
});

// ==========================================================================
// Auth
// ==========================================================================
function showLogin() {
    document.getElementById('login-overlay').classList.remove('hidden');
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('login-error').classList.add('hidden');
    document.getElementById('login-password').value = '';
}

function showDashboard() {
    document.getElementById('login-overlay').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    switchTab('workspace');
}

function logout() {
    sessionStorage.removeItem('admin_token');
    state.token = null;
    showLogin();
}

async function handleLogin() {
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');

    try {
        const resp = await fetch('/api/admin/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.detail || '密码错误');
        }
        const data = await resp.json();
        state.token = data.access_token;
        sessionStorage.setItem('admin_token', state.token);
        showDashboard();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    }
}

// ==========================================================================
// API Helpers
// ==========================================================================
async function fetchAPI(endpoint, options = {}) {
    const headers = {
        'Authorization': `Bearer ${state.token}`,
        ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
    };

    const resp = await fetch(endpoint, { ...options, headers });

    if (resp.status === 401 || resp.status === 403) {
        logout();
        throw new Error('登录已过期，请重新登录');
    }
    return resp;
}

async function apiGet(url) {
    const resp = await fetchAPI(url);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败 (${resp.status})`);
    }
    return resp.json();
}

async function apiPost(url, body) {
    const isFormData = body instanceof FormData;
    const resp = await fetchAPI(url, {
        method: 'POST',
        body: isFormData ? body : JSON.stringify(body),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败 (${resp.status})`);
    }
    const text = await resp.text();
    return text ? JSON.parse(text) : null;
}

async function apiPut(url, body) {
    const resp = await fetchAPI(url, {
        method: 'PUT',
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败 (${resp.status})`);
    }
    const text = await resp.text();
    return text ? JSON.parse(text) : null;
}

async function apiDelete(url) {
    const resp = await fetchAPI(url, { method: 'DELETE' });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败 (${resp.status})`);
    }
}

// ==========================================================================
// Toast
// ==========================================================================
function showToast(message, type) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    const bg = type === 'error' ? 'bg-red-500' : 'bg-green-500';
    toast.className = `${bg} text-white px-5 py-3 rounded-lg shadow-lg text-sm font-medium transition-all duration-300`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => { toast.style.opacity = '1'; });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==========================================================================
// Utilities
// ==========================================================================
function formatDate(isoString) {
    if (!isoString) return '-';
    const d = new Date(isoString);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

// ==========================================================================
// Event Binding (delegation-based)
// ==========================================================================
function bindEvents() {
    // Login
    document.getElementById('login-btn').addEventListener('click', handleLogin);
    document.getElementById('login-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleLogin();
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        if (confirm('确定退出登录吗？')) logout();
    });

    // Sidebar navigation (delegate)
    document.getElementById('sidebar').addEventListener('click', (e) => {
        const btn = e.target.closest('.nav-btn');
        if (!btn) return;
        switchTab(btn.dataset.tab);
    });

    // ── Workspace events (delegate) ──
    document.getElementById('unprocessed-grid').addEventListener('click', (e) => {
        const item = e.target.closest('.thumb-item');
        if (!item || state.processingLock) return;
        selectImage(Number(item.dataset.imageId));
    });

    document.getElementById('tag-pool').addEventListener('click', (e) => {
        const chip = e.target.closest('.tag-chip');
        if (!chip || state.processingLock) return;
        applyTag(Number(chip.dataset.tagId));
    });

    document.getElementById('processed-grid').addEventListener('click', (e) => {
        const item = e.target.closest('.processed-item');
        if (!item) return;
        openEditModal(Number(item.dataset.imageId));
    });

    // Processed filter buttons
    document.getElementById('processed-section').addEventListener('click', (e) => {
        const btn = e.target.closest('.processed-filter-btn');
        if (!btn) return;
        state.processedFilter = btn.dataset.filter;
        renderProcessedFilters();
        renderProcessedGrid();
    });

    // ── Students ──
    document.getElementById('add-students-btn').addEventListener('click', addStudents);
    document.getElementById('student-names-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addStudents();
    });
    document.getElementById('students-tbody').addEventListener('click', (e) => {
        const resetBtn = e.target.closest('.reset-key-btn');
        if (resetBtn) {
            resetKey(Number(resetBtn.dataset.id), resetBtn.dataset.name);
            return;
        }
        const delBtn = e.target.closest('.delete-student-btn');
        if (delBtn) {
            deleteStudent(Number(delBtn.dataset.id), delBtn.dataset.name);
            return;
        }
    });

    // ── Tag Groups ──
    document.getElementById('add-group-btn').addEventListener('click', addTagGroup);
    document.getElementById('group-name-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addTagGroup();
    });
    document.getElementById('tag-group-list').addEventListener('click', (e) => {
        const renameBtn = e.target.closest('.rename-group-btn');
        if (renameBtn) {
            promptRenameGroup(Number(renameBtn.dataset.id), renameBtn.dataset.name);
            return;
        }
        const delBtn = e.target.closest('.delete-group-btn');
        if (delBtn) {
            deleteTagGroup(Number(delBtn.dataset.id), delBtn.dataset.name);
            return;
        }
        const moveSelect = e.target.closest('.move-tag-select');
        if (moveSelect) {
            moveSelect.addEventListener('change', function handler() {
                moveTagToGroup(Number(moveSelect.dataset.tagId), Number(this.value));
                moveSelect.removeEventListener('change', handler);
            });
        }
    });

    // ── Image Upload ──
    document.getElementById('upload-btn').addEventListener('click', uploadImages);

    // ── Settings ──
    document.getElementById('update-password-btn').addEventListener('click', updatePassword);
    document.getElementById('confirm-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') updatePassword();
    });

    // ── Edit Modal ──
    document.getElementById('modal-close-btn').addEventListener('click', closeEditModal);
    document.getElementById('modal-cancel-btn').addEventListener('click', closeEditModal);
    document.getElementById('modal-save-btn').addEventListener('click', saveImageTags);
    document.getElementById('edit-modal').addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-backdrop')) closeEditModal();
    });
    document.getElementById('modal-available-tags').addEventListener('click', (e) => {
        const chip = e.target.closest('.modal-add-tag-chip');
        if (!chip) return;
        addTagToEdit(Number(chip.dataset.tagId));
    });
    document.getElementById('modal-current-tags').addEventListener('click', (e) => {
        const btn = e.target.closest('.modal-remove-tag-btn');
        if (!btn) return;
        removeTagFromEdit(Number(btn.dataset.tagId));
    });
}

// ==========================================================================
// Tab Switching
// ==========================================================================
function switchTab(name) {
    state.currentTab = name;

    // Update sidebar buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        if (btn.dataset.tab === name) {
            btn.classList.add('bg-indigo-50', 'text-indigo-700');
            btn.classList.remove('text-gray-600', 'hover:bg-gray-50');
        } else {
            btn.classList.remove('bg-indigo-50', 'text-indigo-700');
            btn.classList.add('text-gray-600', 'hover:bg-gray-50');
        }
    });

    // Show/hide tab panels
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    const panel = document.getElementById(`tab-${name}`);
    if (panel) panel.classList.remove('hidden');

    // Load data
    if (name === 'workspace') {
        loadAllWorkspaceData();
    } else if (name === 'students') {
        loadStudents();
    } else if (name === 'tag-groups') {
        loadTagGroups();
    } else if (name === 'images') {
        loadAllImages();
    }
}

// ==========================================================================
// Data Loading
// ==========================================================================
async function loadAllWorkspaceData() {
    try {
        await Promise.all([loadImages(), loadTagGroups()]);
        splitImages();
        renderWorkspace();
        renderProcessedGrid();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadImages() {
    const data = await apiGet('/api/admin/images');
    state.allImages = data.images || [];
}

async function loadTagGroups() {
    state.tagGroups = await apiGet('/api/admin/tag-groups');
}

async function loadStudents() {
    try {
        state.students = await apiGet('/api/admin/students');
    } catch (err) {
        showToast(err.message, 'error');
        state.students = [];
    }
    renderStudents();
}

async function loadAllImages() {
    try {
        await loadImages();
        renderAllImages();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ==========================================================================
// Image Splitting
// ==========================================================================
function splitImages() {
    state.unprocessed = state.allImages.filter(img => !img.tags || img.tags.length === 0);
    state.processed = state.allImages
        .filter(img => img.tags && img.tags.length > 0)
        .sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));

    // Auto-select first unprocessed
    if (state.unprocessed.length > 0) {
        state.currentImageId = state.unprocessed[0].id;
    } else {
        state.currentImageId = null;
    }
}

// ==========================================================================
// Workspace Rendering
// ==========================================================================
function renderWorkspace() {
    const area = document.getElementById('workspace-area');
    const empty = document.getElementById('workspace-empty');

    if (state.unprocessed.length === 0) {
        area.classList.add('hidden');
        empty.classList.remove('hidden');
    } else {
        area.classList.remove('hidden');
        empty.classList.add('hidden');
        renderUnprocessedGrid();
        renderTagPool();
    }

    // Update counts
    document.getElementById('unprocessed-count').textContent = `${state.unprocessed.length} 张`;
    document.getElementById('processed-count').textContent = `${state.processed.length} 张`;
}

function renderUnprocessedGrid() {
    const grid = document.getElementById('unprocessed-grid');
    grid.innerHTML = state.unprocessed.map(img => {
        const isSelected = img.id === state.currentImageId;
        const ringClass = isSelected ? 'ring-2 ring-indigo-500 ring-offset-2' : '';
        return `
            <div class="thumb-item ${ringClass} rounded-lg overflow-hidden cursor-pointer bg-gray-100 transition-shadow hover:shadow-md"
                 data-image-id="${img.id}">
                <div class="aspect-[4/3]">
                    <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.file_name || '')}"
                         class="w-full h-full object-cover"
                         loading="lazy"
                         onerror="this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 30%22%3E%3Crect fill=%22%23f3f4f6%22 width=%2240%22 height=%2230%22/%3E%3Ctext x=%2220%22 y=%2217%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%226%22%3E🖼%3C/text%3E%3C/svg%3E'">
                </div>
                <div class="px-2 py-1.5">
                    <p class="text-xs text-gray-600 truncate">${escapeHtml(img.file_name || 'untitled')}</p>
                </div>
            </div>`;
    }).join('');

    if (state.unprocessed.length === 0) {
        grid.innerHTML = '<p class="col-span-full text-center text-gray-400 py-8">暂无待打标图片</p>';
    }
}

function selectImage(id) {
    state.currentImageId = id;
    // Only update highlights, no full re-render needed
    document.querySelectorAll('#unprocessed-grid .thumb-item').forEach(el => {
        if (Number(el.dataset.imageId) === id) {
            el.classList.add('ring-2', 'ring-indigo-500', 'ring-offset-2');
        } else {
            el.classList.remove('ring-2', 'ring-indigo-500', 'ring-offset-2');
        }
    });
}

function renderTagPool() {
    const container = document.getElementById('tag-group-panels');
    container.innerHTML = state.tagGroups.map(group => {
        const tags = group.tags || [];
        return `
            <div class="tag-group-panel bg-white rounded-xl border border-gray-200 p-4">
                <div class="flex items-center justify-between mb-3">
                    <h4 class="text-sm font-semibold text-gray-800">${escapeHtml(group.name)}</h4>
                    <span class="text-xs text-gray-400">${tags.length} 个标签</span>
                </div>
                <div class="flex flex-wrap gap-2">
                    ${tags.map(tag => `
                        <button class="tag-chip inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium transition-all
                                       bg-gray-50 text-gray-700 border border-gray-200
                                       hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-300 active:scale-95"
                                data-tag-id="${tag.id}">
                            ${escapeHtml(tag.name)}
                        </button>
                    `).join('')}
                    ${tags.length === 0 ? '<span class="text-xs text-gray-400">暂无标签</span>' : ''}
                </div>
            </div>`;
    }).join('');

    if (state.tagGroups.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-sm py-4">暂无标签分组，请先在"标签分组"中添加</p>';
    }
}

// ==========================================================================
// Core: Apply Tag (the heart of the workflow)
// ==========================================================================
async function applyTag(tagId) {
    if (state.processingLock) return;
    if (!state.currentImageId) return;

    const image = state.allImages.find(img => img.id === state.currentImageId);
    if (!image) return;

    // Compute new tag_ids: existing + new
    const existingIds = (image.tags || []).map(t => t.id);
    const newTagIds = [...existingIds, tagId];

    // Deduplicate
    const uniqueIds = [...new Set(newTagIds)];

    state.processingLock = true;

    try {
        await apiPut(`/api/admin/images/${image.id}/tags`, { tag_ids: uniqueIds });

        // Update local state
        const tagName = findTagName(tagId);
        image.tags = uniqueIds.map(id => ({ id, name: findTagName(id), group_id: findTagGroupId(id) }));

        // Move from unprocessed to processed
        const idx = state.unprocessed.findIndex(img => img.id === image.id);
        if (idx !== -1) {
            state.unprocessed.splice(idx, 1);
            state.processed.unshift(image);
        }

        // Auto-select next
        if (state.unprocessed.length > 0) {
            state.currentImageId = state.unprocessed[0].id;
        } else {
            state.currentImageId = null;
        }

        renderWorkspace();
        renderProcessedGrid();
        showToast(`已为图片添加标签「${tagName}」`, 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        state.processingLock = false;
    }
}

function findTagName(tagId) {
    for (const group of state.tagGroups) {
        for (const tag of (group.tags || [])) {
            if (tag.id === tagId) return tag.name;
        }
    }
    return `#${tagId}`;
}

function findTagGroupId(tagId) {
    for (const group of state.tagGroups) {
        for (const tag of (group.tags || [])) {
            if (tag.id === tagId) return tag.group_id;
        }
    }
    return null;
}

// ==========================================================================
// Processed Grid
// ==========================================================================
function renderProcessedFilters() {
    document.querySelectorAll('.processed-filter-btn').forEach(btn => {
        if (btn.dataset.filter === state.processedFilter) {
            btn.classList.add('bg-indigo-600', 'text-white');
            btn.classList.remove('bg-gray-100', 'text-gray-600', 'hover:bg-gray-200');
        } else {
            btn.classList.remove('bg-indigo-600', 'text-white');
            btn.classList.add('bg-gray-100', 'text-gray-600', 'hover:bg-gray-200');
        }
    });
}

function renderProcessedGrid() {
    const grid = document.getElementById('processed-grid');
    const empty = document.getElementById('processed-empty');
    const currentFilter = state.processedFilter;

    let items;
    if (currentFilter === 'all') {
        items = state.processed;
    } else if (currentFilter === 'tagged') {
        items = state.processed.filter(img => img.tags && img.tags.length > 0);
    } else {
        items = state.processed.filter(img => !img.tags || img.tags.length === 0);
    }

    if (items.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
    } else {
        empty.classList.add('hidden');
        grid.innerHTML = items.map(img => {
            return `
                <div class="processed-item rounded-lg overflow-hidden cursor-pointer bg-white border border-gray-200 shadow-sm hover:shadow-md transition-shadow"
                     data-image-id="${img.id}">
                    <div class="aspect-[4/3] bg-gray-100">
                        <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.file_name || '')}"
                             class="w-full h-full object-cover"
                             loading="lazy"
                             onerror="this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 30%22%3E%3Crect fill=%22%23f3f4f6%22 width=%2240%22 height=%2230%22/%3E%3Ctext x=%2220%22 y=%2217%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%226%22%3E🖼%3C/text%3E%3C/svg%3E'">
                    </div>
                    <div class="p-2">
                        <p class="text-xs text-gray-600 truncate mb-1.5">${escapeHtml(img.file_name || 'untitled')}</p>
                        <div class="flex flex-wrap gap-1">
                            ${(img.tags || []).map(t => `
                                <span class="inline-block bg-indigo-50 text-indigo-600 text-[10px] px-1.5 py-0.5 rounded">${escapeHtml(t.name)}</span>
                            `).join('')}
                            ${(!img.tags || img.tags.length === 0) ? '<span class="text-[10px] text-gray-400">未打标</span>' : ''}
                        </div>
                    </div>
                </div>`;
        }).join('');
    }
}

// ==========================================================================
// Edit Modal
// ==========================================================================
function openEditModal(imageId) {
    const image = state.allImages.find(img => img.id === imageId);
    if (!image) return;

    state.editingImageId = imageId;
    state.modalTagIds = (image.tags || []).map(t => t.id);

    document.getElementById('modal-preview-img').src = image.url;
    renderModalCurrentTags();
    renderModalAvailableTags();

    document.getElementById('edit-modal').classList.remove('hidden');
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.add('hidden');
    state.editingImageId = null;
    state.modalTagIds = [];
}

function renderModalCurrentTags() {
    const container = document.getElementById('modal-current-tags');
    const empty = document.getElementById('modal-no-tags');

    if (state.modalTagIds.length === 0) {
        container.innerHTML = '';
        empty.classList.remove('hidden');
    } else {
        empty.classList.add('hidden');
        container.innerHTML = state.modalTagIds.map(id => `
            <span class="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 text-sm px-2.5 py-1 rounded-full">
                ${escapeHtml(findTagName(id))}
                <button class="modal-remove-tag-btn text-indigo-400 hover:text-red-500 ml-0.5" data-tag-id="${id}">&times;</button>
            </span>
        `).join('');
    }
}

function renderModalAvailableTags() {
    const container = document.getElementById('modal-available-tags');
    // Flatten all tags from all groups, exclude already added ones
    const allTags = [];
    for (const group of state.tagGroups) {
        for (const tag of (group.tags || [])) {
            if (!state.modalTagIds.includes(tag.id)) {
                allTags.push(tag);
            }
        }
    }

    if (allTags.length === 0) {
        container.innerHTML = '<span class="text-xs text-gray-400">所有标签已添加</span>';
    } else {
        container.innerHTML = allTags.map(tag => `
            <button class="modal-add-tag-chip text-sm px-3 py-1 rounded-full border border-dashed border-gray-300 text-gray-500
                           hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                    data-tag-id="${tag.id}">
                + ${escapeHtml(tag.name)}
            </button>
        `).join('');
    }
}

function addTagToEdit(tagId) {
    if (!state.modalTagIds.includes(tagId)) {
        state.modalTagIds.push(tagId);
        renderModalCurrentTags();
        renderModalAvailableTags();
    }
}

function removeTagFromEdit(tagId) {
    state.modalTagIds = state.modalTagIds.filter(id => id !== tagId);
    renderModalCurrentTags();
    renderModalAvailableTags();
}

async function saveImageTags() {
    if (!state.editingImageId) return;

    try {
        await apiPut(`/api/admin/images/${state.editingImageId}/tags`, {
            tag_ids: state.modalTagIds
        });

        closeEditModal();
        showToast('标签已更新', 'success');

        // Reload all data to refresh state
        await loadImages();
        splitImages();
        renderWorkspace();
        renderProcessedGrid();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ==========================================================================
// Students Management
// ==========================================================================
async function addStudents() {
    const input = document.getElementById('student-names-input');
    const names = input.value.trim();
    if (!names) {
        showToast('请输入学生姓名', 'error');
        return;
    }

    try {
        const data = await apiPost('/api/admin/students', { names });
        const keys = data.map(s => `${s.name}: ${s.secret_key}`).join(', ');
        showToast(`成功添加 ${data.length} 名学生`, 'success');
        if (data.length <= 3) {
            showToast(`密钥: ${keys}`, 'success');
        }
        input.value = '';
        await loadStudents();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderStudents() {
    const tbody = document.getElementById('students-tbody');
    const empty = document.getElementById('students-empty');

    if (state.students.length === 0) {
        tbody.innerHTML = '';
        empty.classList.remove('hidden');
        // Hide table
        tbody.closest('.bg-white').querySelector('.overflow-x-auto').classList.add('hidden');
        return;
    }

    empty.classList.add('hidden');
    tbody.closest('.bg-white').querySelector('.overflow-x-auto').classList.remove('hidden');

    tbody.innerHTML = state.students.map(s => `
        <tr class="border-b border-gray-100">
            <td class="px-4 py-3 font-medium text-gray-800">${escapeHtml(s.name)}</td>
            <td class="px-4 py-3">
                <code class="bg-gray-100 text-gray-700 px-2 py-0.5 rounded text-xs font-mono">${escapeHtml(s.secret_key)}</code>
            </td>
            <td class="px-4 py-3 text-gray-500">${formatDate(s.created_at)}</td>
            <td class="px-4 py-3">
                <button class="reset-key-btn text-xs bg-amber-50 text-amber-700 px-2.5 py-1 rounded hover:bg-amber-100 transition-colors mr-1"
                        data-id="${s.id}" data-name="${escapeHtml(s.name)}">重置密钥</button>
                <button class="delete-student-btn text-xs bg-red-50 text-red-600 px-2.5 py-1 rounded hover:bg-red-100 transition-colors"
                        data-id="${s.id}" data-name="${escapeHtml(s.name)}">删除</button>
            </td>
        </tr>
    `).join('');
}

async function resetKey(id, name) {
    if (!confirm(`确定重置「${name}」的密钥吗？旧密钥将失效。`)) return;
    try {
        const data = await apiPost(`/api/admin/students/${id}/reset-key`);
        showToast(`新密钥: ${data.new_key}`, 'success');
        await loadStudents();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteStudent(id, name) {
    if (!confirm(`确定删除学生「${name}」吗？此操作不可撤销。`)) return;
    try {
        await apiDelete(`/api/admin/students/${id}`);
        showToast(`已删除「${name}」`, 'success');
        await loadStudents();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ==========================================================================
// Tag Groups Management
// ==========================================================================
async function addTagGroup() {
    const input = document.getElementById('group-name-input');
    const name = input.value.trim();
    if (!name) {
        showToast('请输入分组名称', 'error');
        return;
    }

    try {
        await apiPost('/api/admin/tag-groups', { name });
        showToast(`分组「${name}」已创建`, 'success');
        input.value = '';
        await loadTagGroups();
        renderTagGroups();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderTagGroups() {
    const list = document.getElementById('tag-group-list');
    const empty = document.getElementById('groups-empty');

    if (state.tagGroups.length === 0) {
        list.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');

    list.innerHTML = state.tagGroups.map(group => {
        const tags = group.tags || [];
        return `
            <div class="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-2">
                        <h4 class="font-semibold text-gray-800">${escapeHtml(group.name)}</h4>
                        <span class="text-xs text-gray-400">${tags.length} 个标签</span>
                    </div>
                    <div class="flex gap-2">
                        <button class="rename-group-btn text-xs text-gray-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-gray-50 transition-colors"
                                data-id="${group.id}" data-name="${escapeHtml(group.name)}">重命名</button>
                        ${group.name !== '未分类' ? `
                        <button class="delete-group-btn text-xs text-red-400 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50 transition-colors"
                                data-id="${group.id}" data-name="${escapeHtml(group.name)}">删除</button>
                        ` : ''}
                    </div>
                </div>
                <div class="flex flex-wrap gap-2">
                    ${tags.map(tag => `
                        <span class="group inline-flex items-center gap-1 bg-gray-50 border border-gray-200 text-gray-700 text-sm px-2.5 py-1 rounded-full">
                            ${escapeHtml(tag.name)}
                            <select class="move-tag-select text-[10px] border-none bg-transparent text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity outline-none cursor-pointer"
                                    data-tag-id="${tag.id}">
                                <option value="">移动至...</option>
                                ${state.tagGroups.filter(g => g.id !== tag.group_id).map(g => `
                                    <option value="${g.id}">${escapeHtml(g.name)}</option>
                                `).join('')}
                            </select>
                        </span>
                    `).join('')}
                    ${tags.length === 0 ? '<span class="text-xs text-gray-400">暂无标签</span>' : ''}
                </div>
            </div>`;
    }).join('');
}

async function promptRenameGroup(id, currentName) {
    const newName = prompt('重命名分组：', currentName);
    if (!newName || newName.trim() === currentName || !newName.trim()) return;

    try {
        await apiPut(`/api/admin/tag-groups/${id}`, { name: newName.trim() });
        showToast(`分组已更名为「${newName.trim()}」`, 'success');
        await loadTagGroups();
        renderTagGroups();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteTagGroup(id, name) {
    if (!confirm(`确定删除分组「${name}」吗？组内标签将迁移至「未分类」。`)) return;

    try {
        await apiDelete(`/api/admin/tag-groups/${id}`);
        showToast(`分组「${name}」已删除`, 'success');
        await loadTagGroups();
        renderTagGroups();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function moveTagToGroup(tagId, groupId) {
    if (!groupId) return;

    try {
        await apiPut(`/api/admin/tags/${tagId}`, { group_id: groupId });
        showToast('标签已移动', 'success');
        await loadTagGroups();
        renderTagGroups();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ==========================================================================
// Image Upload Management
// ==========================================================================
async function uploadImages() {
    const filesInput = document.getElementById('image-files');
    const tagsInput = document.getElementById('image-tags');
    const statusEl = document.getElementById('upload-status');

    if (!filesInput.files || filesInput.files.length === 0) {
        showToast('请选择图片文件', 'error');
        return;
    }

    const formData = new FormData();
    for (const file of filesInput.files) {
        formData.append('files', file);
    }

    const tagNames = tagsInput.value
        .split(/[,，\s]+/)
        .map(s => s.trim())
        .filter(Boolean);
    if (tagNames.length > 0) {
        formData.append('tags', JSON.stringify(tagNames));
    }

    const uploadBtn = document.getElementById('upload-btn');
    uploadBtn.disabled = true;
    uploadBtn.textContent = '上传中...';
    statusEl.textContent = `正在上传 ${filesInput.files.length} 个文件...`;
    statusEl.classList.remove('hidden');

    try {
        const data = await apiPost('/api/admin/images', formData);
        showToast(`成功上传 ${data.images.length} 张图片`, 'success');
        filesInput.value = '';
        tagsInput.value = '';
        statusEl.classList.add('hidden');
        await loadImages();
        renderAllImages();
    } catch (err) {
        showToast(err.message, 'error');
        statusEl.textContent = '上传失败';
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = '上传';
    }
}

function renderAllImages() {
    const grid = document.getElementById('image-manage-grid');
    const empty = document.getElementById('images-manage-empty');

    if (state.allImages.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    grid.innerHTML = state.allImages.map(img => `
        <div class="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow">
            <div class="aspect-[4/3] bg-gray-100">
                <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.file_name || '')}"
                     class="w-full h-full object-cover"
                     loading="lazy"
                     onerror="this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 30%22%3E%3Crect fill=%22%23f3f4f6%22 width=%2240%22 height=%2230%22/%3E%3Ctext x=%2220%22 y=%2217%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%226%22%3E🖼%3C/text%3E%3C/svg%3E'">
            </div>
            <div class="p-2">
                <p class="text-xs text-gray-600 truncate mb-1">${escapeHtml(img.file_name || 'untitled')}</p>
                <div class="flex flex-wrap gap-1 mb-2">
                    ${(img.tags || []).map(t => `
                        <span class="bg-indigo-50 text-indigo-600 text-[10px] px-1.5 py-0.5 rounded">${escapeHtml(t.name)}</span>
                    `).join('')}
                </div>
                <button class="delete-image-btn w-full text-xs text-red-500 hover:text-red-700 hover:bg-red-50 py-1 rounded transition-colors"
                        data-id="${img.id}" data-name="${escapeHtml(img.file_name || 'untitled')}">
                    删除
                </button>
            </div>
        </div>
    `).join('');

    // Bind delete buttons (event delegation on grid)
    grid.querySelectorAll('.delete-image-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const id = Number(btn.dataset.id);
            const name = btn.dataset.name;
            if (confirm(`确定删除图片「${name}」吗？`)) {
                try {
                    await apiDelete(`/api/admin/images/${id}`);
                    showToast('图片已删除', 'success');
                    await loadImages();
                    renderAllImages();
                } catch (err) {
                    showToast(err.message, 'error');
                }
            }
        });
    });
}

// ==========================================================================
// Settings
// ==========================================================================
async function updatePassword() {
    const newPw = document.getElementById('new-password').value;
    const confirmPw = document.getElementById('confirm-password').value;
    const statusEl = document.getElementById('settings-status');

    if (!newPw) {
        statusEl.textContent = '请输入新密码';
        statusEl.className = 'text-sm text-red-500 mt-3';
        statusEl.classList.remove('hidden');
        return;
    }
    if (newPw !== confirmPw) {
        statusEl.textContent = '两次密码不一致';
        statusEl.className = 'text-sm text-red-500 mt-3';
        statusEl.classList.remove('hidden');
        return;
    }

    try {
        await apiPut('/api/admin/album-password', { password: newPw });
        statusEl.textContent = '密码更新成功';
        statusEl.className = 'text-sm text-green-600 mt-3';
        statusEl.classList.remove('hidden');
        document.getElementById('new-password').value = '';
        document.getElementById('confirm-password').value = '';
    } catch (err) {
        statusEl.textContent = err.message;
        statusEl.className = 'text-sm text-red-500 mt-3';
        statusEl.classList.remove('hidden');
    }
}
