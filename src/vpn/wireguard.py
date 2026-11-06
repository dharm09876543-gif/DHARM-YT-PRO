"""Per-channel outgoing IP for uploads via Surfshark (or any) WireGuard.

- Each channel may have a `vpn_profile` (e.g. "ch01"). Its full WireGuard .conf text comes ONLY from the
  env var / GitHub secret WG_CONF_<PROFILE upper> (e.g. WG_CONF_CH01). It is never written to the repo:
  at runtime it goes to a 0600 temp file in a 0700 temp dir, which is deleted when the tunnel goes down.
- Before uploading: read the public IP, bring the tunnel up (wg-quick), read the public IP again and
  require that it CHANGED. Otherwise the tunnel is torn down and VpnError is raised.
- Logs only show masked IPs (185.x.x.12). The config, keys and wg-quick output are never logged.
- A tunnel changes routing for the whole machine, so only one tunnel can be up per process/runner.
  The executor therefore runs VPN channels one at a time; GitHub Actions runs one channel per matrix job.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager, nullcontext
from pathlib import Path

import httpx

from src.utils.logging import get_logger

log = get_logger("dharm_yt.vpn")

PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,11}$")   # interface name dy<profile> must stay <= 15 chars
DEFAULT_IP_CHECK_URL = "https://api.ipify.org"


class VpnError(RuntimeError):
    """The VPN tunnel could not be brought up or verified; uploads for that channel must not run."""


def normalize_profile(profile: str) -> str:
    p = (profile or "").strip().lower()
    if not PROFILE_RE.match(p):
        raise ValueError("vpn profile must be 1-12 characters: a-z, 0-9, '_' or '-', starting with a letter/digit "
                         "(e.g. ch01)")
    return p


def env_var_for(profile: str) -> str:
    """'ch01' -> 'WG_CONF_CH01' ('-' becomes '_' because secret names cannot contain '-')."""
    return "WG_CONF_" + normalize_profile(profile).upper().replace("-", "_")


def mask_ip(ip: str | None) -> str:
    """185.234.10.12 -> 185.x.x.12 ; 2a02:6ea0:c02f::12 -> 2a02:x:x::12 ; anything else -> x.x.x.x"""
    try:
        a = ipaddress.ip_address(str(ip or "").strip())
    except ValueError:
        return "x.x.x.x"
    if a.version == 4:
        p = str(a).split(".")
        return f"{p[0]}.x.x.{p[3]}"
    full = a.exploded.split(":")
    return f"{full[0].lstrip('0') or '0'}:x:x::{full[-1].lstrip('0') or '0'}"


def get_public_ip(url: str = DEFAULT_IP_CHECK_URL, client: httpx.Client | None = None, timeout: float = 10) -> str:
    cl = client or httpx.Client(timeout=timeout)
    try:
        r = cl.get(url, headers={"Accept": "text/plain"})
    except httpx.HTTPError as e:
        raise VpnError(f"public IP check failed ({type(e).__name__})") from None
    if r.status_code != 200:
        raise VpnError(f"public IP check failed (HTTP {r.status_code})")
    text = r.text.strip()
    if text.startswith("{"):
        try:
            text = str(json.loads(text).get("ip", ""))
        except ValueError:
            text = ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        raise VpnError("public IP check returned something that is not an IP address") from None


class WireGuardTunnel:
    """One wg-quick tunnel. Use as a context manager: `with WireGuardTunnel(...) as t: ...`."""

    def __init__(self, profile: str, conf_text: str, ip_check_url: str = DEFAULT_IP_CHECK_URL,
                 runner=subprocess.run, http: httpx.Client | None = None, use_sudo: bool | None = None,
                 wg_quick: str = "wg-quick", timeout: int = 60):
        self.profile = normalize_profile(profile)
        if not conf_text or "[Interface]" not in conf_text or "[Peer]" not in conf_text:
            raise VpnError(f"{env_var_for(self.profile)} does not look like a WireGuard config "
                           "(needs [Interface] and [Peer])")
        self._conf = conf_text
        self.ip_check_url = ip_check_url or DEFAULT_IP_CHECK_URL
        self.runner = runner
        self.http = http
        if use_sudo is None:
            use_sudo = hasattr(os, "geteuid") and os.geteuid() != 0
        self.prefix = ["sudo", "-n"] if use_sudo else []
        self.wg_quick = wg_quick
        self.timeout = timeout
        self.iface = f"dy{self.profile.replace('-', '_')}"[:15]
        self.conf_path: Path | None = None
        self._dir: str | None = None
        self.is_up = False
        self.ip_before: str | None = None
        self.ip_after: str | None = None

    # ---- temp config file (0600, deleted after) ----
    def _write_conf(self) -> Path:
        self._dir = tempfile.mkdtemp(prefix="dy-wg-")          # mkdtemp is 0700
        path = Path(self._dir) / f"{self.iface}.conf"           # wg-quick takes the interface name from the file name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self._conf if self._conf.endswith("\n") else self._conf + "\n")
        os.chmod(path, 0o600)
        self.conf_path = path
        return path

    def _remove_conf(self) -> None:
        if self.conf_path is not None:
            try:
                self.conf_path.unlink(missing_ok=True)
            except OSError:
                pass
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
        self.conf_path, self._dir = None, None

    def _wg(self, action: str) -> subprocess.CompletedProcess:
        # Output is captured and never logged: wg-quick can echo config-derived lines.
        return self.runner(self.prefix + [self.wg_quick, action, str(self.conf_path)],
                           capture_output=True, text=True, timeout=self.timeout, check=False)

    def _ip(self) -> str:
        return get_public_ip(self.ip_check_url, client=self.http)

    # ---- lifecycle ----
    def up(self) -> str:
        """Bring the tunnel up and verify the public IP changed. Returns the masked new IP."""
        self.ip_before = self._ip()
        self._write_conf()
        try:
            try:
                r = self._wg("up")
            except (OSError, subprocess.SubprocessError) as e:
                raise VpnError(f"wg-quick up failed for profile {self.profile} ({type(e).__name__})") from None
            if r.returncode != 0:
                raise VpnError(f"wg-quick up failed for profile {self.profile} (exit {r.returncode})")
            self.is_up = True
            self.ip_after = self._ip()
            if self.ip_after == self.ip_before:
                raise VpnError(f"VPN {self.profile}: public IP did not change ({mask_ip(self.ip_after)}) - "
                               "refusing to upload from the wrong IP")
        except BaseException:
            self.down()
            raise
        log.info("VPN %s up: public IP %s (runner IP %s)", self.profile, mask_ip(self.ip_after), mask_ip(self.ip_before))
        return mask_ip(self.ip_after)

    def down(self) -> None:
        try:
            if self.is_up and self.conf_path is not None:
                try:
                    r = self._wg("down")
                    if r.returncode != 0:
                        log.warning("VPN %s: wg-quick down exit %s", self.profile, r.returncode)
                except (OSError, subprocess.SubprocessError) as e:
                    log.warning("VPN %s: wg-quick down failed (%s)", self.profile, type(e).__name__)
                self.is_up = False
        finally:
            self._remove_conf()

    @property
    def masked_ip(self) -> str | None:
        return mask_ip(self.ip_after) if self.ip_after else None

    def __enter__(self):
        self.up()
        return self

    def __exit__(self, *exc):
        self.down()
        return False


class VpnGate:
    """Decides per channel whether uploads need a tunnel, and opens it.

    settings.vpn:
      enabled: false                              # master switch
      require_for_channels_with_profile: true     # tunnel failure -> skip that channel's uploads
      ip_check_url: https://api.ipify.org
    """

    def __init__(self, settings: dict, env=None, tunnel_factory=WireGuardTunnel, alert=None):
        v = (settings or {}).get("vpn") or {}
        self.enabled = bool(v.get("enabled", False))
        self.require = bool(v.get("require_for_channels_with_profile", True))
        self.ip_check_url = v.get("ip_check_url") or DEFAULT_IP_CHECK_URL
        self.use_sudo = v.get("use_sudo")
        self.env = os.environ if env is None else env
        self.factory = tunnel_factory
        if alert is None:
            from src.services.alerts import send_alert
            alert = send_alert
        self.alert = alert

    def wants_tunnel(self, channel: dict) -> bool:
        return self.enabled and bool(channel.get("vpn_profile"))

    @property
    def active(self) -> bool:
        return self.enabled

    def _fail(self, channel: dict, msg: str):
        name = channel.get("channel_name") or channel.get("channel_id")
        if self.require:
            self.alert(f"VPN problem for {name}: {msg}. Uploads for this channel were skipped this run "
                       "(jobs stay QUEUED).")
            raise VpnError(msg)
        log.warning("VPN for %s not used (%s); vpn.require_for_channels_with_profile is false, uploading "
                    "from the runner IP", name, msg)
        return nullcontext(None)

    @contextmanager
    def _tunnel(self, tunnel):
        try:
            yield tunnel
        finally:
            tunnel.down()

    def open(self, channel: dict):
        """Context manager for the upload phase. Raises VpnError when a required tunnel is not verified."""
        if not self.wants_tunnel(channel):
            return nullcontext(None)
        try:
            var = env_var_for(channel["vpn_profile"])
        except ValueError as e:
            return self._fail(channel, str(e))
        conf = self.env.get(var, "")
        if not conf:
            return self._fail(channel, f"{var} is not set (add it as a GitHub secret / env var)")
        try:
            t = self.factory(channel["vpn_profile"], conf, ip_check_url=self.ip_check_url, use_sudo=self.use_sudo)
            t.up()
        except VpnError as e:
            return self._fail(channel, str(e))
        return self._tunnel(t)
