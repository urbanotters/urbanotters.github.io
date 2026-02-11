"""
Jekyll Blog Admin Tool
Local-only management interface for Jekyll blog.
Runs on 127.0.0.1:5001 — do NOT change host without adding authentication.
"""

import os
import re
import glob
import json
import subprocess
from datetime import date, datetime
from typing import Optional, List, Tuple, Dict

import frontmatter
from flask import (
    Flask, render_template, request, jsonify, abort, send_from_directory
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BLOG_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
POSTS_DIR = os.path.join(BLOG_ROOT, '_posts')
DRAFTS_DIR = os.path.join(BLOG_ROOT, '_drafts')
ASSETS_DIR = os.path.join(BLOG_ROOT, 'assets')

ALLOWED_UPLOAD_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',
    'pdf', 'csv', 'xlsx', 'json', 'geojson', 'md', 'txt',
    'zip', 'hwp', 'hwpx', 'pptx', 'docx',
}

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

FRONT_MATTER_TEMPLATES = {
    'blank': {
        'label': '빈 템플릿',
        'title': '',
        'tags': [],
        'categories': [],
    },
    'main': {
        'label': 'Main',
        'title': '',
        'tags': ['post'],
        'categories': ['main'],
    },
    'pov': {
        'label': 'POV',
        'title': '',
        'tags': ['post'],
        'categories': ['POV'],
    },
    'data-analysis': {
        'label': '데이터 분석',
        'title': '데이터들 - ',
        'tags': ['post', 'data'],
        'categories': ['POV'],
    },
    'career': {
        'label': '커리어/일 이야기',
        'title': '일 이야기 - ',
        'tags': ['post', 'storytelling', 'career'],
        'categories': ['POV'],
    },
}

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static',
)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

# ---------------------------------------------------------------------------
# Helpers — path safety
# ---------------------------------------------------------------------------

def safe_path(requested: str, allowed_base: str) -> str:
    """Resolve *requested* under *allowed_base* and reject traversal."""
    abs_base = os.path.realpath(allowed_base)
    abs_target = os.path.realpath(os.path.join(allowed_base, requested))
    if not abs_target.startswith(abs_base + os.sep) and abs_target != abs_base:
        abort(403, 'Invalid path')
    return abs_target


def _ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

# ---------------------------------------------------------------------------
# Helpers — posts
# ---------------------------------------------------------------------------

def parse_post(filepath: str) -> dict:
    """Read a markdown file and return structured metadata + body."""
    post = frontmatter.load(filepath)
    filename = os.path.basename(filepath)

    # Extract date and slug from filename  (YYYY-MM-DD-slug.md)
    match = re.match(r'^(\d{4}-\d{2}-\d{2})-(.+)\.md$', filename)
    if match:
        file_date = match.group(1)
        slug = match.group(2)
    else:
        file_date = str(date.today())
        slug = os.path.splitext(filename)[0]

    is_draft = DRAFTS_DIR in os.path.realpath(filepath)

    # Build relative path from BLOG_ROOT
    rel = os.path.relpath(filepath, BLOG_ROOT)

    return {
        'path': rel,
        'filename': filename,
        'date': file_date,
        'slug': slug,
        'title': post.metadata.get('title', ''),
        'tags': post.metadata.get('tags', []) or [],
        'categories': post.metadata.get('categories', []) or [],
        'is_draft': is_draft,
        'body': post.content,
        'excerpt': post.content[:120].replace('\n', ' ').strip(),
    }


def list_posts() -> list:
    """Return all posts + drafts, newest first."""
    items = []

    for directory in (POSTS_DIR, DRAFTS_DIR):
        if not os.path.isdir(directory):
            continue
        for f in glob.glob(os.path.join(directory, '*.md')):
            try:
                items.append(parse_post(f))
            except Exception:
                continue

    items.sort(key=lambda p: p['date'], reverse=True)
    return items


def save_post(data: dict, original_path: Optional[str] = None) -> str:
    """Write a post to disk. Returns the relative path of the saved file.

    *data* must contain: title, date, slug, categories, tags, body, is_draft.
    If *original_path* is given (relative to BLOG_ROOT) the old file is removed
    when the destination differs.
    """
    # Validate slug
    slug = data.get('slug', '').strip()
    if not slug or not re.match(r'^[a-zA-Z0-9_-]+$', slug):
        abort(400, 'Invalid slug')

    # Determine target directory
    target_dir = DRAFTS_DIR if data.get('is_draft') else POSTS_DIR
    os.makedirs(target_dir, exist_ok=True)

    filename = f"{data['date']}-{slug}.md"
    dest = os.path.join(target_dir, filename)

    # Build front matter
    meta = {'title': data.get('title', '')}
    tags = data.get('tags', [])
    categories = data.get('categories', [])
    if tags:
        meta['tags'] = tags
    if categories:
        meta['categories'] = categories

    post = frontmatter.Post(data.get('body', ''), **meta)

    # Remove old file if path changed
    if original_path:
        old_abs = os.path.join(BLOG_ROOT, original_path)
        if os.path.realpath(old_abs) != os.path.realpath(dest) and os.path.exists(old_abs):
            os.remove(old_abs)

    with open(dest, 'w', encoding='utf-8') as f:
        f.write(frontmatter.dumps(post) + '\n')

    return os.path.relpath(dest, BLOG_ROOT)

# ---------------------------------------------------------------------------
# Helpers — assets
# ---------------------------------------------------------------------------

def get_asset_tree(base: str = ASSETS_DIR) -> dict:
    """Walk the assets directory and return a nested dict."""
    tree = {}
    for root, dirs, files in os.walk(base):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        rel_root = os.path.relpath(root, ASSETS_DIR)
        node = tree
        if rel_root != '.':
            for part in rel_root.split(os.sep):
                node = node.setdefault(part, {'_type': 'dir', '_children': {}})['_children']

        for fname in sorted(files):
            if fname.startswith('.'):
                continue
            fpath = os.path.join(root, fname)
            try:
                stat = os.stat(fpath)
                node[fname] = {
                    '_type': 'file',
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            except OSError:
                continue
    return tree


def find_asset_references(asset_rel_path: str) -> List[str]:
    """Grep posts/drafts for references to an asset path."""
    refs = []
    # Normalise for matching  (e.g. "assets/img/photo.png" or "/assets/img/photo.png")
    search_variants = [asset_rel_path, '/' + asset_rel_path]
    for directory in (POSTS_DIR, DRAFTS_DIR):
        if not os.path.isdir(directory):
            continue
        for f in glob.glob(os.path.join(directory, '*.md')):
            try:
                content = open(f, encoding='utf-8').read()
                if any(v in content for v in search_variants):
                    refs.append(os.path.relpath(f, BLOG_ROOT))
            except Exception:
                continue
    # Also check _tabs
    tabs_dir = os.path.join(BLOG_ROOT, '_tabs')
    if os.path.isdir(tabs_dir):
        for f in glob.glob(os.path.join(tabs_dir, '*.md')):
            try:
                content = open(f, encoding='utf-8').read()
                if any(v in content for v in search_variants):
                    refs.append(os.path.relpath(f, BLOG_ROOT))
            except Exception:
                continue
    return refs

# ---------------------------------------------------------------------------
# Helpers — git
# ---------------------------------------------------------------------------

def git_run(args: List[str]) -> Tuple[int, str, str]:
    """Run a git command in BLOG_ROOT."""
    result = subprocess.run(
        ['git'] + args,
        cwd=BLOG_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def git_status() -> dict:
    code, out, _ = git_run(['status', '--porcelain'])
    changes = []
    for line in out.strip().splitlines():
        if len(line) >= 4:
            status = line[:2].strip()
            filepath = line[3:]
            changes.append({'status': status, 'file': filepath})
    code2, branch_out, _ = git_run(['branch', '--show-current'])
    return {
        'clean': len(changes) == 0,
        'branch': branch_out.strip(),
        'changes': changes,
        'change_count': len(changes),
    }


def git_commit_and_push(message: Optional[str] = None) -> dict:
    """Stage all, commit, push. Returns result dict."""
    # Stage
    code, out, err = git_run(['add', '-A'])
    if code != 0:
        return {'status': 'error', 'detail': f'git add failed: {err}'}

    # Check for staged changes
    code, diff_out, _ = git_run(['diff', '--cached', '--name-only'])
    if not diff_out.strip():
        return {'status': 'nothing', 'detail': 'No changes to commit'}

    # Auto-generate message if not provided
    if not message:
        files = diff_out.strip().splitlines()
        parts = []
        for f in files[:5]:
            basename = os.path.basename(f)
            if f.startswith('_posts/'):
                parts.append(f'post: {basename}')
            elif f.startswith('_drafts/'):
                parts.append(f'draft: {basename}')
            elif f.startswith('assets/'):
                parts.append(f'asset: {basename}')
            else:
                parts.append(basename)
        if len(files) > 5:
            parts.append(f'...and {len(files) - 5} more')
        message = 'Update: ' + ', '.join(parts)

    # Commit
    code, out, err = git_run(['commit', '-m', message])
    if code != 0:
        return {'status': 'error', 'detail': f'git commit failed: {err}'}

    # Get commit hash
    _, hash_out, _ = git_run(['rev-parse', '--short', 'HEAD'])

    # Push
    _, branch_out, _ = git_run(['branch', '--show-current'])
    branch = branch_out.strip() or 'main'
    code, push_out, push_err = git_run(['push', 'origin', branch])

    return {
        'status': 'success' if code == 0 else 'push_failed',
        'commit_hash': hash_out.strip(),
        'message': message,
        'push_result': push_out.strip() or push_err.strip(),
    }

# ---------------------------------------------------------------------------
# Helpers — tags & categories discovery
# ---------------------------------------------------------------------------

def discover_tags_and_categories() -> Tuple[List[str], List[str]]:
    """Scan all posts to find used tags and categories."""
    tags_set = set()
    cats_set = set()
    for p in list_posts():
        tags_set.update(p['tags'])
        cats_set.update(p['categories'])
    return sorted(tags_set), sorted(cats_set)

# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/editor')
def editor_new():
    return render_template('editor.html', post_path='')


@app.route('/editor/<path:post_path>')
def editor_edit(post_path):
    return render_template('editor.html', post_path=post_path)


@app.route('/files')
def file_manager():
    return render_template('files.html')

# ---------------------------------------------------------------------------
# API — posts
# ---------------------------------------------------------------------------

@app.route('/api/posts', methods=['GET'])
def api_list_posts():
    return jsonify({'posts': list_posts()})


@app.route('/api/posts', methods=['POST'])
def api_create_post():
    data = request.get_json(force=True)
    if not data.get('date'):
        data['date'] = str(date.today())
    path = save_post(data)
    return jsonify({'path': path, 'status': 'created'}), 201


@app.route('/api/posts/<path:post_path>', methods=['GET'])
def api_get_post(post_path):
    abs_path = safe_path(post_path, BLOG_ROOT)
    if not os.path.isfile(abs_path):
        abort(404)
    return jsonify(parse_post(abs_path))


@app.route('/api/posts/<path:post_path>', methods=['PUT'])
def api_update_post(post_path):
    abs_path = safe_path(post_path, BLOG_ROOT)
    if not os.path.isfile(abs_path):
        abort(404)
    data = request.get_json(force=True)
    new_path = save_post(data, original_path=post_path)
    return jsonify({'path': new_path, 'status': 'updated'})


@app.route('/api/posts/<path:post_path>', methods=['DELETE'])
def api_delete_post(post_path):
    abs_path = safe_path(post_path, BLOG_ROOT)
    if not os.path.isfile(abs_path):
        abort(404)
    os.remove(abs_path)
    return jsonify({'status': 'deleted'})


@app.route('/api/posts/<path:post_path>/publish', methods=['POST'])
def api_publish_post(post_path):
    abs_path = safe_path(post_path, BLOG_ROOT)
    if not os.path.isfile(abs_path):
        abort(404)
    data = parse_post(abs_path)
    data['is_draft'] = False
    new_path = save_post(data, original_path=post_path)
    return jsonify({'path': new_path, 'status': 'published'})


@app.route('/api/posts/<path:post_path>/unpublish', methods=['POST'])
def api_unpublish_post(post_path):
    abs_path = safe_path(post_path, BLOG_ROOT)
    if not os.path.isfile(abs_path):
        abort(404)
    data = parse_post(abs_path)
    data['is_draft'] = True
    new_path = save_post(data, original_path=post_path)
    return jsonify({'path': new_path, 'status': 'unpublished'})

# ---------------------------------------------------------------------------
# API — templates, tags, categories
# ---------------------------------------------------------------------------

@app.route('/api/templates', methods=['GET'])
def api_templates():
    return jsonify({'templates': FRONT_MATTER_TEMPLATES})


@app.route('/api/tags', methods=['GET'])
def api_tags():
    tags, _ = discover_tags_and_categories()
    return jsonify({'tags': tags})


@app.route('/api/categories', methods=['GET'])
def api_categories():
    _, cats = discover_tags_and_categories()
    return jsonify({'categories': cats})

# ---------------------------------------------------------------------------
# API — assets
# ---------------------------------------------------------------------------

@app.route('/api/assets', methods=['GET'])
def api_assets():
    return jsonify({'tree': get_asset_tree()})


@app.route('/api/assets/upload', methods=['POST'])
def api_upload_asset():
    if 'file' not in request.files:
        abort(400, 'No file provided')
    file = request.files['file']
    if not file.filename:
        abort(400, 'Empty filename')

    ext = _ext(file.filename)
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        abort(400, f'File type .{ext} not allowed')

    # Route to subdirectory by extension
    if ext in IMAGE_EXTENSIONS:
        subdir = 'img'
    else:
        subdir = 'docs'

    # Allow custom subdirectory via query param
    custom_subdir = request.args.get('subdir')
    if custom_subdir:
        subdir = custom_subdir

    safe_name = secure_filename(file.filename)
    if not safe_name:
        safe_name = f'upload_{datetime.now().strftime("%Y%m%d%H%M%S")}.{ext}'

    dest_dir = safe_path(subdir, ASSETS_DIR)
    os.makedirs(dest_dir, exist_ok=True)

    dest = os.path.join(dest_dir, safe_name)
    # Handle collision
    if os.path.exists(dest):
        base, ext_part = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(dest_dir, f'{base}_{counter}{ext_part}')
            counter += 1

    file.save(dest)
    rel = os.path.relpath(dest, BLOG_ROOT)
    return jsonify({
        'path': rel,
        'filename': os.path.basename(dest),
        'url': '/' + rel,
    })


@app.route('/api/assets/<path:asset_path>', methods=['DELETE'])
def api_delete_asset(asset_path):
    abs_path = safe_path(asset_path, ASSETS_DIR)
    if not os.path.isfile(abs_path):
        abort(404)
    os.remove(abs_path)
    return jsonify({'status': 'deleted'})


@app.route('/api/assets/<path:asset_path>/usage', methods=['GET'])
def api_asset_usage(asset_path):
    rel = os.path.join('assets', asset_path)
    refs = find_asset_references(rel)
    return jsonify({'references': refs})

# ---------------------------------------------------------------------------
# API — git
# ---------------------------------------------------------------------------

@app.route('/api/git/status', methods=['GET'])
def api_git_status():
    return jsonify(git_status())


@app.route('/api/git/commit-push', methods=['POST'])
def api_git_commit_push():
    data = request.get_json(force=True) if request.is_json else {}
    message = data.get('message')
    result = git_commit_and_push(message)
    status_code = 200 if result['status'] in ('success', 'nothing') else 500
    return jsonify(result), status_code

# ---------------------------------------------------------------------------
# Serve uploaded assets for preview
# ---------------------------------------------------------------------------

@app.route('/assets/<path:filepath>')
def serve_asset(filepath):
    return send_from_directory(ASSETS_DIR, filepath)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Ensure _drafts exists
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    print(f'Blog root: {BLOG_ROOT}')
    print(f'Admin: http://127.0.0.1:5001')
    app.run(host='127.0.0.1', port=5001, debug=True)
