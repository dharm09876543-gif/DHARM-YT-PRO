"""Confirm with YouTube after upload: video is on the right channel and processing is fine."""
from __future__ import annotations

from dataclasses import dataclass

BAD_UPLOAD = {"rejected", "failed", "deleted"}


@dataclass
class VerifyResult:
    ok: bool
    final: bool              # True = no point checking again (passed or definitely failed)
    reason: str
    upload_status: str | None = None
    processing_status: str | None = None
    channel_id: str | None = None


def verify_upload(yt, yt_video_id: str, expected_channel_id: str) -> VerifyResult:
    item = yt.get_video(yt_video_id)
    if not item:
        return VerifyResult(False, False, "Video not visible on YouTube yet")
    ch = item.get("snippet", {}).get("channelId")
    st = item.get("status", {})
    up = st.get("uploadStatus")
    proc = (item.get("processingDetails") or {}).get("processingStatus")
    if ch != expected_channel_id:
        return VerifyResult(False, True, f"Video on the wrong channel: {ch}", up, proc, ch)
    if up in BAD_UPLOAD:
        reason = st.get("rejectionReason") or st.get("failureReason") or up
        return VerifyResult(False, True, f"YouTube marked the video {up}: {reason}", up, proc, ch)
    if proc == "failed":
        return VerifyResult(False, True, "YouTube processing fail", up, proc, ch)
    if up == "processed" or proc == "succeeded":
        return VerifyResult(True, True, "verified", up, proc, ch)
    return VerifyResult(False, False, f"processing in progress ({up}/{proc})", up, proc, ch)
