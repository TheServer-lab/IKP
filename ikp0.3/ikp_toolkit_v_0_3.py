#!/usr/bin/env python3
"""
IKP Toolkit v0.3 -> v0.4-patched
Editor + live preview for IKP .ikp files
- Writes ikp: 0.4 metadata on save
- Structured actions support (goto, set, progress, if (basic))
- Lightweight validation/lint in preview
- Image src resolution relative to opened file
"""

import sys, os, re, yaml, traceback
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox

# Optional image support
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# ---------------------------
# Utilities
# ---------------------------

def safe_load_yaml_text(text):
    try:
        return yaml.safe_load(text)
    except Exception as e:
        raise RuntimeError(f"YAML parse error: {e}")

def safe_dump_yaml(data):
    return yaml.dump(data, sort_keys=False, allow_unicode=True)

# ---------------------------
# Validation
# ---------------------------
def validate_ikp(data):
    errors = []
    warnings = []
    if not isinstance(data, dict):
        errors.append("Root must be a mapping (YAML dictionary).")
        return errors, warnings
    if "ikp" in data:
        # version present - could validate supported versions
        pass
    if "scenes" not in data or not isinstance(data["scenes"], dict):
        errors.append("`scenes` must be a mapping with at least one scene.")
        return errors, warnings
    for sname, scene in data["scenes"].items():
        if not isinstance(scene, dict):
            errors.append(f"Scene '{sname}' must be a mapping/object.")
            continue
        ui = scene.get("ui")
        if ui is None:
            warnings.append(f"Scene '{sname}' has no `ui` list.")
            continue
        if not isinstance(ui, list):
            errors.append(f"Scene '{sname}': `ui` must be a list.")
            continue
        for i, item in enumerate(ui):
            if not isinstance(item, dict):
                errors.append(f"Scene '{sname}' ui[{i}] must be a mapping.")
                continue
            if "type" not in item:
                errors.append(f"Scene '{sname}' ui[{i}] missing required field 'type'.")
    return errors, warnings

# ---------------------------
# Editor / Loader
# ---------------------------
class IKPLoader(ttk.Frame):
    def __init__(self, parent, ikp_data, base_path=None):
        super().__init__(parent)
        self.ikp = ikp_data or {}
        self.vars = {}
        self.frames = {}
        self.curr_scene = None
        self._image_cache = []  # keep references
        self.base_path = base_path or os.getcwd()
        self._build()

    # -----------------------
    def _build(self):
        for name, scene in (self.ikp.get("scenes") or {}).items():
            self.frames[name] = (ttk.Frame(self), scene)

        start = self.ikp.get("start")
        if start in self.frames:
            self.show_scene(start)
        elif self.frames:
            self.show_scene(next(iter(self.frames)))

    def show_scene(self, name):
        if name not in self.frames:
            return
        if self.curr_scene:
            self.frames[self.curr_scene][0].pack_forget()
        frame, scene = self.frames[name]
        self.curr_scene = name
        for w in frame.winfo_children():
            w.destroy()
        self._render_ui(frame, scene.get("ui", []))
        frame.pack(fill="both", expand=True, padx=8, pady=8)

    # -----------------------
    def _interp(self, text):
        if not isinstance(text, str):
            return text
        # simple variable interpolation using ${var}
        def repl(m):
            key = m.group(1)
            v = self.vars.get(key)
            try:
                if callable(v):
                    val = v()
                elif isinstance(v, tk.Variable):
                    val = v.get()
                elif isinstance(v, tk.Text):
                    val = v.get("1.0", "end-1c")
                else:
                    val = v
            except Exception:
                val = v
            return "" if val is None else str(val)
        return re.sub(r"\$\{([a-zA-Z0-9_]+)\}", repl, text)

    # -----------------------
    def set_progress(self, name, value):
        pb = self.vars.get(name)
        if isinstance(pb, ttk.Progressbar):
            try:
                pb['value'] = float(value)
            except Exception:
                pass
        elif isinstance(self.vars.get(name), tk.Variable):
            try:
                self.vars[name].set(float(value))
            except Exception:
                pass

    # -----------------------
    def _execute_action(self, action):
        """Action may be:
           - None
           - string (legacy) e.g., "progress(p1,80)"
           - dict (structured) according to spec
        """
        if not action:
            return
        # Legacy string handling (best-effort)
        if isinstance(action, str):
            try:
                if action.startswith("set(") and action.endswith(")"):
                    k, v = action[4:-1].split(",", 1)
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    self.vars[k] = tk.StringVar(value=v)
                elif action.startswith("progress(") and action.endswith(")"):
                    n, v = action[9:-1].split(",", 1)
                    self.set_progress(n.strip(), float(v))
                elif action.startswith("goto(") and action.endswith(")"):
                    target = action[5:-1].strip()
                    self.show_scene(target)
            except Exception:
                pass
            return

        if not isinstance(action, dict):
            return

        typ = action.get("type")
        if typ == "goto":
            target = action.get("target")
            if target:
                self.show_scene(target)
        elif typ == "set":
            var = action.get("var")
            val = action.get("value")
            if var is not None:
                if isinstance(val, str):
                    val = self._interp(val)
                # store as tk.StringVar for editability
                self.vars[var] = tk.StringVar(value=val)
        elif typ == "progress":
            tgt = action.get("target") or action.get("var")
            val = action.get("value", 0)
            self.set_progress(tgt, val)
        elif typ == "if":
            # very limited evaluator to avoid arbitrary code execution
            cond = action.get("condition", "")
            cond_resolved = self._interp(cond)
            # allow only digits, whitespace, comparison operators and period and parentheses
            if re.match(r'^[0-9\.\s\<\>\=\!\(\)\+\-*/%]+$', cond_resolved):
                try:
                    ok = eval(cond_resolved, {}, {})
                except Exception:
                    ok = False
            else:
                ok = False
            branch = action.get("then") if ok else action.get("else")
            if isinstance(branch, dict):
                self._execute_action(branch)
            elif isinstance(branch, list):
                for a in branch:
                    self._execute_action(a)
        else:
            # unknown action types ignored for now
            # you may log or show warning
            print("Unknown action:", typ)

    # -----------------------
    def _render_ui(self, parent, ui):
        for item in ui:
            t = item.get("type", "").lower()

            # LABEL / RICHTEXT
            if t in ("label", "richtext"):
                text = self._interp(item.get("text", ""))
                ttk.Label(parent, text=text, wraplength=800).pack(anchor="w", pady=4)

            # INPUT
            elif t == "input":
                if item.get("label"):
                    ttk.Label(parent, text=item["label"]).pack(anchor="w")
                var = tk.StringVar(value=item.get("default", ""))
                ent = ttk.Entry(parent, textvariable=var)
                ent.pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # TEXTAREA
            elif t == "textarea":
                ttk.Label(parent, text=item.get("label", "")).pack(anchor="w")
                txt = tk.Text(parent, height=item.get("rows", 5))
                if "default" in item:
                    txt.insert("1.0", item.get("default", ""))
                txt.pack(fill="both")
                if item.get("var"):
                    # store a callable to fetch text
                    self.vars[item["var"]] = lambda w=txt: w.get("1.0", "end-1c")

            # BUTTON
            elif t == "button":
                label = self._interp(item.get("text", "Button"))
                goto = item.get("action")  # structured action or legacy string
                def _on_click(a=goto):
                    # perform action
                    self._execute_action(a)
                    # if action was a simple goto with 'target' specified, _execute_action will handle it
                ttk.Button(parent, text=label, command=_on_click).pack(pady=4)

            # SLIDER
            elif t == "slider":
                ttk.Label(parent, text=item.get("label", "")).pack(anchor="w")
                var = tk.DoubleVar(value=float(item.get("default", 0)))
                ttk.Scale(parent, from_=item.get("from", 0), to=item.get("to", 100), variable=var).pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # PROGRESS
            elif t == "progress":
                pb = ttk.Progressbar(parent, maximum=item.get("max", 100))
                try:
                    pb['value'] = item.get("value", 0)
                except Exception:
                    pass
                pb.pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = pb

            # IMAGE
            elif t == "image":
                src = item.get("src")
                if src:
                    # resolve relative to base_path
                    if not os.path.isabs(src):
                        src = os.path.join(self.base_path, src)
                    if Image and os.path.exists(src):
                        try:
                            img = Image.open(src)
                            img.thumbnail((item.get("width", 800), item.get("height", 400)))
                            tkimg = ImageTk.PhotoImage(img)
                            self._image_cache.append(tkimg)
                            ttk.Label(parent, image=tkimg).pack(pady=4)
                        except Exception:
                            ttk.Label(parent, text="[Image load failed]").pack()
                    else:
                        ttk.Label(parent, text=f"[image missing: {item.get('src')}]").pack()
                else:
                    ttk.Label(parent, text="[image missing]").pack()

            # TABS
            elif t == "tabs":
                nb = ttk.Notebook(parent)
                nb.pack(fill="both", expand=True)
                for tab in item.get("tabs", []):
                    f = ttk.Frame(nb)
                    nb.add(f, text=tab.get("label", "Tab"))
                    self._render_ui(f, tab.get("ui", []))

            # ACCORDION
            elif t == "accordion":
                for sec in item.get("sections", []):
                    head = ttk.Frame(parent)
                    head.pack(fill="x")
                    body = ttk.Frame(parent)
                    body.pack_forget()
                    ttk.Label(head, text=sec.get("title", "Section")).pack(side="left")
                    btn = ttk.Button(head, text="+")
                    btn.pack(side="right")
                    def toggle(b=btn, c=body):
                        if c.winfo_ismapped():
                            c.pack_forget(); b.config(text="+")
                        else:
                            c.pack(fill="x"); b.config(text="-")
                    btn.config(command=toggle)
                    self._render_ui(body, sec.get("ui", []))

            # CANVAS
            elif t == "canvas":
                c = tk.Canvas(parent, width=item.get("width", 400), height=item.get("height", 200), bg=item.get("bg", "#fff"))
                c.pack()
                ttk.Button(parent, text="Clear", command=lambda x=c: x.delete("all")).pack()

            else:
                ttk.Label(parent, text=f"[Unsupported: {t}]").pack()

# ---------------------------
# Editor (simplified: loader-focused build)
# ---------------------------
class IKPEditor(tk.Tk):
    def __init__(self, open_path=None):
        super().__init__()
        self.title("IKP Toolkit v0.4 (Editor)")
        self.geometry("1200x700")
        self.file_path = open_path
        self.base_path = os.path.dirname(open_path) if open_path else os.getcwd()

        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=4, pady=2)
        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Save", command=self.save_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Save As...", command=self.save_file_as).pack(side="left", padx=2)
        ttk.Label(toolbar, text=" ").pack(side="left", padx=6)
        ttk.Button(toolbar, text="Validate", command=self.show_validation).pack(side="left", padx=2)

        self.text = tk.Text(self, font=("Courier", 11))
        self.text.pack(side="left", fill="both", expand=True)
        right_col = ttk.Frame(self)
        right_col.pack(side="right", fill="both", expand=True)

        self.preview = ttk.Frame(right_col)
        self.preview.pack(fill="both", expand=True)

        self.lint_area = tk.Text(right_col, height=10, font=("Courier", 10), foreground="red")
        self.lint_area.pack(fill="x")
        self.text.bind("<KeyRelease>", lambda e: self.update_preview())
        self._load_sample()
        self.update_preview()

    def _load_sample(self):
        sample = """ikp: 0.4
meta:
  title: IKP v0.4 Demo
start: Main
scenes:
  Main:
    ui:
      - type: label
        text: "IKP v0.4 Demo"
      - type: image
        src: sample.png
      - type: input
        label: Name
        var: name
      - type: button
        text: Continue
        action:
          type: goto
          target: Hello
  Hello:
    ui:
      - type: label
        text: "Hello ${name}"
"""
        if self.file_path:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.text.delete("1.0", "end")
                    self.text.insert("1.0", f.read())
                return
            except Exception:
                pass
        self.text.insert("1.0", sample)

    # -----------------------
    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("IKP files","*.ikp"), ("YAML","*.yaml;*.yml"), ("All","*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.file_path = path
            self.base_path = os.path.dirname(path)
            self.text.delete("1.0", "end")
            self.text.insert("1.0", content)
            self.update_preview()
        except Exception as e:
            messagebox.showerror("Open Error", str(e))

    def save_file(self):
        if not self.file_path:
            return self.save_file_as()
        try:
            content = self.text.get("1.0", "end-1c")
            # ensure ikp root exists and version set
            try:
                data = safe_load_yaml_text(content) or {}
            except Exception as e:
                # if parse error, ask user whether to save raw
                if not messagebox.askyesno("YAML parse", f"YAML parse failed: {e}\nSave raw anyway?"):
                    return
                data = {}
            # ensure ikp version and meta exist
            if not isinstance(data, dict):
                data = {}
            if "ikp" not in data:
                data["ikp"] = "0.4"
            if "meta" not in data:
                data["meta"] = {"title": "Untitled"}
            # try to preserve original text where possible: write canonical YAML
            final = safe_dump_yaml(data)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(final)
            messagebox.showinfo("Saved", f"Saved to {self.file_path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def save_file_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".ikp", filetypes=[("IKP files","*.ikp")])
        if not path:
            return
        self.file_path = path
        self.base_path = os.path.dirname(path)
        self.save_file()

    def show_validation(self):
        content = self.text.get("1.0", "end-1c")
        try:
            data = safe_load_yaml_text(content) or {}
        except Exception as e:
            self.lint_area.delete("1.0", "end")
            self.lint_area.insert("1.0", f"YAML parse error: {e}")
            return
        errs, warns = validate_ikp(data)
        out = ""
        if errs:
            out += "ERRORS:\n" + "\n".join(f"- {e}" for e in errs) + "\n"
        if warns:
            out += "WARNINGS:\n" + "\n".join(f"- {w}" for w in warns) + "\n"
        if not out:
            out = "No issues found."
        self.lint_area.delete("1.0", "end")
        self.lint_area.insert("1.0", out)

    # -----------------------
    def update_preview(self):
        for w in self.preview.winfo_children():
            w.destroy()
        try:
            content = self.text.get("1.0", "end-1c")
            data = safe_load_yaml_text(content) or {}
            errs, warns = validate_ikp(data)
            if errs:
                ttk.Label(self.preview, text="Validation failed:", foreground="red").pack(anchor="w")
                for e in errs:
                    ttk.Label(self.preview, text=e, foreground="red").pack(anchor="w")
                return
            loader = IKPLoader(self.preview, data, base_path=self.base_path)
            loader.pack(fill="both", expand=True)
        except Exception as e:
            ttk.Label(self.preview, text=f"Preview error: {e}", foreground="red").pack(anchor="w")
            traceback.print_exc()

# ---------------------------
if __name__ == "__main__":
    # CLI: python ikp_toolkit_v_0_3.py [--open path]
    open_path = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--open":
        open_path = sys.argv[2]
    IKPEditor(open_path).mainloop()
