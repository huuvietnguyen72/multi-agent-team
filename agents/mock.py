"""Agent giả (giai đoạn 2 trong spec): trả dữ liệu cố định, không gọi LLM.

Kịch bản dựng sẵn để demo đủ 2 vòng lặp:
- Vòng review 1: BA thiếu tiêu chí cho BR-03, PM trả lại.
- Vòng review 2: BA bổ sung, PM duyệt.
- Test vòng 1: backend chưa kiểm tra BR-01, Tester báo bug owner=backend.
- Test vòng 2: backend đã sửa, Tester PASS, PM nghiệm thu.
"""
from __future__ import annotations

from tools.file_tools import read_files
from schemas import (BackendOutput, BAOutput, Bug, CodeFile, FrontendOutput, PlanTask, PMAccept,
                     PMPlan, PMReview, TestCase, TesterOutput, UserStory)


def pm_plan(state) -> PMPlan:
    return PMPlan(summary="Xây hệ thống mượn sách thư viện qua 4 task", tasks=[
        PlanTask(key="ANALYSIS", title="Phân tích yêu cầu", role="BA", description="Viết user stories + AC"),
        PlanTask(key="BACKEND", title="Xây REST API Spring Boot", role="BE", description="API + business rules"),
        PlanTask(key="FRONTEND", title="Xây giao diện HTML/JS", role="FE", description="Màn hình cho mọi US"),
        PlanTask(key="TEST", title="Kiểm thử hệ thống", role="QA", description="Test case cho mọi AC"),
    ])


def ba(state) -> BAOutput:
    fixed = bool(state.get("review_notes"))
    borrow_ac = [
        "Given sinh viên đang mượn 3 cuốn, When mượn cuốn thứ 4, Then nhận lỗi 400 'Vượt quá 3 cuốn' (BR-01)",
        "Given mượn thành công, Then hạn trả = ngày mượn + 14 ngày (BR-02)",
        "Given sách có tồn kho = 0, When mượn, Then nhận lỗi 400 'Sách đã hết' (BR-04)",
    ]
    if fixed:
        borrow_ac.append("Given sinh viên có sách quá hạn, When mượn, Then nhận lỗi 400 'Có sách quá hạn' (BR-03)")
    stories = [
        UserStory(id="US-01", title="Đăng nhập", as_a="người dùng", i_want="đăng nhập", so_that="dùng hệ thống",
                  features=["F1"], business_rules=[],
                  acceptance_criteria=["Given tài khoản đúng, When đăng nhập, Then vào trang theo vai trò"]),
        UserStory(id="US-02", title="Tìm sách", as_a="sinh viên", i_want="tìm sách", so_that="chọn sách mượn",
                  features=["F2"], business_rules=[],
                  acceptance_criteria=["Given từ khóa, When tìm theo tên/tác giả/thể loại, Then thấy sách khớp"]),
        UserStory(id="US-03", title="Mượn sách", as_a="sinh viên", i_want="mượn sách", so_that="đọc ở nhà",
                  features=["F3"], business_rules=["BR-01", "BR-02", "BR-04"] + (["BR-03"] if fixed else []),
                  acceptance_criteria=borrow_ac),
        UserStory(id="US-04", title="Xem sách đang mượn", as_a="sinh viên", i_want="xem sách đang mượn",
                  so_that="biết hạn trả", features=["F4"], business_rules=["BR-02"],
                  acceptance_criteria=["Given đang mượn sách, When mở trang, Then thấy danh sách và hạn trả"]),
        UserStory(id="US-05", title="Xác nhận trả", as_a="thủ thư", i_want="xác nhận trả", so_that="cập nhật kho",
                  features=["F5"], business_rules=[],
                  acceptance_criteria=["Given phiếu mượn, When xác nhận trả, Then tồn kho +1"]),
        UserStory(id="US-06", title="Quản lý sách", as_a="thủ thư", i_want="thêm/sửa/xóa sách",
                  so_that="cập nhật danh mục", features=["F6"], business_rules=["BR-05"],
                  acceptance_criteria=["Given sách đang có người mượn, When xóa, Then nhận lỗi 400 (BR-05)"]),
    ]
    return BAOutput(user_stories=stories)


def pm_review(state) -> PMReview:
    rules = {r for us in state["user_stories"] for r in us["business_rules"]}
    missing = sorted({"BR-01", "BR-02", "BR-03", "BR-04", "BR-05"} - rules)
    if missing:
        return PMReview(approved=False, review_notes=f"US-03 thiếu acceptance criteria cho {', '.join(missing)} "
                                                     "(sinh viên có sách quá hạn không được mượn thêm)")
    return PMReview(approved=True, review_notes="Đủ chức năng F1-F6 và BR-01..BR-05")


def backend(state) -> BackendOutput:
    fixed = any(b["ref"] == "BR-01" for b in state.get("bugs", []))
    check = ('        if (activeBorrows >= 3) throw new BadRequest("Vượt quá 3 cuốn");\n' if fixed
             else "        // TODO: kiểm tra BR-01\n")
    service = ("package com.example.library;\n\npublic class BorrowService {\n"
               "    public void borrow(long activeBorrows) {\n" + check + "    }\n}\n")
    return BackendOutput(api_spec="| POST | /api/borrow | {bookId} | 201 | 400 | US-03 |",
                         files=[CodeFile(path="src/main/java/com/example/library/BorrowService.java",
                                         content=service)],
                         notes="Sửa BR-01" if fixed else "Bản đầu")


def frontend(state) -> FrontendOutput:
    return FrontendOutput(files=[CodeFile(path="index.html", content="<!doctype html><h1>Thư viện</h1>\n")])


def tester(state) -> TesterOutput:
    code = read_files(state.get("backend_code", []))
    ok = "Vượt quá 3 cuốn" in code
    tc = TestCase(id="TC-01", story_id="US-03", rule="BR-01", steps="Mượn 4 cuốn liên tiếp",
                  expected="Cuốn thứ 4 bị từ chối 400", status="PASS" if ok else "FAIL")
    bugs = [] if ok else [Bug(id="BUG-01", title="Cho mượn cuốn thứ 4", ref="BR-01", owner="backend",
                              detail="BorrowService.borrow không kiểm tra số sách đang mượn")]
    return TesterOutput(test_cases=[tc], bugs=bugs, report="PASS" if ok else "FAIL: BUG-01 (BR-01)")


def pm_accept(state) -> PMAccept:
    status = "ACCEPTED" if not state.get("bugs") and state.get("approved") else "NEEDS_HUMAN_REVIEW"
    return PMAccept(final_status=status, summary=f"Kết thúc sau {state.get('iteration', 0)} vòng test")
