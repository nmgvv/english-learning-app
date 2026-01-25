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

// ==================== 音频播放 ====================

// 全局音频播放器实例
let globalAudioPlayer = null;

/**
 * 播放音频
 */
function playAudio(url) {
    if (globalAudioPlayer) {
        globalAudioPlayer.unload();
    }

    globalAudioPlayer = new Howl({
        src: [url],
        format: ['mp3'],
        onloaderror: (id, err) => {
            console.error('音频加载失败:', err);
        }
    });

    globalAudioPlayer.play();
}

/**
 * 播放单词发音
 */
function playWord(word, speed = 'normal') {
    const url = `/api/tts/${speed}/${encodeURIComponent(word)}`;
    playAudio(url);
}

/**
 * 播放句子
 */
function playSentence(sentence) {
    const url = `/api/tts/sentence?sentence=${encodeURIComponent(sentence)}`;
    playAudio(url);
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

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    initMobileAdaptation();
});

// 导出函数供 Alpine.js 使用
window.app = {
    api,
    apiGet,
    apiPost,
    playAudio,
    playWord,
    playSentence,
    saveLocal,
    loadLocal
};
