// Khung "Chi tiết" của một role (FR-13 đến FR-15). Props do ui/turns.py dựng (Turns.props).
// Chainlit đưa vào `props` và các hàm toàn cục `callAction`, `updateElement`.
import { useEffect, useRef, useState } from "react";

const COLORS = { PM: "#6941C6", BA: "#B54708", Backend: "#175CD3", Frontend: "#087443", Reviewer: "#C11574", Tester: "#344054" };
const SHORT = { PM: "PM", BA: "BA", Backend: "BE", Frontend: "FE", Reviewer: "RV", Tester: "QA" };

function Avatar({ role, size = 28 }) {
  return (
    <span style={{ width: size, height: size, background: COLORS[role] || "#344054", fontSize: size * 0.4 }}
      className="inline-flex shrink-0 items-center justify-center rounded-full font-bold text-white">
      {SHORT[role] || role.slice(0, 2)}
    </span>
  );
}

function seconds(t) {
  const s = t.status === "running" ? t.elapsed : t.seconds;
  if (s === null || s === undefined) return "";
  const n = Math.round(s);
  return n >= 60 ? `${Math.floor(n / 60)} phút ${String(n % 60).padStart(2, "0")} giây` : `${n} giây`;
}

function Phases({ turn }) {
  const order = props.phases.map(p => p[0]);
  const at = order.indexOf(turn.phase);
  return (
    <ol className="flex flex-wrap gap-1.5 mt-3 text-xs" aria-label="Các bước của lượt này">
      {props.phases.map(([key, label], i) => {
        if (i < at && !(turn.seen || []).includes(key)) return null;  // bước role này không có
        const done = i < at, now = i === at;
        const cls = done ? "bg-green-600/15 text-green-700 dark:text-green-300"
          : now ? "bg-blue-600/15 text-blue-700 dark:text-blue-300 font-semibold"
          : "bg-muted/60 text-muted-foreground";
        return <li key={key} className={`rounded-full px-2.5 py-1 ${cls}`}>{done ? "✓ " : now ? "● " : "○ "}{label}</li>;
      })}
    </ol>
  );
}

function Diff({ file }) {
  const [open, setOpen] = useState(file.lines.length <= 80);
  return (
    <div className="border-t border-border">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 bg-muted/50 text-left font-mono text-xs min-h-[40px]">
        <span className="break-all">{open ? "▾ " : "▸ "}{file.path}{file.new_file ? " (mới)" : ""}</span>
        <span><span className="text-green-700 dark:text-green-400 font-semibold">+{file.added}</span>{" "}
          <span className="text-red-700 dark:text-red-400 font-semibold">-{file.removed}</span></span>
      </button>
      {open && file.note && <div className="px-3 py-2 text-xs text-muted-foreground">{file.note}</div>}
      {open && file.lines.length > 0 && (
        <div className="overflow-x-auto py-1 font-mono text-xs leading-6">
          {file.lines.map((l, i) => {
            const bg = l.kind === "add" ? "bg-green-500/15" : l.kind === "del" ? "bg-red-500/15" : l.kind === "hunk" ? "bg-blue-500/10 text-muted-foreground" : "";
            const sign = l.kind === "add" ? "+" : l.kind === "del" ? "-" : "";
            return (
              <div key={i} className={`flex ${bg}`} style={{ whiteSpace: "pre", width: "max-content", minWidth: "100%" }}>
                <span className="w-9 shrink-0 select-none pr-1 text-right text-muted-foreground">{l.old ?? ""}</span>
                <span className="w-9 shrink-0 select-none pr-1 text-right text-muted-foreground">{l.new ?? ""}</span>
                <span className={`w-5 shrink-0 select-none text-center font-bold ${l.kind === "add" ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>{sign}</span>
                <span className="pr-3">{l.text}</span>
              </div>
            );
          })}
          {file.truncated && <div className="px-3 py-1 text-muted-foreground">(chỉ hiện 400 dòng đầu)</div>}
        </div>
      )}
    </div>
  );
}

function TurnCard({ turn, first }) {
  const [open, setOpen] = useState(first || turn.status === "running");
  const running = turn.status === "running";
  const state = running ? "đang chạy" : turn.status === "failed" ? "lỗi" : "xong";
  return (
    <section className={`rounded-lg overflow-hidden ${running ? "border-2 border-blue-600" : "border border-border"}`}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-left min-h-[44px]">
        <span className="font-semibold text-sm">{open ? "▾ " : "▸ "}Lượt {turn.n} · {turn.task}</span>
        <span className="text-xs text-muted-foreground">{state}{seconds(turn) ? ` · ${seconds(turn)}` : ""}
          {turn.model ? <> · <span className="font-mono">{turn.model}</span></> : null}
          {!running && turn.files.length ? ` · +${turn.added} -${turn.removed}` : ""}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 text-sm">
          {turn.found_by && <div className="text-muted-foreground">Lỗi do {turn.found_by} tìm thấy</div>}
          {turn.escalated_from && (
            <div className="mt-2 rounded-md border border-amber-400/60 bg-amber-400/10 px-2.5 py-1.5 text-xs">
              Đổi model từ <span className="font-mono">{turn.escalated_from}</span> sang <span className="font-mono">{turn.model}</span> vì đây là vòng sửa cuối
            </div>
          )}
          {running && <Phases turn={turn} />}
          {running && turn.chars ? <div className="mt-2 text-xs text-muted-foreground">Đã nhận {turn.chars.toLocaleString("vi-VN")} ký tự từ model</div> : null}
          {running && !turn.chars && turn.phase === "model" ? <div className="mt-2 text-xs text-muted-foreground">Model trả kết quả một lần, phần sửa hiện khi lượt này xong.</div> : null}
          {!running && turn.files.length === 0 && <div className="mt-1 text-muted-foreground">Không đổi tệp nào.</div>}
        </div>
      )}
      {open && !running && turn.files.map(f => <Diff key={f.path} file={f} />)}
    </section>
  );
}

export default function RoleDetail() {
  const turns = props.turns || [];
  const chosen = useRef(null);
  useEffect(() => {  // màn hình hẹp: hàng role cuộn ngang, đưa role đang xem vào tầm nhìn
    if (chosen.current) chosen.current.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [props.role]);
  const running = turns.filter(t => t.status === "running").length;
  return (
    <div className="flex flex-col gap-3 text-foreground">
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label="Đổi role">
        {props.roles.map(r => {
          const st = (props.role_status || {})[r] || "idle";
          return (
            <button key={r} type="button" aria-pressed={r === props.role} ref={r === props.role ? chosen : null}
              title={st === "running" ? `${r} đang làm` : st === "idle" ? `${r} chưa làm lượt nào` : r}
              onClick={() => callAction({ name: "show_role", payload: { role: r } })}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full py-1 pl-1 pr-2.5 text-xs min-h-[36px] ${r === props.role ? "border-2 border-blue-600 font-semibold" : "border border-border"} ${st === "idle" && r !== props.role ? "opacity-50" : ""}`}>
              <Avatar role={r} size={24} />{r}
              {st === "running" && <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 9999, background: "#2563eb" }} />}
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2.5">
        <Avatar role={props.role} size={36} />
        <div>
          <div className="font-bold">{props.role}</div>
          <div className="text-xs text-muted-foreground">{turns.length} lượt{running ? ` · ${running} đang chạy` : ""}</div>
        </div>
      </div>
      {turns.length === 0 && <div className="text-sm text-muted-foreground">Role này chưa làm lượt nào.</div>}
      {turns.map((t, i) => <TurnCard key={`${t.n}-${t.status}`} turn={t} first={i === 0} />)}
    </div>
  );
}
