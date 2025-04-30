#!/usr/bin/env python
"""
scripts/generate_objects.py

Detect objects in video frames for each transcript segment and
add object tags to content_tags.
"""

import os
import cv2
import logging
import subprocess
from pathlib import Path
from ultralytics import YOLO
from config import config
from scripts.db_utils import get_db_connection

logging.basicConfig(level=logging.INFO)

MODEL_NAME = "yolov8n.pt"  # or your chosen YOLOv8 model

def extract_frame(video_path, time_sec, output_path):
    """Use ffmpeg to grab a single frame at time_sec."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", str(time_sec),
        "-i", video_path, "-vframes", "1", output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def generate_object_tags():
    model = YOLO(MODEL_NAME)
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Fetch transcript segments needing object tags
        cur.execute("""
            SELECT t.id, t.media_id, t.start_sec, t.end_sec, m.source_uri
            FROM content_creation.transcripts t
            JOIN content_creation.media m ON t.media_id = m.id
            WHERE t.status = 'tags_generated';  -- or introduce a new status
        """)
        segments = cur.fetchall()

        for seg in segments:
            tid, mid, start_sec, end_sec, uri = seg
            mid_pt = (start_sec + end_sec) / 2
            video_path = uri.replace("file://", "")  # adapt if needed

            frame_file = f"outputs/frames/seg_{tid}.jpg"
            extract_frame(video_path, mid_pt, frame_file)

            # Run YOLO on that frame
            results = model(frame_file)[0]
            for det in results.boxes.data.tolist():
                cls_id, x1, y1, x2, y2, conf = det
                obj_name = model.names[int(cls_id)]
                if conf < 0.3:
                    continue
                # Insert object tag
                cur.execute("""
                    INSERT INTO content_creation.content_tags
                      (transcript_id, tag_type, tag_value, score)
                    VALUES (%s, 'object', %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (tid, obj_name, float(conf)))

            # Optionally update status
            cur.execute("""
                UPDATE content_creation.transcripts
                SET status = 'objects_generated'
                WHERE id = %s;
            """, (tid,))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    generate_object_tags()
    print("Object tag generation completed.")