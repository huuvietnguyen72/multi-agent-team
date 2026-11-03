# Multi-agent team: 5 AI agent mô phỏng team phần mềm

5 agent (PM, BA, Backend, Frontend, Tester) do LangGraph điều phối, cùng xây "Hệ thống mượn sách thư viện" từ `requirements/library_system.md`. Mỗi agent đọc `skills/<role>/SKILL.md` làm system prompt và trả JSON theo schema Pydantic (`schemas.py`). Mọi bước được ghi vào `runs/<run_id>.jsonl` và phản ánh lên Plane.

## Luồng

```
pm_plan → ba → pm_review ─(chưa đạt, <3 vòng)→ ba
                         ─(đạt)→ backend ‖ frontend → tester ─(có bug, <3 vòng)→ dev có bug
                         ─(3 vòng vẫn chưa đạt)→ pm_accept    ─(PASS hoặc hết 3 vòng)→ pm_accept → END
```
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
python main.py --mode mock     # agent giả, không tốn token: 1 lần PM trả BA, 1 bug BR-01, sửa, PASS
python main.py --mode llm      # gọi Claude thật (cần ANTHROPIC_API_KEY trong .env)
python main.py --mode claude-code  # gọi Claude qua `claude -p`, dùng gói thuê bao Pro/Max (không cần API key)
python main.py --draw          # chỉ in sơ đồ Mermaid
python -m pytest -q tests      # kiểm tra luật định tuyến + 1 lần chạy mock
```

Đầu ra: `output/docs/` (user stories, API spec, test case, test report, nghiệm thu), `output/backend/` (Spring Boot), `output/frontend/` (HTML/JS).

## Cấu trúc

| Thư mục / file | Vai trò |
| --- | --- |
| `graph.py` | Node, edge, conditional edge; giới hạn 3 vòng ở cả hai vòng lặp |
| `state.py` | `TeamState` dùng chung; `log` có reducer nối thêm để BE và FE chạy song song |
| `schemas.py` | Schema Pydantic cho đầu ra từng agent |
| `agents/` | Mỗi file một role; `mock.py` là agent giả, `llm.py` gọi Claude |
| `skills/` | `SKILL.md` của 5 role: vai trò, quy tắc, template, tool được phép |
| `tools/` | Ghi file vào `output/`, chạy `mvn test`, `plane_client.py`, ghi log |

## Plane

Tạo project trên Plane với 5 state (Backlog, Todo, In Progress, In Review, Done) và 5 label (PM, BA, BE, FE, QA), rồi điền `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, `PLANE_PROJECT_ID` vào `.env`. Thiếu cấu hình thì client chạy dry-run (in `[plane:dry-run] ...`), lỗi Plane không làm dừng graph.

## LLM

Có hai cách gọi Claude thật:

- `--mode llm` (`agents/llm.py`): Claude API qua thư viện `anthropic`, cần `ANTHROPIC_API_KEY`, tính tiền theo token.
- `--mode claude-code` (`agents/claude_code.py`): mỗi agent là một tiến trình `claude -p` với `skills/<role>/SKILL.md` làm system prompt, không có tool, đầu ra ép theo JSON Schema từ `schemas.py`. Dùng đăng nhập claude.ai của Claude Code (gói Pro/Max), nên cần cài Claude Code và `/login` trước. `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` bị bỏ qua ở chế độ này để không chuyển sang tính tiền API. Lượt dùng tính vào hạn mức của gói (chung với lúc chat trong Claude Code); chạm giới hạn thì bước đang chạy báo lỗi và graph dừng. Model đặt bằng `CC_MODEL` (mặc định `sonnet`) hoặc `CC_MODEL_<ROLE>`, effort dùng chung `LLM_EFFORT`.

Chế độ `llm`: mặc định `claude-opus-5-5`, effort `medium`. Đặt `LLM_EFFORT=low` khi thử để rẻ hơn, hoặc `MODEL_<ROLE>` để dùng model khác cho từng role. Có bật fallback phía server: nếu một yêu cầu bị bộ lọc an toàn từ chối, API tự chạy lại trên model dự phòng. Đầu ra sai schema được thử lại 1 lần rồi dừng.
