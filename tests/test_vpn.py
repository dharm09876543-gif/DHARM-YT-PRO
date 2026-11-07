"""Phase 9: per-channel WireGuard tunnel. subprocess (wg-quick) and HTTP (IP check) are mocked."""
import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from sqlalchemy import text

from src.services.channel_service import ChannelError
from src.vpn.actions import build_matrix, github_env_block, mask_commands, select_wg_secret
from src.vpn.wireguard import VpnError, VpnGate, WireGuardTunnel, env_var_for, mask_ip, normalize_profile

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEY = "SECRETprivKEYdoNotLog0123456789abcdefghijk="
CONF = f"""[Interface]
PrivateKey = {SECRET_KEY}
Address = 10.14.0.2/16
DNS = 162.252.172.57

[Peer]
PublicKey = PEERpubKEY0123456789abcdefghijklmnopqrstu=
AllowedIPs = 0.0.0.0/0
Endpoint = in-mum.prod.surfshark.com:51820
"""
RUNNER_IP, VPN_IP = "20.51.7.33", "185.234.10.12"


def ip_client(ips):
    seq = list(ips)

    def handler(req):
        return httpx.Response(200, text=seq.pop(0) if len(seq) > 1 else seq[0])
    return httpx.Client(transport=httpx.MockTransport(handler))


class FakeRunner:
    def __init__(self, up_rc=0, raise_on=None):
        self.calls, self.up_rc, self.raise_on = [], up_rc, raise_on
        self.modes = []

    def __call__(self, cmd, **kw):
        action, path = cmd[-2], Path(cmd[-1])
        self.calls.append(action)
        assert kw.get("capture_output") and kw.get("check") is False
        if action == "up":
            assert path.exists() and path.read_text().startswith("[Interface]")
            self.modes.append((stat.S_IMODE(path.stat().st_mode), stat.S_IMODE(path.parent.stat().st_mode)))
            self.path = path
        if self.raise_on == action:
            raise OSError("wg-quick missing")
        return subprocess.CompletedProcess(cmd, self.up_rc if action == "up" else 0, "[#] ip link add dyc", "")


def tunnel(runner, ips, **kw):
    return WireGuardTunnel("ch01", CONF, runner=runner, http=ip_client(ips), use_sudo=False, **kw)


# ---------- helpers ----------
def test_mask_ip_and_profile_names():
    assert mask_ip("185.234.10.12") == "185.x.x.12"
    assert mask_ip("2a02:6ea0:c02f::12") == "2a02:x:x::12"
    assert mask_ip("nonsense") == "x.x.x.x" and mask_ip(None) == "x.x.x.x"
    assert env_var_for("CH01") == "WG_CONF_CH01" and env_var_for("in-mum") == "WG_CONF_IN_MUM"
    assert normalize_profile(" Ch01 ") == "ch01"
    for bad in ["", "a b", "../etc", "x" * 13, "-ch"]:
        with pytest.raises(ValueError):
            normalize_profile(bad)


# ---------- tunnel up / verify / down ----------
def test_tunnel_up_verifies_ip_change_then_down_removes_temp_file():
    r = FakeRunner()
    t = tunnel(r, [RUNNER_IP, VPN_IP])
    with t:
        assert t.masked_ip == "185.x.x.12" and t.is_up
        path = t.conf_path
        assert path.exists() and path.name == "dych01.conf"
    assert r.calls == ["up", "down"]
    assert r.modes == [(0o600, 0o700)]                       # 0600 file in a 0700 dir
    assert not path.exists() and not path.parent.exists()     # deleted after
    assert t.conf_path is None and not t.is_up


def test_sudo_prefix_used_when_not_root():
    seen = []

    def runner(cmd, **kw):
        seen.append(cmd[:3])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    with WireGuardTunnel("ch01", CONF, runner=runner, http=ip_client([RUNNER_IP, VPN_IP]), use_sudo=True):
        pass
    assert seen[0] == ["sudo", "-n", "wg-quick"]


def test_unchanged_ip_refuses_and_tears_down():
    r = FakeRunner()
    t = tunnel(r, [RUNNER_IP, RUNNER_IP])
    with pytest.raises(VpnError, match="did not change"):
        t.up()
    assert r.calls == ["up", "down"] and not r.path.exists() and not r.path.parent.exists()


def test_wg_quick_failure_raises_and_removes_file():
    r = FakeRunner(up_rc=1)
    t = tunnel(r, [RUNNER_IP, VPN_IP])
    with pytest.raises(VpnError, match="exit 1"):
        t.up()
    assert r.calls == ["up"] and not r.path.exists()
    r2 = FakeRunner(raise_on="up")
    with pytest.raises(VpnError, match="OSError"):
        tunnel(r2, [RUNNER_IP, VPN_IP]).up()
    assert not r2.path.exists()


def test_ip_check_failure_before_tunnel_is_vpn_error():
    bad = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    t = WireGuardTunnel("ch01", CONF, runner=FakeRunner(), http=bad, use_sudo=False)
    with pytest.raises(VpnError, match="HTTP 503"):
        t.up()
    assert t.conf_path is None
    js = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ip": VPN_IP})))
    from src.vpn.wireguard import get_public_ip
    assert get_public_ip("https://x", client=js) == VPN_IP


def test_invalid_config_rejected_without_echoing_it():
    with pytest.raises(VpnError) as ei:
        WireGuardTunnel("ch01", f"PrivateKey = {SECRET_KEY}", runner=FakeRunner(), use_sudo=False)
    assert SECRET_KEY not in str(ei.value)


def test_config_and_full_ip_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    r = FakeRunner()
    with tunnel(r, [RUNNER_IP, VPN_IP]):
        pass
    with pytest.raises(VpnError) as ei:
        tunnel(FakeRunner(), [RUNNER_IP, RUNNER_IP]).up()
    logs = caplog.text + str(ei.value)
    for secret in [SECRET_KEY, "PEERpubKEY", "surfshark.com", "10.14.0.2", VPN_IP, RUNNER_IP, "[#]"]:
        assert secret not in logs
    assert "185.x.x.12" in caplog.text and "20.x.x.33" in caplog.text


# ---------- gate ----------
def _gate(env, factory=None, require=True, alerts=None):
    s = {"vpn": {"enabled": True, "require_for_channels_with_profile": require, "ip_check_url": "https://ip.test"}}
    return VpnGate(s, env=env, tunnel_factory=factory or WireGuardTunnel,
                   alert=(alerts.append if alerts is not None else (lambda m: None)))


def test_gate_missing_secret_required_vs_optional():
    alerts = []
    ch = {"channel_id": "UCx", "channel_name": "Demo", "vpn_profile": "ch01"}
    with pytest.raises(VpnError, match="WG_CONF_CH01 is not set"):
        _gate({}, alerts=alerts).open(ch)
    assert alerts and "Demo" in alerts[0] and "skipped" in alerts[0]
    with _gate({}, require=False).open(ch) as t:
        assert t is None
    assert not _gate({}).wants_tunnel({"vpn_profile": None})
    assert not VpnGate({"vpn": {"enabled": False}}, env={}, alert=lambda m: None).wants_tunnel(ch)


def test_gate_opens_and_closes_tunnel():
    r = FakeRunner()

    def factory(profile, conf, **kw):
        assert kw["ip_check_url"] == "https://ip.test" and conf == CONF
        return WireGuardTunnel(profile, conf, runner=r, http=ip_client([RUNNER_IP, VPN_IP]), use_sudo=False)
    with _gate({"WG_CONF_CH01": CONF}, factory).open({"channel_id": "UCx", "vpn_profile": "ch01"}) as t:
        assert t.is_up and t.masked_ip == "185.x.x.12"
    assert r.calls == ["up", "down"] and not r.path.exists()


# ---------- executor integration ----------
def _setup_two(engine, cipher, chsvc, tmp_path, monkeypatch):
    from tests.test_scheduler import _ctx_factory
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ids = ["UC" + c * 22 for c in "vw"]
    for cid in ids:
        chsvc.add(cid, "Ch" + cid[-1], "r" + cid); chsvc.save_tokens(cid, "1//r")
    chsvc.set_vpn_profile(ids[0], "ch01")
    factory, _ = _ctx_factory(engine, cipher, {}, tmp_path)
    return ids, factory


def test_vpn_failure_skips_only_that_channels_uploads(engine, cipher, chsvc, tmp_path, monkeypatch):
    from src.scheduler.executor import run_all, summary
    ids, factory = _setup_two(engine, cipher, chsvc, tmp_path, monkeypatch)
    alerts, r = [], FakeRunner()

    def tf(profile, conf, **kw):
        return WireGuardTunnel(profile, conf, runner=r, http=ip_client([RUNNER_IP, RUNNER_IP]), use_sudo=False)
    res = run_all(engine, chsvc.list(), factory, {"uploads": {"max_concurrent_uploads": 2}},
                  {"scheduler": {"enabled": False}}, steps=("discover", "plan", "upload"),
                  vpn=_gate({"WG_CONF_CH01": CONF}, tf, alerts=alerts))
    by = {x.channel_id: x for x in res}
    assert by[ids[0]].stopped == "vpn" and by[ids[0]].completed == 0 and not by[ids[0]].ok
    assert by[ids[1]].completed == 1 and by[ids[1]].ok and by[ids[1]].vpn_ip is None
    with engine.connect() as c:
        st = c.execute(text("SELECT upload_status FROM videos WHERE channel_id=:c"), {"c": ids[0]}).scalar()
    assert st == "QUEUED"                                    # never uploaded from the wrong IP
    assert len(alerts) == 1 and "stopped: vpn" in summary(res)
    assert not r.path.exists()


def test_vpn_success_uploads_through_tunnel_sequentially(engine, cipher, chsvc, tmp_path, monkeypatch):
    from src.scheduler import executor
    ids, factory = _setup_two(engine, cipher, chsvc, tmp_path, monkeypatch)
    r = FakeRunner()

    def tf(profile, conf, **kw):
        return WireGuardTunnel(profile, conf, runner=r, http=ip_client([RUNNER_IP, VPN_IP]), use_sudo=False)

    def no_threads(*a, **k):
        raise AssertionError("VPN channels must not run in parallel threads")
    monkeypatch.setattr(executor, "ThreadPoolExecutor", no_threads)
    res = executor.run_all(engine, chsvc.list(), factory, {"uploads": {"max_concurrent_uploads": 3}},
                           {"scheduler": {"enabled": False}}, steps=("discover", "plan", "upload"),
                           vpn=_gate({"WG_CONF_CH01": CONF}, tf))
    by = {x.channel_id: x for x in res}
    assert by[ids[0]].completed == 1 and by[ids[0]].vpn_ip == "185.x.x.12"
    assert by[ids[1]].completed == 1
    assert r.calls == ["up", "down"] and not r.path.exists()
    assert "vpn=185.x.x.12" in executor.summary(res) and VPN_IP not in executor.summary(res)


# ---------- channel profile + migration ----------
def test_channel_vpn_profile_set_clear(engine, chsvc, channel):
    cid = channel["channel_id"]
    assert chsvc.get(cid)["vpn_profile"] is None
    chsvc.set_vpn_profile(cid, "CH01")
    assert chsvc.get(cid)["vpn_profile"] == "ch01"
    with pytest.raises(ChannelError):
        chsvc.set_vpn_profile(cid, "bad profile!")
    chsvc.set_vpn_profile(cid, None)
    assert chsvc.get(cid)["vpn_profile"] is None
    with engine.connect() as c:
        assert c.execute(text("SELECT 1 FROM schema_migrations WHERE version='005_channel_vpn_profile'")).first()


def test_channels_cli_vpn(tmp_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:////{tmp_path}/cli.db"}
    run = lambda *a: subprocess.run([sys.executable, "main.py", "channels", *a], cwd=ROOT, env=env,
                                    capture_output=True, text=True)
    cid = "UC" + "k" * 22
    assert run("add", cid, "CLI Test", "folder").returncode == 0
    out = run("vpn", "--channel", cid, "--profile", "ch07")
    assert out.returncode == 0 and "WG_CONF_CH07" in out.stdout
    assert "vpn=ch07" in run("list").stdout
    assert run("vpn", "--channel", cid, "--clear").returncode == 0
    assert "vpn=-" in run("list").stdout
    assert run("vpn", "--channel", cid, "--profile", "no good").returncode == 1


# ---------- GitHub Actions helpers ----------
def test_build_matrix_filters_caps_and_rotates():
    chans = [{"channel_id": f"UC{i:03d}", "enabled": True, "auth_status": "active", "vpn_profile": f"ch{i}" if i % 2 else None,
              "channel_name": "secret name"} for i in range(300)]
    chans.append({"channel_id": "UCoff", "enabled": False, "auth_status": "active"})
    chans.append({"channel_id": "UCrev", "enabled": True, "auth_status": "revoked"})
    inc, total = build_matrix(chans)
    assert total == 300 and len(inc) == 256
    assert set(inc[0]) == {"channel_id", "vpn_profile", "wg_secret"} and inc[0]["vpn_profile"] == ""
    inc2, _ = build_matrix(chans, offset=1)
    assert {c["channel_id"] for c in inc} | {c["channel_id"] for c in inc2} == {c["channel_id"] for c in chans[:300]}
    assert build_matrix(chans, max_jobs=1000)[0].__len__() == 256       # GitHub hard limit
    small, t = build_matrix(chans[:3], max_jobs=10)
    assert t == 3 and len(small) == 3


def test_select_secret_and_masking():
    sj = json.dumps({"WG_CONF_CH01": CONF, "OTHER": "x"})
    assert select_wg_secret(sj, "ch01") == ("WG_CONF_CH01", CONF)
    assert select_wg_secret(sj, "ch02") == ("WG_CONF_CH02", None)
    assert select_wg_secret("not json", "ch01")[1] is None
    masks = mask_commands(CONF)
    assert f"::add-mask::{SECRET_KEY}" in masks and all(m.startswith("::add-mask::") for m in masks)
    block = github_env_block("WG_CONF_CH01", CONF)
    head, *_ = block.splitlines()
    delim = head.split("<<", 1)[1]
    assert head.startswith("WG_CONF_CH01<<") and block.rstrip().endswith(delim) and delim not in CONF


def test_select_wg_script_never_prints_config(tmp_path):
    envf = tmp_path / "github_env"
    env = {**os.environ, "SECRETS_JSON": json.dumps({"WG_CONF_CH01": CONF}), "GITHUB_ENV": str(envf)}
    out = subprocess.run([sys.executable, "scripts/actions_helper.py", "select-wg", "--profile", "ch01"],
                         cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.returncode == 0
    for line in (out.stdout + out.stderr).splitlines():
        if SECRET_KEY in line or "surfshark" in line:
            assert line.startswith("::add-mask::")             # consumed by the runner, never shown
    assert SECRET_KEY in envf.read_text() and "WG_CONF_CH01<<" in envf.read_text()
    env.pop("SECRETS_JSON")
    miss = subprocess.run([sys.executable, "scripts/actions_helper.py", "select-wg", "--profile", "ch01"],
                          cwd=ROOT, env=env, capture_output=True, text=True)
    assert miss.returncode == 0 and "WG_CONF_CH01 is not set" in miss.stdout


def test_upload_workflow_matrix_shape():
    raw = (ROOT / ".github" / "workflows" / "upload.yml").read_text()
    wf = yaml.safe_load(raw)
    plan, up = wf["jobs"]["plan"], wf["jobs"]["upload"]
    assert "channels" in plan["outputs"] and up["needs"] == "plan"
    assert up["strategy"]["fail-fast"] is False and "max-parallel" in up["strategy"]
    assert "fromJSON(needs.plan.outputs.channels)" in up["strategy"]["matrix"]["include"]
    assert "matrix.channel_id" in up["concurrency"]["group"] and up["concurrency"]["cancel-in-progress"] is False
    steps = {s.get("name", ""): s for s in up["steps"]}
    assert "wireguard-tools" in steps["Install WireGuard tools"]["run"]
    sel = [s for s in up["steps"] if "secrets[matrix.wg_secret]" in json.dumps(s)]
    assert len(sel) == 1 and "select-wg" in sel[0]["run"]           # only this channel's WG secret, one step
    assert "toJSON(secrets)" not in json.dumps(up.get("env", {}))
    assert 'run --channel "${{ matrix.channel_id }}"' in raw
    assert "echo $WG_CONF" not in raw and "echo \"$WG_CONF" not in raw and "SECRETS_JSON\n" not in raw


def test_settings_vpn_block_and_validation():
    from src.config import load_yaml, validate_settings
    s = yaml.safe_load((ROOT / "config" / "settings.example.yaml").read_text())
    assert s["vpn"]["enabled"] is True and s["vpn"]["require_for_channels_with_profile"] is True
    assert s["vpn"]["ip_check_url"].startswith("https://")
    bad = {**load_yaml("settings"), "vpn": {"enabled": "yes", "ip_check_url": "http://x"}}
    errs = " ".join(validate_settings(bad))
    assert "vpn.enabled" in errs and "ip_check_url" in errs


def test_workflows_never_dump_all_secrets():
    from pathlib import Path
    for wf in Path(".github/workflows").glob("*.yml"):
        assert "toJSON(secrets)" not in wf.read_text(encoding="utf-8"), wf.name


def test_select_wg_from_single_secret_env(tmp_path):
    envf = tmp_path / "env"
    env = {**os.environ, "WG_CONF_VALUE": CONF, "GITHUB_ENV": str(envf)}
    env.pop("SECRETS_JSON", None)
    out = subprocess.run([sys.executable, "scripts/actions_helper.py", "select-wg", "--profile", "ch01"],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0 and "loaded for this job (masked)" in out.stdout
    assert envf.read_text().startswith("WG_CONF_CH01<<")
