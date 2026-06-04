/**
 * 管理后台核心交互逻辑 — 毕业季专属相册
 *
 * 架构：
 * - 状态管理：sessionStorage 持久化 JWT
 * - API 层：fetchAPI 统一注入 token + 处理 401/403
 * - UI 层：Tab 切换 + 动态 DOM 渲染
 */

// ============================================================================
// State
// ============================================================================

const state = {
    token: null,
    currentTab: 'students',
};

// ============================================================================
// Init
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    state.token = sessionStorage.getItem('admin_token');
    if (state.token) {
        showDashboard();
    } else {
        showLogin();
    }
    bindEvents();
});

// ============================================================================
// Auth — Login / Logout
// ============================================================================

function showLogin() {
    document.getElementById('login-overlay').classList.remove('hidden');
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('login-error').classList.add('hidden');
    document.getElementById('login-password').value = '';
}

function showDashboard() {
    document.getElementById('login-overlay').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    switchTab(state.currentTab);
}

function logout() {
    sessionStorage.removeItem('admin_token');
    state.token = null;
    showLogin();
}

async function handleLogin() {
    const password = document.getElementById('login-password').value.trim();
    const errEl = document.getElementById('login-error');

    if (!password) {
        errEl.textContent = '请输入密码';
        errEl.classList.remove('hidden');
        return;
    }

    try {
        const resp = await fetch('/api/admin/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });

        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || '登录失败');
        }

        const data = await resp.json();
        sessionStorage.setItem('admin_token', data.access_token);
        state.token = data.access_token;
        showDashboard();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.remove('hidden');
    }
}

// ============================================================================
// API Wrapper
// ============================================================================

async function fetchAPI(endpoint, options = {}) {
    const headers = {
        ...(options.headers || {}),
        Authorization: `Bearer ${state.token}`,
    };
    // 如果 body 不是 FormData，则设置 Content-Type
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }

    const resp = await fetch(endpoint, { ...options, headers });

    if (resp.status === 401 || resp.status === 403) {
        logout();
        throw new Error('认证已过期，请重新登录');
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
    const options = {
        method: 'POST',
        body: isFormData ? body : JSON.stringify(body),
    };
    const resp = await fetchAPI(url, options);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `操作失败 (${resp.status})`);
    }
    return resp.json();
}

async function apiPut(url, body) {
    const resp = await fetchAPI(url, {
        method: 'PUT',
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `操作失败 (${resp.status})`);
    }
    return resp.json();
}

async function apiDelete(url) {
    const resp = await fetchAPI(url, { method: 'DELETE' });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `操作失败 (${resp.status})`);
    }
}

// ============================================================================
// Toast
// ============================================================================

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');

    const bgColor = type === 'success'
        ? 'bg-green-500'
        : 'bg-red-500';

    toast.className = `${bgColor} text-white px-5 py-3 rounded-lg shadow-lg text-sm font-medium animate-[slideIn_0.3s_ease-out]`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================================================
// Tab Switching
// ============================================================================

function switchTab(name) {
    state.currentTab = name;

    // Update sidebar buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        const isActive = btn.dataset.tab === name;
        btn.classList.toggle('bg-indigo-50', isActive);
        btn.classList.toggle('text-indigo-700', isActive);
        btn.classList.toggle('font-medium', isActive);
        btn.classList.toggle('text-gray-600', !isActive);
    });

    // Update tab panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.toggle('hidden', panel.id !== `tab-${name}`);
    });

    loadTabData(name);
}

function loadTabData(name) {
    switch (name) {
        case 'students': loadStudents(); break;
        case 'tags':     loadTags(); break;
        case 'images':   loadImages(); break;
        // settings tab has no auto-load
    }
}

// ============================================================================
// Event Bindings
// ============================================================================

function bindEvents() {
    // Login
    document.getElementById('login-btn').addEventListener('click', handleLogin);
    document.getElementById('login-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleLogin();
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        if (confirm('确定要退出登录吗？')) logout();
    });

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Students
    document.getElementById('add-student-btn').addEventListener('click', addStudent);
    document.getElementById('student-name-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addStudent();
    });

    // Tags
    document.getElementById('add-tag-btn').addEventListener('click', addTag);
    document.getElementById('tag-name-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addTag();
    });

    // Images
    document.getElementById('upload-btn').addEventListener('click', uploadImages);

    // Settings
    document.getElementById('update-password-btn').addEventListener('click', updatePassword);
    document.getElementById('confirm-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') updatePassword();
    });
}

// ============================================================================
// Student Management
// ============================================================================

async function loadStudents() {
    try {
        const students = await apiGet('/api/admin/students');
        renderStudents(students);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderStudents(students) {
    const tbody = document.getElementById('students-tbody');
    const emptyEl = document.getElementById('students-empty');

    if (!students || students.length === 0) {
        tbody.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
    }

    emptyEl.classList.add('hidden');
    tbody.innerHTML = students.map(s => `
        <tr class="border-b border-gray-100 hover:bg-gray-50 transition-colors">
            <td class="py-3 font-medium">${escapeHtml(s.name)}</td>
            <td class="py-3">
                <code class="bg-gray-100 px-2 py-0.5 rounded text-sm font-mono">${escapeHtml(s.secret_key)}</code>
            </td>
            <td class="py-3 text-sm text-gray-500">${formatDate(s.created_at)}</td>
            <td class="py-3">
                <div class="flex gap-2">
                    <button class="reset-key-btn text-xs px-3 py-1.5 bg-amber-50 text-amber-700 rounded-lg hover:bg-amber-100 transition-colors font-medium"
                            data-id="${s.id}" data-name="${escapeHtml(s.name)}">🔄 重置密钥</button>
                    <button class="delete-student-btn text-xs px-3 py-1.5 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors font-medium"
                            data-id="${s.id}" data-name="${escapeHtml(s.name)}">🗑 删除</button>
                </div>
            </td>
        </tr>
    `).join('');

    // Bind events after render
    tbody.querySelectorAll('.reset-key-btn').forEach(btn => {
        btn.addEventListener('click', () => resetKey(parseInt(btn.dataset.id, 10), btn.dataset.name));
    });
    tbody.querySelectorAll('.delete-student-btn').forEach(btn => {
        btn.addEventListener('click', () => deleteStudent(parseInt(btn.dataset.id, 10), btn.dataset.name));
    });
}

async function addStudent() {
    const input = document.getElementById('student-name-input');
    const name = input.value.trim();
    if (!name) return;

    try {
        const student = await apiPost('/api/admin/students', { name });
        showToast(`已添加学生「${student.name}」，密钥：${student.secret_key}`);
        input.value = '';
        loadStudents();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function resetKey(id, name) {
    if (!confirm(`确定要重置「${name}」的个人密钥吗？`)) return;
    try {
        const result = await apiPost(`/api/admin/students/${id}/reset-key`);
        showToast(`「${name}」的新密钥：${result.new_key}`);
        loadStudents();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteStudent(id, name) {
    if (!confirm(`确定要删除学生「${name}」吗？此操作不可撤销。`)) return;
    try {
        await apiDelete(`/api/admin/students/${id}`);
        showToast(`已删除「${name}」`);
        loadStudents();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ============================================================================
// Tag Management
// ============================================================================

async function loadTags() {
    try {
        const tags = await apiGet('/api/admin/tags');
        renderTags(tags);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderTags(tags) {
    const list = document.getElementById('tags-list');
    const emptyEl = document.getElementById('tags-empty');

    if (!tags || tags.length === 0) {
        list.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
    }

    emptyEl.classList.add('hidden');
    list.innerHTML = tags.map(t => `
        <div class="flex items-center gap-2 bg-white rounded-lg px-4 py-2 shadow-sm border border-gray-200 group hover:border-indigo-300 transition-colors">
            <span class="text-sm font-medium">${escapeHtml(t.name)}</span>
            <button class="delete-tag-btn text-gray-400 hover:text-red-500 transition-colors ml-1"
                    data-id="${t.id}" data-name="${escapeHtml(t.name)}" title="删除">
                &times;
            </button>
        </div>
    `).join('');

    list.querySelectorAll('.delete-tag-btn').forEach(btn => {
        btn.addEventListener('click', () => deleteTag(parseInt(btn.dataset.id, 10), btn.dataset.name));
    });
}

async function addTag() {
    const input = document.getElementById('tag-name-input');
    const name = input.value.trim();
    if (!name) return;

    try {
        await apiPost('/api/admin/tags', { name });
        showToast(`已添加标签「${name}」`);
        input.value = '';
        loadTags();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteTag(id, name) {
    if (!confirm(`确定要删除标签「${name}」吗？`)) return;
    try {
        await apiDelete(`/api/admin/tags/${id}`);
        showToast(`已删除标签「${name}」`);
        loadTags();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ============================================================================
// Image Management
// ============================================================================

async function loadImages() {
    try {
        const data = await apiGet('/api/admin/images');
        renderImages(data);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderImages(data) {
    const grid = document.getElementById('image-grid');
    const emptyEl = document.getElementById('images-empty');

    if (!data || data.images.length === 0) {
        grid.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
    }

    emptyEl.classList.add('hidden');
    grid.innerHTML = data.images.map(img => `
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden group hover:shadow-md transition-shadow">
            <div class="aspect-[4/3] overflow-hidden bg-gray-100">
                <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.file_name || '')}"
                     class="w-full h-full object-cover"
                     loading="lazy"
                     onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22150%22><rect fill=%22%23f3f4f6%22 width=%22200%22 height=%22150%22/><text x=%22100%22 y=%2280%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2214%22>加载失败</text></svg>'"/>
            </div>
            <div class="p-3">
                <div class="flex flex-wrap gap-1 mb-2">
                    ${img.tags.map(t => `<span class="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full font-medium">${escapeHtml(t.name)}</span>`).join('')}
                </div>
                <div class="flex items-center justify-between">
                    <span class="text-xs text-gray-400 truncate max-w-[140px]">${escapeHtml(img.file_name || '—')}</span>
                    <button class="delete-image-btn text-xs text-red-500 hover:text-red-700 hover:bg-red-50 px-2 py-1 rounded transition-colors font-medium"
                            data-id="${img.id}" data-name="${escapeHtml(img.file_name || '图片')}">
                        删除
                    </button>
                </div>
            </div>
        </div>
    `).join('');

    grid.querySelectorAll('.delete-image-btn').forEach(btn => {
        btn.addEventListener('click', () => deleteImage(parseInt(btn.dataset.id, 10), btn.dataset.name));
    });
}

async function uploadImages() {
    const fileInput = document.getElementById('image-files');
    const tagsInput = document.getElementById('image-tags');
    const statusEl = document.getElementById('upload-status');

    const files = fileInput.files;
    if (!files || files.length === 0) {
        showToast('请先选择图片文件', 'error');
        return;
    }

    const tagsRaw = tagsInput.value.trim();
    const tagNames = tagsRaw
        ? tagsRaw.split(/[,，\s]+/).filter(Boolean)
        : [];

    const formData = new FormData();
    if (tagNames.length > 0) {
        formData.append('tags', JSON.stringify(tagNames));
    }
    for (const file of files) {
        formData.append('files', file);
    }

    const btn = document.getElementById('upload-btn');
    btn.disabled = true;
    btn.textContent = '上传中...';
    statusEl.classList.remove('hidden');
    statusEl.className = 'text-sm mt-3 text-gray-500';
    statusEl.textContent = `正在上传 ${files.length} 个文件...`;

    try {
        const result = await apiPost('/api/admin/images', formData);
        showToast(`成功上传 ${result.total} 张图片`);
        statusEl.className = 'text-sm mt-3 text-green-600';
        statusEl.textContent = `上传完成！共 ${result.total} 张图片`;
        fileInput.value = '';
        tagsInput.value = '';
        loadImages();
    } catch (err) {
        showToast(err.message, 'error');
        statusEl.className = 'text-sm mt-3 text-red-500';
        statusEl.textContent = err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = '上 传';
    }
}

async function deleteImage(id, name) {
    if (!confirm(`确定要删除「${name}」吗？`)) return;
    try {
        await apiDelete(`/api/admin/images/${id}`);
        showToast(`已删除「${name}」`);
        loadImages();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ============================================================================
// Album Settings
// ============================================================================

async function updatePassword() {
    const newPass = document.getElementById('new-password').value;
    const confirmPass = document.getElementById('confirm-password').value;
    const statusEl = document.getElementById('settings-status');

    if (!newPass) {
        setStatus(statusEl, '请输入新密码', 'error');
        return;
    }
    if (newPass !== confirmPass) {
        setStatus(statusEl, '两次输入的密码不一致', 'error');
        return;
    }

    try {
        await apiPut('/api/admin/album-password', { password: newPass });
        setStatus(statusEl, '密码已更新', 'success');
        document.getElementById('new-password').value = '';
        document.getElementById('confirm-password').value = '';
    } catch (err) {
        setStatus(statusEl, err.message, 'error');
    }
}

function setStatus(el, msg, type) {
    el.textContent = msg;
    el.classList.remove('hidden');
    el.className = `text-sm mt-3 text-center ${type === 'success' ? 'text-green-600' : 'text-red-500'}`;
}

// ============================================================================
// Utilities
// ============================================================================

function formatDate(isoString) {
    if (!isoString) return '—';
    const d = new Date(isoString);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
