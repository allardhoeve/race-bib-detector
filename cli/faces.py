"""Face clustering CLI commands."""

from __future__ import annotations

import argparse
import logging

import db
from faces.clustering import cluster_album_faces

logger = logging.getLogger(__name__)


def add_faces_subparser(subparsers: argparse._SubParsersAction) -> None:
    faces_parser = subparsers.add_parser(
        "faces",
        help="Face clustering utilities",
    )
    faces_subparsers = faces_parser.add_subparsers(
        dest="faces_command",
        help="Faces command",
    )

    cluster_parser = faces_subparsers.add_parser(
        "cluster",
        help="Cluster face embeddings for an album",
    )
    cluster_group = cluster_parser.add_mutually_exclusive_group(required=True)
    cluster_group.add_argument(
        "--album",
        dest="album_id",
        help="Album ID to cluster",
    )
    cluster_group.add_argument(
        "--all",
        action="store_true",
        help="Cluster faces for all albums",
    )
    cluster_parser.set_defaults(_cmd=cmd_faces_cluster)

    faces_parser.set_defaults(_faces_parser=faces_parser)


def _log_cluster_stats(stats: dict) -> None:
    logger.info(
        "Clustered album %s: %s clusters, %s members, %s faces, %s models",
        stats["album_id"],
        stats["clusters_created"],
        stats["members_created"],
        stats["faces_seen"],
        stats["models"],
    )


def cmd_faces_cluster(args: argparse.Namespace) -> int:
    conn = db.get_connection()
    try:
        if args.all:
            albums = db.list_albums(conn)
            if not albums:
                logger.info("No albums found.")
                return 0
            for album in albums:
                stats = cluster_album_faces(conn, album["album_id"])
                _log_cluster_stats(stats)
        else:
            stats = cluster_album_faces(conn, args.album_id)
            _log_cluster_stats(stats)
    finally:
        conn.close()
    return 0
