"""Local web workbench; credentials and pipeline execution stay on the server."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[1]
# The default dashboard uses the four original Aigawa observations. The
# fixed-camera Ukawa pair remains available in its saved output directory.
DEMO = ROOT / 'output/aigawa_effect_live_v8_20261126'
DEMO_PROGRESS = ROOT / 'output/aigawa_effect_live_v7_20261126'
MAX_FILE = 12 * 1024 * 1024
MAX_BODY = 100 * 1024 * 1024
MAX_PIXELS = 32_000_000
ACTIVE = {'queued', 'running'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def configured():
    return bool(os.environ.get('DEEPSEEK_API_KEY', '').strip())


class BodyLimitMiddleware:
    """Bound multipart requests before the parser, including chunked uploads."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode()
        if origin and (urlsplit(origin).netloc != headers.get(b'host', b'').decode()
                       or urlsplit(origin).scheme not in ('http', 'https')):
            return await JSONResponse({'detail': '不接受其他网站发起的请求。'}, 403)(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            total += len(chunk)
            if total > MAX_BODY:
                return await JSONResponse({'detail': '上传总大小不能超过 100 MB。'}, 413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body'):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)


class JobStore:
    def __init__(self, root, run_command):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_command = run_command
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='recognition')
        self.jobs = {}
        for path in self.root.glob('*/job.json'):
            try:
                job = read_json(path)
                if not re.fullmatch(r'[0-9a-f]{32}', job['id']) or job['id'] != path.parent.name:
                    continue
                if job['status'] in ACTIVE:
                    job.update(status='failed', error='服务曾中断，请点击重试。', updated_at=now())
                    write_json(path, job)
                self.jobs[job['id']] = job
            except (ValueError, KeyError, OSError):
                continue

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise HTTPException(404, '找不到这个识别任务。')
            return copy.deepcopy(self.jobs[job_id])

    def save(self, job_id, **fields):
        with self.lock:
            self.jobs[job_id].update(fields, updated_at=now())
            write_json(self.root / job_id / 'job.json', self.jobs[job_id])

    def capacity(self):
        if sum(j['status'] in ACTIVE for j in self.jobs.values()) >= 6:
            raise HTTPException(429, '待处理任务较多，请稍后再试。')

    def enqueue(self, job):
        with self.lock:
            self.capacity()
            self.jobs[job['id']] = job
            self.save(job['id'])
            self.executor.submit(self.run, job['id'])

    def retry(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job['status'] != 'failed':
                raise HTTPException(409, '只有失败的任务可以重试。')
            job.update(status='queued', completed=0, current_date=None, error=None, attempt=job['attempt'] + 1)
            self.enqueue(job)
            return self.get(job_id)

    def run(self, job_id):
        job = self.get(job_id)
        folder = self.root / job_id
        output = folder / f"run-{job['attempt']}"
        try:
            self.save(job_id, status='running')
            for index, dt in enumerate(job['dates']):
                self.save(job_id, current_date=dt)
                command = [sys.executable, str(ROOT / 'src/run_aigawa.py'),
                           '--new-image', str(folder / f'{index}.png'), '--date', dt,
                           '--context', str(folder / 'context.json'), '--out', str(output),
                           '--fixed-camera', '--skip-cv']
                result = self.run_command(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, text=True, timeout=900,
                                          env={**os.environ, 'MPLBACKEND': 'Agg', 'PYTHONUNBUFFERED': '1'})
                (folder / f"run-{job['attempt']}-{index}.log").write_text(result.stdout or '', encoding='utf-8')
                if result.returncode:
                    self.save(job_id, status='failed', error=f'{dt} 识别失败，请检查模型服务配置或稍后重试。')
                    return
                self.save(job_id, completed=index + 1)
            # Do not report success before a readable, complete result exists.
            state = read_json(output / 'history.json')
            if len(state.get('history', [])) != len(job['dates']):
                raise ValueError('incomplete history')
            self.save(job_id, status='succeeded', current_date=None, error=None)
        except subprocess.TimeoutExpired:
            self.save(job_id, status='failed', error='本期识别超过 15 分钟，请稍后重试。')
        except Exception:
            self.save(job_id, status='failed', error='识别未能完成，请检查本地存储和模型配置后重试。')


def present(state, photo_url, source):
    def construction_overview(h):
        overall = h.get('overall') or {}
        stages = h.get('stages') or []
        parts = []
        status_counts = {'done': 0, 'in_progress': 0, 'not_started': 0, 'unclear': 0}
        total_weight = 0.0
        known_weight = 0.0
        active_weight = 0.0
        status_factor = {'done': 100.0, 'in_progress': 50.0, 'not_started': 0.0, 'unclear': 25.0}
        for stage in stages:
            status = stage.get('status') or 'unclear'
            if status not in status_counts:
                status = 'unclear'
            status_counts[status] += 1
            weight = stage.get('weight')
            if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight >= 0:
                total_weight += weight
                if status in ('done', 'in_progress', 'not_started'):
                    known_weight += weight
                if status in ('done', 'in_progress'):
                    active_weight += weight
            estimate = stage.get('progress_estimate')
            estimate_value = estimate.get('percent') if isinstance(estimate, dict) else estimate
            display_value = estimate_value if isinstance(estimate_value, (int, float)) and not isinstance(estimate_value, bool) else status_factor.get(status, 25.0)
            parts.append({
                'id': stage.get('id'),
                'name': stage.get('name') or stage.get('id'),
                'weight': stage.get('weight'),
                'status': status,
                'evidence': stage.get('evidence') or '',
                'confidence': stage.get('confidence'),
                'progress_estimate': stage.get('progress_estimate'),
                'display_progress_pct': round(float(display_value), 1),
                'observed_date': stage.get('observed_date'),
                'source': stage.get('source'),
                'observation': stage.get('observation') if isinstance(stage.get('observation'), dict) else None,
            })
        progress = overall.get('project_progress_pct')
        coverage = overall.get('current_coverage_pct')
        # Always provide a comparable display estimate. Prefer accepted stage
        # percentages, then use the visible status score for stages without a
        # numeric estimate. This is a dashboard estimate, not measured quantity.
        weighted = 0.0
        weight_sum = 0.0
        status_factor = {'done': 100.0, 'in_progress': 50.0, 'not_started': 0.0, 'unclear': 25.0}
        for part in parts:
            weight = part.get('weight')
            estimate = part.get('progress_estimate')
            value = estimate.get('percent') if isinstance(estimate, dict) else estimate
            if isinstance(weight, (int, float)) and weight > 0:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    weighted += weight * value
                else:
                    weighted += weight * status_factor.get(part['status'], 25.0)
                weight_sum += weight
        display_progress = round(progress, 1) if isinstance(progress, (int, float)) else round(weighted / weight_sum, 1) if weight_sum else 0.0
        display_method = 'direct_stage_weighted' if progress is not None else 'status_fallback_weighted'
        status = 'estimated' if display_progress is not None else 'evidence_insufficient'
        if status_counts['in_progress'] and status_counts['unclear']:
            state = 'visible_work_in_progress_partial'
            state_label = '部分可见部位施工中，其余部位无法确认'
        elif status_counts['in_progress']:
            state = 'visible_work_in_progress'
            state_label = '可见部位正在施工'
        elif status_counts['done'] and status_counts['unclear']:
            state = 'visible_parts_complete_partial'
            state_label = '部分可见部位已完成，其余部位无法确认'
        elif status_counts['done']:
            state = 'visible_parts_complete'
            state_label = '可见部位已完成外观阶段'
        elif status_counts['not_started'] and not status_counts['unclear']:
            state = 'visible_work_not_started'
            state_label = '可见部位尚未开工'
        else:
            state = 'insufficient_observation'
            state_label = '当前照片无法判断施工状态'
        if total_weight:
            status_coverage = round(known_weight / total_weight * 100, 2)
            active_weight_pct = round(active_weight / total_weight * 100, 2)
        else:
            status_coverage = 0.0
            active_weight_pct = 0.0
        return {
            'overall': {
                'status': status,
                'construction_state': state,
                'construction_state_label': state_label,
                'status_counts': status_counts,
                'status_coverage_pct': status_coverage,
                'active_stage_weight_pct': active_weight_pct,
                'progress_pct': progress,
                'display_progress_pct': display_progress,
                'display_progress_method': display_method,
                'coverage_pct': coverage,
                'range_pct': overall.get('total_possible_range_pct'),
                'method': overall.get('display_progress_method') or overall.get('project_progress_method'),
                'basis': overall.get('project_progress_basis'),
            },
            'parts': parts,
        }

    history = []
    for i, h in enumerate(state['history']):
        fields = ('date', 'stages', 'overall', 'summary', 'temporal_changes', 'temporal_review',
                  'quality_review', 'risks', 'execution_mode', 'prompt_version')
        item = {k: h.get(k) for k in fields}
        item['current_image_number'] = min(i + 1, 3)
        if item['temporal_changes'] is None:
            item['temporal_changes'] = []
        if item['risks'] is None:
            item['risks'] = []
        item['construction_overview'] = construction_overview(h)
        item['image_url'] = photo_url(i)
        history.append(item)
    trend = []
    for item in history:
        overview = item.get('construction_overview', {}).get('overall', {})
        trend.append({'date': item.get('date'), 'progress_pct': overview.get('display_progress_pct'),
                      'coverage_pct': overview.get('status_coverage_pct')})
    return {'project_name': state.get('context', {}).get('project_name', '工程监测'),
            'context': state.get('context', {}), 'source': source, 'history': history,
            'trend': trend}


def create_app(storage_root=None, run_command=subprocess.run):
    store = JobStore(storage_root or ROOT / 'output/web_jobs', run_command)

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.executor.shutdown(wait=True)

    app = FastAPI(title='工程进度影像工作台', lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/status')
    def status():
        return {'model_configured': configured(), 'max_photos': 8, 'max_file_mb': 12}

    @app.get('/api/demo')
    def demo():
        if not (DEMO / 'history.json').exists():
            raise HTTPException(404, '实例尚未安装，请直接上传现场照片。')
        visual_state = read_json(DEMO / 'history.json')
        # The V8 run supplies the checked image boxes. The V7 run contains the
        # earlier live stage estimates for the same four original photographs.
        # Merge only the estimate fields so the image evidence remains V8.
        if (DEMO_PROGRESS / 'history.json').exists():
            progress_state = read_json(DEMO_PROGRESS / 'history.json')
            progress_by_date = {h.get('date'): h for h in progress_state.get('history', [])}
            for visual in visual_state.get('history', []):
                progress = progress_by_date.get(visual.get('date'))
                if not progress:
                    continue
                estimates = {s.get('id'): s.get('progress_estimate') for s in progress.get('stages', [])}
                for stage in visual.get('stages', []):
                    estimate = estimates.get(stage.get('id'))
                    if estimate is not None:
                        stage['progress_estimate'] = estimate
        result = present(visual_state, lambda i: f'/api/demo/photos/{i}', 'historical_replay')
        result['source_note'] = '安威川原始现场照片的历史模型分析。识别框来自证据筛选结果，部位百分比来自同一照片的分项估算。'
        return result

    @app.get('/api/demo/photos/{index}')
    def demo_photo(index: int):
        state = read_json(DEMO / 'history.json')
        if not 0 <= index < len(state['history']):
            raise HTTPException(404, '图片不存在。')
        path = (DEMO / state['history'][index]['image']).resolve()
        if not path.is_relative_to(DEMO.resolve()) or not path.is_file():
            raise HTTPException(404, '图片不存在。')
        return FileResponse(path)

    @app.get('/api/jobs')
    def jobs():
        with store.lock:
            return sorted(copy.deepcopy(list(store.jobs.values())), key=lambda x: x['created_at'], reverse=True)

    @app.post('/api/jobs', status_code=202)
    async def submit(request: Request):
        if not configured():
            raise HTTPException(503, '模型服务尚未配置。请在项目 .env 中配置 DEEPSEEK_API_KEY 后重启服务；实例可直接查看。')
        with store.lock:
            store.capacity()
        async with request.form(max_files=8, max_fields=8) as form:
            photos = form.getlist('photos')
            try:
                dates = json.loads(form.get('dates', '[]'))
                if not isinstance(dates, list) or len(photos) != len(dates) or not 2 <= len(photos) <= 8:
                    raise ValueError('请选择 2–8 张照片，并为每张填写日期。')
                if any(not isinstance(d, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d) for d in dates):
                    raise ValueError('照片日期须为 YYYY-MM-DD。')
                for dt in dates:
                    date.fromisoformat(dt)
                if len(set(dates)) != len(dates):
                    raise ValueError('每张照片的日期必须不同。')
            except (ValueError, TypeError) as exc:
                raise HTTPException(400, str(exc)) from exc
            name, dam_type = form.get('project_name', '我的工程'), form.get('dam_type', '未知坝型')
            if not isinstance(name, str) or not isinstance(dam_type, str) or not name.strip() or len(name) > 80 or len(dam_type) > 100:
                raise HTTPException(400, '请填写有效项目名称（最多 80 字）和坝型（最多 100 字）。')
            job_id = uuid4().hex
            staging = Path(tempfile.mkdtemp(prefix='.upload-', dir=store.root))
            try:
                checksums = set()
                for index, (dt, upload) in enumerate(sorted(zip(dates, photos), key=lambda pair: pair[0])):
                    if not hasattr(upload, 'read'):
                        raise HTTPException(400, '请选择图片文件。')
                    content = await upload.read(MAX_FILE + 1)
                    if len(content) > MAX_FILE:
                        raise HTTPException(413, '单张照片不能超过 12 MB。')
                    try:
                        with Image.open(io.BytesIO(content)) as source:
                            if source.format not in ('JPEG', 'PNG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                                raise ValueError('仅支持静态 JPG、PNG 和 WebP 照片。')
                            if source.width * source.height > MAX_PIXELS or min(source.size) < 64:
                                raise ValueError('图片边长须至少 64 像素，总像素不能超过 3200 万。')
                            source.load()
                            photo = ImageOps.exif_transpose(source).convert('RGB')
                            # Hash decoded pixels: duplicate files with different metadata also fail.
                            checksum = hashlib.sha256(str(photo.size).encode() + photo.tobytes()).hexdigest()
                            if checksum in checksums:
                                raise ValueError('检测到重复照片，请上传不同时间的图片。')
                            checksums.add(checksum)
                            photo.save(staging / f'{index}.png')
                    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else '图片损坏或格式不支持，请重新选择。') from exc
                context = {'project_name': name.strip(), 'dam_type': dam_type.strip() or '未知坝型',
                           'scope_note': '同一镜头不同时间照片。仅根据原图判断可见施工状态及同一区域变化。隐蔽工序不可推断，像素和面积变化不能换算为工程量。'}
                write_json(staging / 'context.json', context)
                job = {'id': job_id, 'project_name': name.strip(), 'dates': sorted(dates),
                       'status': 'queued', 'completed': 0, 'total': len(photos), 'current_date': None,
                       'created_at': now(), 'updated_at': now(), 'attempt': 1, 'error': None}
                with store.lock:
                    store.capacity()
                    staging.rename(store.root / job_id)
                    store.enqueue(job)
                return store.get(job_id)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    @app.get('/api/jobs/{job_id}')
    def get_job(job_id: str):
        return store.get(job_id)

    @app.post('/api/jobs/{job_id}/retry', status_code=202)
    def retry(job_id: str):
        if not configured():
            raise HTTPException(503, '请配置模型服务后重试。')
        return store.retry(job_id)

    @app.get('/api/jobs/{job_id}/photos/{index}')
    def job_photo(job_id: str, index: int):
        job = store.get(job_id)
        if not 0 <= index < job['total']:
            raise HTTPException(404, '图片不存在。')
        return FileResponse(store.root / job_id / f'{index}.png')

    @app.get('/api/jobs/{job_id}/result')
    def job_result(job_id: str):
        job = store.get(job_id)
        if job['status'] != 'succeeded':
            raise HTTPException(409, '任务尚未完成。')
        state = read_json(store.root / job_id / f"run-{job['attempt']}" / 'history.json')
        source = 'live' if all(h.get('execution_mode') == 'live' for h in state['history']) else 'offline_test'
        return present(state, lambda i: f'/api/jobs/{job_id}/photos/{i}', source)

    app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'web/index.html')

    return app
