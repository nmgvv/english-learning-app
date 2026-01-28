/**
 * 统一 TTS 播放模块
 *
 * 所有页面通过全局 TTS 对象调用语音播放，避免重复实现 Howler.js 逻辑。
 * 支持英文音色切换（美式/英式 × 男声/女声）和语速选择，设置保存到 localStorage。
 *
 * Usage:
 *   TTS.playWord('hello');                     // 用当前音色+语速播放
 *   TTS.playWord('hello', 'normal');           // 用当前音色+指定语速播放
 *   TTS.playWordWithVoice('hello', 'gb-male'); // 用指定音色+当前语速播放
 *   TTS.playSentence('How are you?');          // 播放英文句子
 *   TTS.playChinese('你好');                   // 播放中文
 *   TTS.stop();                                // 停止播放
 *
 *   // 音色管理
 *   TTS.setVoice('gb-female');                 // 切换到英式女声
 *   TTS.getVoice();                            // 获取当前音色 ID
 *
 *   // 语速管理
 *   TTS.setSpeed('0.75x');                     // 切换到 0.75 倍速
 *   TTS.getSpeed();                            // 获取当前语速 ID
 */
const TTS = {
    _player: null,

    /**
     * 可用英文音色
     */
    voices: [
        { id: 'us-male',   label: '美式男声', accent: 'US', gender: 'male' },
        { id: 'us-female', label: '美式女声', accent: 'US', gender: 'female' },
        { id: 'gb-male',   label: '英式男声', accent: 'GB', gender: 'male' },
        { id: 'gb-female', label: '英式女声', accent: 'GB', gender: 'female' },
    ],

    /**
     * 可用语速
     */
    speeds: [
        { id: 'normal', label: '1倍' },
        { id: '0.75x',  label: '0.75倍' },
        { id: '0.5x',   label: '0.5倍' },
    ],

    // ==================== 音色管理 ====================

    /**
     * 获取当前音色 ID
     * @returns {string}
     */
    getVoice() {
        try {
            return localStorage.getItem('tts_voice') || 'us-male';
        } catch {
            return 'us-male';
        }
    },

    /**
     * 设置音色
     * @param {string} voiceId - 音色 ID（us-male, us-female, gb-male, gb-female）
     */
    setVoice(voiceId) {
        try {
            localStorage.setItem('tts_voice', voiceId);
        } catch {
            // ignore
        }
    },

    // ==================== 语速管理 ====================

    /**
     * 获取当前语速 ID
     * @returns {string}
     */
    getSpeed() {
        try {
            return localStorage.getItem('tts_speed') || 'normal';
        } catch {
            return 'normal';
        }
    },

    /**
     * 设置语速
     * @param {string} speedId - 语速 ID（normal, 0.75x, 0.5x）
     */
    setSpeed(speedId) {
        try {
            localStorage.setItem('tts_speed', speedId);
        } catch {
            // ignore
        }
    },

    // ==================== URL 构建 ====================

    /**
     * 构建带音色参数的 URL
     * @param {string} baseUrl - 基础 URL
     * @param {string} [voiceId] - 指定音色（可选，默认用当前设置）
     * @returns {string}
     */
    _withVoice(baseUrl, voiceId) {
        const voice = voiceId || this.getVoice();
        const sep = baseUrl.includes('?') ? '&' : '?';
        return `${baseUrl}${sep}voice=${voice}`;
    },

    // ==================== 播放控制 ====================

    /**
     * 停止当前播放
     */
    stop() {
        if (this._player) {
            this._player.unload();
            this._player = null;
        }
    },

    /**
     * 播放音频 URL
     * @param {string} url - 音频 URL
     * @returns {Promise<void>} 播放结束后 resolve
     */
    play(url) {
        return new Promise((resolve, reject) => {
            this.stop();
            this._player = new Howl({
                src: [url],
                format: ['mp3'],
                onend: () => {
                    resolve();
                },
                onloaderror: (id, err) => {
                    console.error('TTS 加载失败:', err);
                    reject(err);
                },
                onplayerror: (id, err) => {
                    console.error('TTS 播放失败:', err);
                    reject(err);
                }
            });
            this._player.play();
        });
    },

    // ==================== 英文播放 ====================

    /**
     * 播放英文单词（使用当前音色，可指定语速）
     * @param {string} word - 单词
     * @param {string} [speed] - 语速（可选，默认用当前设置）
     * @returns {Promise<void>}
     */
    playWord(word, speed) {
        const effectiveSpeed = speed || this.getSpeed();
        const url = this._withVoice(`/api/tts/${effectiveSpeed}/${encodeURIComponent(word)}`);
        return this.play(url);
    },

    /**
     * 用指定音色播放英文单词（语速用当前设置）
     * @param {string} word - 单词
     * @param {string} voiceId - 音色 ID
     * @param {string} [speed] - 语速（可选，默认用当前设置）
     * @returns {Promise<void>}
     */
    playWordWithVoice(word, voiceId, speed) {
        const effectiveSpeed = speed || this.getSpeed();
        const url = this._withVoice(`/api/tts/${effectiveSpeed}/${encodeURIComponent(word)}`, voiceId);
        return this.play(url);
    },

    /**
     * 播放英文句子
     * @param {string} text - 句子文本
     * @returns {Promise<void>}
     */
    playSentence(text) {
        const url = this._withVoice(`/api/tts/sentence?sentence=${encodeURIComponent(text)}`);
        return this.play(url);
    },

    // ==================== 其他语言 ====================

    /**
     * 播放中文文本
     * @param {string} text - 中文文本
     * @returns {Promise<void>}
     */
    playChinese(text) {
        const url = `/api/tts/chinese?text=${encodeURIComponent(text)}`;
        return this.play(url);
    },

    /**
     * 智能播放（自动检测语言）
     * @param {string} text - 文本
     * @returns {Promise<void>}
     */
    playAuto(text) {
        const hasChinese = /[\u4e00-\u9fff]/.test(text);
        return hasChinese ? this.playChinese(text) : this.playSentence(text);
    },

    /**
     * 是否正在播放
     * @returns {boolean}
     */
    get isPlaying() {
        return !!(this._player && this._player.playing());
    }
};

window.TTS = TTS;
