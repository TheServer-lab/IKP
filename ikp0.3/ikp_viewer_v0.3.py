#!/usr/bin/env python3
"""
IKP Viewer v0.3 -> v0.4-patched
Lightweight runtime for .ikp files
- Structured action support (goto, set, progress, if (basic))
- Interpolation consistent with Toolkit
- Image paths resolved relative to file
- CLI: --open path, --validate, --start SceneName
"""

import sys, os, yaml, re, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# -------------------------
# Helpers
# -------------------------

def safe_load_ikp(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Root IKP node must be a mapping")
    return data

def interpolate(text, vars_map):
    if not isinstance(text, str):
        return text
    def repl(m):
        key = m.group(1)
        v = vars_map.get(key)
        try:
            if isinstance(v, tk.Variable):
                return str(v.get())
            elif isinstance(v, tk.Text):
                return v.get("1.0", "end-1c").strip()
            elif callable(v):
                return str(v())
            elif v is None:
                return ""
            else:
                return str(v)
        except Exception:
            return ""
    return re.sub(r"\$\{([a-zA-Z0-9_]+)\}", repl, text)

def validate_ikp(data):
    errors = []
    warnings = []
    if not isinstance(data, dict):
        errors.append("Root must be a mapping")
        return errors, warnings
    if "scenes" not in data or not isinstance(data["scenes"], dict):
        errors.append("`scenes` must be a mapping")
        return errors, warnings
    for sname, scene in data["scenes"].items():
        if "ui" not in scene or not isinstance(scene["ui"], list):
            warnings.append(f"Scene {sname}: missing `ui` list or not a list.")
    return errors, warnings

# -------------------------
# Viewer
# -------------------------
class IKPViewer(tk.Tk):
    def __init__(self, ikp_file=None, start_scene=None):
        super().__init__()
        self.title("IKP Viewer v0.4")
        self.geometry("900x600")
        self.vars = {}
        self.scenes = {}
        self.images = []  # keep refs
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
            data = safe_load_ikp(path)
        except Exception as e:
            messagebox.showerror("IKP Error", str(e))
            self.destroy()
            return

        errs, warns = validate_ikp(data)
        if errs:
            messagebox.showerror("IKP Validation Error", "\n".join(errs))
            self.destroy()
            return

        scenes = data.get("scenes", {})
        if not isinstance(scenes, dict) or not scenes:
            messagebox.showerror("IKP Error", "No scenes found.")
            self.destroy()
            return

        self.ikp = data
        self.scenes.clear()
        self.base_path = os.path.dirname(path) or os.getcwd()
        self.ikp_file = path

        for name, scene in scenes.items():
            frame = ttk.Frame(self)
            self.scenes[name] = (frame, scene)

        start = start_scene or data.get("start") or next(iter(scenes))
        self.show_scene(start)

    # -------------------------
    def _execute_action(self, action):
        if not action:
            return
        if isinstance(action, str):
            # legacy: simple parsing
            try:
                if action.startswith("goto(") and action.endswith(")"):
                    t = action[5:-1].strip()
                    self.show_scene(t)
                elif action.startswith("set(") and action.endswith(")"):
                    k,v = action[4:-1].split(",",1)
                    self.vars[k.strip()] = v.strip().strip('"').strip("'")
                elif action.startswith("progress(") and action.endswith(")"):
                    n,v = action[9:-1].split(",",1)
                    if n.strip() in self.vars and isinstance(self.vars[n.strip()], tk.Variable):
                        try:
                            self.vars[n.strip()].set(float(v))
                        except Exception:
                            pass
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
            if isinstance(val, str):
                val = interpolate(val, self.vars)
            self.vars[var] = val
        elif typ == "progress":
            target = action.get("target") or action.get("var")
            value = action.get("value", 0)
            if target in self.vars and isinstance(self.vars[target], tk.Variable):
                try:
                    self.vars[target].set(float(value))
                except Exception:
                    pass
        elif typ == "if":
            cond = action.get("condition", "")
            cond_resolved = interpolate(cond, self.vars)
            # only allow a limited character set for safety
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
            print("Unknown action:", typ)

    # -------------------------
    def show_scene(self, name):
        for f, _ in self.scenes.values():
            f.pack_forget()

        if name not in self.scenes:
            messagebox.showerror("Scene Error", f"Scene '{name}' not found")
            return

        frame, scene = self.scenes[name]
        self.render_scene(frame, scene)
        frame.pack(fill="both", expand=True)

    def _bind_var(self, item, var_name):
        # helper to create or reuse tk.Variable for a var name
        v = self.vars.get(var_name)
        if isinstance(v, tk.Variable):
            return v
        new = tk.StringVar(value=item.get("default", "") if isinstance(item, dict) else "")
        self.vars[var_name] = new
        return new

    def render_scene(self, frame, scene):
        for w in frame.winfo_children():
            w.destroy()
        self.images.clear()

        root = ttk.Frame(frame)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        for item in scene.get("ui", []):
            typ = item.get("type", "").lower()

            # LABEL
            if typ == "label":
                txt = interpolate(item.get("text", ""), self.vars)
                ttk.Label(root, text=txt, wraplength=800).pack(anchor="w", pady=4)

            # INPUT
            elif typ == "input":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                var = tk.StringVar(value=item.get("default", ""))
                ttk.Entry(root, textvariable=var).pack(fill="x", pady=2)
                if item.get("var"):
                    self.vars[item["var"]] = var

            # TEXTAREA
            elif typ == "textarea":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                txt = tk.Text(root, height=item.get("rows", 6))
                txt.pack(fill="both", pady=4)
                if "default" in item:
                    txt.insert("1.0", item["default"])
                if item.get("var"):
                    self.vars[item["var"]] = txt

            # BUTTON
            elif typ == "button":
                label = interpolate(item.get("text", "Button"), self.vars) if isinstance(item.get("text",""), str) else item.get("text","Button")
                action = item.get("action") or item.get("goto")
                def act(a=action):
                    self._execute_action(a)
                ttk.Button(root, text=label, command=act).pack(pady=4)

            # DROPDOWN
            elif typ == "dropdown":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                opts = item.get("options", [])
                var = tk.StringVar(value=item.get("default") or (opts[0] if opts else ""))
                ttk.Combobox(root, values=opts, textvariable=var).pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # CHECKBOX
            elif typ == "checkbox":
                var = tk.BooleanVar(value=item.get("default", False))
                ttk.Checkbutton(root, text=item.get("label", ""), variable=var).pack(anchor="w")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # RADIOGROUP
            elif typ == "radiogroup":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                var = tk.StringVar(value=item.get("default", ""))
                box = ttk.Frame(root)
                box.pack(anchor="w")
                for opt in item.get("options", []):
                    ttk.Radiobutton(box, text=opt, variable=var, value=opt).pack(side="left")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # COLORPICKER
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

            # SLIDER
            elif typ == "slider":
                ttk.Label(root, text=item.get("label", "")).pack(anchor="w")
                var = tk.DoubleVar(value=item.get("value", 0))
                ttk.Scale(root, from_=item.get("from", 0), to=item.get("to", 100), variable=var).pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # PROGRESS
            elif typ == "progress":
                var = tk.DoubleVar(value=item.get("value", 0))
                pb = ttk.Progressbar(root, maximum=item.get("max", 100), variable=var)
                pb.pack(fill="x")
                if item.get("var"):
                    self.vars[item["var"]] = var

            # IMAGE
            elif typ == "image":
                src = item.get("src")
                if src:
                    if not os.path.isabs(src):
                        src = os.path.join(self.base_path, src)
                    if Image and os.path.exists(src):
                        try:
                            img = Image.open(src)
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

# -------------------------
# Entry
# -------------------------

def main():
    # CLI: --open path --validate --start SceneName
    args = sys.argv[1:]
    path = None
    start_scene = None
    do_validate = False
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
            print("Usage: python ikp_viewer_v0.4.py --open path. Options: --validate, --start SceneName")
            return
        else:
            i += 1

    if path and do_validate:
        try:
            data = safe_load_ikp(path)
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
