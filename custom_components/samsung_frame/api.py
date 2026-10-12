"""Local API client for Samsung Frame TVs (Tizen 2018+).

Talks to the TV over three local channels, with no cloud and no extra
Python dependencies (only aiohttp, which ships with Home Assistant):

* REST      http://<host>:8001/api/v2/                 power state, device info, app status
* WebSocket wss://<host>:8002/.../samsung.remote.control  remote keys, app launching
* WebSocket wss://<host>:8002/.../com.samsung.art-app     Art Mode get/set
* UPnP SOAP http://<host>:9197/upnp/control/RenderingControl1  absolute volume / mute
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import re
import socket
import uuid
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REST_PORT = 8001
WS_PORT = 8002
UPNP_PORT = 9197

REMOTE_CHANNEL = "samsung.remote.control"
ART_CHANNEL = "com.samsung.art-app"

EV_CONNECT = "ms.channel.connect"
EV_READY = "ms.channel.ready"
EV_UNAUTHORIZED = "ms.channel.unauthorized"
EV_TIMEOUT = "ms.channel.timeOut"
EV_D2D = "d2d_service_message"

RENDERING_CONTROL = "urn:schemas-upnp-org:service:RenderingControl:1"


class FrameTVError(Exception):
    """Generic communication failure."""


class FrameTVUnauthorized(FrameTVError):
    """The pairing prompt on the TV was denied or timed out."""


class FrameTV:
    """Async client for one Samsung Frame TV."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        token: str | None = None,
        client_name: str = "Home Assistant",
        on_new_token: Callable[[str], None] | None = None,
    ) -> None:
        self._session = session
        self.host = host
        self.token = token
        self._client_name = base64.b64encode(client_name.encode()).decode()
        self._on_new_token = on_new_token

        self._remote_ws: aiohttp.ClientWebSocketResponse | None = None
        self._remote_reader: asyncio.Task | None = None
        self._remote_lock = asyncio.Lock()
        self._art_lock = asyncio.Lock()

    # ------------------------------------------------------------------ REST

    async def device_info(self, timeout: float = 3) -> dict[str, Any] | None:
        """Return /api/v2/ device info, or None if the TV is unreachable."""
        try:
            async with self._session.get(
                f"http://{self.host}:{REST_PORT}/api/v2/",
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    async def app_visible(self, app_id: str) -> bool:
        """Return True if the given app is currently in the foreground."""
        try:
            async with self._session.get(
                f"http://{self.host}:{REST_PORT}/api/v2/applications/{app_id}",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json(content_type=None)
                return bool(data.get("visible"))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return False

    # ------------------------------------------------------------- websocket

    def _ws_url(self, channel: str) -> str:
        url = (
            f"wss://{self.host}:{WS_PORT}/api/v2/channels/{channel}"
            f"?name={self._client_name}"
        )
        if self.token:
            url += f"&token={self.token}"
        return url

    async def _open_channel(
        self, channel: str, timeout: float, wait_ready: bool
    ) -> aiohttp.ClientWebSocketResponse:
        """Open a channel and complete the Samsung handshake."""
        try:
            async with asyncio.timeout(8):
                ws = await self._session.ws_connect(
                    self._ws_url(channel),
                    ssl=False,
                    timeout=aiohttp.ClientWSTimeout(ws_receive=None, ws_close=5),
                )
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
            raise FrameTVError(f"Cannot connect to {self.host}: {err}") from err

        try:
            async with asyncio.timeout(timeout):
                connected = False
                while True:
                    msg = await ws.receive()
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        raise FrameTVError(f"Channel closed during handshake: {msg.type}")
                    data = json.loads(msg.data)
                    event = data.get("event")
                    if event in (EV_UNAUTHORIZED, EV_TIMEOUT):
                        raise FrameTVUnauthorized(event)
                    if event == EV_CONNECT:
                        new_token = (data.get("data") or {}).get("token")
                        if new_token and new_token != self.token:
                            self.token = new_token
                            if self._on_new_token:
                                self._on_new_token(new_token)
                        connected = True
                        if not wait_ready:
                            return ws
                    elif event == EV_READY and connected:
                        return ws
        except BaseException:
            await ws.close()
            raise

    async def pair(self, timeout: float = 30) -> str | None:
        """Connect once so the TV shows its 'Allow' prompt. Returns the token."""
        ws = await self._open_channel(REMOTE_CHANNEL, timeout, wait_ready=False)
        await ws.close()
        return self.token

    async def _ensure_remote(self) -> aiohttp.ClientWebSocketResponse:
        if self._remote_ws is not None and not self._remote_ws.closed:
            return self._remote_ws
        ws = await self._open_channel(REMOTE_CHANNEL, 10, wait_ready=False)
        self._remote_ws = ws
        self._remote_reader = asyncio.create_task(self._drain(ws))
        return ws

    async def _drain(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Read and discard incoming messages so the socket stays healthy."""
        with contextlib.suppress(Exception):
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    _LOGGER.debug("remote event: %s", msg.data[:200])

    async def _send_remote(self, payloads: list[dict[str, Any] | float]) -> None:
        """Send payloads on the remote channel. A float means sleep that long."""
        async with self._remote_lock:
            for attempt in (1, 2):
                try:
                    ws = await self._ensure_remote()
                    for payload in payloads:
                        if isinstance(payload, (int, float)):
                            await asyncio.sleep(payload)
                        else:
                            await ws.send_str(json.dumps(payload))
                    return
                except (aiohttp.ClientError, ConnectionResetError, RuntimeError) as err:
                    await self._close_remote()
                    if attempt == 2:
                        raise FrameTVError(str(err)) from err

    async def _close_remote(self) -> None:
        if self._remote_ws is not None:
            with contextlib.suppress(Exception):
                await self._remote_ws.close()
        if self._remote_reader is not None:
            self._remote_reader.cancel()
        self._remote_ws = None
        self._remote_reader = None

    @staticmethod
    def _key(cmd: str, key: str) -> dict[str, Any]:
        return {
            "method": "ms.remote.control",
            "params": {
                "Cmd": cmd,
                "DataOfCmd": key,
                "Option": "false",
                "TypeOfRemote": "SendRemoteKey",
            },
        }

    async def send_key(self, key: str, hold: float | None = None) -> None:
        """Click a remote key, or press-and-hold it for `hold` seconds."""
        key = key.upper()
        if not key.startswith("KEY_"):
            key = f"KEY_{key}"
        if hold:
            await self._send_remote(
                [self._key("Press", key), hold, self._key("Release", key)]
            )
        else:
            await self._send_remote([self._key("Click", key)])

    async def launch_app(self, app_id: str, native: bool = False) -> None:
        await self._send_remote(
            [
                {
                    "method": "ms.channel.emit",
                    "params": {
                        "event": "ed.apps.launch",
                        "to": "host",
                        "data": {
                            "action_type": "NATIVE_LAUNCH" if native else "DEEP_LINK",
                            "appId": app_id,
                            "metaTag": "",
                        },
                    },
                }
            ]
        )

    # -------------------------------------------------------------- art mode

    async def _art_request(self, request: dict[str, Any], timeout: float = 6) -> dict:
        async with self._art_lock:
            ws = await self._open_channel(ART_CHANNEL, timeout, wait_ready=True)
            try:
                req_id = str(uuid.uuid4())
                payload = {**request, "id": req_id, "request_id": req_id}
                await ws.send_str(
                    json.dumps(
                        {
                            "method": "ms.channel.emit",
                            "params": {
                                "event": "art_app_request",
                                "to": "host",
                                "data": json.dumps(payload),
                            },
                        }
                    )
                )
                async with asyncio.timeout(timeout):
                    while True:
                        msg = await ws.receive()
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            raise FrameTVError("Art channel closed")
                        frame = json.loads(msg.data)
                        if frame.get("event") != EV_D2D:
                            continue
                        try:
                            data = json.loads(frame.get("data") or "{}")
                        except ValueError:
                            continue
                        if data.get("request_id", data.get("id")) != req_id:
                            continue
                        if data.get("event") == "error":
                            raise FrameTVError(f"Art request failed: {data}")
                        return data
            except asyncio.TimeoutError as err:
                raise FrameTVError("Art request timed out") from err
            except (aiohttp.ClientError, ConnectionResetError, ValueError) as err:
                raise FrameTVError(f"Art request failed: {err}") from err
            finally:
                await ws.close()

    async def get_art_mode(self) -> bool:
        data = await self._art_request({"request": "get_artmode_status"})
        return str(data.get("value", "")).lower() == "on"

    async def set_art_mode(self, on: bool) -> None:
        await self._art_request(
            {"request": "set_artmode_status", "value": "on" if on else "off"}
        )

    # ------------------------------------------------------------------ UPnP

    async def _soap(self, action: str, args: str = "") -> str | None:
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{RENDERING_CONTROL}">'
            f"<InstanceID>0</InstanceID><Channel>Master</Channel>{args}"
            f"</u:{action}></s:Body></s:Envelope>"
        )
        try:
            async with self._session.post(
                f"http://{self.host}:{UPNP_PORT}/upnp/control/RenderingControl1",
                data=body,
                headers={
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPACTION": f'"{RENDERING_CONTROL}#{action}"',
                },
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    async def get_volume(self) -> int | None:
        text = await self._soap("GetVolume")
        match = text and re.search(r"<CurrentVolume>(\d+)</CurrentVolume>", text)
        return int(match.group(1)) if match else None

    async def set_volume(self, level: int) -> bool:
        level = max(0, min(100, int(level)))
        return await self._soap("SetVolume", f"<DesiredVolume>{level}</DesiredVolume>") is not None

    async def get_mute(self) -> bool | None:
        text = await self._soap("GetMute")
        match = text and re.search(r"<CurrentMute>(\d)</CurrentMute>", text)
        return match.group(1) == "1" if match else None

    async def set_mute(self, mute: bool) -> bool:
        return (
            await self._soap("SetMute", f"<DesiredMute>{1 if mute else 0}</DesiredMute>")
            is not None
        )

    # ----------------------------------------------------------------- power

    @staticmethod
    def wake_on_lan(mac: str, broadcast: str = "255.255.255.255") -> None:
        mac_bytes = bytes.fromhex(re.sub(r"[^0-9a-fA-F]", "", mac))
        if len(mac_bytes) != 6:
            return
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, 9))

    async def close(self) -> None:
        await self._close_remote()
