/*
 * Frame TV Card — one card for a Samsung Frame TV.
 * Served automatically by the samsung_frame integration.
 *
 *   type: custom:frame-tv-card
 *   entity: media_player.frame_tv
 */

const BRANDS = {
  netflix: ["#E50914", "#fff"],
  youtube: ["#FF0000", "#fff"],
  "prime video": ["#00A8E1", "#fff"],
  "disney+": ["#0E2A8C", "#fff"],
  hulu: ["#1CE783", "#0b0c0f"],
  max: ["#002BE7", "#fff"],
  "apple tv": ["#111", "#fff"],
  plex: ["#E5A00D", "#1f1f1f"],
  spotify: ["#1DB954", "#0b0c0f"],
  "paramount+": ["#0064FF", "#fff"],
  peacock: ["#111", "#fff"],
  "pluto tv": ["#2D2D2D", "#FFF200"],
  tubi: ["#7408FF", "#fff"],
};

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class FrameTvCard extends HTMLElement {
  static getConfigForm() {
    const bool = (name) => ({ name, selector: { boolean: {} } });
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: { integration: "samsung_frame", domain: "media_player" } } },
        },
        { name: "name", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [bool("show_inputs"), bool("show_apps"), bool("show_navigation"), bool("show_media"), bool("show_volume")],
        },
      ],
      computeLabel: (s) =>
        ({
          entity: "Frame TV",
          name: "Name",
          show_inputs: "Inputs",
          show_apps: "Apps",
          show_navigation: "Navigation pad",
          show_media: "Playback buttons",
          show_volume: "Volume",
        })[s.name],
    };
  }

  static getStubConfig(hass) {
    const ent = Object.values(hass.entities || {}).find(
      (e) => e.platform === "samsung_frame" && e.entity_id.startsWith("media_player.")
    );
    return { entity: ent ? ent.entity_id : "media_player.frame_tv" };
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("Set `entity` to your Frame TV media_player");
    this._config = {
      show_inputs: true,
      show_apps: true,
      show_navigation: true,
      show_media: true,
      show_volume: true,
      ...config,
    };
    this._built = false;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // ---------------------------------------------------------------- helpers

  get _stateObj() {
    return this._hass && this._hass.states[this._config.entity];
  }

  _sibling(domain) {
    if (this._config[`${domain}_entity`]) return this._config[`${domain}_entity`];
    const reg = this._hass.entities || {};
    const me = reg[this._config.entity];
    if (!me || !me.device_id) return undefined;
    const found = Object.values(reg).find(
      (e) => e.device_id === me.device_id && e.entity_id.startsWith(`${domain}.`)
    );
    return found && found.entity_id;
  }

  _call(domain, service, data) {
    this.dispatchEvent(new CustomEvent("haptic", { detail: "light", bubbles: true, composed: true }));
    return this._hass.callService(domain, service, data).catch((err) => {
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: { message: `Frame TV: ${err.message || err}` },
          bubbles: true,
          composed: true,
        })
      );
    });
  }

  _key(key) {
    const remote = this._sibling("remote");
    if (remote) this._call("remote", "send_command", { entity_id: remote, command: key });
    else this._call("media_player", "play_media", {
      entity_id: this._config.entity, media_content_type: "key", media_content_id: key,
    });
  }

  _action(action, value) {
    const entity_id = this._config.entity;
    const st = this._stateObj;
    const off = !st || st.state === "off";
    const art = this._sibling("switch");
    switch (action) {
      case "power":
        return this._call("media_player", off ? "turn_on" : "turn_off", { entity_id });
      case "mode-tv":
        return off
          ? this._call("media_player", "turn_on", { entity_id })
          : art && this._call("switch", "turn_off", { entity_id: art });
      case "mode-art":
        return art && this._call("switch", "turn_on", { entity_id: art });
      case "source":
        return this._call("media_player", "select_source", { entity_id, source: value });
      case "key":
        return this._key(value);
      case "mute":
        return this._call("media_player", "volume_mute", {
          entity_id,
          is_volume_muted: !st.attributes.is_volume_muted,
        });
      case "vol-up":
        return this._call("media_player", "volume_up", { entity_id });
      case "vol-down":
        return this._call("media_player", "volume_down", { entity_id });
    }
  }

  // ---------------------------------------------------------------- render

  _render() {
    if (!this._config || !this._hass) return;
    const st = this._stateObj;
    if (!st) {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">Entity not found: ${esc(this._config.entity)}</div></ha-card>`;
      this._built = false;
      return;
    }
    const sig = JSON.stringify([st.attributes.inputs, st.attributes.apps, this._config]);
    if (!this._built || sig !== this._sig) {
      this._build(st);
      this._sig = sig;
    }
    this._update(st);
  }

  _build(st) {
    const c = this._config;
    const inputs = st.attributes.inputs || [];
    const apps = Object.keys(st.attributes.apps || {});
    const btn = (action, icon, label, value = "", cls = "") =>
      `<button class="btn ${cls}" data-action="${action}" data-value="${esc(value)}" title="${esc(label)}" aria-label="${esc(label)}"><ha-icon icon="${icon}"></ha-icon></button>`;

    const appTile = (name) => {
      const [bg, fg] = BRANDS[name.toLowerCase()] || ["var(--ftv-surface-2)", "var(--primary-text-color)"];
      return `<button class="app" data-action="source" data-value="${esc(name)}" style="--app-bg:${bg};--app-fg:${fg}">${esc(name)}</button>`;
    };

    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <ha-card>
        <div class="head">
          <div class="icon"><ha-icon icon="mdi:television"></ha-icon></div>
          <div class="title">
            <div class="name">${esc(c.name || st.attributes.friendly_name || "Frame TV")}</div>
            <div class="status"></div>
          </div>
          ${btn("power", "mdi:power", "Power", "", "power")}
        </div>

        <div class="seg" role="group" aria-label="Mode">
          <button data-action="mode-tv" class="seg-tv"><ha-icon icon="mdi:television-play"></ha-icon>TV</button>
          <button data-action="mode-art" class="seg-art"><ha-icon icon="mdi:palette"></ha-icon>Art</button>
        </div>

        ${c.show_inputs && inputs.length ? `
        <div class="label">Inputs</div>
        <div class="chips">
          ${inputs.map((i) => `<button class="chip" data-action="source" data-value="${esc(i)}">${esc(i)}</button>`).join("")}
        </div>` : ""}

        ${c.show_apps && apps.length ? `
        <div class="label">Apps</div>
        <div class="apps">${apps.map(appTile).join("")}</div>` : ""}

        ${c.show_navigation ? `
        <div class="nav">
          <div class="dpad">
            ${btn("key", "mdi:chevron-up", "Up", "KEY_UP", "d up")}
            ${btn("key", "mdi:chevron-left", "Left", "KEY_LEFT", "d left")}
            <button class="ok" data-action="key" data-value="KEY_ENTER" aria-label="OK">OK</button>
            ${btn("key", "mdi:chevron-right", "Right", "KEY_RIGHT", "d right")}
            ${btn("key", "mdi:chevron-down", "Down", "KEY_DOWN", "d down")}
          </div>
          <div class="side">
            ${btn("key", "mdi:arrow-u-left-top", "Back", "KEY_RETURN")}
            ${btn("key", "mdi:home", "Home", "KEY_HOME")}
            ${btn("key", "mdi:cog", "Menu", "KEY_MENU")}
            ${btn("key", "mdi:information-outline", "Info", "KEY_INFO")}
          </div>
        </div>` : ""}

        ${c.show_media ? `
        <div class="row media">
          ${btn("key", "mdi:rewind", "Rewind", "KEY_REWIND")}
          ${btn("key", "mdi:play", "Play", "KEY_PLAY")}
          ${btn("key", "mdi:pause", "Pause", "KEY_PAUSE")}
          ${btn("key", "mdi:fast-forward", "Fast forward", "KEY_FF")}
        </div>` : ""}

        ${c.show_volume ? `
        <div class="row vol">
          ${btn("mute", "mdi:volume-high", "Mute", "", "mute")}
          ${btn("vol-down", "mdi:volume-minus", "Volume down")}
          <input class="slider" type="range" min="0" max="100" step="1" aria-label="Volume">
          <span class="vol-num"></span>
          ${btn("vol-up", "mdi:volume-plus", "Volume up")}
        </div>` : ""}
      </ha-card>`;

    const root = this.shadowRoot;
    root.querySelectorAll("[data-action]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._action(el.dataset.action, el.dataset.value);
      })
    );
    const slider = root.querySelector(".slider");
    if (slider) {
      slider.addEventListener("input", () => (root.querySelector(".vol-num").textContent = slider.value));
      slider.addEventListener("change", () =>
        this._call("media_player", "volume_set", {
          entity_id: this._config.entity,
          volume_level: Number(slider.value) / 100,
        })
      );
    }
    this._built = true;
  }

  _update(st) {
    const root = this.shadowRoot;
    const a = st.attributes;
    const off = st.state === "off" || st.state === "unavailable";
    const art = !off && !!a.art_mode;
    const source = a.source;

    root.host.classList.toggle("off", off);
    root.querySelector("ha-card").classList.toggle("off", off);
    root.querySelector(".status").textContent = off
      ? "Off"
      : art
        ? "Showing art"
        : source ? `On · ${source}` : "On";
    root.querySelector(".icon ha-icon").setAttribute("icon", art ? "mdi:palette" : "mdi:television");
    root.querySelector(".icon").classList.toggle("active", !off);
    root.querySelector(".power").classList.toggle("active", !off);
    root.querySelector(".seg-tv").classList.toggle("sel", !off && !art);
    root.querySelector(".seg-art").classList.toggle("sel", art);

    root.querySelectorAll('[data-action="source"]').forEach((el) =>
      el.classList.toggle("sel", !off && !art && el.dataset.value === source)
    );

    const mute = root.querySelector(".mute ha-icon");
    if (mute) mute.setAttribute("icon", a.is_volume_muted ? "mdi:volume-off" : "mdi:volume-high");
    const slider = root.querySelector(".slider");
    if (slider) {
      const hasLevel = typeof a.volume_level === "number";
      slider.disabled = off || !hasLevel;
      if (hasLevel && root.activeElement !== slider) {
        slider.value = Math.round(a.volume_level * 100);
      }
      root.querySelector(".vol-num").textContent = hasLevel ? Math.round(a.volume_level * 100) : "–";
    }
  }
}

const STYLES = `
  :host { --ftv-surface-2: var(--secondary-background-color, rgba(127,127,127,.12)); --ftv-radius: 14px; }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  button { font: inherit; color: inherit; border: 0; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

  .head { display: flex; align-items: center; gap: 12px; }
  .icon { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center;
          background: var(--ftv-surface-2); color: var(--secondary-text-color); transition: .2s; }
  .icon.active { background: color-mix(in srgb, var(--primary-color) 18%, transparent); color: var(--primary-color); }
  .title { flex: 1; min-width: 0; }
  .name { font-weight: 600; font-size: 16px; }
  .status { color: var(--secondary-text-color); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .btn { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center;
         background: var(--ftv-surface-2); transition: background .15s, transform .08s; }
  .btn:active, .app:active, .chip:active, .ok:active, .seg button:active { transform: scale(.94); }
  .btn.power.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }

  .seg { display: grid; grid-template-columns: 1fr 1fr; background: var(--ftv-surface-2); border-radius: 999px; padding: 4px; }
  .seg button { display: flex; align-items: center; justify-content: center; gap: 6px; height: 38px;
                border-radius: 999px; background: transparent; font-weight: 500; transition: .2s; }
  .seg button ha-icon { --mdc-icon-size: 18px; }
  .seg button.sel { background: var(--card-background-color, #fff); box-shadow: 0 1px 4px rgba(0,0,0,.18); color: var(--primary-color); }

  .label { font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--secondary-text-color); margin-bottom: -4px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { padding: 8px 14px; border-radius: 999px; background: var(--ftv-surface-2); font-size: 14px; }
  .chip.sel { background: var(--primary-color); color: var(--text-primary-color, #fff); }

  .apps { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 8px; }
  .app { height: 52px; border-radius: 12px; background: var(--app-bg); color: var(--app-fg);
         font-weight: 700; font-size: 14px; padding: 0 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .app.sel { outline: 3px solid var(--primary-color); outline-offset: 2px; }

  .nav { display: flex; align-items: center; justify-content: center; gap: 20px; flex-wrap: wrap; }
  .dpad { position: relative; width: 168px; height: 168px; border-radius: 50%; background: var(--ftv-surface-2); }
  .dpad .d { position: absolute; background: transparent; width: 52px; height: 52px; }
  .dpad .up { top: 4px; left: 58px; } .dpad .down { bottom: 4px; left: 58px; }
  .dpad .left { left: 4px; top: 58px; } .dpad .right { right: 4px; top: 58px; }
  .dpad .ok { position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%); width: 64px; height: 64px;
              border-radius: 50%; background: var(--card-background-color, #fff); font-weight: 700;
              box-shadow: 0 1px 4px rgba(0,0,0,.18); }
  .dpad .ok:active { transform: translate(-50%,-50%) scale(.94); }
  .side { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

  .row { display: flex; align-items: center; gap: 8px; }
  .media { justify-content: center; gap: 14px; }
  .vol .slider { flex: 1; min-width: 60px; accent-color: var(--primary-color); height: 28px; }
  .vol-num { width: 28px; text-align: right; font-variant-numeric: tabular-nums; color: var(--secondary-text-color); font-size: 13px; }

  ha-card.off .chips, ha-card.off .apps, ha-card.off .nav, ha-card.off .media, ha-card.off .vol { opacity: .45; }
`;

if (!customElements.get("frame-tv-card")) {
  customElements.define("frame-tv-card", FrameTvCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
  type: "frame-tv-card",
  name: "Frame TV Card",
  description: "Power, Art Mode, inputs, apps, navigation and volume for a Samsung Frame TV.",
    preview: true,
  });
}
