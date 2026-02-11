/* Jekyll Blog Admin — Shared JS */

const API = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`GET ${url}: ${res.status}`);
        return res.json();
    },
    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `POST ${url}: ${res.status}`);
        }
        return res.json();
    },
    async put(url, data) {
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `PUT ${url}: ${res.status}`);
        }
        return res.json();
    },
    async delete(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) throw new Error(`DELETE ${url}: ${res.status}`);
        return res.json();
    },
    async upload(url, formData) {
        const res = await fetch(url, { method: 'POST', body: formData });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Upload failed: ${res.status}`);
        }
        return res.json();
    },
};

/* --- Notifications (Bootstrap toasts) --- */

function showNotification(message, type = 'success') {
    const container = document.querySelector('.toast-container') || createToastContainer();
    const id = 'toast-' + Date.now();
    const bgClass = {
        success: 'text-bg-success',
        error: 'text-bg-danger',
        warning: 'text-bg-warning',
        info: 'text-bg-info',
    }[type] || 'text-bg-secondary';

    const html = `
        <div id="${id}" class="toast align-items-center ${bgClass} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto"
                        data-bs-dismiss="toast"></button>
            </div>
        </div>`;
    container.insertAdjacentHTML('beforeend', html);
    const el = document.getElementById(id);
    const toast = new bootstrap.Toast(el, { delay: 3000 });
    toast.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}

function createToastContainer() {
    const c = document.createElement('div');
    c.className = 'toast-container';
    document.body.appendChild(c);
    return c;
}

/* --- Git status polling --- */

async function refreshGitStatus() {
    try {
        const data = await API.get('/api/git/status');
        const badge = document.getElementById('git-status-badge');
        if (!badge) return;
        if (data.clean) {
            badge.className = 'git-badge clean';
            badge.textContent = 'clean';
        } else {
            badge.className = 'git-badge dirty';
            badge.textContent = `${data.change_count} changes`;
        }
        // Update branch display
        const branchEl = document.getElementById('git-branch');
        if (branchEl) branchEl.textContent = data.branch;
    } catch (e) {
        // Silently fail — git status is non-critical
    }
}

function startGitStatusPolling(intervalMs = 30000) {
    refreshGitStatus();
    setInterval(refreshGitStatus, intervalMs);
}

/* --- Commit & Push --- */

async function openCommitModal() {
    try {
        const data = await API.get('/api/git/status');
        if (data.clean) {
            showNotification('No changes to commit', 'info');
            return;
        }
        const listEl = document.getElementById('commit-changes-list');
        if (listEl) {
            listEl.innerHTML = data.changes
                .map(c => `<div><span class="text-muted">${c.status}</span> ${c.file}</div>`)
                .join('');
        }
        const modal = new bootstrap.Modal(document.getElementById('commitModal'));
        modal.show();
    } catch (e) {
        showNotification('Failed to get git status: ' + e.message, 'error');
    }
}

async function doCommitPush() {
    const msgInput = document.getElementById('commit-message');
    const message = msgInput ? msgInput.value.trim() : '';
    const btn = document.getElementById('btn-do-commit');
    if (btn) btn.disabled = true;

    try {
        const result = await API.post('/api/git/commit-push', {
            message: message || undefined,
        });
        if (result.status === 'success') {
            showNotification(`Committed & pushed: ${result.commit_hash}`, 'success');
        } else if (result.status === 'nothing') {
            showNotification('No changes to commit', 'info');
        } else if (result.status === 'push_failed') {
            showNotification(`Committed (${result.commit_hash}) but push failed: ${result.push_result}`, 'warning');
        } else {
            showNotification('Error: ' + (result.detail || 'Unknown'), 'error');
        }
        // Close modal
        const modalEl = document.getElementById('commitModal');
        if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
        // Refresh status
        refreshGitStatus();
    } catch (e) {
        showNotification('Commit failed: ' + e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

/* --- Format file sizes --- */

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/* --- Init on DOMContentLoaded --- */

document.addEventListener('DOMContentLoaded', () => {
    startGitStatusPolling();
});
