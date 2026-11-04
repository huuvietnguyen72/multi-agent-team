"""Schema Pydantic ép đầu ra của từng agent, để hàm định tuyến đọc được."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlanTask(BaseModel):
    key: str = Field(description="Mã task ngắn, ví dụ ANALYSIS, BACKEND, FRONTEND, TEST")
    title: str
    role: Literal["PM", "BA", "BE", "FE", "QA"]
    description: str


class PMPlan(BaseModel):
    summary: str
    tasks: list[PlanTask]


class UserStory(BaseModel):
    id: str = Field(description="US-01, US-02, ...")
    title: str
    as_a: str
    i_want: str
    so_that: str
    features: list[str] = Field(description="Mã chức năng liên quan, ví dụ F3")
    business_rules: list[str] = Field(description="Mã BR liên quan, ví dụ BR-01")
    acceptance_criteria: list[str]


class BAOutput(BaseModel):
    user_stories: list[UserStory]


class PMReview(BaseModel):
    approved: bool
    review_notes: str = Field(description="Lý do trả lại BA, hoặc nhận xét khi duyệt")


class CodeFile(BaseModel):
    path: str = Field(description="Đường dẫn tương đối trong thư mục output của role")
    content: str


class BackendOutput(BaseModel):
    api_spec: str = Field(description="Đặc tả API dạng Markdown: method, path, request, response, mã lỗi")
    files: list[CodeFile]
    notes: str = ""


class FrontendOutput(BaseModel):
    files: list[CodeFile]
    notes: str = ""


class ReviewFinding(BaseModel):
    id: str = Field(description="CR-01, CR-02, ...")
    severity: Literal["critical", "required", "nit"] = Field(
        description="critical/required chặn, phải sửa trước khi test; nit không chặn")
    owner: Literal["backend", "frontend"]
    file: str
    detail: str
    suggestion: str


class ReviewOutput(BaseModel):
    approved: bool = Field(description="true khi không còn finding critical hoặc required")
    findings: list[ReviewFinding]
    summary: str


class TestCase(BaseModel):
    id: str = Field(description="TC-01, TC-02, ...")
    story_id: str
    rule: str = Field(default="", description="Mã BR được kiểm tra, nếu có")
    steps: str
    expected: str
    status: Literal["PASS", "FAIL"]


class Bug(BaseModel):
    id: str = Field(description="BUG-01, ...")
    title: str
    ref: str = Field(description="Mã BR hoặc US bị vi phạm")
    owner: Literal["backend", "frontend"]
    detail: str


class TesterOutput(BaseModel):
    test_cases: list[TestCase]
    bugs: list[Bug]
    report: str


class PMAccept(BaseModel):
    final_status: str
    summary: str


class ManagerReply(BaseModel):
    """Quản lý trên giao diện: trả lời người dùng và (khi người dùng yêu cầu rõ) đề xuất một lệnh."""
    reply: str = Field(description="Câu trả lời cho người dùng, tiếng Việt, ngắn gọn, dựa trên trạng thái được đưa")
    action: Literal["none", "stop", "resume", "dismiss_finding", "add_note"] = Field(
        description="none: chỉ trả lời; stop: tạm dừng sau bước đang chạy; resume: chạy tiếp; "
                    "dismiss_finding: bỏ qua finding CR-xx hoặc bug BUG-xx; add_note: dặn một role cho lượt kế tiếp")
    ids: list[str] = Field(default_factory=list, description="dismiss_finding: mã CR-xx hoặc BUG-xx có trong trạng thái")
    role: Literal["ba", "backend", "frontend", "reviewer", "tester", ""] = Field(
        default="", description="add_note: role nhận ghi chú")
    note: str = Field(default="", description="add_note: nội dung dặn; dismiss_finding: lý do bỏ qua")
