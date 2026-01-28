/**
 * 英语学习应用 - 前端公共逻辑
 */

// ==================== 工具函数 ====================

/**
 * 发送 API 请求
 */
async function api(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json'
        }
    };

    const response = await fetch(url, { ...defaultOptions, ...options });

    if (response.status === 401) {
        // 未登录，跳转登录页
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }

    return response;
}

/**
 * GET 请求
 */
async function apiGet(url) {
    return api(url);
}

/**
 * POST 请求
 */
async function apiPost(url, data) {
    return api(url, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

// ==================== 移动端适配 ====================

/**
 * 初始化移动端适配
 */
function initMobileAdaptation() {
    // 解锁音频（移动端需要用户交互后才能播放）
    const unlockAudio = () => {
        if (Howler.ctx && Howler.ctx.state === 'suspended') {
            Howler.ctx.resume();
        }
        document.removeEventListener('touchstart', unlockAudio);
        document.removeEventListener('click', unlockAudio);
    };

    document.addEventListener('touchstart', unlockAudio, { once: true, passive: true });
    document.addEventListener('click', unlockAudio, { once: true, passive: true });

    // 处理软键盘弹出时的视口变化
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            // 可以在这里调整布局
        });
    }
}

// ==================== 本地存储 ====================

/**
 * 保存到本地存储
 */
function saveLocal(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.error('保存失败:', e);
    }
}

/**
 * 从本地存储读取
 */
function loadLocal(key, defaultValue = null) {
    try {
        const value = localStorage.getItem(key);
        return value ? JSON.parse(value) : defaultValue;
    } catch (e) {
        console.error('读取失败:', e);
        return defaultValue;
    }
}

// ==================== 翻译分层显示 ====================

/**
 * 将翻译拆分为主要释义和扩展释义
 * 扩展释义：包含 [法]、[医]、[化]、[计]、[网络]、[建]、[经] 等专业领域标注的部分
 * 返回 { main: string, extended: string }
 */
function splitTranslation(translation) {
    if (!translation) return { main: '', extended: '' };

    const parts = translation.split('；');
    const mainParts = [];
    const extParts = [];

    for (const part of parts) {
        const trimmed = part.trim();
        if (/^\[.+?\]/.test(trimmed)) {
            extParts.push(trimmed);
        } else {
            mainParts.push(trimmed);
        }
    }

    return {
        main: mainParts.join('；'),
        extended: extParts.join('；')
    };
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    initMobileAdaptation();
});

// 导出函数供 Alpine.js 使用
window.app = {
    api,
    apiGet,
    apiPost,
    saveLocal,
    loadLocal,
    splitTranslation
};
