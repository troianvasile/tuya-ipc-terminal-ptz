import "/local/little-elf-ptt-card.js";

class TuyaIpcBridgeSetupCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this.loaded = false;
    this.render();
  }

  set hass(value) {
    this._hass = value;
    for (const child of this.querySelectorAll("hui-picture-entity-card, little-elf-ptt-card")) {
      child.hass = value;
    }
    if (!this.loaded) {
      this.loaded = true;
      this.refresh();
    }
  }

  getCardSize() { return 12; }

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
    for (const camera of this.data.cameras) {
      const section = document.createElement("section");
      section.style.cssText = "padding:0 12px 16px";
      const title = document.createElement("h3");
      title.textContent = camera.name;
      section.append(title);
      if (camera.entity_id) {
        const video = document.createElement("hui-picture-entity-card");
        video.setConfig({
          type: "picture-entity", entity: camera.entity_id, name: camera.name,
          camera_view: this.config.live === true ? "live" : "auto", show_state: false,
        });
        video.hass = this._hass;
        section.append(video);
      } else {
        const pending = document.createElement("p");
        pending.textContent = "Camera entity is still being registered. Refresh in a moment.";
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
    }
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
  description: "Discovered camera video, audio, push-to-talk and PTZ controls",
});
