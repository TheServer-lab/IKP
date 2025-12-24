#!/usr/bin/env python3
"""
IKP Viewer v0.4
Lightweight runtime for .ikp files
Uses ikp_core for YAML, validation, interpolation, action execution
"""

import sys, os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from ikp_core import load_yaml_text, validate_ikp, interpolate, resolve_path, execute_action

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

class IKPViewer(tk.Tk):
    def __init__(self, ikp_file=None, start_scene=None):
        super().__init__()
        self.title("IKP Viewer v0.4")
        self.geometry("900x600")
        self.vars = {}
        self.scenes = {}
        self.images = []
        self.ikp_file = ikp_file
        self.base_path = os.path.dirname(ikp_file) if ikp_file else os.getcwd()

        if ikp_file:
            self.load_file(ikp_file, start_scene)
        else:
            self.ask_open()

    def ask_open(self):
        path = filedialog.askopenfilename(
            title="Open IKP File",
            filetypes=[("IKP Files", "*.ikp"), ("YAML", "*.yaml;*.yml"), ("All Files", "*.*")]
        )
        if not path:
            self.destroy()
            return
        self.load_file(path)

    def load_file(self, path, start_scene=None):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = load_yaml_text(f.read())
        except Exception as e:
            messagebox.showerror("IKP Error", str(e))
            self.destroy(); return

        errs, warns = validate_ikp(data)
        if errs:
            messagebox.showerror("IKP Validation Error", "\n".join(errs))
            self.destroy(); return

        scenes = data.get("scenes", {})
        if not isinstance(scenes, dict) or not scenes:
            messagebox.showerror("IKP Error", "No scenes found.")
            self.destroy(); return

        self.ikp = data
        self.scenes.clear()
        self.base_path = os.path.dirname(path) or os.getcwd()
        self.ikp_file = path

        for name, scene in scenes.items():
            frame = ttk.Frame(self)
            self.scenes[name] = (frame, scene)

        start = start_scene or data.get("start") or next(iter(scenes))
        self.show_scene(start)

    def _get_vars_map(self):
        result = {}
        for k, v in self.vars.items():
            try:
                if callable(v):
                    result[k] = v()
                elif hasattr(v, "get") and callable(v.get):
                    result[k] = v.get()
                else:
                    result[k] = v
            except Exception:
                try:
                    result[k] = str(v)
                except Exception:
                    result[k] = None
        return result

    def _set_var(self, name, value):
        cur = self.vars.get(name)
        if hasattr(cur, "set") and callable(cur.set):
            try:
                cur.set(value); return
            except Exception:
                pass
        try:
            v = tk.StringVar(value=value)
            self.vars[name] = v
        except Exception:
            self.vars[name] = value

    def _set_progress(self, name, value):
        cur = self.vars.get(name)
        if isinstance(cur, ttk.Progressbar):
            try:
                cur['value'] = float(value); return
            except Exception:
                pass
        if hasattr(cur, "set") and callable(cur.set):
            try:
                cur.set(value); return
            except Exception:
                pass
        self.vars[name] = value

    def _execute_action(self, action):
        context = {
            "show_scene": lambda t: self.show_scene(t) if t else None,
            "set_var": lambda n, v: self._set_var(n, v),
            "set_progress": lambda n, v: self._set_progress(n, v),
            "get_vars": lambda: self._get_vars_map(),
            "handle_action": None,
        }
        execute_action(action, context)

    def show_scene(self, name):
        for f, _ in self.scenes.values():
            f.pack_forget()

        if name not in self.scenes:
            messagebox.showerror("Scene Error", f"Scene '{name}' not found")
            return

        frame, scene = self.scenes[name]
        self.render_scene(frame, scene)
        frame.pack(fill="both", expand=True)

    def render_scene(self, frame, scene):
        for w in frame.winfo_children():
            w.destroy()
        self.images.clear()

        root = ttk.Frame(frame)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        for item in scene.get("ui", []):
            typ = item.get("type", "").lower()

            if typ == "label":
                txt = interpolate(item.get("text", ""), self._get_vars_map())
                ttk.Label(root, text=txt, wraplength=800).pack(anchor="w", pady=4)

            elif typ == "input":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                var = tk.StringVar(value=item.get("default", ""))
                ttk.Entry(root, textvariable=var).pack(fill="x", pady=2)
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "textarea":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                txt = tk.Text(root, height=item.get("rows", 6))
                txt.pack(fill="both", pady=4)
                if "default" in item:
                    txt.insert("1.0", item["default"])
                if item.get("var"):
                    self.vars[item["var"]] = txt

            elif typ == "button":
                label = interpolate(item.get("text", "Button"), self._get_vars_map())
                action = item.get("action") or item.get("goto")
                def act(a=action):
                    self._execute_action(a)
                ttk.Button(root, text=label, command=act).pack(pady=4)

            elif typ == "dropdown":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                opts = item.get("options", [])
                var = tk.StringVar(value=item.get("default") or (opts[0] if opts else ""))
                ttk.Combobox(root, values=opts, textvariable=var).pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "checkbox":
                var = tk.BooleanVar(value=item.get("default", False))
                ttk.Checkbutton(root, text=item.get("label", ""), variable=var).pack(anchor="w")
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "radiogroup":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                var = tk.StringVar(value=item.get("default", ""))
                box = ttk.Frame(root); box.pack(anchor="w")
                for opt in item.get("options", []):
                    ttk.Radiobutton(box, text=opt, variable=var, value=opt).pack(side="left")
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "colorpicker":
                var = tk.StringVar(value=item.get("default", "#ffffff"))
                def pick():
                    c = colorchooser.askcolor()[1]
                    if c:
                        var.set(c)
                row = ttk.Frame(root); row.pack(anchor="w")
                ttk.Button(row, text=item.get("label", "Pick"), command=pick).pack(side="left")
                ttk.Label(row, textvariable=var).pack(side="left", padx=8)
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "slider":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                var = tk.DoubleVar(value=item.get("value", 0))
                ttk.Scale(root, from_=item.get("from", 0), to=item.get("to", 100), variable=var).pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "progress":
                var = tk.DoubleVar(value=item.get("value", 0))
                pb = ttk.Progressbar(root, maximum=item.get("max", 100), variable=var)
                pb.pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            elif typ == "image":
                src = item.get("src")
                if src:
                    path = resolve_path(src, self.base_path)
                    if Image and path and os.path.exists(path):
                        try:
                            img = Image.open(path)
                            img.thumbnail((600,400))
                            tkimg = ImageTk.PhotoImage(img)
                            self.images.append(tkimg)
                            ttk.Label(root, image=tkimg).pack(pady=4)
                        except Exception:
                            ttk.Label(root, text="[Image load failed]").pack()
                    else:
                        ttk.Label(root, text=f"[Image missing: {item.get('src')}]").pack()
                else:
                    ttk.Label(root, text="[Image missing]").pack()

            else:
                ttk.Label(root, text=f"[Unsupported widget: {typ}]").pack()

def main():
    args = sys.argv[1:]
    path = None; start_scene = None; do_validate = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--open" and i+1 < len(args):
            path = args[i+1]; i += 2
        elif a == "--start" and i+1 < len(args):
            start_scene = args[i+1]; i += 2
        elif a == "--validate":
            do_validate = True; i += 1
        elif a in ("-h","--help"):
            print("Usage: python ikp_viewer_v0.4.py --open path. Options: --validate, --start SceneName"); return
        else:
            i += 1

    if path and do_validate:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = load_yaml_text(f.read())
            errs, warns = validate_ikp(data)
            if errs:
                print("VALIDATION ERRORS:")
                for e in errs: print("-", e)
                sys.exit(1)
            else:
                print("No validation errors.")
                if warns:
                    print("WARNINGS:")
                    for w in warns: print("-", w)
                sys.exit(0)
        except Exception as e:
            print("Error:", e)
            sys.exit(2)

    IKPViewer(path, start_scene).mainloop()

if __name__ == "__main__":
    main()
