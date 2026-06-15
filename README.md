# Flow Product Autofill Bot

Bot tự động điền dữ liệu sản phẩm vào Google Flow bằng Playwright. Repo này có 2 cách dùng:

- `CLI bot`: chạy trực tiếp bằng terminal
- `FastAPI Bot UI`: mở web UI local để upload Excel, map cột, import preset, upload logo, rồi bấm `Run Bot`

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chrome
```

## Python Bot (CLI)

CLI phù hợp khi bạn muốn debug nhanh hoặc chạy bot không cần web UI.

### Lưu phiên đăng nhập

```powershell
python run_flow_bot.py login --slow-mo 400
```

Trình duyệt sẽ mở Flow. Đăng nhập thủ công, vào đúng màn hình Flow, rồi quay lại terminal nhấn `Enter`. Session sẽ được lưu vào `playwright/.auth/flow.json`.

### Dùng Chrome profile có sẵn

```powershell
python run_flow_bot.py login `
  --user-data-dir "C:\Users\YOUR_USER\AppData\Local\Google\Chrome\User Data" `
  --profile-directory "Default" `
  --slow-mo 400
```

Ví dụ chạy batch với profile đang dùng:

```powershell
python run_flow_bot.py run `
  --file .\products.xlsx `
  --user-data-dir "C:\Users\YOUR_USER\AppData\Local\Google\Chrome\User Data" `
  --profile-directory "Profile 1" `
  --count 5 `
  --slow-mo 400
```

### Kiểm tra file Excel và mapping

```powershell
python run_flow_bot.py inspect --file .\products.xlsx
```

### Chạy batch

```powershell
python run_flow_bot.py run --file .\products.xlsx --count 5 --slow-mo 400
```

Ví dụ chạy từ sản phẩm thứ 3:

```powershell
python run_flow_bot.py run --file .\products.xlsx --start 3 --count 2 --slow-mo 500
```

### Flag hữu ích

- `--sheet Sheet1`
- `--headless`
- `--no-auto-next`
- `--no-auto-generate`
- `--no-auto-restart`
- `--wait-timeout 900`
- `--auth-state custom.json`

## FastAPI Bot UI

Đây là cách dùng chính hiện tại của dự án.

### Chạy server bot

```powershell
python -m uvicorn fastapi_app.main:app --host 127.0.0.1 --port 8000 --reload
```

Mở giao diện tại:

```text
http://127.0.0.1:8000/
```

Nếu chỉ muốn chạy nhanh, không cần tự reload khi sửa code:

```powershell
python -m uvicorn fastapi_app.main:app --host 127.0.0.1 --port 8000
```

### Cách run dự án

1. Khởi động server FastAPI bằng một trong hai lệnh ở trên.
2. Mở Chrome bằng remote debugging trước khi bấm `Run Bot`.

```powershell
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\Users\YOUR_USER\AppData\Local\Google\Chrome\User Data" --profile-directory="Profile 12" "https://labs.google/fx/vi/tools/flow/project/f59c99c2-23b5-44a8-b9c7-e89f1fd6a39e/tool/f5f0a297-5a81-48b0-bcec-e4a6e63ec4d9"
```

3. Mở `http://127.0.0.1:8000/`.
4. Ở `Upload Excel / CSV`, chọn file rồi bấm `Upload File`.
5. Ở `Field Mapping`, kiểm tra mapping cho:
- `product_name`
- `short_description`
- `long_description`
- `product_image` nếu có
6. Nếu dùng preset, vào `Preset Import`:
- paste JSON hoặc import file `.json`
- trường `website_logo` trong preset sẽ tự bị bỏ qua
- nếu có logo website riêng thì upload bằng `Upload Logo`
7. Ở `Batch Settings`, kiểm tra:
- `Dataset ID`
- `CDP Port`
- `Start Product`
- `Product Count`
- `Slow Mo`
- `Video Timeout`
8. Bấm `Run Bot`.
9. Theo dõi log trong tab `Realtime Log` và toast log trên website mà bot đang thao tác.

### Ghi chú khi chạy UI

- `CDP Port` trong UI phải khớp với `--remote-debugging-port` của Chrome
- Bot hiện import preset và upload logo ngay trong Step 1 nếu bạn đã cấu hình
- Dataset upload được lưu trong `bot-output/uploads`
- Logo upload được lưu trong `bot-output/uploads/logos`
- Nếu sửa code UI/backend trong lúc đang chạy bằng `--reload`, Uvicorn sẽ tự restart

### API hiện có

- `GET /`
- `GET /api/health`
- `POST /api/login/open`
- `POST /api/login/save`
- `POST /api/datasets/upload`
- `POST /api/assets/logo`
- `GET /api/datasets`
- `GET /api/datasets/{dataset_id}`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/stream`

## Cấu trúc chính

```text
run_flow_bot.py
requirements.txt

fastapi_app/
  __init__.py
  main.py
  schemas.py
  state.py
  ui.py

flow_bot/
  cli.py
  excel_mapper.py
  flow_runner.py
  models.py
```

## Field chính

Bot hiện tập trung vào 4 field sản phẩm:

- `product_image`
- `product_name`
- `short_description`
- `long_description`
