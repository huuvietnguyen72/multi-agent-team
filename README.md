# Multi-agent team: AI agent mô phỏng team phần mềm

Khung dùng chung cho nhiều dự án: 6 agent (PM, BA, Backend, Frontend, Reviewer, Tester) do LangGraph điều phối, cùng xây một phần mềm từ requirements của một dự án trong `projects/<tên>/`. Mỗi agent đọc `skills/<role>/SKILL.md` (quy trình chung, không gắn với dự án nào) làm system prompt; stack và quy ước kỹ thuật riêng của dự án (`projects/<tên>/stack.md`) được chèn vào đầu prompt. Agent trả JSON theo schema Pydantic (`schemas.py`). Mọi bước được ghi vào `runs/<run_id>.jsonl` và phản ánh lên Plane.

Dự án có sẵn: `library` (hệ thống mượn sách thư viện, Spring Boot + HTML/JS) và `library-borrow-detail` (một module nhỏ của nó, dùng để thử nhanh).

## Luồng

```
pm_plan → ba → pm_review ─(chưa đạt, <3 vòng)→ ba
                         ─(3 vòng vẫn chưa đạt)→ pm_accept
                         ─(đạt)→ backend ‖ frontend → reviewer ─(finding chặn, <3 vòng)→ dev có finding → reviewer
                                                               ─(duyệt hoặc hết vòng)→ tester
tester ─(có bug, <3 vòng)→ dev có bug → reviewer → tester
       ─(PASS hoặc hết 3 vòng)→ pm_accept → END
```
Mọi lần Dev sửa code (kể cả sửa bug của Tester) đều qua Reviewer trước khi test lại.
Sơ đồ Mermaid sinh từ code: `docs/graph.mmd` (dán vào https://mermaid.live để xuất ảnh).

## Cài đặt (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Chạy

```powershell
python main.py --list                                # liệt kê dự án trong projects/
python main.py --project library --model mock         # kịch bản giả cố định, không tốn token, để thử luồng
python main.py --project library                      # model theo MODEL / MODEL_<ROLE> trong .env, hỏi xác nhận trước
python main.py --project library --model ollama:qwen3:8b  # một model cho cả team lần này, bỏ qua MODEL_<ROLE>
python main.py --project library --yes                # không hỏi xác nhận (bắt buộc khi chạy nền / CI)
python main.py --project library --requirements projects/library/modules/x.md  # chạy riêng một module
python main.py --draw                                # chỉ in sơ đồ Mermaid
python -m pytest -q tests                            # test khung (không gọi model, không ghi vào projects/)
```

Đặt `PROJECT=<tên>` trong `.env` để khỏi gõ `--project` mỗi lần.

Đầu ra nằm trong `projects/<tên>/output/` (không commit): `docs/` (user stories, API spec, code review, test case, test report, nghiệm thu), `backend/`, `frontend/`. Mỗi dự án một thư mục riêng nên chạy dự án này không ghi đè dự án khác.

## Tạo dự án mới

1. Chép `projects/_template/` thành `projects/<tên-dự-án>/`.
2. Sửa `requirements.md`: vai trò người dùng, chức năng `F1..Fn`, business rules `BR-xx` (đo được, kèm đúng thông báo lỗi), ví dụ kiểm thử.
3. Sửa `stack.md`: ngôn ngữ và framework backend/frontend, CSDL, cấu trúc thư mục, định dạng lỗi, cách xác thực, địa chỉ chạy. Đây là chỗ duy nhất ghi chi tiết kỹ thuật riêng của dự án; skills chỉ giữ nguyên tắc chung.
4. Sửa `project.toml`: tên hiển thị và `[tests].command` (ví dụ `mvn -q -B test`, `pytest -q`, `npm test --silent`). Đặt `RUN_TESTS=1` trong `.env` để Tester chạy lệnh này trên code agent sinh ra và dùng kết quả làm bằng chứng.
5. Chạy `python main.py --project <tên-dự-án> --model mock` để kiểm tra cấu hình, rồi chạy với model thật.

Team (6 role) và luồng là cố định; muốn đổi thì xem mục Skills bên dưới.

## Cấu trúc

| Thư mục / file | Vai trò |
| --- | --- |
| `graph.py` | Node, edge, conditional edge; giới hạn 3 vòng ở cả hai vòng lặp |
| `state.py` | `TeamState` dùng chung; `log` có reducer nối thêm để BE và FE chạy song song |
| `schemas.py` | Schema Pydantic cho đầu ra từng agent |
| `agents/` | Mỗi file một role; `common.py` gọi model của role và chèn stack của dự án vào prompt; `mock.py` là kịch bản giả cố định; `skills.py` đọc SKILL.md |
| `agents/providers/` | Chọn model theo role (`__init__.py`) và các adapter: `anthropic_api.py`, `openai_compat.py`, `claude_code.py` |
| `providers.toml` | Danh sách provider dùng chung (endpoint, tên biến chứa key, tùy chọn); `providers.local.toml` (không commit) thêm hoặc ghi đè cho riêng máy bạn |
| `skills/` | `skills/<role>/SKILL.md` cho 6 role, theo chuẩn Agent Skills (frontmatter `name`/`description`; Overview, When to Use, Process, Rules, Output Template, Red Flags, Verification). Chỉ chứa quy trình chung |
| `projects/` | Mỗi dự án một thư mục: `project.toml`, `requirements.md`, `stack.md`, `output/`. `_template/` là mẫu |
| `tools/` | `project.py` đọc dự án, `file_tools.py` ghi file vào output của dự án, `test_runner.py` chạy lệnh test của dự án, `plane_client.py`, `runlog.py` |

## Plane

Tạo project trên Plane với 5 state (Backlog, Todo, In Progress, In Review, Done) và 5 label (PM, BA, BE, FE, QA), rồi điền `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, `PLANE_PROJECT_ID` vào `.env`. Thiếu cấu hình thì client chạy dry-run (in `[plane:dry-run] ...`), lỗi Plane không làm dừng graph.

## Model và provider

Mỗi role gọi một model, chọn bằng cú pháp `<provider>:<model>` trong `.env`:

```
MODEL=claude-code:sonnet                  # mặc định cho mọi role
MODEL_BACKEND=opencode-go:glm-5.3         # riêng một role: pm, ba, backend, frontend, reviewer, tester
MODEL_TESTER=ollama:qwen3:8b              # role khác nhau có thể dùng nhà cung cấp khác nhau
EFFORT_BACKEND=high                       # tùy chọn: mức suy luận, giá trị hợp lệ tùy model
MAX_TOKENS_BACKEND=131072                 # tùy chọn: trần token đầu ra, tính cả token suy luận
```

`--model <provider>:<model>` dùng một model cho cả team trong lần chạy đó, bỏ qua `MODEL` và `MODEL_<ROLE>`. `--model mock` (hoặc `MODEL=mock`) cho cả team chạy kịch bản giả, không tốn token.

Trước khi chạy, `main.py` kiểm tra cấu hình và dừng nếu sai (provider chưa khai báo, thiếu model, thiếu key). Nếu có role dùng model thật, nó in bảng role → model và hỏi xác nhận; khi không có terminal (chạy nền, CI) thì phải thêm `--yes`, nếu không sẽ dừng.

**Provider** là một endpoint đặt tên trong `providers.toml`: adapter (`type`), địa chỉ, **tên** biến môi trường chứa key (key thật để trong `.env`, không bao giờ ghi vào toml), và tùy chọn. Có sẵn:

| Provider | Adapter | Ghi chú |
| --- | --- | --- |
| `claude-code` | `claude-code` | Claude Code CLI `claude -p`, dùng gói Claude Pro/Max đang đăng nhập; không cần API key. Bỏ qua `ANTHROPIC_API_KEY` để không chuyển sang tính tiền API |
| `claude-api` | `anthropic` | Claude API, `ANTHROPIC_API_KEY`; bật fallback phía server khi bị bộ lọc an toàn từ chối |
| `opencode-go` | `openai-compatible` | Gói OpenCode Go (GLM, Kimi, DeepSeek, ...), `OPENCODE_GO_API_KEY`; gửi header phiên `x-opencode-session` mà Go yêu cầu. DeepSeek mặc định chỉ phục vụ Châu Âu và Mỹ (bật **Global** trong Settings › Privacy › Regions nếu cần) |
| `openai`, `openrouter`, `deepseek`, `gemini` | `openai-compatible` | Cấu hình mẫu theo tài liệu nhà cung cấp, **chưa chạy thử** với dự án này |
| `ollama`, `lmstudio` | `openai-compatible` | Model chạy local, không cần key; **chưa chạy thử** |
| `mock` | `mock` | Kịch bản giả, luôn có |

Đã chạy thật với dự án này: `claude-code` và `opencode-go`.

Thêm nhà cung cấp khác: nếu nó theo chuẩn OpenAI Chat Completions hoặc Anthropic Messages, chỉ cần thêm một mục vào `providers.local.toml` (hoặc `providers.toml` nếu muốn chia sẻ), ví dụ:

```toml
[providers.my-vllm]
type = "openai-compatible"
base_url = "http://gpu-box:8000/v1"
api_key_env = "MY_VLLM_KEY"          # bỏ dòng này nếu server không cần key
response_format = "json_object"      # json_schema (mặc định) | json_object | none, tùy server hỗ trợ
```

rồi đặt `MODEL_BACKEND=my-vllm:<tên model>`. Tùy chọn của từng adapter (header, tên tham số effort/max_tokens, timeout, ...) ghi ở đầu file adapter trong `agents/providers/`. Với giao thức khác hẳn: viết `agents/providers/<adapter>.py` có hàm `call(target, role, prompt, schema)` và đăng ký trong `agents/providers/__init__.py`.

Mọi adapter: skill của role làm system prompt, đầu ra ép theo JSON Schema từ `schemas.py` (adapter `openai-compatible` còn ghi schema vào system prompt cho server ép lỏng), sai schema thì thử lại 1 lần rồi dừng; đầu ra bị cắt do trần token thì báo lỗi kèm số ký tự trả lời và suy luận để biết nên tăng `MAX_TOKENS_<ROLE>` hay giảm `EFFORT_<ROLE>`. Lượt dùng tính theo nhà cung cấp: gói Claude và OpenCode Go có hạn mức theo khung giờ; chạm giới hạn thì bước đang chạy báo lỗi và graph dừng.

## Skills

Mỗi role có một `skills/<role>/SKILL.md`. Nội dung quy trình được rút gọn và chỉnh từ [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (MIT, xem `THIRD_PARTY_NOTICES.md`) và viết chung cho mọi dự án: không nhắc đề, stack hay framework cụ thể. `tests/test_project.py` kiểm tra điều này. Khi stack của dự án quy định khác một quy tắc chung trong skill, agent làm theo stack. Adapter `anthropic` và `openai-compatible` bỏ frontmatter rồi dùng phần còn lại làm system prompt (`anthropic` có prompt caching); adapter `claude-code` nạp nguyên file.

`--model mock` dùng một kịch bản giả trung tính (3 user story về "mục" của người dùng), không đọc requirements hay stack; nó chỉ để kiểm tra luồng và định tuyến.

Thêm một role mới: tạo `skills/<role>/SKILL.md` cùng định dạng, thêm schema đầu ra trong `schemas.py`, một file trong `agents/`, một hàm giả trong `agents/mock.py`, rồi nối node vào `graph.py`.
