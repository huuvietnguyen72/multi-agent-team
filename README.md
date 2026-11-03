# Multi-agent team: AI agent mô phỏng team phần mềm

6 agent (PM, BA, Backend, Frontend, Reviewer, Tester) do LangGraph điều phối, cùng xây "Hệ thống mượn sách thư viện" từ `requirements/library_system.md`. Mỗi agent đọc `skills/<role>/SKILL.md` làm system prompt và trả JSON theo schema Pydantic (`schemas.py`). Mọi bước được ghi vào `runs/<run_id>.jsonl` và phản ánh lên Plane.

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
python main.py --mode mock     # agent giả, không tốn token: PM trả BA 1 lần, Reviewer trả FE 1 lần, bug BR-01, sửa, PASS
python main.py --mode llm      # gọi Claude thật (cần ANTHROPIC_API_KEY trong .env)
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
| `skills/` | `skills/<role>/SKILL.md` cho 6 role, theo chuẩn Agent Skills (frontmatter `name`/`description`; Overview, When to Use, Process, Rules, Output Template, Red Flags, Verification) |
| `tools/` | Ghi file vào `output/`, chạy `mvn test`, `plane_client.py`, ghi log |

## Plane

Tạo project trên Plane với 5 state (Backlog, Todo, In Progress, In Review, Done) và 5 label (PM, BA, BE, FE, QA), rồi điền `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, `PLANE_PROJECT_ID` vào `.env`. Thiếu cấu hình thì client chạy dry-run (in `[plane:dry-run] ...`), lỗi Plane không làm dừng graph.

## LLM

Mặc định `claude-opus-5-5`, effort `medium`. Đặt `LLM_EFFORT=low` khi thử để rẻ hơn, hoặc `MODEL_<ROLE>` để dùng model khác cho từng role. Có bật fallback phía server: nếu một yêu cầu bị bộ lọc an toàn từ chối, API tự chạy lại trên model dự phòng. Đầu ra sai schema được thử lại 1 lần rồi dừng.

## Skills

Mỗi role có một `skills/<role>/SKILL.md`. Nội dung quy trình được rút gọn và chỉnh từ [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (MIT, xem `THIRD_PARTY_NOTICES.md`), cộng với quy tắc riêng của đề thư viện. Khi gọi LLM, frontmatter được bỏ đi và phần còn lại làm system prompt (có prompt caching).

Thêm một role mới: tạo `skills/<role>/SKILL.md` cùng định dạng, thêm schema đầu ra trong `schemas.py`, một file trong `agents/`, một hàm giả trong `agents/mock.py`, rồi nối node vào `graph.py`.
