"""Agent giả: trả dữ liệu cố định, không gọi LLM, không đọc requirements hay stack của dự án.

Dùng để thử luồng graph và định tuyến mà không tốn token (`--model mock`). Nội dung là một đề mẫu trung tính
("mục" của người dùng, 3 business rule) và ghi vào output của dự án đang chọn. Kịch bản dựng sẵn để đi qua mọi vòng lặp:
- Vòng review 1: BA thiếu tiêu chí cho BR-03, PM trả lại.
- Vòng review 2: BA bổ sung, PM duyệt.
- Review code vòng 1: frontend không hiện thông báo lỗi từ API, Reviewer trả frontend.
- Review code vòng 2: frontend đã sửa, Reviewer duyệt.
- Test vòng 1: backend chưa kiểm tra BR-01, Tester báo bug owner=backend.
- Backend sửa, Reviewer duyệt lại, test vòng 2 PASS, PM nghiệm thu.
"""
from __future__ import annotations

from tools.file_tools import read_files
from schemas import (BackendOutput, BAOutput, Bug, CodeFile, FrontendOutput, PlanTask, PMAccept,
                     PMPlan, PMReview, ReviewFinding, ReviewOutput, TestCase, TesterOutput, UserStory)

LIMIT_ERROR = "Vượt quá giới hạn 3 mục"
ALL_RULES = {"BR-01", "BR-02", "BR-03"}


def pm_plan(state) -> PMPlan:
    return PMPlan(summary="Kịch bản mock: 4 task theo luồng phân tích → BE ‖ FE → review → test", tasks=[
        PlanTask(key="ANALYSIS", title="Phân tích yêu cầu", role="BA", description="Viết user stories + AC"),
        PlanTask(key="BACKEND", title="Xây API backend", role="BE", description="API + business rules + test"),
        PlanTask(key="FRONTEND", title="Xây giao diện", role="FE", description="Màn hình cho mọi US"),
        PlanTask(key="TEST", title="Kiểm thử hệ thống", role="QA", description="Test case cho mọi AC"),
    ])


def ba(state) -> BAOutput:
    fixed = bool(state.get("review_notes"))
    view_rules = ["BR-03"] if fixed else []
    view_ac = ["Given người dùng có 2 mục, When mở danh sách, Then thấy đúng 2 mục của mình"]
    if fixed:
        view_ac.append("Given mục thuộc người khác, When xem chi tiết, Then nhận lỗi 403 (BR-03)")
    stories = [
        UserStory(id="US-01", title="Đăng nhập", as_a="người dùng", i_want="đăng nhập", so_that="dùng hệ thống",
                  features=["F1"], business_rules=[],
                  acceptance_criteria=["Given tài khoản đúng, When đăng nhập, Then vào trang chính"]),
        UserStory(id="US-02", title="Tạo mục", as_a="người dùng", i_want="tạo một mục mới", so_that="lưu lại",
                  features=["F2"], business_rules=["BR-01", "BR-02"],
                  acceptance_criteria=[
                      f"Given người dùng đã có 3 mục, When tạo mục thứ 4, Then nhận lỗi 400 '{LIMIT_ERROR}' (BR-01)",
                      "Given tên mục để trống, When tạo, Then nhận lỗi 400 'Tên không được trống' (BR-02)"]),
        UserStory(id="US-03", title="Xem mục của mình", as_a="người dùng", i_want="xem các mục của mình",
                  so_that="theo dõi", features=["F3"], business_rules=view_rules, acceptance_criteria=view_ac),
    ]
    return BAOutput(user_stories=stories)


def pm_review(state) -> PMReview:
    rules = {r for us in state["user_stories"] for r in us["business_rules"]}
    missing = sorted(ALL_RULES - rules)
    if missing:
        return PMReview(approved=False, review_notes=f"US-03 thiếu acceptance criteria cho {', '.join(missing)} "
                                                     "(không xem được mục của người khác)")
    return PMReview(approved=True, review_notes="Đủ chức năng F1-F3 và BR-01..BR-03")


def backend(state) -> BackendOutput:
    fixed = any(b["ref"] == "BR-01" for b in state.get("bugs", []))
    check = (f'    if count >= 3:\n        raise BadRequest("{LIMIT_ERROR}")\n' if fixed
             else "    # TODO: kiểm tra BR-01\n")
    service = "def create_item(count: int, name: str):\n" + check + "    ...\n"
    return BackendOutput(api_spec=f"| POST | /api/items | {{name}} | 201 | 400 \"{LIMIT_ERROR}\" (BR-01) | US-02 |",
                         files=[CodeFile(path="item_service.py", content=service)],
                         notes="Sửa BR-01" if fixed else "Bản đầu")


def frontend(state) -> FrontendOutput:
    fixed = any(f["owner"] == "frontend" for f in state.get("review_findings", []))
    on_error = ("showError(body.error)" if fixed else 'alert("Có lỗi xảy ra")')
    app = ("const API_BASE = \"http://localhost:8080/api\";\n"
           "async function createItem(name) {\n"
           "  const res = await fetch(`${API_BASE}/items`, {method: \"POST\"});\n"
           "  const body = await res.json();\n"
           f"  if (!res.ok) {on_error};\n"
           "}\n")
    return FrontendOutput(files=[CodeFile(path="index.html", content="<!doctype html><h1>Demo</h1>\n"),
                                 CodeFile(path="app.js", content=app)],
                          notes="Hiện lỗi từ API" if fixed else "Bản đầu")


def reviewer(state) -> ReviewOutput:
    code = read_files(state.get("frontend_code", []))
    if "showError(body.error)" in code:
        return ReviewOutput(approved=True, summary="Không còn finding chặn", findings=[
            ReviewFinding(id="CR-02", severity="nit", owner="backend", file="item_service.py",
                          detail="Nên tách hằng số 3 thành MAX_ITEMS", suggestion="Thêm hằng số")])
    return ReviewOutput(approved=False, summary="Frontend nuốt thông báo lỗi từ API", findings=[
        ReviewFinding(id="CR-01", severity="required", owner="frontend", file="app.js",
                      detail=f"createItem() chỉ hiện 'Có lỗi xảy ra', không hiện trường error (vd '{LIMIT_ERROR}')",
                      suggestion="Hiển thị body.error cho người dùng")])


def tester(state) -> TesterOutput:
    code = read_files(state.get("backend_code", []))
    ok = LIMIT_ERROR in code
    tc = TestCase(id="TC-01", story_id="US-02", rule="BR-01", steps="Tạo 4 mục liên tiếp",
                  expected="Mục thứ 4 bị từ chối 400", status="PASS" if ok else "FAIL")
    bugs = [] if ok else [Bug(id="BUG-01", title="Cho tạo mục thứ 4", ref="BR-01", owner="backend",
                              detail="create_item không kiểm tra số mục hiện có")]
    return TesterOutput(test_cases=[tc], bugs=bugs, report="PASS" if ok else "FAIL: BUG-01 (BR-01)")


def pm_accept(state) -> PMAccept:
    status = "ACCEPTED" if not state.get("bugs") and state.get("approved") else "NEEDS_HUMAN_REVIEW"
    return PMAccept(final_status=status, summary=f"Kết thúc sau {state.get('review_round', 0)} lần trả BA, "
                                                 f"{state.get('iteration', 0)} vòng test")
