"""Generate title/description/tags with Gemini.

  python main.py ai "video_file.mp4" --notes "Holi festival vlog in Mathura" --channel "My Channel"
  --language English|Hindi|Hinglish (default English)   --style "funny"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.ai.gemini import GeminiError, GeminiMetadata  # noqa: E402

argv = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "ai" else sys.argv[1:]
p = argparse.ArgumentParser()
p.add_argument("filename")
p.add_argument("--notes", default="")
p.add_argument("--channel", default="")
p.add_argument("--language", default="English")
p.add_argument("--style", default="friendly, energetic")
a = p.parse_args(argv)
try:
    m = GeminiMetadata().generate(a.filename, a.channel, a.notes, a.language, a.style)
except GeminiError as e:
    sys.exit(f"Error: {e}")
print(json.dumps({"title": m.title, "description": m.description, "tags": m.tags,
                  "category_id": m.category_id}, ensure_ascii=False, indent=2))
