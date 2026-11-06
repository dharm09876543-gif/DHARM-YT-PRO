from datetime import datetime, timedelta, timezone

from src.upload.metadata import VideoMetadata


def test_clean_limits():
    m = VideoMetadata(title="<Hi> " + "x" * 200, description="a<b>c",
                      tags=["holi", "Holi", "", "mathura vlog"] + [f"t{i}" * 20 for i in range(40)]).clean()
    assert len(m.title) <= 100 and "<" not in m.title and m.description == "abc"
    assert m.tags[:2] == ["holi", "mathura vlog"]
    assert sum(len(t) for t in m.tags) <= 500


def test_schedule_forces_private_and_body():
    when = datetime.now(timezone.utc) + timedelta(days=1)
    m = VideoMetadata(title="x", privacy_status="public", publish_at=when).clean()
    assert m.privacy_status == "private" and m.errors() == []
    assert m.to_youtube_body()["status"]["publishAt"] == when.isoformat()


def test_errors():
    m = VideoMetadata(title="", category_id="999", privacy_status="secret",
                      publish_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    errs = " ".join(m.errors())
    assert "title" in errs and "category" in errs and "privacy" in errs and "future" in errs
