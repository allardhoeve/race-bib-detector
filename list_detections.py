#!/usr/bin/env python3
"""List all photos and their detected bib numbers."""

import argparse

import db


def main():
    parser = argparse.ArgumentParser(description="List photos and detected bibs")
    parser.add_argument("--cache", "-c", action="store_true",
                        help="Show cache file paths instead of URLs")
    parser.add_argument("--id", type=int, help="Show details for a specific photo ID")
    args = parser.parse_args()

    if not db.DB_PATH.exists():
        print("Database not found. Run scan_album.py first.")
        return

    conn = db.get_connection()
    cursor = conn.cursor()

    # Show single photo details
    if args.id:
        cursor.execute("""
            SELECT p.id, p.photo_url, p.cache_path,
                   GROUP_CONCAT(bd.bib_number || ' (' || ROUND(bd.confidence, 2) || ')', ', ') as bibs
            FROM photos p
            LEFT JOIN bib_detections bd ON p.id = bd.photo_id
            WHERE p.id = ?
            GROUP BY p.id
        """, (args.id,))
        row = cursor.fetchone()
        if row:
            photo_id, photo_url, cache_path, bibs = row
            print(f"Photo ID:    {photo_id}")
            print(f"Bibs:        {bibs or '(none)'}")
            print(f"Cache:       {cache_path or '(not cached)'}")
            print(f"URL:         {photo_url}")
        else:
            print(f"Photo ID {args.id} not found.")
        conn.close()
        return

    # Get all photos with their detected bibs
    cursor.execute("""
        SELECT
            p.id,
            p.photo_url,
            p.cache_path,
            GROUP_CONCAT(bd.bib_number || ' (' || ROUND(bd.confidence, 2) || ')', ', ') as bibs
        FROM photos p
        LEFT JOIN bib_detections bd ON p.id = bd.photo_id
        GROUP BY p.id
        ORDER BY p.id
    """)

    rows = cursor.fetchall()

    if not rows:
        print("No photos in database.")
        return

    if args.cache:
        print(f"{'ID':<6} {'Bibs Detected':<40} {'Cache Path'}")
        print("-" * 90)
        for photo_id, photo_url, cache_path, bibs in rows:
            bibs_str = bibs if bibs else "(none)"
            cache_display = cache_path if cache_path else "(not cached)"
            print(f"{photo_id:<6} {bibs_str:<40} {cache_display}")
    else:
        print(f"{'ID':<6} {'Bibs Detected':<40} {'Photo URL'}")
        print("-" * 100)
        for photo_id, photo_url, cache_path, bibs in rows:
            bibs_str = bibs if bibs else "(none)"
            print(f"{photo_id:<6} {bibs_str:<40} {photo_url}")

    # Summary stats
    cursor.execute("SELECT COUNT(*) FROM photos")
    total_photos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM bib_detections")
    total_detections = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT bib_number) FROM bib_detections")
    unique_bibs = cursor.fetchone()[0]

    print("-" * 100)
    print(f"Total: {total_photos} photos, {total_detections} detections, {unique_bibs} unique bibs")

    conn.close()


if __name__ == "__main__":
    main()
