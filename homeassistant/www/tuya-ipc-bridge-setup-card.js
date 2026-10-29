import "/local/little-elf-ptt-card.js?v=09450d4";

class TuyaIpcBridgeSetupCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this.loaded = false;
    this.render();
  }

  set hass(value) {
    this._hass = value;
    for (const child of this.querySelectorAll("webrtc-camera, little-elf-ptt-card")) {
      child.hass = value;
    }
    if (!this.loaded) {
      this.loaded = true;
      this.refresh();
    }
  }

  getCardSize() { return 7; }

  async refresh() {
    try {
      const data = await this._hass.callWS({
        type: "tuya_ipc_bridge/manage", action: "dashboard", entry_id: this.config.entry_id,
      });
      this.data = data;
      this.render();
    } catch (_) {
      this.error = "Bridge unavailable or administrator access required";
      this.render();
    }
  }

  render() {
    this.replaceChildren();
    const card = document.createElement("ha-card");
    const header = document.createElement("div");
    header.style.cssText = "padding:16px 16px 8px;font-size:20px;font-weight:500";
    header.textContent = "Tuya IPC Bridge";
    card.append(header);
    if (this.error) {
      const message = document.createElement("p");
      message.style.padding = "0 16px 16px";
      message.textContent = this.error;
      card.append(message);
      this.append(card);
      return;
    }
    if (!this.data) {
      const message = document.createElement("p");
      message.style.padding = "0 16px 16px";
      message.textContent = "Loading discovered cameras…";
      card.append(message);
      this.append(card);
      return;
    }
    if (this.data.manager_url) {
      const open = document.createElement("a");
      open.href = this.data.manager_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = "Open bridge manager";
      open.style.cssText = "display:inline-block;margin:0 16px 12px";
      card.append(open);
    }
    const camera = this.data.cameras.find(
      (item) => item.camera_id === (this.selectedCameraId || this.config.camera_id),
    ) || this.data.cameras[0];
    if (!camera) {
      const message = document.createElement("p");
      message.style.padding = "0 16px 16px";
      message.textContent = "No cameras have been discovered yet.";
      card.append(message);
      this.append(card);
      return;
    }
    this.selectedCameraId = camera.camera_id;
    const section = document.createElement("section");
    section.style.cssText = "padding:0 12px 16px";
    const picker = document.createElement("select");
    picker.setAttribute("aria-label", "Selected Tuya camera");
    picker.style.cssText = "width:100%;box-sizing:border-box;margin:0 0 12px;padding:8px";
    for (const item of this.data.cameras) {
      const option = document.createElement("option");
      option.value = item.camera_id;
      option.textContent = item.name;
      option.selected = item.camera_id === camera.camera_id;
      picker.append(option);
    }
    picker.onchange = () => {
      this.selectedCameraId = picker.value;
      this.render();
    };
    section.append(picker);
    if (camera.rtsp_url && customElements.get("webrtc-camera")) {
      const video = document.createElement("webrtc-camera");
      video.setConfig({
        type: "custom:webrtc-camera", url: camera.rtsp_url,
        mode: this.config.mode || "mse,hls", media: "video,audio", ui: true,
        ...(this.config.go2rtc_server ? {server: this.config.go2rtc_server} : {}),
      });
      video.hass = this._hass;
      section.append(video);
    } else {
      const pending = document.createElement("p");
      pending.textContent = camera.rtsp_url
        ? "Install and configure the WebRTC integration to enable MSE playback."
        : "Camera stream is still being registered. Refresh in a moment.";
      section.append(pending);
    }
    const ptt = document.createElement("little-elf-ptt-card");
    ptt.setConfig({entry_id: this.data.entry_id, camera_id: camera.camera_id});
    ptt.hass = this._hass;
    section.append(ptt);
    const controls = document.createElement("div");
    controls.style.cssText = "display:flex;gap:8px;justify-content:center;padding-top:8px";
    for (const direction of ["UP", "LEFT", "RIGHT", "DOWN"]) {
      const button = document.createElement("button");
      button.textContent = direction.toLowerCase();
      button.onclick = () => this.ptz(camera.camera_id, direction);
      controls.append(button);
    }
    section.append(controls);
    card.append(section);
    this.append(card);
  }

  async ptz(camera, direction) {
    try {
      await this._hass.callWS({
        type: "tuya_ipc_bridge/manage", action: "ptz_move", entry_id: this.data.entry_id,
        camera, direction, duration_ms: 400,
      });
    } catch (_) {
      this.error = "PTZ command failed";
      this.render();
    }
  }
}

customElements.define("tuya-ipc-bridge-setup-card", TuyaIpcBridgeSetupCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "tuya-ipc-bridge-setup-card",
  name: "Tuya IPC Bridge setup",
  description: "One selected Tuya camera with video, push-to-talk and PTZ controls",
});
