from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import threading
import traceback
import uuid
import zipfile
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from flow_bot.excel_mapper import SCENE_SCHEMA_KEYS, SCHEMA_KEYS, auto_map_headers, build_products, read_rows
from flow_bot.flow_runner import FlowBot
from flow_bot.models import RunConfig
from flow_bot.video_postprocess import overlay_logo_with_ffmpeg

from .schemas import LoginOpenRequest, LogoOverlayRequest, RunContinueRequest, RunRequest
from .state import RunRecord, UploadedDataset, app_state, now_iso
from .ui import render_home

app = FastAPI(title="Google Flow Bot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "bot-output" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOGO_UPLOAD_DIR = UPLOAD_DIR / "logos"
LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATASET_INDEX_PATH = UPLOAD_DIR / "datasets.json"
STORAGE_DIR = BASE_DIR / "bot-output" / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_FILE_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi"}

FLOW_URL = "https://labs.google/fx/vi/tools/flow/project/29290e6e-cefb-45dc-bb4a-7d536bf5b33f/tool/fd2e21f2-9304-4ec9-8026-866a0672264c"


def serialize_dataset(dataset: UploadedDataset) -> dict:
    return {
        "dataset_id": dataset.dataset_id,
        "original_name": dataset.original_name,
        "file_path": dataset.file_path.as_posix(),
        "created_at": dataset.created_at,
        "sheet_name": dataset.sheet_name,
        "mapping": dataset.mapping,
        "row_count": dataset.row_count,
        "preview": dataset.preview,
        "columns": dataset.columns,
        "raw_preview": dataset.raw_preview,
    }


def serialize_run(record: RunRecord) -> dict:
    return {
        "run_id": record.run_id,
        "dataset_id": record.dataset_id,
        "created_at": record.created_at,
        "status": record.status,
        "paused": record.paused,
        "pause_message": record.pause_message,
        "logs": record.logs,
        "options": record.options,
        "error": record.error,
    }


def build_dataset_metadata(
    dataset_id: str,
    file_path: Path,
    original_name: str,
    created_at: str | None = None,
) -> UploadedDataset:
    headers, raw_rows, sheet_name = read_rows(file_path)
    mapping = auto_map_headers(headers, raw_rows)
    mapping.sheet_name = sheet_name

    required_mapping = ("product_name", "short_description", "long_description")
    has_required_mapping = all(mapping.mapped_headers.get(key) for key in required_mapping)
    if has_required_mapping:
        products, mapping = build_products(file_path, sheet_name)
        row_count = len(products)
        preview = [
            {
                "product_name": item.product_name,
                "short_description": item.short_description[:120],
                "long_description": item.long_description[:120],
                "product_image": item.product_image,
            }
            for item in products[:5]
        ]
    else:
        row_count = len(raw_rows)
        header_index = {header: index for index, header in enumerate(headers)}
        preview = []
        for row in raw_rows[:5]:
            item: dict[str, str] = {}
            for schema_key in SCHEMA_KEYS:
                source_header = mapping.mapped_headers.get(schema_key)
                if source_header is None:
                    item[schema_key] = ""
                    continue
                index = header_index[source_header]
                item[schema_key] = str(row[index]).strip() if index < len(row) else ""
            item["short_description"] = item["short_description"][:120]
            item["long_description"] = item["long_description"][:120]
            preview.append(item)

    return UploadedDataset(
        dataset_id=dataset_id,
        file_path=file_path,
        original_name=original_name,
        created_at=created_at or now_iso(),
        sheet_name=mapping.sheet_name,
        mapping=mapping.mapped_headers,
        row_count=row_count,
        preview=preview,
        columns=headers,
        raw_preview=[
            {
                header: str(row[index]).strip() if index < len(row) else ""
                for index, header in enumerate(headers)
            }
            for row in raw_rows[:5]
        ],
    )


def save_dataset_index() -> None:
    with app_state.lock:
        payload = {"items": [serialize_dataset(item) for item in app_state.datasets.values()]}
    temp_path = DATASET_INDEX_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(DATASET_INDEX_PATH)


def load_dataset_index() -> None:
    if not DATASET_INDEX_PATH.exists():
        return
    try:
        payload = json.loads(DATASET_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return

    restored: dict[str, UploadedDataset] = {}
    for item in payload.get("items", []):
        file_path = Path(item.get("file_path", ""))
        if not file_path.exists():
            continue
        dataset_id = item.get("dataset_id")
        if not dataset_id:
            continue
        restored[dataset_id] = UploadedDataset(
            dataset_id=dataset_id,
            file_path=file_path,
            original_name=item.get("original_name") or file_path.name,
            created_at=item.get("created_at") or now_iso(),
            sheet_name=item.get("sheet_name"),
            mapping=item.get("mapping") or {},
            row_count=item.get("row_count") or 0,
            preview=item.get("preview") or [],
            columns=item.get("columns") or [],
            raw_preview=item.get("raw_preview") or [],
        )

    with app_state.lock:
        app_state.datasets.update(restored)


def find_uploaded_dataset_file(dataset_id: str) -> Path | None:
    matches = sorted(
        UPLOAD_DIR.glob(f"{dataset_id}.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def get_dataset_or_restore(dataset_id: str) -> UploadedDataset | None:
    with app_state.lock:
        dataset = app_state.datasets.get(dataset_id)
    if dataset is not None:
        return dataset

    file_path = find_uploaded_dataset_file(dataset_id)
    if file_path is None:
        return None

    dataset = build_dataset_metadata(
        dataset_id=dataset_id,
        file_path=file_path,
        original_name=file_path.name,
        created_at=now_iso(),
    )
    with app_state.lock:
        app_state.datasets[dataset_id] = dataset
    save_dataset_index()
    return dataset


@app.on_event("startup")
def restore_uploaded_datasets() -> None:
    load_dataset_index()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return render_home(FLOW_URL)
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Google Flow Bot</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:Arial,sans-serif;background:#0f172a;color:#f1f5f9;font-size:14px}}
    .wrap{{max-width:980px;margin:0 auto;padding:24px;display:flex;flex-direction:column;gap:18px}}
    h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
    h2{{font-size:15px;font-weight:700;margin-bottom:10px;color:#94a3b8}}
    .card{{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:18px}}
    .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
    label{{display:block;font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:4px}}
    input,select{{width:100%;padding:9px 12px;border-radius:8px;border:1px solid #475569;
      background:#0f172a;color:#f1f5f9;font-size:13px;outline:none}}
    input:focus,select:focus{{border-color:#3b82f6}}
    .btn-row{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
    button{{padding:9px 16px;border-radius:8px;border:none;font-size:13px;font-weight:600;
      cursor:pointer;transition:opacity .15s}}
    button:hover{{opacity:.85}} button:disabled{{opacity:.4;cursor:default}}
    .btn-blue{{background:#2563eb;color:#fff}}
    .btn-green{{background:#16a34a;color:#fff}}
    .btn-gray{{background:#334155;color:#cbd5e1}}
    .log-box{{background:#020617;border:1px solid #1e3a5f;border-radius:10px;
      padding:12px;min-height:120px;max-height:340px;overflow-y:auto;
      font-family:monospace;font-size:12px;line-height:1.6;white-space:pre-wrap;
      word-break:break-all}}
    .log-INFO{{color:#7dd3fc}} .log-SUCCESS{{color:#86efac}} .log-WARNING{{color:#fde047}}
    .log-ERROR{{color:#fca5a5}} .log-default{{color:#94a3b8}}
    .badge{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700}}
    .badge-running{{background:#1d4ed8;color:#bfdbfe}}
    .badge-completed{{background:#166534;color:#bbf7d0}}
    .badge-failed{{background:#7f1d1d;color:#fecaca}}
    .badge-queued{{background:#374151;color:#d1d5db}}
    #status-bar{{padding:8px 12px;border-radius:8px;font-size:12px;font-weight:600;
      background:#0c1a2e;color:#7dd3fc;border:1px solid #1e3a5f;display:none}}
    .hint{{font-size:11px;color:#64748b;margin-top:6px;line-height:1.5}}
  </style>
</head>
<body>
<div class="wrap">
  <div>
    <h1>⚡ Google Flow Bot</h1>
    <div class="hint">
      Trước khi chạy, mở Chrome bằng lệnh CMD:&nbsp;
      <code style="color:#fde047;font-size:11px">
        chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\Users\\acer\\AppData\\Local\\Google\\Chrome\\User Data" --profile-directory="Profile 12" {FLOW_URL}
      </code>
    </div>
  </div>

  <div id="status-bar"></div>

  <!-- Upload -->
  <div class="card">
    <h2>1. Upload Excel / CSV</h2>
    <input type="file" id="file" accept=".xlsx,.xls,.csv"/>
    <div class="btn-row">
      <button class="btn-blue" onclick="uploadFile()">⬆ Upload File</button>
    </div>
    <div id="dataset-info" class="hint" style="margin-top:8px"></div>
  </div>

  <!-- Run -->
  <div class="card">
    <h2>2. Chạy Batch</h2>
    <div class="row">
      <div>
        <label>Dataset ID</label>
        <input id="dataset-id" placeholder="Tự điền sau khi upload"/>
      </div>
      <div>
        <label>CDP Port (Chrome đang chạy)</label>
        <input id="cdp-port" type="number" value="9222"/>
      </div>
    </div>
    <div class="row" style="margin-top:10px">
      <div>
        <label>Bắt đầu từ sản phẩm số</label>
        <input id="start" type="number" value="1" min="1"/>
      </div>
      <div>
        <label>Số lượng sản phẩm</label>
        <input id="count" type="number" value="1" min="1"/>
      </div>
    </div>
    <div class="row" style="margin-top:10px">
      <div>
        <label>Slow Mo (ms)</label>
        <input id="slow-mo" type="number" value="400" min="0"/>
      </div>
      <div>
        <label>Timeout video (giây)</label>
        <input id="wait-timeout" type="number" value="600" min="30"/>
      </div>
    </div>
    <div class="btn-row">
      <button class="btn-green" id="btn-run" onclick="startRun()">▶ Chạy Bot</button>
      <button class="btn-gray" onclick="stopStream()">⏹ Dừng stream</button>
    </div>
  </div>

  <!-- Real-time log -->
  <div class="card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
      <h2 style="margin:0">Log realtime &nbsp;<span id="run-status-badge"></span></h2>
      <button class="btn-gray" style="padding:4px 10px;font-size:11px" onclick="clearLog()">Xóa</button>
    </div>
    <div id="log-box" class="log-box">Chờ chạy batch...</div>
  </div>
</div>

<script>
  const FLOW_URL = "{FLOW_URL}";
  let evtSource = null;
  let currentRunId = null;

  function setStatus(msg, ok=true) {{
    const bar = document.getElementById('status-bar');
    bar.style.display = 'block';
    bar.style.color = ok ? '#86efac' : '#fca5a5';
    bar.style.borderColor = ok ? '#166534' : '#7f1d1d';
    bar.style.background = ok ? '#052e16' : '#1c0a0a';
    bar.textContent = msg;
  }}

  function clearLog() {{
    document.getElementById('log-box').innerHTML = '';
  }}

  function appendLog(time, level, message) {{
    const box = document.getElementById('log-box');
    const cls = ['INFO','SUCCESS','WARNING','ERROR'].includes(level) ? `log-${{level}}` : 'log-default';
    const line = document.createElement('div');
    line.className = cls;
    line.textContent = `[${{time}}] [${{level}}] ${{message}}`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
  }}

  function setBadge(status) {{
    const el = document.getElementById('run-status-badge');
    const map = {{running:'badge-running',completed:'badge-completed',failed:'badge-failed',queued:'badge-queued'}};
    el.className = 'badge ' + (map[status] || 'badge-queued');
    el.textContent = status.toUpperCase();
  }}

  function stopStream() {{
    if (evtSource) {{ evtSource.close(); evtSource = null; }}
  }}

  function startLogStream(runId) {{
    stopStream();
    currentRunId = runId;
    clearLog();
    evtSource = new EventSource(`/api/runs/${{runId}}/stream`);

    evtSource.addEventListener('log', e => {{
      const d = JSON.parse(e.data);
      appendLog(d.time, d.level, d.message);
    }});

    evtSource.addEventListener('status', e => {{
      const d = JSON.parse(e.data);
      setBadge(d.status);
      if (d.status === 'completed') {{
        setStatus('✓ Batch hoàn thành!');
        stopStream();
      }} else if (d.status === 'failed') {{
        setStatus('✗ Batch thất bại: ' + (d.error || ''), false);
        stopStream();
      }}
    }});

    evtSource.onerror = () => {{
      // SSE auto-reconnects; only close if run already done
      if (!currentRunId) evtSource.close();
    }};
  }}

  async function uploadFile() {{
    const input = document.getElementById('file');
    if (!input.files[0]) {{ setStatus('Chọn file trước!', false); return; }}
    setStatus('Đang upload...');
    const form = new FormData();
    form.append('file', input.files[0]);
    const resp = await fetch('/api/datasets/upload', {{method:'POST',body:form}});
    const data = await resp.json();
    if (data.dataset_id) {{
      document.getElementById('dataset-id').value = data.dataset_id;
      document.getElementById('dataset-info').textContent =
        `✓ ${{data.original_name}} — ${{data.row_count}} sản phẩm (ID: ${{data.dataset_id}})`;
      setStatus(`Upload thành công: ${{data.row_count}} sản phẩm`);
    }} else {{
      setStatus('Upload thất bại: ' + JSON.stringify(data), false);
    }}
  }}

  async function startRun() {{
    const dsId = document.getElementById('dataset-id').value.trim();
    if (!dsId) {{ setStatus('Nhập Dataset ID!', false); return; }}
    clearLog();
    setStatus('Đang khởi động bot...');
    document.getElementById('btn-run').disabled = true;

    const payload = {{
      dataset_id: dsId,
      start: Number(document.getElementById('start').value || 1),
      count: Number(document.getElementById('count').value || 1),
      slow_mo: Number(document.getElementById('slow-mo').value || 400),
      wait_timeout_seconds: Number(document.getElementById('wait-timeout').value || 600),
      cdp_port: Number(document.getElementById('cdp-port').value || 9222),
      user_data_dir: "cdp",
    }};

    const resp = await fetch('/api/runs', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(payload)
    }});
    const data = await resp.json();
    document.getElementById('btn-run').disabled = false;

    if (data.run_id) {{
      setBadge('queued');
      setStatus(`Run started: ${{data.run_id}}`);
      startLogStream(data.run_id);
    }} else {{
      setStatus('Lỗi: ' + JSON.stringify(data), false);
    }}
  }}
</script>
</body>
</html>"""


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/login/open")
def open_login(request: LoginOpenRequest) -> dict:
    with app_state.lock:
        if app_state.active_login_bot is not None:
            return {"ok": True, "message": "Login browser is already open."}

        config = RunConfig(
            file_path=Path("."),
            flow_url=request.flow_url,
            chrome_user_data_dir=Path(request.user_data_dir) if request.user_data_dir else None,
            chrome_profile_directory=request.profile_directory,
            cdp_port=request.cdp_port,
            headless=request.headless,
            slow_mo_ms=request.slow_mo,
        )
        bot = FlowBot(config)
        try:
            bot.start()
            bot.open_flow()
        except Exception as exc:
            traceback.print_exc()
            bot.close()
            message = str(exc)
            raise HTTPException(status_code=400, detail=message) from exc
        app_state.active_login_bot = bot
        return {"ok": True, "message": "Browser opened. Navigate to Flow, then call /api/login/save."}


@app.post("/api/login/save")
def save_login() -> dict:
    with app_state.lock:
        bot = app_state.active_login_bot
        if bot is None:
            raise HTTPException(status_code=404, detail="No active login browser.")
        if bot.config.chrome_user_data_dir:
            auth_path = bot.config.chrome_user_data_dir.as_posix()
            message = "Persistent profile mode is already using your Chrome profile."
        else:
            assert bot.context is not None
            bot.context.storage_state(path=bot.config.auth_state_path.as_posix(), indexed_db=True)
            auth_path = bot.config.auth_state_path.as_posix()
            message = "Saved login session."
        bot.close()
        app_state.active_login_bot = None
        return {"ok": True, "message": message, "auth_state": auth_path}


@app.post("/api/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict:
    dataset_id = app_state.create_dataset_id()
    suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
    target = UPLOAD_DIR / f"{dataset_id}{suffix}"
    content = await file.read()
    target.write_bytes(content)

    try:
        dataset = build_dataset_metadata(
            dataset_id=dataset_id,
            file_path=target,
            original_name=file.filename or target.name,
        )
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with app_state.lock:
        app_state.datasets[dataset_id] = dataset
    save_dataset_index()

    return serialize_dataset(dataset)


@app.post("/api/assets/logo")
async def upload_logo(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "logo.png").suffix.lower() or ".png"
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail="Logo must be an image file (.png, .jpg, .jpeg, .webp, .gif).",
        )

    target = LOGO_UPLOAD_DIR / f"logo_{uuid.uuid4().hex}{suffix}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Logo file is empty.")
    target.write_bytes(content)

    return {
        "ok": True,
        "file_path": target.as_posix(),
        "original_name": file.filename or target.name,
        "size": len(content),
    }


@app.get("/api/datasets")
def list_datasets() -> dict:
    with app_state.lock:
        return {"items": [serialize_dataset(item) for item in app_state.datasets.values()]}


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    dataset = get_dataset_or_restore(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return serialize_dataset(dataset)


@app.get("/api/storage/batches")
def list_storage_batches() -> dict:
    items = []
    for manifest_path in STORAGE_DIR.glob("*/manifest.json"):
        batch_dir = manifest_path.parent
        batch_id = batch_dir.name
        with suppress(Exception):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            items.append(serialize_batch_manifest(batch_id, batch_dir, manifest))
    items.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return {"items": items}


@app.get("/api/storage/batches/{batch_id}")
def get_storage_batch(batch_id: str) -> dict:
    batch_dir, manifest = load_batch_manifest(batch_id)
    return serialize_batch_manifest(batch_id, batch_dir, manifest)


@app.post("/api/storage/batches/{batch_id}/logo-overlay/test")
def test_storage_batch_logo_overlay(batch_id: str, request: LogoOverlayRequest) -> dict:
    batch_dir, manifest = load_batch_manifest(batch_id)
    logo_path = Path(request.logo_file_path).expanduser()
    if not logo_path.is_absolute():
        logo_path = (BASE_DIR / logo_path).resolve()
    if not logo_path.exists() or not logo_path.is_file():
        raise HTTPException(status_code=400, detail=f"Logo file not found: {logo_path}")

    processed = 0
    failed = 0
    for item in manifest.get("items", []):
        if str(item.get("status") or "").lower() != "completed":
            continue
        source_path = resolve_existing_batch_video(batch_dir, item)
        if source_path is None:
            continue

        raw_rel = str(item.get("raw_video_file") or "").strip()
        raw_name = f"item_{parse_storage_item_index(item, processed + failed + 1):04d}_{source_path.name}"
        raw_path = batch_dir / raw_rel if raw_rel else batch_dir / "raw" / raw_name
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if not raw_path.exists() or raw_path.resolve() != source_path.resolve():
            shutil.copyfile(source_path, raw_path)

        final_rel = str(item.get("final_video_file") or f"videos/{raw_path.name}")
        final_path = batch_dir / final_rel
        try:
            overlay_logo_with_ffmpeg(
                raw_path,
                logo_path,
                final_path,
                position=request.logo_position,
                logo_width_percent=request.logo_width_percent,
                margin=request.logo_margin,
            )
            item.update(
                {
                    "raw_video_file": raw_path.relative_to(batch_dir).as_posix(),
                    "final_video_file": final_path.relative_to(batch_dir).as_posix(),
                    "video_file": final_path.relative_to(batch_dir).as_posix(),
                    "raw_storage_path": raw_path.relative_to(STORAGE_DIR.parent).as_posix(),
                    "storage_path": final_path.relative_to(STORAGE_DIR.parent).as_posix(),
                    "logo_overlay_enabled": True,
                    "logo_overlay_status": "success",
                    "logo_overlay_error": "",
                    "logo_position": request.logo_position,
                    "logo_width_percent": request.logo_width_percent,
                    "logo_margin": request.logo_margin,
                }
            )
            processed += 1
        except Exception as exc:
            item.update(
                {
                    "raw_video_file": raw_path.relative_to(batch_dir).as_posix(),
                    "logo_overlay_enabled": True,
                    "logo_overlay_status": "failed",
                    "logo_overlay_error": str(exc),
                    "logo_position": request.logo_position,
                    "logo_width_percent": request.logo_width_percent,
                    "logo_margin": request.logo_margin,
                }
            )
            failed += 1

    manifest["updated_at"] = now_iso()
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = serialize_batch_manifest(batch_id, batch_dir, manifest)
    payload["logo_overlay_processed"] = processed
    payload["logo_overlay_failed"] = failed
    return payload


@app.get("/api/storage/batches/{batch_id}/subtitles/{filename}")
def get_storage_batch_subtitle(batch_id: str, filename: str):
    batch_dir, _ = load_batch_manifest(batch_id)
    target = (batch_dir / "subtitles" / Path(filename).name).resolve()
    subtitle_root = (batch_dir / "subtitles").resolve()
    if subtitle_root not in target.parents and target != subtitle_root:
        raise HTTPException(status_code=400, detail="Invalid subtitle path.")
    if not target.exists() or not target.is_file() or target.suffix.lower() != ".srt":
        raise HTTPException(status_code=404, detail="Subtitle file not found.")
    return FileResponse(target, filename=target.name, media_type="application/x-subrip")


@app.get("/api/storage/batches/{batch_id}/clips/{scene_group_id}/zip")
def download_storage_batch_clips_zip(batch_id: str, scene_group_id: str):
    batch_dir, _ = load_batch_manifest(batch_id)
    safe_group = Path(scene_group_id).name
    clips_dir = (batch_dir / "clips" / safe_group).resolve()
    clips_root = (batch_dir / "clips").resolve()
    if clips_root not in clips_dir.parents and clips_dir != clips_root:
        raise HTTPException(status_code=400, detail="Invalid clip group path.")
    if not clips_dir.exists() or not clips_dir.is_dir():
        raise HTTPException(status_code=404, detail="Clip group not found.")
    zip_path = batch_dir / f"{safe_group}-clips.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(clips_dir.iterdir()):
            if source.is_file() and source.name != "manifest.json":
                archive.write(source, arcname=source.name)
    return FileResponse(zip_path, filename=f"{safe_group}-clips.zip", media_type="application/zip")


@app.get("/api/storage/batches/{batch_id}/files/{storage_path:path}")
def get_storage_batch_file(batch_id: str, storage_path: str, resolution: str = Query("original")):
    batch_dir, _ = load_batch_manifest(batch_id)
    target = (STORAGE_DIR / storage_path) if storage_path.startswith("storage/") else (batch_dir / storage_path)
    resolved_target = target.resolve()
    resolved_root = batch_dir.resolve()
    if resolved_root not in resolved_target.parents and resolved_target != resolved_root:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not resolved_target.exists() or not resolved_target.is_file():
        raise HTTPException(status_code=404, detail="Video file not found.")
    target_short_side, _ = parse_zip_resolution(resolution)
    download_target = resolved_target
    if target_short_side is not None and resolved_target.suffix.lower() in VIDEO_FILE_SUFFIXES:
        download_target = upscale_video_for_zip(
            resolved_target,
            batch_dir,
            resolved_target.relative_to(batch_dir),
            target_short_side,
        )
    return FileResponse(download_target, filename=resolved_target.name)


@app.get("/api/storage/batches/{batch_id}/zip")
def download_storage_batch_zip(batch_id: str, resolution: str = Query("1080p")):
    batch_dir, manifest = load_batch_manifest(batch_id)
    target_short_side, resolution_label = parse_zip_resolution(resolution)
    zip_path = batch_dir / f"{batch_id}-{resolution_label}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archived_paths: set[Path] = set()
        for item in manifest.get("items", []):
            if str(item.get("status") or "").lower() != "completed":
                continue
            file_path = resolve_batch_storage_path(batch_dir, str(item.get("storage_path") or ""))
            if file_path is None or file_path.suffix.lower() not in VIDEO_FILE_SUFFIXES:
                continue
            source_relative_path = file_path.relative_to(batch_dir)
            if source_relative_path in archived_paths:
                continue
            archive_path = upscale_video_for_zip(file_path, batch_dir, source_relative_path, target_short_side)
            archive.write(archive_path, arcname=source_relative_path)
            archived_paths.add(source_relative_path)
    return FileResponse(zip_path, filename=f"{batch_id}.zip", media_type="application/zip")


def parse_zip_resolution(resolution: str) -> tuple[int | None, str]:
    normalized = str(resolution or "1080p").strip().lower()
    if normalized in {"original", "source", "none", "raw"}:
        return None, "original"
    if normalized.endswith("p"):
        normalized = normalized[:-1]
    if not normalized.isdigit():
        raise HTTPException(status_code=400, detail="Invalid ZIP video resolution.")
    height = int(normalized)
    if height not in {720, 1080, 1440, 2160}:
        raise HTTPException(status_code=400, detail="Unsupported ZIP video resolution.")
    return height, f"{height}p"


def upscale_video_for_zip(
    source_path: Path,
    batch_dir: Path,
    source_relative_path: Path,
    target_short_side: int | None,
) -> Path:
    if target_short_side is None:
        return source_path

    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        raise HTTPException(
            status_code=500,
            detail="FFmpeg is not available. Install FFmpeg or run: pip install -r requirements.txt",
        )

    target_long_side = target_short_side * 16 // 9
    target_path = batch_dir / "_upscaled" / f"{target_short_side}p-canvas" / source_relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and target_path.stat().st_mtime >= source_path.stat().st_mtime:
        return target_path

    canvas_width = f"if(gte(iw,ih),{target_long_side},{target_short_side})"
    canvas_height = f"if(gte(iw,ih),{target_short_side},{target_long_side})"
    video_filter = (
        f"scale=w='{canvas_width}':h='{canvas_height}':"
        "force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad=w='{canvas_width}':h='{canvas_height}':x=(ow-iw)/2:y=(oh-ih)/2:color=black,"
        "setsar=1"
    )

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(source_path),
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(target_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        with suppress(Exception):
            target_path.unlink()
        error = (result.stderr or result.stdout or "FFmpeg failed.").strip()
        raise HTTPException(status_code=500, detail=f"Video upscale failed: {error[-1200:]}")
    return target_path


def find_ffmpeg_path() -> str | None:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    with suppress(Exception):
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    return None


def resolve_batch_storage_path(batch_dir: Path, storage_path: str) -> Path | None:
    storage_path = storage_path.strip()
    if not storage_path:
        return None
    target = (STORAGE_DIR / storage_path.removeprefix("storage/")) if storage_path.startswith("storage/") else (batch_dir / storage_path)
    resolved_target = target.resolve()
    resolved_root = batch_dir.resolve()
    if resolved_root not in resolved_target.parents and resolved_target != resolved_root:
        return None
    if not resolved_target.exists() or not resolved_target.is_file():
        return None
    return resolved_target


def resolve_existing_batch_video(batch_dir: Path, item: dict) -> Path | None:
    keys = (
        ("raw_storage_path", "raw_video_file", "storage_path", "final_video_file", "video_file")
        if item.get("logo_overlay_status") == "success"
        else ("storage_path", "video_file", "raw_storage_path", "raw_video_file", "final_video_file")
    )
    for key in keys:
        path_value = str(item.get(key) or "").strip()
        path = resolve_batch_storage_path(batch_dir, path_value)
        if path is not None and path.suffix.lower() in VIDEO_FILE_SUFFIXES:
            return path
    return None


def parse_storage_item_index(item: dict, fallback: int) -> int:
    try:
        return max(1, int(float(str(item.get("index")))))
    except (TypeError, ValueError):
        return fallback


def load_batch_manifest(batch_id: str) -> tuple[Path, dict]:
    batch_dir = STORAGE_DIR / batch_id
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Batch not found.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Batch manifest is invalid.") from exc
    return batch_dir, manifest


def serialize_batch_manifest(batch_id: str, batch_dir: Path, manifest: dict) -> dict:
    def file_url(path_value: object) -> str:
        storage_path = str(path_value or "").strip()
        if not storage_path:
            return ""
        relative_storage_path = storage_path.removeprefix("storage/") if storage_path.startswith("storage/") else storage_path
        if relative_storage_path.startswith(f"{batch_id}/"):
            relative_storage_path = relative_storage_path[len(batch_id) + 1 :]
        resolved = resolve_batch_storage_path(batch_dir, relative_storage_path)
        version = int(resolved.stat().st_mtime) if resolved else 0
        suffix = f"?v={version}" if version else ""
        return f"/api/storage/batches/{batch_id}/files/{relative_storage_path}{suffix}"

    items = []
    for item in manifest.get("items", []):
        item_payload = dict(item)
        item_payload["raw_download_url"] = file_url(item.get("raw_storage_path") or item.get("raw_video_file"))
        item_payload["final_download_url"] = file_url(item.get("storage_path") or item.get("final_video_file"))
        clip_payloads = []
        for clip in item.get("clips", []) if isinstance(item.get("clips"), list) else []:
            clip_item = dict(clip)
            clip_item["download_url"] = file_url(clip.get("video_file"))
            clip_item["last_frame_url"] = file_url(clip.get("last_frame"))
            clip_payloads.append(clip_item)
        item_payload["clips"] = clip_payloads
        item_payload["native_scene_download_url"] = file_url(item.get("native_scene_file"))
        subtitle_file = str(item.get("subtitle_file") or "").strip()
        subtitle_name = Path(subtitle_file).name if subtitle_file else ""
        item_payload["subtitle_download_url"] = (
            f"/api/storage/batches/{batch_id}/subtitles/{subtitle_name}" if subtitle_name else ""
        )
        item_payload["preview_url"] = item_payload["final_download_url"] or item_payload["raw_download_url"]
        item_payload["download_url"] = item_payload["preview_url"]
        items.append(item_payload)

    return {
        "batch_id": manifest.get("batch_id", batch_id),
        "run_id": manifest.get("run_id", batch_id),
        "created_at": manifest.get("created_at", ""),
        "updated_at": manifest.get("updated_at", ""),
        "item_count": manifest.get("item_count", len(items)),
        "completed_count": manifest.get("completed_count", 0),
        "failed_count": manifest.get("failed_count", 0),
        "zip_url": f"/api/storage/batches/{batch_id}/zip",
        "items": items,
    }


def run_bot_job(record: RunRecord, dataset: UploadedDataset, payload: RunRequest) -> None:
    def push_log(message: str, level: str = "INFO") -> None:
        with app_state.lock:
            record.add_log(message, level)

    def wait_for_manual_scene_continue(timeout_ms: int) -> bool:
        record.continue_event.clear()
        return record.continue_event.wait(timeout=max(timeout_ms, 1) / 1000)

    def notify_manual_scene_pause(paused: bool, message: str) -> None:
        with app_state.lock:
            record.paused = paused
            record.pause_message = message if paused else ""

    try:
        with app_state.lock:
            record.status = "running"
            record.paused = False
            record.pause_message = ""
            record.add_log("Starting batch run.", "INFO")

        products, mapping = build_products(dataset.file_path, dataset.sheet_name, payload.mapping)
        scene_field_keys = tuple(
            key for key in SCENE_SCHEMA_KEYS if mapping.mapped_headers.get(key)
        )
        config = RunConfig(
            file_path=dataset.file_path,
            run_id=record.run_id,
            sheet_name=dataset.sheet_name,
            start_index=payload.start - 1,
            limit=payload.count,
            ui_base_url=payload.ui_base_url,
            chrome_user_data_dir=Path(payload.user_data_dir) if payload.user_data_dir else None,
            chrome_profile_directory=payload.profile_directory,
            cdp_port=payload.cdp_port,
            headless=payload.headless,
            slow_mo_ms=payload.slow_mo,
            wait_timeout_ms=payload.wait_timeout_seconds * 1000,
            auto_next=payload.auto_next,
            auto_generate=payload.auto_generate,
            auto_restart=payload.auto_restart,
            continue_on_video_failure=payload.continue_on_video_failure or payload.continue_on_error,
            scene_mode=payload.scene_mode,
            video_model=payload.video_model,
            aspect_ratio=payload.aspect_ratio,
            enable_logo_overlay=payload.enable_logo_overlay,
            logo_file_path=payload.logo_file_path,
            logo_position=payload.logo_position,
            logo_width_percent=payload.logo_width_percent,
            logo_margin=payload.logo_margin,
            strict_logo_overlay=payload.strict_logo_overlay,
            auto_logo_overlay_after_batch=payload.auto_logo_overlay_after_batch,
            enable_subtitles=payload.enable_subtitles,
            subtitle_source=payload.subtitle_source,
            subtitle_position=payload.subtitle_position,
            subtitle_font_size=payload.subtitle_font_size,
            subtitle_style=payload.subtitle_style,
            enable_product_image_cleanup=payload.enable_product_image_cleanup,
            cleanup_mode=payload.cleanup_mode,
            cleanup_background=payload.cleanup_background,
            cleanup_sharpen=payload.cleanup_sharpen,
            cleanup_white_background_fallback=payload.cleanup_white_background_fallback,
            cleanup_cache_enabled=payload.cleanup_cache_enabled,
            max_upload_dialog_retries=payload.max_upload_dialog_retries,
            max_page_refresh_retries=payload.max_page_refresh_retries,
            max_browser_reconnect_retries=payload.max_browser_reconnect_retries,
            scene_field_keys=scene_field_keys,
            merge_after_group_complete=payload.merge_after_group_complete,
            multi_clip_mode=payload.multi_clip_mode,
            scene_builder_mode=payload.scene_builder_mode,
            target_final_duration=payload.target_final_duration,
            download_mode=payload.download_mode,
            max_generate_retries=payload.max_generate_retries,
            keep_browser_open=payload.keep_browser_open,
            preset_json=payload.preset_json,
            website_logo_path=Path(payload.website_logo_path) if payload.website_logo_path else None,
            wait_for_manual_scene_continue=wait_for_manual_scene_continue,
            notify_manual_scene_pause=notify_manual_scene_pause,
        )
        with FlowBot(config, log_hook=push_log) as bot:
            bot.run_batch(products)

        with app_state.lock:
            record.status = "completed"
            record.paused = False
            record.pause_message = ""
            record.add_log("Batch completed.", "SUCCESS")
    except Exception as exc:
        with app_state.lock:
            record.status = "failed"
            record.paused = False
            record.pause_message = ""
            record.error = str(exc)
            record.add_log(str(exc), "ERROR")


@app.post("/api/runs")
def create_run(payload: RunRequest) -> dict:
    dataset = get_dataset_or_restore(payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    with app_state.lock:
        run_id = app_state.create_run_id()
        record = RunRecord(
            run_id=run_id,
            dataset_id=payload.dataset_id,
            created_at=now_iso(),
            options=payload.model_dump(),
        )
        app_state.runs[run_id] = record

    thread = threading.Thread(target=run_bot_job, args=(record, dataset, payload), daemon=True)
    thread.start()
    return serialize_run(record)


@app.post("/api/runs/{run_id}/continue")
def continue_run_after_scene_manual(run_id: str, payload: RunContinueRequest) -> dict:
    with app_state.lock:
        record = app_state.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        if record.status != "running":
            raise HTTPException(status_code=409, detail="Run is not active.")
        if not record.paused:
            raise HTTPException(status_code=409, detail="Run is not paused for manual scene setup.")
        record.add_log("Continue signal received from bot UI.", "SUCCESS")
        record.paused = False
        record.pause_message = ""
        record.continue_event.set()
    return {"ok": True, "run_id": run_id, "action": payload.action}


@app.get("/api/runs")
def list_runs() -> dict:
    with app_state.lock:
        return {"items": [serialize_run(item) for item in app_state.runs.values()]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    with app_state.lock:
        record = app_state.runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        return serialize_run(record)


@app.get("/api/runs/{run_id}/stream")
async def stream_run_logs(run_id: str):
    """Server-Sent Events endpoint — pushes log lines in real time."""

    async def event_generator():
        sent_count = 0
        last_status = None
        last_paused = None
        last_pause_message = None

        while True:
            await asyncio.sleep(0.4)

            with app_state.lock:
                record = app_state.runs.get(run_id)
                if record is None:
                    yield f"event: error\ndata: {json.dumps({'message': 'run not found'})}\n\n"
                    return

                # Send any new log lines
                new_logs = record.logs[sent_count:]
                current_status = record.status
                current_error = record.error
                current_paused = record.paused
                current_pause_message = record.pause_message

            for entry in new_logs:
                payload = json.dumps(entry)
                yield f"event: log\ndata: {payload}\n\n"
                sent_count += 1

            # Send status change event
            if (
                current_status != last_status
                or current_paused != last_paused
                or current_pause_message != last_pause_message
            ):
                last_status = current_status
                last_paused = current_paused
                last_pause_message = current_pause_message
                status_payload = json.dumps(
                    {
                        "status": current_status,
                        "error": current_error,
                        "paused": current_paused,
                        "pause_message": current_pause_message,
                    }
                )
                yield f"event: status\ndata: {status_payload}\n\n"

            # Stop streaming once the run is terminal
            if current_status in ("completed", "failed"):
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
