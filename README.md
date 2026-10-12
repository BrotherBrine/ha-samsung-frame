# Samsung Frame TV for Home Assistant

A local integration and dashboard card for Samsung Frame TVs (built for the 2024 Frame, model QN43LS03DAFXZA, and it should work on any 2018+ Tizen Frame).

It gives you one card with:

- **Power** on/off (a long press of the power key for a true off, plus Wake-on-LAN)
- **TV / Art Mode** switching, with the real Art Mode state read from the TV
- **Inputs**: TV, HDMI 1, HDMI 2 and HDMI 3
- **Apps**: one-tap launch, with the app that's currently open highlighted
- **Navigation**: D-pad, OK, Back, Home, Menu and Info
- **Playback**: rewind, play, pause and fast-forward
- **Volume**: a 0–100 slider, +/- buttons and mute

Everything stays on your network. There's no cloud, and you don't need to install any extra Python packages.

## Entities created

| Entity | What it does |
|---|---|
| `media_player.<name>` | power, volume, source (inputs and apps), playback. Its state is `idle` while in Art Mode |
| `switch.<name>_art_mode` | on means showing art |
| `remote.<name>_remote` | `remote.send_command` with any `KEY_*` (for example `KEY_HOME`, `KEY_UP` or `KEY_HDMI1`) |

## Install

You need [HACS](https://hacs.xyz/docs/use/download/download/) installed first.

**1. Download it.** Click this button, choose your Home Assistant, then click **Download**:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BrotherBrine&repository=ha-samsung-frame&category=integration)

**2. Restart Home Assistant** (Settings → ⋮ → Restart).

**3. Add your TV.** Turn the TV on, then click:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=samsung_frame)

Enter the TV's IP address and click Submit. Click Submit again on the next screen, then press **Allow** on the TV with its remote.

**4. Optional:** open **Configure** on the integration to edit the app or input lists, or to link SmartThings so the card shows the active input.

HACS tells you when a new version is out, and updating is one click.

<details>
<summary>Manual install (without HACS)</summary>

Download the latest [release](https://github.com/BrotherBrine/ha-samsung-frame/releases), copy `custom_components/samsung_frame` into your Home Assistant `config/custom_components/` folder, then restart Home Assistant and follow step 3.
</details>

> Give the TV a DHCP reservation in your router so its IP never changes.
> On the TV, turn on **Settings → General → Network → Expert Settings → Power On with Mobile**. That lets Home Assistant turn the TV on from off.

## Add the card

The card loads automatically, with no resource to add. Edit a dashboard, click **Add card**, and search for **Frame TV Card**. Or paste this:

```yaml
type: custom:frame-tv-card
entity: media_player.frame_tv
```

All options:

```yaml
type: custom:frame-tv-card
entity: media_player.frame_tv
name: Living Room Frame
show_inputs: true
show_apps: true
show_navigation: true
show_media: true
show_volume: true
# auto-detected from the same device; set these only to override
switch_entity: switch.frame_tv_art_mode
remote_entity: remote.frame_tv_remote
```

### A whole dashboard for the TV

Settings → Dashboards → Add dashboard → open it → ⋮ → Edit → Raw configuration editor:

```yaml
views:
  - title: Frame TV
    type: panel
    cards:
      - type: custom:frame-tv-card
        entity: media_player.frame_tv
```

## Apps and inputs

Options use one line per item in the form `Name: value`:

```
Netflix: 3201907018807
YouTube: 111299001912
Some App: 3201234567890, native
```

- **App IDs:** find them in the [community app ID list](https://github.com/tavicu/homebridge-samsung-tizen/wiki/Applications). If an app won't open, add `, native` to its line.
- **Inputs** use remote keys: `KEY_TV`, `KEY_HDMI1`, `KEY_HDMI2`, `KEY_HDMI3` or `KEY_HDMI4`.

## Use in automations

```yaml
# Art Mode at 11pm
- action: switch.turn_on
  target: { entity_id: switch.frame_tv_art_mode }

# Launch an app
- action: media_player.select_source
  target: { entity_id: media_player.frame_tv }
  data: { source: Netflix }

# Any key
- action: remote.send_command
  target: { entity_id: remote.frame_tv_remote }
  data: { command: [KEY_HOME, KEY_RIGHT, KEY_ENTER], delay_secs: 0.5 }
```

## Notes and troubleshooting

- **Use only one integration per TV.** If you added Home Assistant's built-in *Samsung Smart TV* integration for the same TV, remove it so the two don't fight over the connection. You can keep SmartThings.
- **If Art Mode won't toggle,** the integration falls back to pressing the power key, which switches between TV and Art when the TV is on. Some firmware updates temporarily break the Art API. Turn on debug logging for `custom_components.samsung_frame` to see what happened.
- **If volume shows "–",** the TV's UPnP service (port 9197) isn't answering. The +/- and mute buttons still work through remote keys.
- **The app highlight lags by up to about 10 seconds,** because state is polled every 10 seconds.
- **Active input:** the TV doesn't report its current input over the local network. To fix that, open **Configure** and pick the TV's **SmartThings media player**. The card then highlights the real active input, including changes made with the physical remote. That one value comes from Samsung's cloud, so it can lag a few seconds; everything else stays local. Without SmartThings linked, the card shows the last input you picked.
