-- Where a video's title/description/tags came from: sidecar | gemini_name | filename | gemini_video.
-- Gemini only rewrites metadata from the real video when it did not come from the creator's sidecar.
ALTER TABLE videos ADD COLUMN metadata_source TEXT;
