// Khung "Mã nguồn": chọn bản đầu ra (lượt mới nhất hoặc lượt cũ trong output_history), cây thư mục, bấm file để xem.
// Props do ui/app.py dựng (_code_props). Nội dung file hiện ngay bên dưới bằng phần tử Text của Chainlit (tô màu cú pháp).
import { useMemo, useState } from "react";

function buildTree(files) {
  const root = { dirs: {}, files: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let node = root;
    for (const part of parts.slice(0, -1)) {
      node.dirs[part] = node.dirs[part] || { dirs: {}, files: [] };
      node = node.dirs[part];
    }
    node.files.push({ ...f, name: parts[parts.length - 1] });
  }
  return root;
}

function size(n) {
  return n >= 1024 ? `${(n / 1024).toFixed(n >= 10240 ? 0 : 1)} KB` : `${n} B`;
}

function Dir({ name, node, prefix, depth, open, toggle, filter }) {
  const path = prefix ? `${prefix}/${name}` : name;
  const isOpen = filter || open[path] !== false && (open[path] || depth < 1);
  return (
    <li>
      <button type="button" onClick={() => toggle(path, !isOpen)} aria-expanded={isOpen}
        className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left hover:bg-accent"
        style={{ paddingLeft: depth * 14 + 6 }}>
        <span className="text-muted-foreground" style={{ width: 10 }}>{isOpen ? "▾" : "▸"}</span>
        <span className="font-medium">{name}/</span>
      </button>
      {isOpen && <Items node={node} prefix={path} depth={depth + 1} open={open} toggle={toggle} filter={filter} />}
    </li>
  );
}

function Items({ node, prefix, depth, open, toggle, filter }) {
  return (
    <ul>
      {Object.keys(node.dirs).sort().map(d =>
        <Dir key={d} name={d} node={node.dirs[d]} prefix={prefix} depth={depth} open={open} toggle={toggle} filter={filter} />)}
      {node.files.sort((a, b) => a.name.localeCompare(b.name)).map(f => {
        const active = f.path === props.open;
        return (
          <li key={f.path}>
            <button type="button" title={f.path}
              onClick={() => callAction({ name: "code_open", payload: { source: props.source, path: f.path } })}
              className={`flex w-full items-center justify-between gap-2 rounded px-1.5 py-0.5 text-left hover:bg-accent ${active ? "bg-accent font-semibold" : ""}`}
              style={{ paddingLeft: depth * 14 + 22 }}>
              <span className="truncate">{f.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{size(f.size)}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function CodeBrowser() {
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState({});
  const toggle = (path, value) => setOpen(o => ({ ...o, [path]: value }));
  const q = filter.trim().toLowerCase();
  const files = useMemo(() => props.files.filter(f => !q || f.path.toLowerCase().includes(q)), [props.files, q]);
  const root = useMemo(() => buildTree(files), [files]);

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-muted-foreground" htmlFor="code-source">Bản đầu ra</label>
        <select id="code-source" value={props.source}
          onChange={e => callAction({ name: "code_source", payload: { source: e.target.value } })}
          className="rounded-md border bg-background px-2 py-1">
          {props.sources.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <button type="button" onClick={() => callAction({ name: "code_source", payload: { source: props.source } })}
          className="rounded-md border px-2 py-1 hover:bg-accent" title="Đọc lại thư mục">Làm mới</button>
      </div>
      <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Lọc theo tên file…"
        className="rounded-md border bg-background px-2 py-1" aria-label="Lọc theo tên file" />
      {props.files.length === 0
        ? <p className="text-muted-foreground">Chưa có file nào. Team ghi code vào đây khi chạy.</p>
        : <div className="overflow-auto rounded-md border p-1" style={{ maxHeight: props.open ? "32vh" : "70vh" }}>
            {files.length ? <Items node={root} prefix="" depth={0} open={open} toggle={toggle} filter={!!q} />
              : <p className="p-2 text-muted-foreground">Không có file nào khớp.</p>}
          </div>}
      <p className="text-xs text-muted-foreground">
        {props.files.length} file{props.truncated ? " (chỉ hiện một phần)" : ""}
        {props.open ? <> · đang xem <span className="font-mono">{props.open}</span></> : " · bấm vào file để xem code"}
      </p>
    </div>
  );
}
