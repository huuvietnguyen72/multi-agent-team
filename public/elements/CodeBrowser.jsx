// Khung "Mã nguồn" kiểu IDE: cây file bên trái, code bên phải có số dòng và tô màu cú pháp. Khung hẹp (dưới 560px)
// thì cây nằm trên, gập lại được, code ngay bên dưới. Props do ui/app.py dựng (_code_props); bấm file hay đổi bản đầu
// ra thì gọi action code_read / code_tree và nhận dữ liệu trả về, không vẽ lại cả khung nên cây giữ nguyên trạng thái.
import { useEffect, useMemo, useRef, useState } from "react";

// ---------- tô màu cú pháp (đơn giản, đủ đọc) ----------
const WORDS = {
  python: "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield self",
  javascript: "async await break case catch class const continue default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while yield",
  java: "abstract boolean break byte case catch char class continue default do double else enum extends final finally float for if implements import instanceof int interface long new null package private protected public return short static super switch this throw throws true false try void while var record",
  sql: "select from where insert into values update set delete create table primary key foreign references not null unique default index on and or join left inner order by group having limit integer text real boolean varchar check",
  bash: "if then else elif fi for while do done case esac function in export local return echo cd",
};
WORDS.typescript = WORDS.javascript + " interface type enum implements private public readonly as";
const HASH = new Set(["python", "bash", "yaml", "toml", "ini"]);
const SLASH = new Set(["javascript", "typescript", "java"]);
const STR = String.raw`"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'`;

function rules(lang) {
  const r = [];
  if (lang === "markdown") return [["h", String.raw`^#{1,6} .*$`], ["s", "`[^`\\n]+`"], ["c", "^```.*$"]];
  if (lang === "html" || lang === "xml")
    return [["c", "<!--[\\s\\S]*?-->"], ["t", "</?[\\w:-]+|/?>"], ["a", "[\\w:-]+(?==)"], ["s", STR]];
  if (HASH.has(lang)) r.push(["c", "#.*$"]);
  if (SLASH.has(lang)) r.push(["c", "//.*$"]);
  if (SLASH.has(lang) || lang === "css" || lang === "sql") r.push(["c", "/\\*[\\s\\S]*?\\*/"]);
  if (lang === "sql") r.push(["c", "--.*$"]);
  if (lang === "javascript" || lang === "typescript") r.push(["s", "`(?:\\\\.|[^`\\\\])*`"]);
  r.push(["s", STR]);
  if (lang === "json") r.push(["k", "\\b(?:true|false|null)\\b"]);
  if (lang === "java" || lang === "python") r.push(["a", "@[\\w.]+"]);
  r.push(["n", "\\b\\d+(?:\\.\\d+)?\\b"]);
  if (WORDS[lang]) r.push(["k", `\\b(?:${WORDS[lang].split(" ").join("|")})\\b`]);
  return r;
}

function highlight(text, lang) {
  // -> mảng dòng, mỗi dòng là mảng [lớp, chữ]
  const rs = rules(lang);
  const lines = [[]];
  const push = (cls, s) => s.split("\n").forEach((part, i) => {
    if (i) lines.push([]);
    if (part) lines[lines.length - 1].push([cls, part]);
  });
  if (!rs.length || text.length > 150000) {
    push("", text);
    if (lines.length > 1 && !lines[lines.length - 1].length) lines.pop();
    return lines;
  }
  const re = new RegExp(rs.map(([, p]) => `(${p})`).join("|"), lang === "sql" ? "gmi" : "gm");
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (!m[0]) { re.lastIndex++; continue; }
    push("", text.slice(last, m.index));
    push(`cb-${rs[m.slice(1).findIndex(g => g !== undefined)][0]}`, m[0]);
    last = m.index + m[0].length;
  }
  push("", text.slice(last));
  if (lines.length > 1 && !lines[lines.length - 1].length) lines.pop();  // dòng trống cuối file
  return lines;
}

// ---------- cây file ----------
function buildTree(files) {
  const root = { dirs: {}, files: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let node = root;
    for (const part of parts.slice(0, -1)) node = node.dirs[part] = node.dirs[part] || { dirs: {}, files: [] };
    node.files.push({ ...f, name: parts[parts.length - 1] });
  }
  return root;
}

const size = n => n >= 1024 ? `${(n / 1024).toFixed(n >= 10240 ? 0 : 1)} KB` : `${n} B`;
const row = "flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left hover:bg-accent";

function Items({ node, prefix, depth, ctx }) {
  return (
    <ul>
      {Object.keys(node.dirs).sort().map(name => {
        const path = prefix ? `${prefix}/${name}` : name;
        const isOpen = ctx.filter || (ctx.open[path] ?? depth < 1);
        return (
          <li key={path}>
            <button type="button" className={row} style={{ paddingLeft: depth * 12 + 6 }} aria-expanded={isOpen}
              onClick={() => ctx.toggle(path, !isOpen)}>
              <span className="text-muted-foreground" style={{ width: 10 }}>{isOpen ? "▾" : "▸"}</span>
              <span className="font-medium">{name}</span>
            </button>
            {isOpen && <Items node={node.dirs[name]} prefix={path} depth={depth + 1} ctx={ctx} />}
          </li>
        );
      })}
      {node.files.sort((a, b) => a.name.localeCompare(b.name)).map(f => (
        <li key={f.path}>
          <button type="button" title={`${f.path} · ${size(f.size)}`} onClick={() => ctx.pick(f.path)}
            className={`${row} ${f.path === ctx.current ? "bg-accent font-semibold" : ""}`}
            style={{ paddingLeft: depth * 12 + 22 }}>
            <span className="truncate">{f.name}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

// ---------- trạng thái giữ qua các lần vẽ lại khung (trong lúc chạy, mỗi file mới làm khung vẽ lại) ----------
const KEY = "codebrowser-ui";
const loadUi = () => { try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch { return {}; } };
const saveUi = v => { try { sessionStorage.setItem(KEY, JSON.stringify(v)); } catch { /* không lưu được thì thôi */ } };

export default function CodeBrowser() {
  const saved = useMemo(loadUi, []);
  const [source, setSource] = useState(props.source);
  const [files, setFiles] = useState(props.files);
  const [truncated, setTruncated] = useState(props.truncated);
  const [file, setFile] = useState(props.file || null);   // {path, content, language, size} | {path, error}
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(saved.open || {});
  const [wrap, setWrap] = useState(!!saved.wrap);
  const [copied, setCopied] = useState(false);
  const [wide, setWide] = useState(true);
  const [showTree, setShowTree] = useState(!props.file);
  const box = useRef(null);

  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setWide(e.contentRect.width >= 560));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => saveUi({ open, wrap }), [open, wrap]);

  const q = filter.trim().toLowerCase();
  const shown = useMemo(() => files.filter(f => !q || f.path.toLowerCase().includes(q)), [files, q]);
  const root = useMemo(() => buildTree(shown), [shown]);
  const lines = useMemo(() => file && !file.error ? highlight(file.content, file.language) : [], [file]);

  async function pick(path) {
    if (!wide) setShowTree(false);  // khung hẹp: chọn xong thì gập cây để code có chỗ
    setLoading(true);
    try {
      const res = await callAction({ name: "code_read", payload: { source, path } });
      setFile(res?.response || { path, error: "Không đọc được file." });
    } catch {
      setFile({ path, error: "Không đọc được file." });
    } finally {
      setLoading(false);
    }
  }

  async function changeSource(id) {
    setSource(id);
    setLoading(true);
    try {
      const res = await callAction({ name: "code_tree", payload: { source: id } });
      const r = res?.response || {};
      setFiles(r.files || []);
      setTruncated(!!r.truncated);
      if (file && !(r.files || []).some(f => f.path === file.path)) setFile(null);
      else if (file) {
        const again = await callAction({ name: "code_read", payload: { source: id, path: file.path } });
        setFile(again?.response || null);
      }
    } finally {
      setLoading(false);
    }
  }

  function copy() {
    navigator.clipboard?.writeText(file.content).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); });
  }

  const ctx = { open, filter: !!q, current: file?.path, pick, toggle: (p, v) => setOpen(o => ({ ...o, [p]: v })) };
  const btn = "rounded-md border px-2 py-1 hover:bg-accent";

  const tree = (
    <div className="flex flex-col gap-2" style={wide ? { minHeight: 0, borderRight: "1px solid hsl(var(--border))", paddingRight: 8 }
      : { maxHeight: "38vh", minHeight: 0 }}>
      <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Lọc theo tên file…"
        className="rounded-md border bg-background px-2 py-1" aria-label="Lọc theo tên file" />
      <div className="flex-1 overflow-auto" style={{ minHeight: 0 }}>
        {files.length === 0 ? <p className="p-2 text-muted-foreground">Chưa có file nào. Team ghi code vào đây khi chạy.</p>
          : shown.length ? <Items node={root} prefix="" depth={0} ctx={ctx} />
          : <p className="p-2 text-muted-foreground">Không có file nào khớp.</p>}
      </div>
      <p className="text-xs text-muted-foreground">{files.length} file{truncated ? " (chỉ hiện một phần)" : ""}</p>
    </div>
  );

  const crumbs = file?.path.split("/") || [];
  const code = (
    <div className="flex flex-col overflow-hidden rounded-md border" style={{ minHeight: 0, minWidth: 0, flex: 1 }}>
      {file ? <>
        <div className="flex flex-wrap items-center gap-2 border-b" style={{ padding: "6px 8px" }}>
          <span className="flex-1 truncate font-mono text-xs" style={{ minWidth: 160 }} title={file.path}>
            {crumbs.slice(0, -1).map((c, i) => <span key={i} className="text-muted-foreground">{c} / </span>)}
            <span className="font-semibold">{crumbs[crumbs.length - 1]}</span>
          </span>
          {!file.error && <button type="button" className={`${btn} text-xs`} aria-pressed={wrap} onClick={() => setWrap(w => !w)}>
            {wrap ? "Không xuống dòng" : "Xuống dòng"}</button>}
          {!file.error && <button type="button" className={`${btn} text-xs`} onClick={copy}>{copied ? "Đã chép" : "Sao chép"}</button>}
        </div>
        {file.error ? <p className="p-3 text-muted-foreground">{file.error}</p> :
          <div className="cb-code flex-1 overflow-auto font-mono text-xs"
            style={{ minHeight: 0, padding: "4px 0", lineHeight: 1.6, opacity: loading ? 0.5 : 1 }}>
            {lines.map((toks, i) => (
              <div key={i} className="flex" style={{ minWidth: wrap ? 0 : "max-content" }}>
                <span className="cb-ln text-muted-foreground" style={{ minWidth: `${String(lines.length).length + 3}ch`,
                  padding: "0 12px 0 8px", textAlign: "right", userSelect: "none", flexShrink: 0 }}>{i + 1}</span>
                <span style={{ minWidth: 0, paddingRight: 16, whiteSpace: wrap ? "pre-wrap" : "pre", wordBreak: wrap ? "break-word" : "normal" }}>
                  {toks.length ? toks.map(([c, s], j) => c ? <span key={j} className={c}>{s}</span> : s) : " "}
                </span>
              </div>
            ))}
          </div>}
        {!file.error && <div className="border-t text-xs text-muted-foreground" style={{ padding: "3px 8px" }}>
          {lines.length} dòng · {size(file.size || 0)} · {file.language}</div>}
      </> : <div className="flex flex-1 items-center justify-center p-6 text-center text-muted-foreground">
        {loading ? "Đang mở…" : files.length ? "Chọn một file để xem code." : "Chưa có code."}
      </div>}
    </div>
  );

  return (
    <div ref={box} className="flex flex-col gap-2 text-sm" style={{ height: "calc(100vh - 150px)", minHeight: 420 }}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-muted-foreground" htmlFor="code-source">Bản</label>
        <select id="code-source" value={source} onChange={e => changeSource(e.target.value)}
          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1" style={{ maxWidth: 320 }}>
          {props.sources.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <button type="button" onClick={() => changeSource(source)} className={btn} title="Đọc lại thư mục">Làm mới</button>
      </div>
      {wide ? (
        <div className="grid flex-1 gap-2" style={{ minHeight: 0, gridTemplateColumns: "minmax(180px, 32%) minmax(0, 1fr)" }}>
          {tree}
          {code}
        </div>
      ) : <>
        <button type="button" className={`${btn} text-left`} onClick={() => setShowTree(s => !s)} aria-expanded={showTree}>
          {showTree ? "▾" : "▸"} Cây file ({files.length})
        </button>
        {showTree && tree}
        {code}
      </>}
    </div>
  );
}
