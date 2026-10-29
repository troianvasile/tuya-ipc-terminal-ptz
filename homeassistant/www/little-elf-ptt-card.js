/** Little Elf push-to-talk microphone button for Home Assistant.
 * Backend: homeassistant/custom_components/little_elf_talk.
 * Audio: Web Audio -> mono 8kHz PCMU -> authenticated HA WebSocket -> RTSP.
 * No camera IPs, tokens, cloud account details, or go2rtc addresses in JS.
 */
// The microphone processor is served from /local/little-elf-talk-processor.js.
// A static file avoids Blob-based AudioWorklet CSP restrictions.

class LittleElfPttCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._hass = null;
    this._pressed = false;
    this._generation = 0;
    this._session = null;
    this._stream = null;
    this._ctx = null;
    this._node = null;
    this._audioQueue = [];
    this._sendTimer = null;
    this._testTimer = null;
    this._testSession = null;
    this._blur = () => this._stop();
    this._visibility = () => { if (document.hidden) this._stop(); };
  }

  setConfig(config) {
    const legacy = typeof config.camera === 'string';
    const bridge = typeof config.entry_id === 'string' && typeof config.camera_id === 'string';
    if (!legacy && !bridge) {
      throw new Error('Set camera, or entry_id and camera_id for Tuya IPC Bridge discovery');
    }
    this._config = {...config};
    this._bridge = bridge;
    this._render();
  }
  set hass(hass) { this._hass = hass; }
  getCardSize() { return 2; }

  connectedCallback() {
    window.addEventListener('blur', this._blur);
    document.addEventListener('visibilitychange', this._visibility);
    if (this._config) this._render();
  }
  disconnectedCallback() {
    window.removeEventListener('blur', this._blur);
    document.removeEventListener('visibilitychange', this._visibility);
    this._stop();
  }

  _render() {
    if (this._button || !this._config) return;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        button { display:block; width:100%; box-sizing:border-box; padding:16px 12px;
          border:1px solid var(--divider-color,#666); border-radius:12px;
          background:var(--card-background-color,#242830);
          color:var(--primary-text-color,#fff);
          font-size:16px; font-weight:600; touch-action:none; user-select:none;
          cursor:pointer; }
        button.active { background:#982c34; color:#fff; border-color:#d66; }
        button:focus-visible { outline:2px solid var(--primary-color,#48b); }
        .hint { text-align:center; font-size:12px; padding:7px 0 2px;
          color:var(--secondary-text-color,#999); }
      </style>
      <button type="button" aria-pressed="false">🎙 Hold to talk</button>
      <button class="test" type="button">🔊 Test speaker tone</button>
      <div class="hint" role="status" aria-live="polite">Microphone off · Hold to speak</div>`;
    this._button = this.shadowRoot.querySelector('button');
    this._hint = this.shadowRoot.querySelector('.hint');
    this._button.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault();
      try { this._button.setPointerCapture(event.pointerId); } catch (_) {}
      this._start();
    });
    this._button.addEventListener('pointerup', () => this._stop());
    this._button.addEventListener('pointercancel', () => this._stop());
    this._button.addEventListener('lostpointercapture', () => this._stop());
    this._button.addEventListener('keydown', event => {
      if ((event.code === 'Space' || event.code === 'Enter') && !event.repeat) {
        event.preventDefault(); this._start();
      }
    });
    this._button.addEventListener('keyup', event => {
      if (event.code === 'Space' || event.code === 'Enter') {
        event.preventDefault(); this._stop();
      }
    });
    this.shadowRoot.querySelector('.test').addEventListener('click', () => this._startSpeakerTest());
  }

  _status(label, detail, active=false) {
    if (!this._button || !this._hint) return;
    this._button.textContent = label;
    this._button.classList.toggle('active', active);
    this._button.setAttribute('aria-pressed', String(active));
    this._hint.textContent = detail;
  }

  async _start() {
    if (this._pressed || !this.isConnected) return;
    this._pressed = true;
    const generation = ++this._generation;
    this._status('🔴 Connecting microphone…', 'Allow microphone access if prompted', true);
    try {
      if (!this._hass?.connection) throw new Error('Home Assistant is not connected');
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Microphone needs HTTPS or localhost');
      }
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass || !window.AudioWorkletNode) {
        throw new Error('This browser does not support AudioWorklet');
      }
      // Create/resume in the press gesture before permission and network awaits.
      const context = new AudioContextClass();
      this._ctx = context;
      await context.resume();
      const mic = await navigator.mediaDevices.getUserMedia({
        audio: {channelCount:1, echoCancellation:true, noiseSuppression:true, autoGainControl:true},
        video:false,
      });
      if (!this._pressed || this._generation !== generation) {
        mic.getTracks().forEach(track => track.stop()); return;
      }
      this._stream = mic;

      const response = await this._hass.connection.sendMessagePromise(this._message('start'));
      const token = response?.session;
      if (!token) throw new Error('Talkback backend returned no session');
      if (!this._pressed || this._generation !== generation) {
        this._hass.connection.sendMessagePromise(this._message('stop', {session:token})).catch(() => {});
        return;
      }
      this._session = token;

      await context.audioWorklet.addModule('/local/little-elf-talk-processor.js?v=09450d4');
      if (!this._pressed || this._generation !== generation) return;

      const source = context.createMediaStreamSource(mic);
      const processor = new AudioWorkletNode(context, 'little-elf-pcmu', {outputChannelCount:[1]});
      this._node = processor;
      const mute = context.createGain();
      mute.gain.value = 0;
      source.connect(processor);
      processor.connect(mute);
      mute.connect(context.destination);
      processor.port.onmessage = event => {
        if (!this._pressed || this._session !== token || !this._hass?.connection) return;
        const bytes = new Uint8Array(event.data);
        let binary = '';
        for (const byte of bytes) binary += String.fromCharCode(byte);
        // Tuya's G.711u IPC talkback requires 320-byte, 40-ms frames.
        if (this._audioQueue.length >= 13) this._audioQueue.shift();
        this._audioQueue.push(btoa(binary));
      };
      this._sendTimer = window.setInterval(() => {
        if (!this._pressed || this._session !== token || !this._hass?.connection) return;
        const audio = this._audioQueue.shift();
        if (!audio) return;
        try {
          this._hass.connection.sendMessage(this._message('chunk', {session:token, audio}));
        } catch (_) {
          this._stop();
        }
      }, 40);
      this._status('🔴 Talking — release to stop', `${context.sampleRate} Hz PCMU · Sending microphone`, true);
    } catch (error) {
      if (this._generation === generation) {
        this._status('🎙 Hold to talk', String(error?.message || error), false);
        this._stop(true);
      }
    }
  }

  _toneFrame() {
    const frame = new Uint8Array(320);
    for (let index = 0; index < frame.length; index++) {
      const sample = Math.sin(2 * Math.PI * 1000 * index / 8000) * 0.2;
      frame[index] = LittleElfPttCard._encodePCMU(sample);
    }
    return frame;
  }

  static _encodePCMU(sample) {
    let pcm = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
    const mask = pcm < 0 ? 0x7f : 0xff;
    if (pcm < 0) pcm = -pcm;
    pcm = Math.min(32635, pcm + 132);
    let segment = 0, value = pcm >> 7;
    while (value > 1 && segment < 7) { segment++; value >>= 1; }
    return (((segment << 4) | ((pcm >> (segment + 3)) & 15)) ^ mask) & 255;
  }

  async _startSpeakerTest() {
    if (this._pressed || this._testTimer || !this._hass?.connection) return;
    try {
      const response = await this._hass.connection.sendMessagePromise(this._message('start'));
      const session = response?.session;
      if (!session) throw new Error('Talkback backend returned no session');
      this._testSession = session;
      const frame = this._toneFrame();
      let binary = '';
      for (const byte of frame) binary += String.fromCharCode(byte);
      const audio = btoa(binary);
      const send = () => this._hass?.connection?.sendMessage(
        this._message('chunk', {session, audio})
      );
      send();
      this._status('🔊 Testing speaker…', 'Three-second 1 kHz PCMU reference tone', true);
      this._testTimer = window.setInterval(send, 40);
      window.setTimeout(() => this._stopSpeakerTest(), 3000);
    } catch (error) {
      this._status('🎙 Hold to talk', String(error?.message || error), false);
    }
  }

  _stopSpeakerTest() {
    if (this._testTimer) window.clearInterval(this._testTimer);
    this._testTimer = null;
    const session = this._testSession;
    this._testSession = null;
    if (session && this._hass?.connection) {
      this._hass.connection.sendMessagePromise(this._message('stop', {session})).catch(() => {});
    }
    if (!this._pressed) this._status('🎙 Hold to talk', 'Microphone off · Hold to speak');
  }

  _stop(keepError=false) {
    if (!this._pressed && !this._stream && !this._ctx && !this._session) return;
    this._pressed = false;
    this._stopSpeakerTest();
    if (this._sendTimer) window.clearInterval(this._sendTimer);
    this._sendTimer = null;
    this._audioQueue = [];
    this._generation++;
    const token = this._session;
    this._session = null;
    if (this._node) {
      try { this._node.port.onmessage = null; this._node.disconnect(); } catch (_) {}
      this._node = null;
    }
    if (this._stream) {
      this._stream.getTracks().forEach(track => track.stop());
      this._stream = null;
    }
    if (this._ctx) {
      this._ctx.close().catch(() => {});
      this._ctx = null;
    }
    if (token && this._hass?.connection) {
      this._hass.connection.sendMessagePromise(this._message('stop', {session:token})).catch(() => {});
    }
    if (!keepError) this._status('🎙 Hold to talk', 'Microphone off · Hold to speak');
  }

  _message(action, data = {}) {
    if (!this._bridge) {
      return {
        type:`little_elf_talk/${action}`,
        ...(action === 'start' ? {camera:this._config.camera} : {}),
        ...data,
      };
    }
    const type = {start:'ptt_start', chunk:'ptt_chunk', stop:'ptt_stop'}[action];
    return {
      type:`tuya_ipc_bridge/${type}`,
      ...(action === 'start' ? {entry_id:this._config.entry_id, camera_id:this._config.camera_id} : {}),
      ...data,
    };
  }
}

if (!customElements.get('little-elf-ptt-card')) {
  customElements.define('little-elf-ptt-card', LittleElfPttCard);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type:'little-elf-ptt-card',
  name:'Little Elf Push-to-Talk',
  description:'Hold-to-talk microphone for the Little Elf HA RTSP bridge',
});
