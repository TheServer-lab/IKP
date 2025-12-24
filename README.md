# IKP — Interactive Knowledge Prompt

**IKP (Interactive Knowledge Prompt)** is a declarative, YAML-based format for building **interactive, knowledge-driven experiences** — without writing application code.

IKP files describe **content, UI, state, and flow** in a single portable document that can be rendered by different runtimes (desktop, web, etc.).

> Think of IKP as *executable knowledge*.

---

## Why IKP?

Traditional formats fall short:

- **Markdown** → static
- **JSON UI schemas** → technical, not knowledge-centric
- **Tutorial platforms** → locked to ecosystems
- **No-code tools** → opaque, non-portable

IKP is designed to be:

- 🧠 **Knowledge-first**
- 🧾 **Human-readable**
- 🔁 **Interactive**
- 🧩 **Extensible**
- 🔒 **Safe & sandboxed**

---

## What Can IKP Be Used For?

- Interactive documentation
- Tutorials & learning modules
- Decision trees & guided workflows
- Knowledge bases with interaction
- Prompt scaffolds for AI systems
- Lightweight interactive apps

---

## Core Concepts

### 1. Declarative YAML
IKP uses YAML to describe *what exists*, not *how it is implemented*.

```yaml
- type: label
  text: "Hello, IKP"
```

---

### 2. Scenes
Content is organized into **scenes**, similar to pages or steps.

```yaml
scenes:
  Intro:
    ui: ...
```

Scenes can navigate to each other via actions.

---

### 3. UI Blocks (Widgets)
Each scene contains a list of UI blocks:

- Text (`label`, `richtext`)
- Inputs (`input`, `textarea`)
- Controls (`button`, `slider`, `progress`)
- Selection (`checkbox`, `dropdown`, `radiogroup`)
- Media (`image`)
- Layout (`tabs`, `accordion`)

---

### 4. Variables & State
Widgets can bind values to variables using `var`.

```yaml
- type: input
  label: "Your name"
  var: username

- type: label
  text: "Hello ${username}"
```

---

### 5. Actions & Flow
Actions define behavior such as navigation or state updates.

```yaml
- type: button
  text: "Next"
  action:
    type: goto
    target: NextScene
```

Actions are **structured data**, not scripts.

---

## Example IKP File

```yaml
ikp: 0.4

meta:
  title: "IKP Demo"
  author: "You"

start: Main

scenes:
  Main:
    ui:
      - type: label
        text: "Welcome to IKP"

      - type: input
        label: "Your name"
        var: name

      - type: button
        text: "Continue"
        action:
          type: goto
          target: Hello

  Hello:
    ui:
      - type: label
        text: "Hello ${name}!"
```

---

## Tooling Included

### 🧰 IKP Toolkit
- Text editor + live preview
- YAML-first workflow
- Fast iteration

### 👁️ IKP Viewer
- Lightweight runtime for `.ikp` files
- Scene navigation
- Variable interpolation

### 🎨 IKP Visual IDE
- Drag-and-drop scene builder
- Live preview
- Auto-generated YAML

---

## Running IKP (Python)

### Requirements
```bash
pip install pyyaml pillow
```

### Run the Toolkit
```bash
python ikp_toolkit_v0.3.py
```

### Open an IKP file in the Viewer
```bash
python ikp_viewer_v0.3.py --open example.ikp
```

### Launch the Visual IDE
```bash
python ikp_visual_v0.3.py
```

---

## File Format

- Extension: `.ikp`
- Encoding: UTF-8
- Format: YAML
- Spec versioned via root `ikp:` field

---

## Specification

IKP is versioned and forward-compatible.

Current draft spec:
- **IKP Spec v0.4**

Renderers should gracefully ignore unknown fields and widget types.

---

## Design Philosophy

- **No arbitrary code execution**
- **Renderer-agnostic**
- **Human-readable first**
- **Extensible by design**
- **Safe defaults**

---

## Roadmap (High-Level)

- Knowledge-native widgets (quiz, definition, example)
- Conditional logic
- JSON Schema validation
- Web renderer
- Export to static HTML
- AI-assisted IKP generation

---

## License

Open and extensible by design.
(Server-lab Open-Control License)

---

## One-Line Definition

> **IKP is a declarative format for interactive knowledge experiences.**

