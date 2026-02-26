"""Identity management routes."""

from flask import Blueprint, jsonify, request

from benchmarking.services.identity_service import (
    list_identities,
    create_identity,
    rename_identity_across_gt,
)

identities_bp = Blueprint('identities', __name__)


@identities_bp.route('/api/identities')
def get_identities():
    return jsonify({'identities': list_identities()})


@identities_bp.route('/api/identities', methods=['POST'])
def post_identity():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Missing name'}), 400
    ids = create_identity(name)
    return jsonify({'identities': ids})


@identities_bp.route('/api/rename_identity', methods=['POST'])
def rename_identity_legacy():
    """Legacy rename endpoint — gone. Use PATCH /api/identities/<name>."""
    return jsonify({'error': 'Use PATCH /api/identities/<name>'}), 410


@identities_bp.route('/api/identities/<name>', methods=['PATCH'])
def patch_identity(name):
    """Rename an identity across all face GT entries and the identities list."""
    data = request.get_json() or {}
    new_name = (data.get('new_name') or '').strip()

    if not new_name:
        return jsonify({'error': 'Missing new_name'}), 400

    try:
        updated_count, ids = rename_identity_across_gt(name, new_name)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'updated_count': updated_count, 'identities': ids})
