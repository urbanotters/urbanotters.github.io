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

import yaml
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


def _trigger_jekyll_rebuild() -> None:
    """Touch index.html to trigger Jekyll auto-regeneration."""
    index_file = os.path.join(BLOG_ROOT, 'index.html')
    if os.path.isfile(index_file):
        os.utime(index_file, None)


def _is_jekyll_running() -> bool:
    """Check if Jekyll is already serving on port 4000."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        sock.connect(('127.0.0.1', 4000))
        sock.close()
        return True
    except (socket.error, OSError):
        return False


JEKYLL_LOG = os.path.join(SCRIPT_DIR, 'jekyll.log')
_jekyll_proc = None  # type: Optional[subprocess.Popen]


def _ruby_env() -> Dict[str, str]:
    """Build env dict with rbenv/user Ruby on PATH (subprocess inherits
    system PATH which may lack rbenv shims)."""
    env = os.environ.copy()
    home = os.path.expanduser('~')
    rbenv_shims = os.path.join(home, '.rbenv', 'shims')
    if os.path.isdir(rbenv_shims):
        env['PATH'] = rbenv_shims + ':' + env.get('PATH', '')
    return env


def _start_jekyll() -> bool:
    """Start Jekyll serve in background if not already running.
    Returns True if started, False if already running."""
    global _jekyll_proc
    if _is_jekyll_running():
        return False
    log_fh = open(JEKYLL_LOG, 'w', encoding='utf-8')
    _jekyll_proc = subprocess.Popen(
        ['bundle', 'exec', 'jekyll', 'serve', '--port', '4000', '--livereload'],
        cwd=BLOG_ROOT,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=_ruby_env(),
    )
    return True


def _jekyll_log_tail(lines: int = 30) -> str:
    """Return last N lines of Jekyll log."""
    if not os.path.isfile(JEKYLL_LOG):
        return ''
    with open(JEKYLL_LOG, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    return ''.join(all_lines[-lines:])


def _restart_jekyll() -> None:
    """Kill and restart Jekyll serve (needed after _config.yml changes)."""
    import signal
    # Find jekyll process
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'jekyll serve'],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in result.stdout.strip().splitlines():
            pid = int(pid_str)
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    # Wait briefly for old process to die
    import time
    time.sleep(2)

    # Start fresh
    _start_jekyll()

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

    # Push current branch to origin/main (deploy target)
    _, branch_out, _ = git_run(['branch', '--show-current'])
    local_branch = branch_out.strip() or 'main'
    code, push_out, push_err = git_run(['push', 'origin', f'{local_branch}:main'])

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

@app.route('/preview')
def preview():
    return render_template('preview.html')

@app.route('/pages')
def pages():
    return render_template('pages.html')

# ---------------------------------------------------------------------------
# API — site pages (Home profile, CV, Publications)
# ---------------------------------------------------------------------------

PROFILE_LAYOUT = os.path.join(BLOG_ROOT, '_layouts', 'profile.html')
PROFILE_EN_LAYOUT = os.path.join(BLOG_ROOT, '_layouts', 'profile-en.html')
CV_TAB = os.path.join(BLOG_ROOT, '_tabs', 'cv.md')
# CV_EN_TAB removed — merged into CV_TAB with EN/KR tabs
PUBLICATIONS_TAB = os.path.join(BLOG_ROOT, '_tabs', 'publications.md')
CONTACT_TAB = os.path.join(BLOG_ROOT, '_tabs', 'contact.md')


def _parse_profile(filepath: str = PROFILE_LAYOUT) -> dict:
    """Parse a profile layout into editable fields."""
    content = open(filepath, 'r', encoding='utf-8').read()

    def _extract(pattern: str, default: str = '') -> str:
        m = re.search(pattern, content, re.DOTALL)
        return m.group(1).strip() if m else default

    # name_primary is the main name shown in <h1>, name_secondary in <span>
    name_primary = _extract(r'<h1[^>]*>([^<]+)<span')
    name_secondary = _extract(r'class="profile-name-en"[^>]*>/\s*(.+?)</span>')
    affiliation = _extract(r'class="profile-affiliation[^"]*"[^>]*>(.+?)</p>')
    bio_raw = _extract(r'class="profile-bio[^"]*"[^>]*>\s*(.+?)\s*</p>')
    bio = re.sub(r'\s*<br>\s*', '\n', bio_raw)
    keywords = _extract(r'class="profile-keywords"[^>]*>\s*(.+?)\s*</p>')
    cv_pdf = _extract(r'href="([^"]+)"[^>]*title="CV \(PDF\)"')

    # Parse thesis
    thesis = _extract(r'<!-- Thesis -->.*?<p[^>]*>\s*(.+?)\s*</p>')

    # Parse links
    links = {}
    link_map = {
        'linkedin': r'href="(https://www\.linkedin\.com/[^"]*)"',
        'github': r'href="(https://github\.com/[^"]*)"',
        'twitter': r'href="(https://(?:twitter|x)\.com/[^"]*)"',
        'email': r'href="mailto:([^"]*)"',
    }
    for key, pat in link_map.items():
        m = re.search(pat, content)
        if m:
            links[key] = m.group(1)

    # Parse recent publications
    pubs = []
    for m in re.finditer(r'<li><a href="([^"]+)">(.+?)</a>\s*<span[^>]*>(.+?)</span></li>', content):
        pubs.append({'url': m.group(1), 'title': m.group(2), 'source': m.group(3)})

    return {
        'name_primary': name_primary,
        'name_secondary': name_secondary,
        'affiliation': affiliation,
        'bio': bio,
        'keywords': keywords,
        'thesis': thesis,
        'cv_pdf': cv_pdf,
        'links': links,
        'recent_publications': pubs,
    }


def _save_profile(data: dict, lang: str = 'ko') -> None:
    """Rebuild profile layout from data. lang='ko' or 'en'."""
    pubs_html = ''
    for p in data.get('recent_publications', []):
        if p.get('url') and p.get('title'):
            pubs_html += '      <li><a href="{url}">{title}</a> <span class="text-muted">{source}</span></li>\n'.format(**p)

    if lang == 'ko':
        lang_switch = ('  <!-- Language switch -->\n'
                       '  <div class="lang-switch">\n'
                       '    <a href="/" class="lang-inactive">EN</a>\n'
                       '    <span class="lang-active">KR</span>\n'
                       '  </div>\n\n')
        heading = '{name_primary} <span class="profile-name-en">/ {name_secondary}</span>'
        filepath = PROFILE_LAYOUT
    else:
        lang_switch = ('  <!-- Language switch -->\n'
                       '  <div class="lang-switch">\n'
                       '    <span class="lang-active">EN</span>\n'
                       '    <a href="/ko/" class="lang-inactive">KR</a>\n'
                       '  </div>\n\n')
        heading = '{name_primary} <span class="profile-name-en">/ {name_secondary}</span>'
        filepath = PROFILE_EN_LAYOUT

    html = '''---
layout: default
---

{{% include lang.html %}}

<article class="px-1">
{lang_switch}  <!-- Header -->
  <div class="profile-header mb-4">
    <h1 class="mt-0 mb-1">{heading}</h1>
    <p class="profile-affiliation mb-1">{affiliation}</p>
    <p class="profile-bio text-muted">
      {bio}
    </p>
  </div>

  <!-- Research Interests -->
  <div class="profile-section">
    <h2 class="profile-section-title">Research Interests</h2>
    <p class="profile-keywords">
      {keywords}
    </p>
  </div>

  <!-- Thesis -->
  <div class="profile-section">
    <h2 class="profile-section-title">Thesis</h2>
    <p class="text-muted fst-italic">
      {thesis}
    </p>
  </div>

  <!-- Recent Publications -->
  <div class="profile-section">
    <h2 class="profile-section-title">Recent Publications</h2>
    <ul class="profile-list">
{pubs_html}    </ul>
    <a href="/publications/" class="profile-see-all">See all &rarr;</a>
  </div>

  <!-- Latest Posts -->
  <div class="profile-section">
    <h2 class="profile-section-title">Latest Posts</h2>
    <ul class="profile-list">
      {{% assign recent_posts = site.posts | where_exp: 'item', 'item.hidden != true' %}}
      {{% for post in recent_posts limit: 3 %}}
        <li>
          <a href="{{{{ post.url | relative_url }}}}">{{{{ post.title }}}}</a>
          <span class="text-muted">{{{{ post.date | date: "%Y.%m" }}}}</span>
        </li>
      {{% endfor %}}
    </ul>
    <a href="/blog/" class="profile-see-all">See all &rarr;</a>
  </div>
</article>
'''.format(
        lang_switch=lang_switch,
        heading=heading.format(
            name_primary=data.get('name_primary', ''),
            name_secondary=data.get('name_secondary', ''),
        ),
        affiliation=data.get('affiliation', ''),
        bio=data.get('bio', '').replace('\n', '<br>\n      '),
        keywords=data.get('keywords', ''),
        thesis=data.get('thesis', ''),
        pubs_html=pubs_html,
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)


@app.route('/api/pages/profile', methods=['GET'])
def api_get_profile():
    return jsonify(_parse_profile(PROFILE_LAYOUT))


@app.route('/api/pages/profile', methods=['PUT'])
def api_save_profile():
    data = request.get_json(force=True)
    _save_profile(data, lang='ko')
    _trigger_jekyll_rebuild()
    return jsonify({'status': 'saved'})


@app.route('/api/pages/profile-en', methods=['GET'])
def api_get_profile_en():
    return jsonify(_parse_profile(PROFILE_EN_LAYOUT))


@app.route('/api/pages/profile-en', methods=['PUT'])
def api_save_profile_en():
    data = request.get_json(force=True)
    _save_profile(data, lang='en')
    _trigger_jekyll_rebuild()
    return jsonify({'status': 'saved'})


def _parse_cv_tab() -> dict:
    """Parse cv.md and return both EN and KR PDF paths."""
    content = open(CV_TAB, 'r', encoding='utf-8').read()
    # EN PDF is in div#cv-en, KR is in div#cv-kr
    en_m = re.search(r'id="cv-en".*?src="([^"]+)"', content, re.DOTALL)
    kr_m = re.search(r'id="cv-kr".*?src="([^"]+)"', content, re.DOTALL)
    result = {}
    for key, m in [('en', en_m), ('kr', kr_m)]:
        pdf_path = m.group(1) if m else ''
        abs_pdf = os.path.join(BLOG_ROOT, pdf_path.lstrip('/')) if pdf_path else ''
        exists = os.path.isfile(abs_pdf) if abs_pdf else False
        size = os.path.getsize(abs_pdf) if exists else 0
        result[key] = {'pdf_path': pdf_path, 'exists': exists, 'size': size}
    return result


def _save_cv_tab(en_path: str, kr_path: str) -> None:
    """Rewrite cv.md with EN/KR lang-switch tab layout."""
    cv_content = '''---
title: CV
icon: fas fa-file-alt
order: 1
---

<div class="lang-switch">
  <span class="lang-active" id="lang-en" onclick="switchCV('en')">EN</span>
  <span class="lang-inactive" id="lang-kr" onclick="switchCV('kr')">KR</span>
</div>

<div id="cv-en">
  <div class="cv-embed">
    <iframe src="{en_path}" title="CV (EN)"></iframe>
  </div>
  <p class="text-center mt-3">
    <a href="{en_path}" class="btn btn-outline-primary btn-sm" download>
      <i class="fas fa-download me-1"></i>Download PDF
    </a>
  </p>
</div>

<div id="cv-kr" style="display:none">
  <div class="cv-embed">
    <iframe src="{kr_path}" title="CV (KR)"></iframe>
  </div>
  <p class="text-center mt-3">
    <a href="{kr_path}" class="btn btn-outline-primary btn-sm" download>
      <i class="fas fa-download me-1"></i>Download PDF
    </a>
  </p>
</div>

<script>
function switchCV(lang) {{
  var enDiv = document.getElementById('cv-en');
  var krDiv = document.getElementById('cv-kr');
  var enBtn = document.getElementById('lang-en');
  var krBtn = document.getElementById('lang-kr');
  if (lang === 'kr') {{
    enDiv.style.display = 'none';
    krDiv.style.display = 'block';
    enBtn.className = 'lang-inactive';
    krBtn.className = 'lang-active';
  }} else {{
    enDiv.style.display = 'block';
    krDiv.style.display = 'none';
    enBtn.className = 'lang-active';
    krBtn.className = 'lang-inactive';
  }}
}}
</script>
'''.format(en_path=en_path, kr_path=kr_path)

    with open(CV_TAB, 'w', encoding='utf-8') as f:
        f.write(cv_content)


@app.route('/api/pages/cv', methods=['GET'])
def api_get_cv():
    """Return both EN and KR CV PDF info."""
    return jsonify(_parse_cv_tab())


@app.route('/api/pages/cv/upload', methods=['POST'])
def api_upload_cv():
    """Upload a CV PDF for a specific lang (en or kr)."""
    lang = request.args.get('lang', 'en')
    if lang not in ('en', 'kr'):
        abort(400, 'lang must be en or kr')

    if 'file' not in request.files:
        abort(400, 'No file provided')
    file = request.files['file']
    if not file.filename or _ext(file.filename) != 'pdf':
        abort(400, 'Only PDF files allowed')

    safe_name = secure_filename(file.filename)
    if not safe_name:
        safe_name = 'resume.pdf'

    dest_dir = os.path.join(ASSETS_DIR, 'docs')
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, safe_name)
    file.save(dest)

    rel_path = '/' + os.path.relpath(dest, BLOG_ROOT)

    # Read current paths, update the changed lang
    current = _parse_cv_tab()
    en_path = rel_path if lang == 'en' else current['en']['pdf_path']
    kr_path = rel_path if lang == 'kr' else current['kr']['pdf_path']
    _save_cv_tab(en_path, kr_path)

    _trigger_jekyll_rebuild()
    return jsonify({'status': 'uploaded', 'path': rel_path, 'filename': safe_name})


@app.route('/api/pages/publications', methods=['GET'])
def api_get_publications():
    """Return publications.md body (markdown after front matter)."""
    post = frontmatter.load(PUBLICATIONS_TAB)
    return jsonify({'body': post.content, 'title': post.metadata.get('title', 'Publications')})


@app.route('/api/pages/publications', methods=['PUT'])
def api_save_publications():
    """Save publications.md body."""
    data = request.get_json(force=True)
    post = frontmatter.load(PUBLICATIONS_TAB)
    post.content = data.get('body', '')
    with open(PUBLICATIONS_TAB, 'w', encoding='utf-8') as f:
        f.write(frontmatter.dumps(post) + '\n')
    _trigger_jekyll_rebuild()
    return jsonify({'status': 'saved'})


# ---------------------------------------------------------------------------
# API — contact page (_tabs/contact.md)
# ---------------------------------------------------------------------------

@app.route('/api/pages/contact', methods=['GET'])
def api_get_contact():
    """Return contact.md body (markdown after front matter)."""
    post = frontmatter.load(CONTACT_TAB)
    return jsonify({'body': post.content, 'title': post.metadata.get('title', 'Contact')})


@app.route('/api/pages/contact', methods=['PUT'])
def api_save_contact():
    """Save contact.md body."""
    data = request.get_json(force=True)
    post = frontmatter.load(CONTACT_TAB)
    post.content = data.get('body', '')
    with open(CONTACT_TAB, 'w', encoding='utf-8') as f:
        f.write(frontmatter.dumps(post) + '\n')
    _trigger_jekyll_rebuild()
    return jsonify({'status': 'saved'})


# ---------------------------------------------------------------------------
# API — sidebar (_config.yml + _data/contact.yml)
# ---------------------------------------------------------------------------

CONFIG_YML = os.path.join(BLOG_ROOT, '_config.yml')
CONTACT_YML = os.path.join(BLOG_ROOT, '_data', 'contact.yml')


@app.route('/api/pages/sidebar', methods=['GET'])
def api_get_sidebar():
    """Read sidebar-related fields from _config.yml and _data/contact.yml."""
    with open(CONFIG_YML, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    contact_raw = ''
    if os.path.isfile(CONTACT_YML):
        with open(CONTACT_YML, 'r', encoding='utf-8') as f:
            contact_raw = f.read()

    return jsonify({
        'title': cfg.get('title', ''),
        'tagline': cfg.get('tagline', ''),
        'avatar': cfg.get('avatar', ''),
        'social_name': (cfg.get('social') or {}).get('name', ''),
        'social_email': (cfg.get('social') or {}).get('email', ''),
        'github_username': (cfg.get('github') or {}).get('username', ''),
        'twitter_username': (cfg.get('twitter') or {}).get('username', ''),
        'contact_yml': contact_raw,
    })


@app.route('/api/pages/sidebar', methods=['PUT'])
def api_save_sidebar():
    """Update sidebar fields in _config.yml and overwrite _data/contact.yml."""
    data = request.get_json(force=True)

    # ── Update _config.yml via line-level replacements ──
    with open(CONFIG_YML, 'r', encoding='utf-8') as f:
        lines = f.read()

    replacements = [
        (r'^(title:\s*).*$', r'\g<1>' + data.get('title', '')),
        (r'^(avatar:\s*).*$', r'\g<1>' + data.get('avatar', '')),
    ]
    for pat, repl in replacements:
        lines = re.sub(pat, repl, lines, count=1, flags=re.MULTILINE)

    # Tagline: replace as YAML |- block to support newlines
    tagline = data.get('tagline', '')
    tagline_lines = tagline.strip().split('\n')
    if len(tagline_lines) > 1:
        tagline_yaml = 'tagline: |-\n' + '\n'.join('  ' + l for l in tagline_lines)
    else:
        tagline_yaml = 'tagline: ' + tagline_lines[0]
    # Remove existing tagline (may be multi-line |- block)
    lines = re.sub(
        r'^tagline:.*?(?=\n\S|\Z)',
        tagline_yaml,
        lines, count=1, flags=re.MULTILINE | re.DOTALL,
    )

    # github.username
    lines = re.sub(
        r'^(\s*username:\s*).*?(#.*change to your github.*)$',
        r'\g<1>' + data.get('github_username', '') + r' \2',
        lines, count=1, flags=re.MULTILINE,
    )
    # twitter.username
    lines = re.sub(
        r'^(\s*username:\s*).*?(#.*change to your twitter.*)$',
        r'\g<1>' + data.get('twitter_username', '') + r' \2',
        lines, count=1, flags=re.MULTILINE,
    )
    # social.name
    lines = re.sub(
        r'^(\s*name:\s*).*?(#.*|$)',
        r'\g<1>' + data.get('social_name', '') + r' \2',
        lines, count=1, flags=re.MULTILINE,
    )
    # social.email
    lines = re.sub(
        r'^(\s*email:\s*).*?(#.*change to your email.*)$',
        r'\g<1>' + data.get('social_email', '') + r' \2',
        lines, count=1, flags=re.MULTILINE,
    )

    with open(CONFIG_YML, 'w', encoding='utf-8') as f:
        f.write(lines)

    # ── Overwrite _data/contact.yml ──
    contact_yml = data.get('contact_yml', '')
    if contact_yml is not None:
        os.makedirs(os.path.dirname(CONTACT_YML), exist_ok=True)
        with open(CONTACT_YML, 'w', encoding='utf-8') as f:
            f.write(contact_yml)

    _restart_jekyll()
    return jsonify({'status': 'saved'})


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
    # push_failed still returns 200 — the commit succeeded, only push failed
    status_code = 200 if result['status'] in ('success', 'nothing', 'push_failed') else 500
    return jsonify(result), status_code

# ---------------------------------------------------------------------------
# API — Jekyll server
# ---------------------------------------------------------------------------

@app.route('/api/jekyll/status', methods=['GET'])
def api_jekyll_status():
    global _jekyll_proc
    running = _is_jekyll_running()
    crashed = False
    if _jekyll_proc is not None and _jekyll_proc.poll() is not None and not running:
        crashed = True
    return jsonify({
        'running': running,
        'crashed': crashed,
        'log': _jekyll_log_tail(20),
    })


@app.route('/api/jekyll/start', methods=['POST'])
def api_jekyll_start():
    if _is_jekyll_running():
        return jsonify({'status': 'already_running'})
    _start_jekyll()
    return jsonify({'status': 'starting'})


@app.route('/api/jekyll/restart', methods=['POST'])
def api_jekyll_restart():
    _restart_jekyll()
    return jsonify({'status': 'restarting'})


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

    # Auto-start Jekyll (only in reloader child to avoid double-start)
    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if is_reloader or not app.debug:
        if _is_jekyll_running():
            print('Jekyll: already running on http://localhost:4000')
        else:
            print('Jekyll: starting on http://localhost:4000 ...')
            _start_jekyll()

    print(f'Blog root: {BLOG_ROOT}')
    print(f'Admin: http://127.0.0.1:5001')
    app.run(host='127.0.0.1', port=5001, debug=True)
