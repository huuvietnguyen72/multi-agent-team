// Khung soạn dự án: tạo dự án mới từ bản nháp của PM, hoặc sửa requirements và stack của dự án đang mở.
// Props do ui/app.py dựng (_show_editor). Bấm Lưu thì gửi cả nội dung về server (action project_save).
import { useEffect, useState } from "react";

const FIELDS = ["title", "name", "requirements", "stack", "test_command"];

export default function ProjectEditor() {
  const pick = () => Object.fromEntries(FIELDS.map(k => [k, props[k] || ""]));
  const [form, setForm] = useState(pick);
  const [tab, setTab] = useState("requirements");
  useEffect(() => setForm(pick()), [props.version]);  // bản nháp mới từ PM thì nạp lại
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  const create = props.mode === "create";
  const input = "w-full rounded-md border bg-background px-2 py-1";

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="grid gap-2" style={{ gridTemplateColumns: create ? "1fr 1fr" : "1fr" }}>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">Tên dự án</span>
          <input className={input} value={form.title} onChange={set("title")} />
        </label>
        {create && (
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Thư mục (projects/…)</span>
            <input className={`${input} font-mono`} value={form.name} onChange={set("name")} />
          </label>
        )}
      </div>
      <div className="flex gap-1" role="tablist">
        {[["requirements", "requirements.md"], ["stack", "stack.md"]].map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`rounded-md border px-3 py-1 font-mono ${tab === k ? "bg-accent font-semibold" : "text-muted-foreground"}`}>
            {label}
          </button>
        ))}
      </div>
      <textarea className={`${input} font-mono text-xs`} value={form[tab]} onChange={set(tab)}
        style={{ height: "50vh", resize: "vertical", whiteSpace: "pre" }} spellCheck={false} aria-label={tab} />
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">Lệnh test của backend (chạy khi RUN_TESTS=1, có thể để trống)</span>
        <input className={`${input} font-mono`} value={form.test_command} onChange={set("test_command")}
          placeholder="python -m pytest -q" />
      </label>
      {props.error && <p className="text-red-600 dark:text-red-400">{props.error}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => callAction({ name: "project_save", payload: { ...form, mode: props.mode } })}
          className="rounded-md bg-primary px-4 py-1.5 font-semibold text-primary-foreground hover:opacity-90">
          {create ? "Lưu và tạo dự án" : "Lưu thay đổi"}
        </button>
        <button type="button" onClick={() => setForm(pick())} className="rounded-md border px-3 py-1.5 hover:bg-accent">
          Hoàn tác
        </button>
        {create && <span className="text-xs text-muted-foreground">Muốn PM soạn lại? Gõ yêu cầu sửa vào ô chat.</span>}
      </div>
    </div>
  );
}
