/**
 * 录音工具类
 *
 * 使用 MediaRecorder API 录制音频
 *
 * Usage:
 *   const recorder = new AudioRecorder();
 *   await recorder.requestPermission();
 *   await recorder.start();
 *   const audioBlob = await recorder.stop();
 *   const result = await recorder.uploadForRecognition(audioBlob);
 */
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.stream = null;
    }

    /**
     * 检查浏览器是否支持录音
     */
    static isSupported() {
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    }

    /**
     * 请求麦克风权限
     * @returns {Promise<boolean>} 是否获得权限
     */
    async requestPermission() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            // 立即停止，只是检查权限
            stream.getTracks().forEach(track => track.stop());
            return true;
        } catch (e) {
            console.error('麦克风权限被拒绝:', e);
            return false;
        }
    }

    /**
     * 获取支持的 MIME 类型
     */
    _getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
            'audio/wav'
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }

        // 返回空字符串让浏览器自己选择
        return '';
    }

    /**
     * 开始录音
     */
    async start() {
        if (this.isRecording) {
            console.warn('已经在录音中');
            return;
        }

        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            const mimeType = this._getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};

            this.mediaRecorder = new MediaRecorder(this.stream, options);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onerror = (event) => {
                console.error('录音错误:', event.error);
            };

            // 每 100ms 收集一次数据，确保短录音也有数据
            this.mediaRecorder.start(100);
            this.isRecording = true;

            console.log('录音开始, MIME 类型:', this.mediaRecorder.mimeType);

        } catch (e) {
            console.error('录音启动失败:', e);
            throw e;
        }
    }

    /**
     * 停止录音并返回音频 Blob
     * @returns {Promise<Blob>} 音频数据
     */
    async stop() {
        return new Promise((resolve, reject) => {
            if (!this.mediaRecorder || !this.isRecording) {
                reject(new Error('未在录音'));
                return;
            }

            this.mediaRecorder.onstop = () => {
                const mimeType = this.mediaRecorder.mimeType || 'audio/webm';
                const audioBlob = new Blob(this.audioChunks, { type: mimeType });

                console.log('录音结束, 大小:', audioBlob.size, 'bytes');

                this.isRecording = false;
                this.audioChunks = [];

                // 停止所有音轨
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }

                resolve(audioBlob);
            };

            this.mediaRecorder.stop();
        });
    }

    /**
     * 取消录音
     */
    cancel() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
        }

        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }

        this.isRecording = false;
        this.audioChunks = [];
    }

    /**
     * 上传音频到服务器进行识别
     * @param {Blob} audioBlob 音频数据
     * @returns {Promise<Object>} 识别结果
     */
    async uploadForRecognition(audioBlob) {
        const formData = new FormData();

        // 根据 MIME 类型确定文件扩展名
        let filename = 'recording.webm';
        if (audioBlob.type.includes('ogg')) {
            filename = 'recording.ogg';
        } else if (audioBlob.type.includes('mp4')) {
            filename = 'recording.m4a';
        } else if (audioBlob.type.includes('wav')) {
            filename = 'recording.wav';
        }

        formData.append('audio', audioBlob, filename);

        try {
            const response = await fetch('/api/speech/recognize', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }

            return await response.json();

        } catch (e) {
            console.error('上传识别失败:', e);
            return {
                success: false,
                text: '',
                error: e.message || '网络错误'
            };
        }
    }

    /**
     * 获取音频的本地播放 URL
     * @param {Blob} audioBlob 音频数据
     * @returns {string} 本地 URL
     */
    static createPlaybackUrl(audioBlob) {
        return URL.createObjectURL(audioBlob);
    }

    /**
     * 释放本地播放 URL
     * @param {string} url 本地 URL
     */
    static revokePlaybackUrl(url) {
        URL.revokeObjectURL(url);
    }
}

// 导出到全局
window.AudioRecorder = AudioRecorder;
