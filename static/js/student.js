/**
 * 学生门户核心交互逻辑 — 毕业季专属相册 V2.0 (Phase 12)
 *
 * 架构：
 * - 状态管理：sessionStorage 持久化 JWT（关闭标签页即清除）
 * - 双重认证：相册密码 + 姓名 + 个人密钥
 * - 隐私隔离：后端只返回 Tag 匹配的照片，前端按标签过滤
 * - Lightbox：全屏预览 + 键盘导航 + 触摸滑动
 * - 多选模式：点击切换选中 → 批量队列下载（防拦截 400ms 间隔）
 * - OSS 缩略图：列表用 400px 缩略图，Lightbox 和下载用原图
 */

// ============================================================================
// State
// ============================================================================

const state = {
    token: null,
    studentName: null,
    allImages: [],
    allTags: [],
    activeTag: '__all__',
    lightboxIndex: -1,

    // Phase 12: 多选与下载
    isMultiSelectMode: false,
    selectedIds: new Set(),
    downloadProgress: null,     // { current: number, total: number } | null
    downloadAborted: false,
};

// ============================================================================
// Init
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    state.token = sessionStorage.getItem('student_token');
    state.studentName = sessionStorage.getItem('student_name');
    if (state.token && state.studentName) {
        showMain();
        loadData();
    } else {
        showLogin();
    }
});

// ============================================================================
// Login / Logout
// ============================================================================

function showLogin() {
    document.getElementById('login-overlay').classList.remove('hidden');
    document.getElementById('main-app').classList.add('hidden');
    document.getElementById('login-error').classList.add('hidden');
}

function showMain() {
    document.getElementById('login-overlay').classList.add('hidden');
    document.getElementById('main-app').classList.remove('hidden');
    document.getElementById('student-name-display').textContent = `— ${escapeHtml(state.studentName)}`;
}

function clearToken() {
    sessionStorage.removeItem('student_token');
    sessionStorage.removeItem('student_name');
    state.token = null;
    state.studentName = null;
    state.allImages = [];
    state.allTags = [];
    state.activeTag = '__all__';
    state.isMultiSelectMode = false;
    state.selectedIds = new Set();
    state.downloadProgress = null;
    state.downloadAborted = false;
}

async function handleLogin() {
    const albumPassword = document.getElementById('login-album-pw').value.trim();
    const name = document.getElementById('login-name').value.trim();
    const secretKey = document.getElementById('login-secret').value.trim();
    const errEl = document.getElementById('login-error');
    const btn = document.getElementById('login-btn');

    if (!albumPassword || !name || !secretKey) {
        errEl.textContent = '请填写所有字段';
        errEl.classList.remove('hidden');
        return;
    }

    btn.disabled = true;
    btn.textContent = '登录中...';
    errEl.classList.add('hidden');

    try {
        const resp = await fetch('/api/student/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                album_password: albumPassword,
                name: name,
                secret_key: secretKey,
            }),
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.detail || '登录失败');
        }

        const data = await resp.json();
        sessionStorage.setItem('student_token', data.access_token);
        sessionStorage.setItem('student_name', name);
        state.token = data.access_token;
        state.studentName = name;

        document.getElementById('login-album-pw').value = '';
        document.getElementById('login-name').value = '';
        document.getElementById('login-secret').value = '';

        showMain();
        loadData();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.remove('hidden');
    } finally {
        btn.disabled = false;
        btn.textContent = '登 录';
    }
}

function logout() {
    clearToken();
    showLogin();
}

// ============================================================================
// API Wrapper
// ============================================================================

async function fetchAPI(endpoint, options = {}) {
    const headers = {
        ...(options.headers || {}),
        Authorization: `Bearer ${state.token}`,
    };
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }

    const resp = await fetch(endpoint, { ...options, headers });

    if (resp.status === 401 || resp.status === 403) {
        clearToken();
        showLogin();
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

// ============================================================================
// Data Loading
// ============================================================================

async function loadData() {
    try {
        const [imagesData, tags] = await Promise.all([
            apiGet('/api/student/my-images'),
            apiGet('/api/student/my-tags'),
        ]);
        state.allImages = imagesData.images || [];
        state.allTags = tags || [];

        // Keep selectedIds in sync: remove IDs no longer in allImages
        if (state.isMultiSelectMode) {
            const validIds = new Set(state.allImages.map(img => img.id));
            state.selectedIds = new Set([...state.selectedIds].filter(id => validIds.has(id)));
        }

        renderTagFilter();
        renderPhotoGrid();
        updateSelectionUI();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ============================================================================
// Tag Filter
// ============================================================================

function renderTagFilter() {
    const list = document.getElementById('tag-filter-list');
    let html = `<button class="filter-pill ${state.activeTag === '__all__' ? 'bg-indigo-600 text-white shadow-md' : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'} px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all" data-tag="__all__">全部</button>`;

    state.allTags.forEach(tag => {
        const isActive = state.activeTag === tag.name;
        html += `<button class="filter-pill ${isActive ? 'bg-indigo-600 text-white shadow-md' : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'} px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all" data-tag="${escapeHtml(tag.name)}">${escapeHtml(tag.name)}</button>`;
    });

    list.innerHTML = html;

    list.querySelectorAll('.filter-pill').forEach(btn => {
        btn.addEventListener('click', () => {
            state.activeTag = btn.dataset.tag;
            renderTagFilter();
            renderPhotoGrid();
        });
    });
}

function getFilteredImages() {
    if (state.activeTag === '__all__') return state.allImages;
    return state.allImages.filter(img =>
        img.tags && img.tags.some(t => t.name === state.activeTag)
    );
}

// ============================================================================
// OSS Thumbnail URL Helper
// ============================================================================

/**
 * 在 OSS 签名 URL 后拼接缩略图处理参数。
 * 签名 URL 已含 ? 参数，因此用 & 拼接 x-oss-process。
 * 格式: ...?Expires=...&Signature=...&x-oss-process=image/resize,m_lfit,w_400,h_400
 */
function thumbnailUrl(originalUrl) {
    if (!originalUrl) return '';
    const sep = originalUrl.includes('?') ? '&' : '?';
    return `${originalUrl}${sep}x-oss-process=image/resize,m_lfit,w_400,h_400`;
}

// ============================================================================
// Photo Grid (Mobile-First)
// ============================================================================

function renderPhotoGrid() {
    const grid = document.getElementById('photo-grid');
    const emptyEl = document.getElementById('photos-empty');
    const filteredEmptyEl = document.getElementById('photos-filtered-empty');

    const images = getFilteredImages();

    if (state.allImages.length === 0) {
        grid.innerHTML = '';
        emptyEl.classList.remove('hidden');
        filteredEmptyEl.classList.add('hidden');
        return;
    }
    emptyEl.classList.add('hidden');

    if (images.length === 0) {
        grid.innerHTML = '';
        filteredEmptyEl.classList.remove('hidden');
        return;
    }
    filteredEmptyEl.classList.add('hidden');

    grid.innerHTML = images.map((img, index) => {
        const isSelected = state.isMultiSelectMode && state.selectedIds.has(img.id);
        // Use thumbnail for grid, original for lightbox
        const gridSrc = thumbnailUrl(img.url);

        return `
            <div class="photo-card group relative rounded-2xl overflow-hidden shadow-sm hover:shadow-lg transition-all cursor-pointer animate-slide-up bg-gray-100"
                 data-id="${img.id}"
                 data-index="${index}"
                 data-img-url="${escapeHtml(img.url)}"
                 style="animation-delay: ${index * 0.03}s">
                <div class="aspect-[4/5] sm:aspect-square overflow-hidden">
                    <img
                        src="${escapeHtml(gridSrc)}"
                        alt="${escapeHtml(img.file_name || '照片')}"
                        class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                        loading="lazy"
                        onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22300%22><rect fill=%22%23e5e7eb%22 width=%22300%22 height=%22300%22/><text x=%22150%22 y=%22155%22 text-anchor=%22middle%22 fill=%22%239ca3af%22 font-size=%2216%22>加载失败</text></svg>'"
                    />
                </div>

                <!-- Multi-select overlay (visible when selected) -->
                <div class="multi-select-overlay absolute inset-0 ${isSelected ? 'flex' : 'hidden'} items-center justify-center bg-indigo-500/30 border-2 border-indigo-500 rounded-2xl pointer-events-none">
                    <div class="w-8 h-8 bg-indigo-600 rounded-full flex items-center justify-center shadow-lg">
                        <span class="text-white text-sm font-bold">✓</span>
                    </div>
                </div>

                ${img.tags && img.tags.length > 0 ? `
                <div class="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent p-3 pt-6">
                    <div class="flex flex-wrap gap-1">
                        ${img.tags.map(t => `<span class="text-[10px] sm:text-xs bg-white/20 backdrop-blur text-white px-2 py-0.5 rounded-full">${escapeHtml(t.name)}</span>`).join('')}
                    </div>
                </div>` : ''}
            </div>`;
    }).join('');

    // Bind click on cards
    grid.querySelectorAll('.photo-card').forEach(card => {
        card.addEventListener('click', () => {
            if (state.isMultiSelectMode) {
                const id = Number(card.dataset.id);
                toggleSelectImage(id);
            } else {
                const idx = parseInt(card.dataset.index, 10);
                openLightbox(idx);
            }
        });
    });
}

// ============================================================================
// Multi-Select Mode
// ============================================================================

function toggleMultiSelectMode() {
    state.isMultiSelectMode = !state.isMultiSelectMode;

    if (state.isMultiSelectMode) {
        state.selectedIds = new Set();
        document.getElementById('multi-select-toggle-btn').textContent = '退出多选';
        document.getElementById('multi-select-toggle-btn').classList.remove('text-indigo-600', 'hover:text-indigo-700', 'hover:bg-indigo-50');
        document.getElementById('multi-select-toggle-btn').classList.add('text-amber-600', 'hover:text-amber-700', 'hover:bg-amber-50');
        document.getElementById('selection-bar').classList.remove('hidden');
        document.getElementById('selection-bar-spacer').classList.remove('hidden');
    } else {
        state.selectedIds = new Set();
        state.downloadProgress = null;
        document.getElementById('multi-select-toggle-btn').textContent = '开启多选';
        document.getElementById('multi-select-toggle-btn').classList.add('text-indigo-600', 'hover:text-indigo-700', 'hover:bg-indigo-50');
        document.getElementById('multi-select-toggle-btn').classList.remove('text-amber-600', 'hover:text-amber-700', 'hover:bg-amber-50');
        document.getElementById('selection-bar').classList.add('hidden');
        document.getElementById('selection-bar-spacer').classList.add('hidden');
        document.getElementById('download-progress-bar').classList.add('hidden');
    }

    renderPhotoGrid();
    updateSelectionUI();
}

function toggleSelectImage(id) {
    if (!state.isMultiSelectMode) return;

    if (state.selectedIds.has(id)) {
        state.selectedIds.delete(id);
    } else {
        state.selectedIds.add(id);
    }

    updateSelectionUI();

    // Update just the overlay for this card (no full re-render)
    const card = document.querySelector(`.photo-card[data-id="${id}"]`);
    if (card) {
        const overlay = card.querySelector('.multi-select-overlay');
        if (state.selectedIds.has(id)) {
            overlay.style.display = 'flex';
        } else {
            overlay.style.display = 'none';
        }
    }
}

function selectAll() {
    const images = getFilteredImages();
    images.forEach(img => state.selectedIds.add(img.id));
    updateSelectionUI();
    renderPhotoGrid();  // re-render to show all overlays
}

function deselectAll() {
    state.selectedIds = new Set();
    updateSelectionUI();
    renderPhotoGrid();
}

function updateSelectionUI() {
    if (!state.isMultiSelectMode) return;

    const count = state.selectedIds.size;
    document.getElementById('selection-count').textContent = `已选 ${count} 张`;

    const downloadBtn = document.getElementById('download-selected-btn');
    downloadBtn.textContent = count > 0 ? `下载选中 (${count})` : '下载选中';
    downloadBtn.disabled = count === 0;
}

// ============================================================================
// Download Queue (Sequential, anti-throttle)
// ============================================================================

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function startDownload() {
    if (state.selectedIds.size === 0) return;

    // Gather selected images from allImages
    const selectedImages = state.allImages.filter(img => state.selectedIds.has(img.id));
    if (selectedImages.length === 0) return;

    // Setup progress
    state.downloadProgress = { current: 0, total: selectedImages.length };
    state.downloadAborted = false;

    document.getElementById('download-progress-bar').classList.remove('hidden');
    document.getElementById('download-progress-text').textContent = '准备下载...';
    document.getElementById('selection-bar').classList.add('hidden');

    let successCount = 0;

    for (let i = 0; i < selectedImages.length; i++) {
        if (state.downloadAborted) break;

        const img = selectedImages[i];
        state.downloadProgress.current = i + 1;

        document.getElementById('download-progress-text').textContent =
            `正在下载 ${state.downloadProgress.current}/${state.downloadProgress.total} — ${escapeHtml(img.file_name || '照片')}`;

        try {
            // Fetch original image as blob
            const resp = await fetch(img.url);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const blob = await resp.blob();

            // Trigger browser download via virtual <a> element
            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = img.file_name || `photo_${img.id}.jpg`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            // Delay revoke to let browser finish async download
            setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);

            successCount++;
        } catch (err) {
            showToast(`${escapeHtml(img.file_name || '照片')} 下载失败: ${err.message}`, 'error');
        }

        // 400ms interval between downloads to prevent browser blocking
        if (i < selectedImages.length - 1 && !state.downloadAborted) {
            await sleep(400);
        }
    }

    // Cleanup
    document.getElementById('download-progress-bar').classList.add('hidden');
    document.getElementById('selection-bar').classList.remove('hidden');
    state.downloadProgress = null;

    if (state.downloadAborted) {
        showToast(`下载已中止 (成功 ${successCount}/${selectedImages.length})`, 'error');
    } else {
        showToast(`下载完成: ${successCount}/${selectedImages.length}`, 'success');
    }

    // Auto-exit multi-select mode
    state.isMultiSelectMode = false;
    state.selectedIds = new Set();
    state.downloadAborted = false;

    document.getElementById('multi-select-toggle-btn').textContent = '开启多选';
    document.getElementById('multi-select-toggle-btn').classList.add('text-indigo-600', 'hover:text-indigo-700', 'hover:bg-indigo-50');
    document.getElementById('multi-select-toggle-btn').classList.remove('text-amber-600', 'hover:text-amber-700', 'hover:bg-amber-50');
    document.getElementById('selection-bar').classList.add('hidden');
    document.getElementById('selection-bar-spacer').classList.add('hidden');

    renderPhotoGrid();
}

function abortDownload() {
    state.downloadAborted = true;
    document.getElementById('abort-download-btn').disabled = true;
    document.getElementById('abort-download-btn').textContent = '中止中...';
}

// ============================================================================
// Lightbox
// ============================================================================

function openLightbox(index) {
    // Don't open lightbox in multi-select mode
    if (state.isMultiSelectMode) return;

    const images = getFilteredImages();
    if (images.length === 0) return;

    state.lightboxIndex = index;
    const lightbox = document.getElementById('lightbox');
    lightbox.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    updateLightboxContent();

    document.addEventListener('keydown', lightboxKeyHandler);
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    lightbox.classList.add('hidden');
    document.body.style.overflow = '';
    state.lightboxIndex = -1;
    document.removeEventListener('keydown', lightboxKeyHandler);
}

function updateLightboxContent() {
    const images = getFilteredImages();
    if (images.length === 0 || state.lightboxIndex < 0) return;

    const img = images[state.lightboxIndex];
    const lightboxImg = document.getElementById('lightbox-img');
    const counter = document.getElementById('lightbox-counter');
    const prevBtn = document.getElementById('lightbox-prev');
    const nextBtn = document.getElementById('lightbox-next');

    // Animation
    lightboxImg.classList.remove('animate-fade-in');
    void lightboxImg.offsetWidth;
    lightboxImg.classList.add('animate-fade-in');

    // Use original URL for full resolution in lightbox
    lightboxImg.src = img.url;
    lightboxImg.alt = img.file_name || '照片';

    counter.textContent = `${state.lightboxIndex + 1} / ${images.length}`;

    prevBtn.disabled = state.lightboxIndex === 0;
    nextBtn.disabled = state.lightboxIndex === images.length - 1;
}

function prevImage() {
    if (state.lightboxIndex > 0) {
        state.lightboxIndex--;
        updateLightboxContent();
    }
}

function nextImage() {
    const images = getFilteredImages();
    if (state.lightboxIndex < images.length - 1) {
        state.lightboxIndex++;
        updateLightboxContent();
    }
}

function lightboxKeyHandler(e) {
    switch (e.key) {
        case 'Escape':
            closeLightbox();
            break;
        case 'ArrowLeft':
            prevImage();
            break;
        case 'ArrowRight':
            nextImage();
            break;
    }
}

// ============================================================================
// Toast
// ============================================================================

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');

    const bgColor = type === 'success' ? 'bg-green-500' : 'bg-red-500';
    toast.className = `${bgColor} text-white px-5 py-3 rounded-lg shadow-lg text-sm font-medium`;
    toast.style.animation = 'slideUp 0.3s ease-out';
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================================================
// Event Bindings
// ============================================================================

let eventsBound = false;

function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;

    // Login
    document.getElementById('login-btn').addEventListener('click', handleLogin);
    document.getElementById('login-secret').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleLogin();
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        logout();
    });

    // Multi-select toggle
    document.getElementById('multi-select-toggle-btn').addEventListener('click', toggleMultiSelectMode);

    // Selection bar buttons
    document.getElementById('select-all-btn').addEventListener('click', selectAll);
    document.getElementById('deselect-all-btn').addEventListener('click', deselectAll);
    document.getElementById('download-selected-btn').addEventListener('click', startDownload);
    document.getElementById('cancel-select-btn').addEventListener('click', toggleMultiSelectMode);

    // Download progress
    document.getElementById('abort-download-btn').addEventListener('click', abortDownload);

    // Lightbox controls
    document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
    document.getElementById('lightbox-prev').addEventListener('click', prevImage);
    document.getElementById('lightbox-next').addEventListener('click', nextImage);

    // Lightbox backdrop click to close
    document.getElementById('lightbox').addEventListener('click', function (e) {
        if (e.target === this) closeLightbox();
    });

    // Touch swipe support for lightbox
    let touchStartX = 0;
    let touchStartY = 0;
    document.getElementById('lightbox').addEventListener('touchstart', (e) => {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
    }, { passive: true });
    document.getElementById('lightbox').addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (dx > 0) prevImage();
            else nextImage();
        }
    });
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
