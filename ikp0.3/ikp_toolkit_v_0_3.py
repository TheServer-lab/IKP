#!/usr/bin/env python3
"""
IKP Toolkit v0.4 (patched to use ikp_core)
Editor + live preview for IKP .ikp files
- Uses ikp_core for shared logic
"""

import sys, os, re, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# local shared core
from ikp_core import load_yaml_text, dump_yaml, validate_ikp, interpolate, resolve_path, execute_action

# Optional image support
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# ---------------------------
# IKP Loader (uses core)
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

    # helper to get variable value for interpolation / safe eval
    def _get_vars_map(self):
        return self.vars

    def _set_var(self, name, value):
        # if exists as tk.Variable, set it; else create a StringVar
        cur = self.vars.get(name)
        if hasattr(cur, "set") and callable(cur.set):
            try:
                cur.set(value)
                return
            except Exception:
                pass
        # replace with StringVar for editability
        try:
            v = tk.StringVar(value=value)
            self.vars[name] = v
        except Exception:
            self.vars[name] = value

    def _set_progress(self, name, value):
        # progress stored either as ttk.Progressbar or tk.Variable
        cur = self.vars.get(name)
        if isinstance(cur, ttk.Progressbar):
            try:
                cur['value'] = float(value)
                return
            except Exception:
                pass
        if hasattr(cur, "set") and callable(cur.set):
            try:
                cur.set(value)
                return
            except Exception:
                pass
        # fallback: store numeric value
        self.vars[name] = value

    # wrapper that bridges execute_action(context) to this instance
    def _execute_action(self, action):
        context = {
            "show_scene": lambda t: self.show_scene(t) if t else None,
            "set_var": lambda n, v: self._set_var(n, v),
            "set_progress": lambda n, v: self._set_progress(n, v),
            "get_vars": lambda: {k: (v.get() if hasattr(v, "get") and callable(v.get) else (v() if callable(v) else v)) for k, v in self.vars.items()},
            "handle_action": None,
        }
        execute_action(action, context)

    def _render_ui(self, parent, ui):
        for item in ui:
            t = item.get("type", "").lower()

            # LABEL / RICHTEXT
            if t in ("label", "richtext"):
                text = interpolate(item.get("text", ""), self.vars)
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
                    # store callable to fetch text on demand
                    self.vars[item["var"]] = lambda w=txt: w.get("1.0", "end-1c")

            # BUTTON
            elif t == "button":
                label = interpolate(item.get("text", "Button"), self.vars)
                action = item.get("action") or item.get("goto")
                def _on_click(a=action):
                    self._execute_action(a)
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
                    # store Progressbar widget itself to update later
                    self.vars[item["var"]] = pb

            # IMAGE
            elif t == "image":
                src = item.get("src")
                if src:
                    path = resolve_path(src, self.base_path)
                    if Image and path and os.path.exists(path):
                        try:
                            img = Image.open(path)
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

            else:
                ttk.Label(parent, text=f"[Unsupported: {t}]").pack()

# ---------------------------
# Editor app
# ---------------------------
class IKPEditor(tk.Tk):
    def __init__(self, open_path=None):
        super().__init__()
        self.title("IKP Toolkit v0.4 (Editor)")
        self.geometry("1200x700")
        self.file_path = open_path
        self.base_path = os.path.dirname(open_path) if open_path else os.getcwd()

        # toolbar
        toolbar = ttk.Frame(self); toolbar.pack(side="top", fill="x", padx=4, pady=2)
        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Save", command=self.save_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Save As...", command=self.save_file_as).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Validate", command=self.show_validation).pack(side="left", padx=2)

        self.text = tk.Text(self, font=("Courier", 11)); self.text.pack(side="left", fill="both", expand=True)
        right_col = ttk.Frame(self); right_col.pack(side="right", fill="both", expand=True)

        self.preview = ttk.Frame(right_col); self.preview.pack(fill="both", expand=True)
        self.lint_area = tk.Text(right_col, height=10, font=("Courier", 10), foreground="red"); self.lint_area.pack(fill="x")
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
                    self.text.delete("1.0", "end"); self.text.insert("1.0", f.read()); return
            except Exception:
                pass
        self.text.insert("1.0", sample)

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("IKP files","*.ikp"), ("YAML","*.yaml;*.yml"), ("All","*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.file_path = path; self.base_path = os.path.dirname(path)
            self.text.delete("1.0", "end"); self.text.insert("1.0", content); self.update_preview()
        except Exception as e:
            messagebox.showerror("Open Error", str(e))

    def save_file(self):
        if not self.file_path:
            return self.save_file_as()
        try:
            content = self.text.get("1.0", "end-1c")
            try:
                data = load_yaml_text(content) or {}
            except Exception as e:
                if not messagebox.askyesno("YAML parse", f"YAML parse failed: {e}\nSave raw anyway?"):
                    return
                data = {}
            if not isinstance(data, dict):
                data = {}
            if "ikp" not in data:
                data["ikp"] = "0.4"
            if "meta" not in data:
                data["meta"] = {"title": "Untitled"}
            final = dump_yaml(data)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(final)
            messagebox.showinfo("Saved", f"Saved to {self.file_path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def save_file_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".ikp", filetypes=[("IKP files","*.ikp")])
        if not path:
            return
        self.file_path = path; self.base_path = os.path.dirname(path); self.save_file()

    def show_validation(self):
        content = self.text.get("1.0", "end-1c")
        try:
            data = load_yaml_text(content) or {}
        except Exception as e:
            self.lint_area.delete("1.0", "end"); self.lint_area.insert("1.0", f"YAML parse error: {e}"); return
        errs, warns = validate_ikp(data)
        out = ""
        if errs: out += "ERRORS:\n" + "\n".join(f"- {e}" for e in errs) + "\n"
        if warns: out += "WARNINGS:\n" + "\n".join(f"- {w}" for w in warns) + "\n"
        if not out: out = "No issues found."
        self.lint_area.delete("1.0", "end"); self.lint_area.insert("1.0", out)

    def update_preview(self):
        for w in self.preview.winfo_children(): w.destroy()
        try:
            content = self.text.get("1.0", "end-1c")
            data = load_yaml_text(content) or {}
            errs, warns = validate_ikp(data)
            if errs:
                ttk.Label(self.preview, text="Validation failed:", foreground="red").pack(anchor="w")
                for e in errs: ttk.Label(self.preview, text=e, foreground="red").pack(anchor="w")
                return
            loader = IKPLoader(self.preview, data, base_path=self.base_path)
            loader.pack(fill="both", expand=True)
        except Exception as e:
            ttk.Label(self.preview, text=f"Preview error: {e}", foreground="red").pack(anchor="w")
            traceback.print_exc()

# ---------------------------
if __name__ == "__main__":
    # CLI usage: --open path
    open_path = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--open":
        open_path = sys.argv[2]
    IKPEditor(open_path).mainloop()
