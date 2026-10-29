class TuyaBridgeManager extends HTMLElement {
  setConfig(config) {
    if (!config.entry_id) throw new Error("entry_id required");
    this.config = config;
    this.innerHTML = '<ha-card header="Tuya IPC Bridge"><div style="padding:16px"><p id="state">Loading...</p><button id="refresh">Refresh</button><button id="open-manager" style="display:none">Open bridge manager</button><ul id="cams"></ul><p>Region <select id="region"><option>eu-central</option><option>eu-east</option><option>us-west</option><option>us-east</option><option>china</option><option>india</option></select></p><p>Email <input id="email" type="email"></p><button id="login">Start QR login</button><p id="message"></p><img id="qr" width="240" style="display:none"></div></ha-card>';
    this.querySelector("#refresh").onclick = () => this.refresh();
    this.querySelector("#login").onclick = () => this.login();
    this.querySelector("#open-manager").onclick = () => window.open(this.managerUrl, "_blank", "noopener");
  }
  set hass(value) {
    this._hass = value;
    if (!this.loaded && this.config) {
      this.loaded = true;
      this.refresh();
    }
  }
  call(action, extra = {}) {
    return this._hass.callWS({type: "tuya_ipc_bridge/manage", entry_id: this.config.entry_id, action, ...extra});
  }
  async refresh() {
    try {
      const status = await this.call("status");
      const cameras = await this.call("cameras");
      this.querySelector("#state").textContent = "RTSP: " + status.rtsp + "; accounts: " + status.account_count;
      if (status.manager_url) {
        this.managerUrl = status.manager_url;
        this.querySelector("#open-manager").style.display = "inline-block";
      }
      const list = this.querySelector("#cams");
      list.replaceChildren();
      for (const c of cameras.cameras || []) {
        const li = document.createElement("li");
        li.append(c.name + " — ");
        for (const direction of ["UP", "LEFT", "RIGHT", "DOWN"]) {
          const button = document.createElement("button");
          button.textContent = direction.toLowerCase();
          button.onclick = () => this.ptz(c.device_id, direction);
          li.append(button);
        }
        list.appendChild(li);
      }
    } catch (_) {
      this.querySelector("#state").textContent = "Bridge unavailable or administrator access required";
    }
  }
  async ptz(camera, direction) {
    try {
      await this.call("ptz_move", {camera, direction, duration_ms:400});
    } catch (_) {
      this.querySelector("#message").textContent = "PTZ command failed";
    }
  }
  async login() {
    const button = this.querySelector("#login"), msg = this.querySelector("#message"), img = this.querySelector("#qr");
    button.disabled = true;
    img.style.display = "none";
    try {
      const started = await this.call("qr_start", {
        region: this.querySelector("#region").value,
        email: this.querySelector("#email").value.trim()
      });
      const until = Date.now() + 190000;
      let shown = false;
      while (Date.now() < until && this.isConnected) {
        const state = await this.call("qr_status", {job_id: started.id});
        msg.textContent = state.status;
        if (state.ready && !shown) {
          const result = await this.call("qr_image", {job_id: started.id});
          img.src = "data:image/png;base64," + result.image;
          img.style.display = "block";
          shown = true;
        }
        if (state.status === "success" || state.status === "error") {
          await this.refresh();
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
      msg.textContent = "QR session expired";
    } catch (_) {
      msg.textContent = "Unable to complete login";
    } finally {
      button.disabled = false;
      img.style.display = "none";
    }
  }
  getCardSize() { return 5; }
}
customElements.define("tuya-bridge-manager", TuyaBridgeManager);
