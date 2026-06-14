#!/usr/bin/env python3
"""
dash_app_main.py

Dash web frontend for the educational round-robin homophonic substitution cipher.

This file intentionally does NOT modify main.py.  It imports and uses:
    parse_mapping()
    encrypt()
    decrypt()

Run:
    pip install dash
    python3 dash_app_main.py --host 0.0.0.0 --port 8050

Mapping files are stored as human-readable .txt files in ./mappings by default.
"""

from __future__ import annotations

import argparse
import re
import string
from pathlib import Path
from typing import Dict, List, Tuple

from dash import Dash, Input, Output, State, ALL, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

# IMPORTANT: this Dash frontend expects the CLI code in ./main.py
from main import decrypt, encrypt, generate_mapping_text, parse_mapping, normalize_to_ascii


APP_TITLE = "Letter Code Lab"
DEFAULT_MAPPING_DIR = "mappings"


# ---------------------------------------------------------------------------
# Mapping-file helpers
# ---------------------------------------------------------------------------


def safe_name(name: str) -> str:
    """Return a safe mapping filename stem."""
    name = (name or "").strip()
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    name = name.strip("._-")
    return name or "mapping"


def mapping_path(mapping_dir: Path, name: str) -> Path:
    return mapping_dir / f"{safe_name(name)}.txt"


def list_mappings(mapping_dir: Path) -> List[str]:
    mapping_dir.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in mapping_dir.glob("*.txt"))


def dropdown_options(mapping_dir: Path) -> List[Dict[str, str]]:
    return [{"label": name, "value": name} for name in list_mappings(mapping_dir)]


def parse_mapping_text_to_rows(text: str) -> List[Dict[str, str]]:
    """Parse editable mapping text into table rows without validating tokens."""
    rows: List[Dict[str, str]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()

        if "->" in line:
            key, values = line.split("->", 1)
        elif "=" in line:
            key, values = line.split("=", 1)
        else:
            continue

        rows.append({"key": key.strip(), "tokens": values.strip()})

    return rows


def load_rows(mapping_dir: Path, name: str) -> List[Dict[str, str]]:
    path = mapping_path(mapping_dir, name)
    if not path.exists():
        return []
    return parse_mapping_text_to_rows(path.read_text(encoding="utf-8"))


def rows_to_mapping_text(keys: List[str], token_lists: List[str]) -> str:
    lines = [
        "# Mapping file for main.py",
        "# Format: A -> AX, AY, AZ",
        "# Use SPACE for the space character, for example: SPACE -> _",
        "",
    ]

    for key, tokens in zip(keys or [], token_lists or []):
        key = (key or "").strip()
        tokens = (tokens or "").strip()
        if not key and not tokens:
            continue
        if not key or not tokens:
            # Keep visibly incomplete rows so the user can fix them.
            lines.append(f"# INCOMPLETE ROW: {key} -> {tokens}")
            continue
        lines.append(f"{key.upper()} -> {tokens}")

    return "\n".join(lines).rstrip() + "\n"


def generated_rows(variants: int) -> List[Dict[str, str]]:
    """Generate safe non-leaking rows using main_fixed.generate_mapping_text()."""
    text = generate_mapping_text(variants=max(1, min(int(variants or 3), 26)))
    return parse_mapping_text_to_rows(text)


def ensure_demo_mapping(mapping_dir: Path) -> None:
    mapping_dir.mkdir(parents=True, exist_ok=True)
    if list_mappings(mapping_dir):
        return

    demo = mapping_path(mapping_dir, "demo")
    demo.write_text(generate_mapping_text(variants=3), encoding="utf-8")


def validate_mapping_file(mapping_dir: Path, name: str) -> Tuple[bool, str]:
    try:
        parse_mapping(str(mapping_path(mapping_dir, name)))
        return True, "Mapping saved and validated."
    except Exception as exc:  # keep UI friendly
        return False, f"Saved, but validation failed: {exc}"


# ---------------------------------------------------------------------------
# Dash UI
# ---------------------------------------------------------------------------


def css() -> str:
    return """
    body {
        margin: 0;
        background: #f5f7fb;
        font-family: Arial, Helvetica, sans-serif;
        color: #20242a;
    }
    .app-shell {
        max-width: 1220px;
        margin: 0 auto;
        padding: 18px;
    }
    .top-title {
        font-size: 42px;
        font-weight: 800;
        margin: 8px 0 2px 0;
    }
    .subtitle {
        font-size: 22px;
        margin: 0 0 18px 0;
        color: #555;
    }
    .card {
        background: white;
        border-radius: 18px;
        padding: 20px;
        margin: 16px 0;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    }
    .row {
        display: flex;
        flex-wrap: wrap;
        gap: 14px;
        align-items: end;
    }
    .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
        min-width: 220px;
        flex: 1;
    }
    .field-small {
        min-width: 150px;
        max-width: 190px;
        flex: 0 0 auto;
    }
    .label {
        font-size: 20px;
        font-weight: 700;
    }
    .big-input input,
    .big-input .Select-control,
    .big-input .Select-placeholder,
    .big-input .Select-value-label {
        font-size: 22px !important;
        min-height: 48px;
        line-height: 48px;
    }
    .large-textarea textarea,
    textarea.large-textarea {
        width: 100%;
        min-height: 230px;
        font-size: 30px;
        line-height: 1.35;
        border-radius: 14px;
        border: 2px solid #d4d9e5;
        padding: 14px;
        box-sizing: border-box;
        resize: vertical;
        font-family: Arial, Helvetica, sans-serif;
    }
    .button {
        border: 0;
        border-radius: 14px;
        padding: 14px 20px;
        font-size: 24px;
        font-weight: 800;
        cursor: pointer;
        background: #1f6feb;
        color: white;
        min-height: 58px;
    }
    .button-secondary {
        background: #667085;
    }
    .button-green {
        background: #078a45;
    }
    .button-orange {
        background: #c66a00;
    }
    .button-red {
        background: #b42318;
    }
    .status {
        font-size: 22px;
        font-weight: 700;
        padding-top: 10px;
    }
    .hint {
        font-size: 18px;
        color: #666;
        margin-top: 8px;
    }
    .mapping-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0 8px;
    }
    .mapping-table th {
        text-align: left;
        font-size: 22px;
        padding: 8px 10px;
    }
    .mapping-table td {
        padding: 4px 10px;
        background: #f7f9fc;
    }
    .mapping-table td:first-child {
        border-radius: 12px 0 0 12px;
        width: 180px;
    }
    .mapping-table td:last-child {
        border-radius: 0 12px 12px 0;
    }
    .table-input {
        width: 100%;
        font-size: 26px;
        padding: 12px;
        border-radius: 10px;
        border: 2px solid #d0d5dd;
        box-sizing: border-box;
    }
    .tab-style {
        font-size: 24px !important;
        font-weight: 800;
        padding: 16px !important;
    }
    .dash-tabs .tab--selected {
        border-top: 5px solid #1f6feb !important;
    }
    """


def big_button(label: str, button_id: str, extra_class: str = ""):
    return html.Button(label, id=button_id, n_clicks=0, className=f"button {extra_class}".strip())


def render_mapping_table(rows: List[Dict[str, str]]):
    table_rows = []
    for i, row in enumerate(rows or []):
        table_rows.append(
            html.Tr(
                [
                    html.Td(
                        dcc.Input(
                            id={"type": "map-key", "index": i},
                            value=row.get("key", ""),
                            className="table-input",
                            debounce=False,
                        )
                    ),
                    html.Td(
                        dcc.Input(
                            id={"type": "map-tokens", "index": i},
                            value=row.get("tokens", ""),
                            className="table-input",
                            debounce=False,
                        )
                    ),
                ]
            )
        )

    return html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Input letter"),
                        html.Th("Output choices, used one by one"),
                    ]
                )
            ),
            html.Tbody(table_rows),
        ],
        className="mapping-table",
    )


def configuration_tab(mapping_dir: Path):
    options = dropdown_options(mapping_dir)
    default_value = options[0]["value"] if options else None

    return html.Div(
        [
            dcc.Store(id="config-rows-store", data=load_rows(mapping_dir, default_value) if default_value else []),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Choose mapping", className="label"),
                            dcc.Dropdown(
                                id="cfg-mapping-select",
                                options=options,
                                value=default_value,
                                clearable=False,
                                className="big-input",
                            ),
                        ],
                        className="field",
                    ),
                    html.Div(
                        [
                            html.Label("Save as name", className="label"),
                            dcc.Input(
                                id="cfg-name-input",
                                value=default_value or "demo",
                                className="table-input",
                                debounce=False,
                            ),
                        ],
                        className="field",
                    ),
                    html.Div(
                        [
                            html.Label("Choices per letter", className="label"),
                            dcc.Input(
                                id="cfg-variants-input",
                                value=3,
                                type="number",
                                min=1,
                                max=26,
                                step=1,
                                className="table-input",
                            ),
                        ],
                        className="field field-small",
                    ),
                ],
                className="row card",
            ),
            html.Div(
                [
                    big_button("📂 Load", "cfg-load-btn", "button-secondary"),
                    big_button("✨ Generate A-Z", "cfg-generate-btn", "button-orange"),
                    big_button("➕ Add row", "cfg-add-row-btn", "button-secondary"),
                    big_button("💾 Save", "cfg-save-btn", "button-green"),
                ],
                className="row card",
            ),
            html.Div(id="cfg-status", className="status"),
            html.Div(
                [
                    html.Div(
                        "Use examples like: A -> NN, 4E, CL. The encrypt button rotates through the choices, one by one.",
                        className="hint",
                    ),
                    html.Div(id="mapping-table-container"),
                ],
                className="card",
            ),
        ]
    )


def code_lab_tab(mapping_dir: Path):
    options = dropdown_options(mapping_dir)
    default_value = options[0]["value"] if options else None

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Mapping", className="label"),
                            dcc.Dropdown(
                                id="work-mapping-select",
                                options=options,
                                value=default_value,
                                clearable=False,
                                className="big-input",
                            ),
                        ],
                        className="field",
                    ),
                    html.Div(
                        [
                            html.Label("Token separator", className="label"),
                            dcc.Input(
                                id="work-separator-input",
                                value="",
                                placeholder="empty or space",
                                className="table-input",
                            ),
                            html.Div("Leave empty for AXBA... or type one space for AX BA ...", className="hint"),
                        ],
                        className="field",
                    ),
                ],
                className="row card",
            ),
            html.Div(
                [
                    html.Label("Text", className="label"),
                    dcc.Textarea(
                        id="plain-textarea",
                        value="ABBAA",
                        className="large-textarea",
                    ),
                    html.Div(
                        [
                            big_button("🔐 Encrypt", "encrypt-btn", "button-green"),
                            big_button("🔓 Decrypt", "decrypt-btn", "button-orange"),
                            big_button("⬆️ Use output as text", "copy-output-btn", "button-secondary"),
                            big_button("🧹 Clear", "clear-btn", "button-red"),
                        ],
                        className="row",
                    ),
                ],
                className="card",
            ),
            html.Div(
                [
                    html.Label("Result", className="label"),
                    dcc.Textarea(id="result-textarea", value="", className="large-textarea"),
                    html.Div(id="work-status", className="status"),
                ],
                className="card",
            ),
        ]
    )


def make_layout(mapping_dir: Path):
    return html.Div(
        [
            html.Div(
                [
                    html.Div(APP_TITLE, className="top-title"),
                    html.Div(
                        "A large-button classroom frontend for simple non-leaking letter substitution.",
                        className="subtitle",
                    ),
                    dcc.Tabs(
                        id="tabs",
                        value="tab-work",
                        parent_className="dash-tabs",
                        children=[
                            dcc.Tab(
                                label="🔐 Encrypt / Decrypt",
                                value="tab-work",
                                className="tab-style",
                                selected_className="tab-style",
                                children=code_lab_tab(mapping_dir),
                            ),
                            dcc.Tab(
                                label="⚙️ Configuration",
                                value="tab-config",
                                className="tab-style",
                                selected_className="tab-style",
                                children=configuration_tab(mapping_dir),
                            ),
                        ],
                    ),
                ],
                className="app-shell",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Dash callbacks
# ---------------------------------------------------------------------------


def register_callbacks(app: Dash, mapping_dir: Path) -> None:
    @app.callback(
        Output("mapping-table-container", "children"),
        Input("config-rows-store", "data"),
    )
    def update_table(rows):
        return render_mapping_table(rows or [])

    @app.callback(
        Output("config-rows-store", "data"),
        Output("cfg-status", "children"),
        Output("cfg-mapping-select", "options"),
        Output("cfg-mapping-select", "value"),
        Output("work-mapping-select", "options"),
        Output("work-mapping-select", "value"),
        Input("cfg-load-btn", "n_clicks"),
        Input("cfg-generate-btn", "n_clicks"),
        Input("cfg-add-row-btn", "n_clicks"),
        Input("cfg-save-btn", "n_clicks"),
        State("cfg-mapping-select", "value"),
        State("cfg-name-input", "value"),
        State("cfg-variants-input", "value"),
        State("work-mapping-select", "value"),
        State({"type": "map-key", "index": ALL}, "value"),
        State({"type": "map-tokens", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def config_actions(
        load_clicks,
        generate_clicks,
        add_clicks,
        save_clicks,
        selected_name,
        name_input,
        variants,
        current_work_name,
        keys,
        tokens,
    ):
        trigger = ctx.triggered_id

        current_rows = [
            {"key": key or "", "tokens": token_list or ""}
            for key, token_list in zip(keys or [], tokens or [])
        ]

        if trigger == "cfg-load-btn":
            if not selected_name:
                return no_update, "No mapping selected.", no_update, no_update, no_update, no_update
            return (
                load_rows(mapping_dir, selected_name),
                f"Loaded mapping: {selected_name}",
                no_update,
                no_update,
                no_update,
                no_update,
            )

        if trigger == "cfg-generate-btn":
            return (
                generated_rows(int(variants or 3)),
                "Generated A-Z mapping. Edit it and click Save.",
                no_update,
                no_update,
                no_update,
                no_update,
            )

        if trigger == "cfg-add-row-btn":
            current_rows.append({"key": "", "tokens": ""})
            return (
                current_rows,
                "Added an empty row.",
                no_update,
                no_update,
                no_update,
                no_update,
            )

        if trigger == "cfg-save-btn":
            name = safe_name(name_input or selected_name or "mapping")
            text = rows_to_mapping_text(keys or [], tokens or [])
            path = mapping_path(mapping_dir, name)
            path.write_text(text, encoding="utf-8")

            ok, validation_message = validate_mapping_file(mapping_dir, name)
            options = dropdown_options(mapping_dir)
            status_prefix = "✅" if ok else "⚠️"
            work_value = current_work_name or name

            return (
                current_rows,
                f"{status_prefix} {validation_message} File: {path}",
                options,
                name,
                options,
                work_value,
            )

        raise PreventUpdate

    @app.callback(
        Output("plain-textarea", "value"),
        Output("result-textarea", "value"),
        Output("work-status", "children"),
        Input("encrypt-btn", "n_clicks"),
        Input("decrypt-btn", "n_clicks"),
        Input("copy-output-btn", "n_clicks"),
        Input("clear-btn", "n_clicks"),
        State("work-mapping-select", "value"),
        State("work-separator-input", "value"),
        State("plain-textarea", "value"),
        State("result-textarea", "value"),
        prevent_initial_call=True,
    )
    def work_actions(
        encrypt_clicks,
        decrypt_clicks,
        copy_clicks,
        clear_clicks,
        mapping_name,
        separator,
        text,
        result_text,
    ):
        trigger = ctx.triggered_id

        if trigger == "copy-output-btn":
            return result_text or "", no_update, "Copied result to text box."

        if trigger == "clear-btn":
            return "", "", "Cleared."

        if trigger in ("encrypt-btn", "decrypt-btn"):
            if not mapping_name:
                return no_update, "", "Choose a mapping first."

            try:
                mapping = parse_mapping(str(mapping_path(mapping_dir, mapping_name)))
                sep = separator or ""
                source = text or ""

                if trigger == "encrypt-btn":
                    return no_update, encrypt(normalize_to_ascii(source), mapping, sep=sep), f"Encrypted with mapping: {mapping_name}"

                if trigger == "decrypt-btn":
                    return no_update, decrypt(source, mapping, sep=sep), f"Decrypted with mapping: {mapping_name}"

            except Exception as exc:
                return no_update, "", f"Error: {exc}"

        raise PreventUpdate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def create_app(mapping_dir: Path) -> Dash:
    ensure_demo_mapping(mapping_dir)

    app = Dash(__name__, title=APP_TITLE, suppress_callback_exceptions=True)

    # Dash does not expose html.Style in current versions.
    # Keep this app single-file by injecting CSS through index_string.
    app.index_string = f"""
    <!DOCTYPE html>
    <html>
        <head>
            {{%metas%}}
            <title>{{%title%}}</title>
            {{%favicon%}}
            {{%css%}}
            <style>
            {css()}
            </style>
        </head>
        <body>
            {{%app_entry%}}
            <footer>
                {{%config%}}
                {{%scripts%}}
                {{%renderer%}}
            </footer>
        </body>
    </html>
    """

    app.layout = make_layout(mapping_dir)
    register_callbacks(app, mapping_dir)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dash frontend for main.py")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8050, type=int)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--mapping-dir", default=DEFAULT_MAPPING_DIR)
    args = parser.parse_args()

    mapping_dir = Path(args.mapping_dir).resolve()
    app = create_app(mapping_dir)

    # Dash 2.0+ uses app.run(); older Dash uses app.run_server().
    if hasattr(app, "run"):
        app.run(host=args.host, port=args.port, debug=args.debug)
    else:
        app.run_server(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
