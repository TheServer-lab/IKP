#!/usr/bin/env python3
"""
IKP Visual IDE v0.4
Graphical scene/canvas editor + live preview.
Uses ikp_core for dump/validation/interpolation rules.
"""

import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from tkinter.scrolledtext import ScrolledText
import os, traceback

from ikp_core import dump_yaml, validate_ikp, load_yaml_text, interpolate

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

PALETTE = ["label", "input", "textarea", "button", "checkbox", "dropdown", "slider", "progress", "image"]
BLOCK_COLORS = {
    "label":"#ffd54f", "input":"#a5d6a7", "textarea":"#ffe082",
    "button":"#4fc3f7", "checkbox":"#ffab91", "dropdown":"#ce93d8",
    "slider":"#b3e5fc", "progress":"#90caf9", "image":"#b0bec5"
}
FIELDS = {
    "label":["text"], "input":["label","var","default"],
    "textarea":["label","var","rows","default"], "button":["text","action_type","action_target","action_var","action_value"],
    "checkbox":["label","var","default"], "dropdown":["label","var","options","default"],
    "slider":["label","var","from","to","default"], "progress":["var","max","value"],
    "image":["src", "width", "height"]
}

class IKPLivePreview(ttk.Frame):
    def __init__(self, parent, ikp_data, active_scene):
        super().__init__(parent)
        self.ikp = ikp_data or {}
        self._image_cache = []
        ui_list = self.ikp.get("scenes", {}).get(active_scene, {}).get("ui", [])
        self.render_ui(self, ui_list)

    def render_ui(self, parent, ui):
        for item in ui:
            t = item.get("type", "").lower()
            try:
                if t == "label":
                    ttk.Label(parent, text=item.get("text", "Label"), wraplength=350).pack(anchor="w", pady=2)
                elif t == "input":
                    ttk.Label(parent, text=item.get("label", "Input")).pack(anchor="w")
                    ttk.Entry(parent).pack(fill="x", pady=2)
                elif t == "button":
                    ttk.Button(parent, text=item.get("text", "Button")).pack(pady=4)
                elif t == "checkbox":
                    ttk.Checkbutton(parent, text=item.get("label", "Checkbox")).pack(anchor="w")
                elif t == "slider":
                    ttk.Scale(parent, from_=item.get("from",0), to=item.get("to",100)).pack(fill="x")
                elif t == "progress":
                    p = ttk.Progressbar(parent, maximum=item.get("max",100))
                    p['value'] = item.get("value", 20)
                    p.pack(fill="x", pady=2)
                elif t == "image":
                    src = item.get("src")
                    if src and os.path.exists(src) and Image:
                        img = Image.open(src); img.thumbnail((200,150))
                        tkimg = ImageTk.PhotoImage(img)
                        self._image_cache.append(tkimg)
                        ttk.Label(parent, image=tkimg).pack(pady=4)
                    else:
                        ttk.Label(parent, text="[Image Placeholder]", background="#ccc").pack(pady=4, fill="x")
            except Exception:
                ttk.Label(parent, text=f"Error rendering {t}", foreground="red").pack()

class SceneCanvas(tk.Canvas):
    def __init__(self, parent, app, scene_data):
        super().__init__(parent, bg="#ffffff", highlightthickness=0)
        self.app = app
        self.scene_data = scene_data
        self.dragging_idx = None
        self.ghost = None
        self.render()

    def render(self):
        self.delete("all")
        y = 10
        for i, b in enumerate(self.scene_data.get("ui", [])):
            t = b["type"]
            col = BLOCK_COLORS.get(t, "#ddd")
            tag = f"idx_{i}"
            rect = self.create_rectangle(10, y, 240, y+35, fill=col, outline="#333", width=2, tags=("block", tag))
            txt = self.create_text(20, y+17, anchor="w", text=f"{t.upper()}: {b.get('text', b.get('label', ''))[:15]}",
                                   font=("Arial", 9, "bold"), tags=("block", tag))
            self.tag_bind(tag, "<Button-1>", lambda e, idx=i: self.start_drag(e, idx))
            self.tag_bind(tag, "<Double-Button-1>", lambda e, idx=i: self.app.edit_block(idx))
            self.tag_bind(tag, "<Button-3>", lambda e, idx=i: self.show_context_menu(e, idx))
            y += 45

    def show_context_menu(self, event, idx):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Edit Properties", command=lambda: self.app.edit_block(idx))
        menu.add_separator()
        menu.add_command(label="Delete Block", foreground="red", command=lambda: self.delete_block(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def delete_block(self, idx):
        self.scene_data["ui"].pop(idx)
        self.app.refresh_ui()

    def start_drag(self, event, idx):
        self.dragging_idx = idx
        self.ghost = self.create_rectangle(event.x-115, event.y-17, event.x+115, event.y+17,
                                          fill="white", stipple="gray50", outline="blue", dash=(2,2))

    def do_drag(self, event):
        if self.dragging_idx is None: return
        self.coords(self.ghost, event.x-115, event.y-17, event.x+115, event.y+17)
        self.delete("guide")
        target_idx = max(0, event.y // 45)
        guide_y = (target_idx * 45) + 5
        self.create_line(5, guide_y, 245, guide_y, fill="blue", width=3, tags="guide")

    def stop_drag(self, event):
        if self.dragging_idx is not None:
            target_idx = max(0, event.y // 45)
            item = self.scene_data["ui"].pop(self.dragging_idx)
            target_idx = min(target_idx, len(self.scene_data["ui"]))
            self.scene_data["ui"].insert(target_idx, item)
            self.dragging_idx = None
            self.delete("guide")
            self.app.refresh_ui()

class IKPVisualIDE(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("IKP Visual v0.4")
        self.geometry("1200x800")
        self.model = {"start": "Main", "scenes": {"Main": {"ui": []}}}
        self.active_scene = "Main"
        self.project_title = "Untitled Project"
        self.project_path = None

        self.setup_ui()
        self.refresh_ui()

    def setup_ui(self):
        bar = ttk.Frame(self); bar.pack(side="top", fill="x", padx=5, pady=5)
        ttk.Button(bar, text="New Scene", command=self.add_scene).pack(side="left", padx=2)
        ttk.Button(bar, text="Save .ikp", command=self.save_file).pack(side="right", padx=2)
        ttk.Button(bar, text="Open .ikp", command=self.open_file).pack(side="right", padx=2)
        ttk.Button(bar, text="Export Examples", command=self.export_examples).pack(side="right", padx=2)

        self.pane = ttk.PanedWindow(self, orient="horizontal")
        self.pane.pack(fill="both", expand=True)

        pal_frame = ttk.Frame(self.pane); self.pane.add(pal_frame, weight=0)
        ttk.Label(pal_frame, text="PALETTE", font=("Arial", 10, "bold")).pack(pady=10)
        for t in PALETTE:
            btn = ttk.Button(pal_frame, text=t.capitalize(), command=lambda tt=t: self.add_block(tt)); btn.pack(fill="x", padx=10, pady=2)

        center = ttk.Frame(self.pane); self.pane.add(center, weight=1)
        self.scene_sel = ttk.Combobox(center, state="readonly"); self.scene_sel.pack(fill="x", padx=5, pady=5)
        self.scene_sel.bind("<<ComboboxSelected>>", self.on_scene_change)
        self.canvas_container = ttk.Frame(center); self.canvas_container.pack(fill="both", expand=True)

        right = ttk.Frame(self.pane); self.pane.add(right, weight=1)
        self.tabs = ttk.Notebook(right); self.tabs.pack(fill="both", expand=True)
        self.preview_area = ttk.Frame(self.tabs); self.tabs.add(self.preview_area, text="LIVE PREVIEW")
        self.yaml_area = ScrolledText(self.tabs, width=40, font=("Courier New", 10)); self.tabs.add(self.yaml_area, text="YAML")

    def add_block(self, type_name):
        block = {"type": type_name}
        if type_name == "label": block["text"] = "Label text"
        elif type_name == "input": block.update({"label":"Label","var":"v1","default":""})
        elif type_name == "textarea": block.update({"label":"Label","var":"v1","rows":4,"default":""})
        elif type_name == "button": block.update({"text":"Button","action":{"type":"goto","target":"Main"}})
        elif type_name == "checkbox": block.update({"label":"Check","var":"v1","default":False})
        elif type_name == "dropdown": block.update({"label":"Choose","var":"v1","options":["A","B"],"default":"A"})
        elif type_name == "slider": block.update({"label":"Scale","var":"v1","from":0,"to":100,"default":0})
        elif type_name == "progress": block.update({"var":"p1","max":100,"value":0})
        elif type_name == "image": block.update({"src":"","width":200,"height":150})
        self.model["scenes"][self.active_scene]["ui"].append(block)
        self.refresh_ui()

    def edit_block(self, idx):
        block = self.model["scenes"][self.active_scene]["ui"][idx]
        edit_win = tk.Toplevel(self); edit_win.title(f"Edit {block['type']}")
        fields = FIELDS.get(block["type"], ["text", "var"])
        entries = {}
        for i, f in enumerate(fields):
            ttk.Label(edit_win, text=f).grid(row=i, column=0, padx=10, pady=5)
            e = ttk.Entry(edit_win)
            if f == "options": e.insert(0, ",".join(block.get(f, [])))
            elif f.startswith("action") and block.get("action"):
                if f == "action_type": e.insert(0, block.get("action", {}).get("type", ""))
                elif f == "action_target": e.insert(0, block.get("action", {}).get("target", ""))
                elif f == "action_var": e.insert(0, block.get("action", {}).get("var", ""))
                elif f == "action_value": e.insert(0, str(block.get("action", {}).get("value", "")))
            else:
                e.insert(0, str(block.get(f, "")))
            e.grid(row=i, column=1, padx=10, pady=5); entries[f] = e

        def save():
            for f, e in entries.items():
                val = e.get()
                if f == "options": block[f] = [s.strip() for s in val.split(",") if s.strip()]
                elif f in ("rows","from","to","max","width","height"): block[f] = int(val) if val.isdigit() else val
                elif f.startswith("action"): pass
                else:
                    if val.lower() in ("true","false"):
                        block[f] = val.lower() == "true"
                    else:
                        block[f] = val
            if block["type"] == "button":
                typ = entries.get("action_type").get()
                if typ:
                    action = {"type": typ}
                    if typ == "goto": action["target"] = entries.get("action_target").get()
                    elif typ == "set": action["var"] = entries.get("action_var").get(); action["value"] = entries.get("action_value").get()
                    elif typ == "progress":
                        action["target"] = entries.get("action_target").get()
                        try: action["value"] = float(entries.get("action_value").get())
                        except Exception: action["value"] = entries.get("action_value").get()
                    else: action["target"] = entries.get("action_target").get()
                    block["action"] = action
            edit_win.destroy(); self.refresh_ui()

        ttk.Button(edit_win, text="Save Changes", command=save).grid(row=len(fields), columnspan=2, pady=10)

    def refresh_ui(self):
        for w in self.canvas_container.winfo_children(): w.destroy()
        canvas = SceneCanvas(self.canvas_container, self, self.model["scenes"][self.active_scene]); canvas.pack(fill="both", expand=True)
        canvas.bind("<B1-Motion>", canvas.do_drag); canvas.bind("<ButtonRelease-1>", canvas.stop_drag)

        for w in self.preview_area.winfo_children(): w.destroy()
        IKPLivePreview(self.preview_area, self.model, self.active_scene).pack(fill="both", expand=True, padx=20, pady=20)

        self.yaml_area.delete("1.0", "end")
        out = {"ikp":"0.4", "meta":{"title":self.project_title}, **self.model}
        self.yaml_area.insert("1.0", dump_yaml(out))

        self.scene_sel["values"] = list(self.model["scenes"].keys()); self.scene_sel.set(self.active_scene)

    def on_scene_change(self, e):
        self.active_scene = self.scene_sel.get(); self.refresh_ui()

    def add_scene(self):
        name = simpledialog.askstring("New Scene", "Enter scene name:")
        if name:
            self.model["scenes"][name] = {"ui": []}
            self.active_scene = name
            self.refresh_ui()

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".ikp")
        if not path: return
        try:
            out = {"ikp":"0.4","meta":{"title":self.project_title}, **self.model}
            with open(path, "w", encoding="utf-8") as f:
                f.write(dump_yaml(out))
            self.project_path = os.path.dirname(path)
            messagebox.showinfo("Saved", f"Saved {path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("IKP Files","*.ikp"), ("YAML","*.yaml;*.yml"), ("All Files","*.*")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = load_yaml_text(f.read())
        except Exception as e:
            messagebox.showerror("Open Error", str(e)); return
        if not isinstance(data, dict) or "scenes" not in data:
            messagebox.showerror("Open Error", "Not a valid IKP file."); return
        self.model = {k:v for k,v in data.items() if k != "meta"}
        if "start" not in self.model:
            self.model["start"] = next(iter(self.model.get("scenes",{})))
        self.active_scene = self.model.get("start","Main")
        self.project_title = (data.get("meta") or {}).get("title","Untitled")
        self.project_path = os.path.dirname(path)
        self.refresh_ui()

    def export_examples(self):
        base = self.project_path or os.getcwd()
        exdir = filedialog.askdirectory(initialdir=base, title="Select export directory for examples")
        if not exdir: return
        examples = {
            "hello_world.ikp": {
                "ikp":"0.4","meta":{"title":"Hello"}, "start":"Main",
                "scenes":{
                    "Main":{"ui":[
                        {"type":"label","text":"Welcome to IKP v0.4"},
                        {"type":"input","label":"Your name","var":"name"},
                        {"type":"button","text":"Say hello","action":{"type":"goto","target":"Hello"}}
                    ]},
                    "Hello":{"ui":[{"type":"label","text":"Hello ${name}!"}]}
                }
            },
            "ui_showcase.ikp": {
                "ikp":"0.4","meta":{"title":"Showcase"}, "start":"Main",
                "scenes":{"Main":{"ui":[
                    {"type":"label","text":"UI Showcase"},
                    {"type":"slider","label":"Volume","var":"vol","from":0,"to":100,"default":20},
                    {"type":"progress","var":"p1","max":100,"value":30},
                    {"type":"dropdown","label":"Pick","var":"choice","options":["A","B","C"],"default":"A"},
                    {"type":"checkbox","label":"Agree","var":"ok","default":False}
                ]}}
            }
        }
        try:
            for name, data in examples.items():
                p = os.path.join(exdir, name)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(dump_yaml(data))
            messagebox.showinfo("Exported", f"Examples exported to {exdir}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

if __name__ == "__main__":
    IKPVisualIDE().mainloop()
