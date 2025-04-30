#!/usr/bin/env python
"""
scripts/generate_objects.py

Detect objects in video frames for each transcript segment and
add object tags to content_tags.
"""

import os
import subprocess
import logging
from pathlib import Path
from ultralytics import YOLO
from scripts.db_utils import get_db_connection

logging.basicConfig(level=logging.INFO)

MODEL_NAME = "yolov8n.pt"  # change if you want a larger model

def extract_frame(video_path: str, time_sec: float, output_path: str) -> str:
    """Grab one frame at time_sec using ffmpeg."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(time_sec),
        "-i", video_path,
        "-vframes", "1",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def generate_object_tags():
    model = YOLO(MODEL_NAME)
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.id, t.media_id, t.start_sec, t.end_sec, m.source_uri
            FROM content_creation.transcripts t
            JOIN content_creation.media m ON t.media_id = m.id
            WHERE t.status = 'tags_generated'
        """)
        segments = cur.fetchall()

        for tid, mid, start_sec, end_sec, src in segments:
            midpoint = (start_sec + end_sec) / 2
            # Convert file:// URI if needed
            video = src.replace("file://", "")
            frame_file = f"outputs/frames/seg_{tid}.jpg"
            extract_frame(video, midpoint, frame_file)

            results = model(frame_file)[0]
            for box in results.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                name = model.names[cls_id]
                if conf < 0.3:
                    continue
                cur.execute(
                    """
                    INSERT INTO content_creation.content_tags
                      (transcript_id, tag_type, tag_value, score)
                    VALUES (%s, 'object', %s, %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (tid, name, conf)
                )
            # Mark status advanced if desired
            cur.execute(
                "UPDATE content_creation.transcripts SET status = 'objects_generated' WHERE id = %s;",
                (tid,)
            )

    conn.commit()
    conn.close()
    logging.info("Object tag generation completed.")

if __name__ == "__main__":
    generate_object_tags()