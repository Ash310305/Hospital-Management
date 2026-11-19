import json
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from tkinter import messagebox, ttk
from typing import Any, get_args, get_origin

from bson import ObjectId
from pydantic import BaseModel, ValidationError

from app import Treatment
from db import get_database
from models.appointments import Appointment
from models.billing_info import Payment
from models.doctor import Doctor
from models.medical_records import PatientClinicalProfile
from models.patient import Patient
from models.prescriptions import Treatment as Prescription


COLORS = {
    "background": "#0B1220",
    "surface": "#111B2B",
    "surface_light": "#172438",
    "surface_hover": "#1D2D43",
    "border": "#24344B",
    "text": "#EFF5FC",
    "muted": "#8FA2B9",
    "green": "#72E0B2",
    "teal": "#67D5D0",
    "blue": "#8CB8FF",
    "purple": "#B8A0FF",
    "red": "#FF8191",
}


@dataclass(frozen=True)
class Resource:
    key: str
    label: str
    singular: str
    collection: str
    model: type[BaseModel]
    fields: tuple[str, ...]
    search_fields: tuple[str, ...]
    badge: str


RESOURCES = (
    Resource(
        "patients",
        "Patients",
        "Patient",
        "patients",
        Patient,
        ("name", "age", "sex", "phone_number"),
        ("name", "phone_number", "address"),
        "PT",
    ),
    Resource(
        "doctors",
        "Doctors",
        "Doctor",
        "doctors",
        Doctor,
        ("name", "specialization", "sex", "visiting_time"),
        ("name", "specialization", "college_name"),
        "DR",
    ),
    Resource(
        "appointments",
        "Appointments",
        "Appointment",
        "appointments",
        Appointment,
        ("patient_id", "doctor_id", "date", "time", "fees"),
        ("patient_id", "doctor_id", "date"),
        "AP",
    ),
    Resource(
        "medical-records",
        "Medical records",
        "Medical record",
        "medical_records",
        PatientClinicalProfile,
        ("patient_id", "blood_group", "chronic_conditions", "height", "weight"),
        ("patient_id", "blood_group", "chronic_conditions"),
        "MR",
    ),
    Resource(
        "prescriptions",
        "Prescriptions",
        "Prescription",
        "prescriptions",
        Prescription,
        ("patient_id", "doctor_id", "medicines", "machines"),
        ("patient_id", "doctor_id", "medicines"),
        "RX",
    ),
    Resource(
        "treatments",
        "Treatments",
        "Treatment",
        "treatments",
        Treatment,
        ("patient_id", "doctor_id", "target_diagnosis", "treatment_type", "treatment_status"),
        ("patient_id", "doctor_id", "target_diagnosis", "treatment_type"),
        "TX",
    ),
    Resource(
        "billing",
        "Billing",
        "Billing record",
        "payments",
        Payment,
        ("patient_id", "doctor_id", "payment_mode", "amount", "status"),
        ("patient_id", "doctor_id", "payment_mode", "status"),
        "$",
    ),
)

RESOURCE_BY_KEY = {resource.key: resource for resource in RESOURCES}


def _unwrap_optional(annotation: Any) -> Any:
    args = get_args(annotation)
    if args and type(None) in args:
        return next((arg for arg in args if arg is not type(None)), str)
    return annotation


def _enum_type(annotation: Any) -> type[Enum] | None:
    resolved = _unwrap_optional(annotation)
    if isinstance(resolved, type) and issubclass(resolved, Enum):
        return resolved
    return None


def format_field_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (date, time, datetime)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str, ensure_ascii=False, indent=2)
    return str(value)


def format_form_value(field: Any, value: Any, model: type[BaseModel]) -> str:
    if isinstance(value, datetime) and _unwrap_optional(field.annotation) is date:
        value = value.date()
    if model is Appointment and field.alias == "date" and isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    return format_field_value(value)


def validate_form_data(model: type[BaseModel], values: dict[str, Any]) -> BaseModel:
    cleaned = dict(values)
    for name, field in model.model_fields.items():
        if name not in cleaned or not isinstance(cleaned[name], str):
            continue
        value = cleaned[name].strip()
        if value == "":
            if field.is_required():
                cleaned[name] = value
            else:
                cleaned[name] = None
            continue

        annotation = _unwrap_optional(field.annotation)
        if _enum_type(field.annotation) is not None:
            enum_class = _enum_type(field.annotation)
            assert enum_class is not None
            cleaned[name] = enum_class(value)
        elif get_origin(annotation) in (list, dict):
            cleaned[name] = json.loads(value)
        elif annotation is bool:
            cleaned[name] = value.lower() in ("true", "1", "yes", "on")
        elif annotation is int:
            cleaned[name] = int(value)
        elif annotation is float:
            cleaned[name] = float(value)
        elif annotation is date and model is Appointment:
            cleaned[name] = datetime.strptime(value, "%d-%m-%Y").date()
    return model.model_validate(cleaned)


def record_to_mongo(model: BaseModel) -> dict:
    converter = getattr(model, "to_mongo_dict", None)
    if converter is not None:
        return converter()
    return model.model_dump(mode="python")


class RecordForm(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        resource: Resource,
        record: dict | None = None,
    ):
        super().__init__(parent)
        self.resource = resource
        self.record = record or {}
        self.result: BaseModel | None = None
        self.inputs: dict[str, Any] = {}
        self.title(f"{'Edit' if record else 'New'} {resource.singular}")
        self.configure(background=COLORS["background"])
        self.transient(parent)
        self.grab_set()
        self.geometry("620x760")
        self.minsize(520, 460)
        self._build()

    def _build(self):
        shell = tk.Frame(self, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=16, pady=16)

        header = tk.Frame(shell, bg=COLORS["surface"])
        header.pack(fill="x", padx=24, pady=(22, 14))
        title = "Edit " + self.resource.singular if self.record else "Create " + self.resource.singular
        tk.Label(
            header,
            text=title,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Helvetica Neue", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Fields marked with * are required. Dates use YYYY-MM-DD unless noted.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(5, 0))

        body = tk.Frame(shell, bg=COLORS["surface"])
        body.pack(fill="both", expand=True, padx=24)
        canvas = tk.Canvas(body, bg=COLORS["surface"], highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        fields_frame = tk.Frame(canvas, bg=COLORS["surface"])
        fields_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=fields_frame, anchor="nw", tags=("fields",))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure("fields", width=event.width),
        )

        for name, field in self.resource.model.model_fields.items():
            if name in ("treatment_id", "record_id"):
                continue
            if name in self.record:
                current = self.record[name]
            elif field.default_factory is not None:
                current = field.default_factory()
            elif field.is_required():
                current = ""
            else:
                current = field.default
            self._add_field(fields_frame, name, field, current)

        footer = tk.Frame(shell, bg=COLORS["surface"])
        footer.pack(fill="x", padx=24, pady=20)
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right", padx=(10, 0))
        ttk.Button(footer, text="Save record", style="Accent.TButton", command=self._save).pack(side="right")

    def _add_field(self, parent: tk.Frame, name: str, field: Any, current: Any):
        row = tk.Frame(parent, bg=COLORS["surface"])
        row.pack(fill="x", pady=(0, 15))
        label = name.replace("_", " ").capitalize()
        if field.is_required():
            label += " *"
        tk.Label(
            row,
            text=label,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Helvetica Neue", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        enum_class = _enum_type(field.annotation)
        base_type = _unwrap_optional(field.annotation)
        if enum_class:
            variable = tk.StringVar(value=format_field_value(current))
            widget = ttk.Combobox(
                row,
                textvariable=variable,
                values=[str(option.value) for option in enum_class],
                state="readonly",
                style="Dark.TCombobox",
            )
            widget.pack(fill="x")
            self.inputs[name] = variable
        elif base_type is bool:
            variable = tk.BooleanVar(value=bool(current))
            widget = ttk.Checkbutton(row, text="Enabled", variable=variable)
            widget.pack(anchor="w")
            self.inputs[name] = variable
        elif get_origin(base_type) in (list, dict):
            widget = tk.Text(
                row,
                height=4,
                wrap="word",
                bg=COLORS["surface_light"],
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                relief="flat",
                font=("SF Mono", 10),
                padx=10,
                pady=8,
            )
            widget.pack(fill="x")
            widget.insert(
                "1.0",
                format_form_value(field, current, self.resource.model),
            )
            self.inputs[name] = widget
            tk.Label(
                row,
                text="Enter valid JSON (for example: [\"item one\", \"item two\"]).",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Helvetica Neue", 9),
            ).pack(anchor="w", pady=(4, 0))
        else:
            variable = tk.StringVar(
                value=format_form_value(field, current, self.resource.model)
            )
            widget = ttk.Entry(row, textvariable=variable, style="Dark.TEntry")
            widget.pack(fill="x", ipady=7)
            self.inputs[name] = variable

    def _save(self):
        values = {}
        for name, widget in self.inputs.items():
            if isinstance(widget, tk.Text):
                values[name] = widget.get("1.0", "end-1c")
            elif isinstance(widget, tk.Variable):
                values[name] = widget.get()
        for name in ("treatment_id", "record_id"):
            if name in self.resource.model.model_fields:
                values[name] = self.record.get(name)
        try:
            self.result = validate_form_data(self.resource.model, values)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror("Check record details", str(error), parent=self)
            return
        self.destroy()


class HospitalDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Careflow  |  Hospital management")
        self.root.geometry("1440x900")
        self.root.minsize(1120, 700)
        self.root.configure(bg=COLORS["background"])
        self.current_resource: Resource | None = None
        self.records: list[dict] = []
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Connecting to database…")
        self.count_vars: dict[str, tk.StringVar] = {}
        self._configure_style()
        self._build_shell()
        self._show_overview()
        self._refresh_counts()

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            borderwidth=0,
            rowheight=42,
            font=("Helvetica Neue", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["surface_light"],
            foreground=COLORS["muted"],
            borderwidth=0,
            font=("Helvetica Neue", 9, "bold"),
            padding=(12, 12),
        )
        style.map(
            "Treeview",
            background=[("selected", "#25443F")],
            foreground=[("selected", COLORS["text"])],
        )
        style.configure(
            "TButton",
            background=COLORS["surface_light"],
            foreground=COLORS["text"],
            borderwidth=0,
            padding=(14, 9),
            font=("Helvetica Neue", 10, "bold"),
        )
        style.map(
            "TButton",
            background=[("active", COLORS["surface_hover"]), ("disabled", COLORS["surface"])],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Accent.TButton",
            background="#59C99C",
            foreground="#091A16",
            padding=(14, 10),
            font=("Helvetica Neue", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#78E0B5")])
        style.configure(
            "Dark.TEntry",
            fieldbackground=COLORS["surface_light"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            borderwidth=0,
            padding=(10, 9),
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLORS["surface_light"],
            background=COLORS["surface_light"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["green"],
            borderwidth=0,
            padding=(8, 8),
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", COLORS["surface_light"])],
            foreground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["surface_light"],
            troughcolor=COLORS["surface"],
            borderwidth=0,
            arrowcolor=COLORS["muted"],
        )
        style.configure(
            "TCheckbutton",
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.map("TCheckbutton", background=[("active", COLORS["surface"])])

    def _build_shell(self):
        self.shell = tk.Frame(self.root, bg=COLORS["background"])
        self.shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(self.shell, bg=COLORS["surface"], width=246)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=COLORS["surface"])
        brand.pack(fill="x", padx=22, pady=(25, 30))
        logo = tk.Canvas(brand, width=38, height=38, bg=COLORS["surface"], highlightthickness=0)
        logo.pack(side="left")
        logo.create_oval(3, 3, 35, 35, fill="#204B45", outline="")
        logo.create_text(19, 19, text="+", fill=COLORS["green"], font=("Helvetica Neue", 24, "bold"))
        brand_text = tk.Frame(brand, bg=COLORS["surface"])
        brand_text.pack(side="left", padx=10)
        tk.Label(
            brand_text,
            text="careflow",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Helvetica Neue", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand_text,
            text="HOSPITAL MANAGEMENT",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 7, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            self.sidebar,
            text="WORKSPACE",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 8, "bold"),
        ).pack(anchor="w", padx=24, pady=(0, 10))
        self.nav_buttons: dict[str, tk.Button] = {}
        self._add_nav_button("overview", "Overview", "OV", self._show_overview)
        for resource in RESOURCES:
            self._add_nav_button(
                resource.key,
                resource.label,
                resource.badge,
                lambda selected=resource: self.show_resource(selected),
            )

        bottom = tk.Frame(self.sidebar, bg=COLORS["surface"])
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)
        tk.Frame(bottom, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 14))
        tk.Label(
            bottom,
            text="SECURE DATABASE",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 8, "bold"),
        ).pack(anchor="w", padx=5)
        self.connection_dot = tk.Label(
            bottom,
            text="●  Checking connection",
            bg=COLORS["surface"],
            fg=COLORS["teal"],
            font=("Helvetica Neue", 10),
        )
        self.connection_dot.pack(anchor="w", padx=5, pady=(8, 0))

        self.main = tk.Frame(self.shell, bg=COLORS["background"])
        self.main.pack(side="left", fill="both", expand=True)
        self.header = tk.Canvas(
            self.main,
            height=122,
            bg=COLORS["surface"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.header.pack(fill="x")
        self.header.bind("<Configure>", self._draw_aurora)
        self.header_title = self.header.create_text(
            34,
            42,
            anchor="w",
            text="Hospital overview",
            fill=COLORS["text"],
            font=("Helvetica Neue", 24, "bold"),
        )
        self.header_subtitle = self.header.create_text(
            36,
            78,
            anchor="w",
            text="A clear view of your hospital operations.",
            fill="#B7C7D9",
            font=("Helvetica Neue", 11),
        )
        self.content = tk.Frame(self.main, bg=COLORS["background"])
        self.content.pack(fill="both", expand=True, padx=30, pady=(22, 10))
        footer = tk.Frame(self.main, bg=COLORS["background"])
        footer.pack(fill="x", padx=30, pady=(0, 12))
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 9),
        ).pack(side="left")
        tk.Label(
            footer,
            text="CARE WITH CLARITY",
            bg=COLORS["background"],
            fg="#50637B",
            font=("Helvetica Neue", 8, "bold"),
        ).pack(side="right")

    def _draw_aurora(self, event):
        self.header.delete("background")
        width = max(event.width, 1)
        height = 122
        stops = (
            (0.0, (17, 27, 43)),
            (0.34, (20, 54, 51)),
            (0.62, (19, 48, 65)),
            (0.84, (43, 36, 67)),
            (1.0, (17, 27, 43)),
        )
        pieces = max(80, min(width // 3, 420))
        for index in range(pieces):
            ratio = index / max(pieces - 1, 1)
            for stop_index in range(len(stops) - 1):
                left, left_color = stops[stop_index]
                right, right_color = stops[stop_index + 1]
                if left <= ratio <= right:
                    blend = (ratio - left) / (right - left)
                    color = tuple(
                        round(a + (b - a) * blend)
                        for a, b in zip(left_color, right_color)
                    )
                    break
            hex_color = "#%02x%02x%02x" % color
            x1 = round(index * width / pieces)
            x2 = round((index + 1) * width / pieces) + 1
            self.header.create_rectangle(
                x1,
                0,
                x2,
                height,
                fill=hex_color,
                outline=hex_color,
                tags=("background",),
            )
        self.header.tag_lower("background")
        self.header.tag_raise(self.header_title)
        self.header.tag_raise(self.header_subtitle)

    def _add_nav_button(self, key: str, label: str, badge: str, command):
        button = tk.Button(
            self.sidebar,
            text=f"  {badge:<3}  {label}",
            command=command,
            anchor="w",
            relief="flat",
            bd=0,
            padx=14,
            pady=11,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            activebackground=COLORS["surface_hover"],
            activeforeground=COLORS["text"],
            font=("Helvetica Neue", 10, "bold"),
            cursor="hand2",
        )
        button.pack(fill="x", padx=12, pady=2)
        self.nav_buttons[key] = button

    def _set_active_nav(self, key: str):
        for nav_key, button in self.nav_buttons.items():
            active = nav_key == key
            button.configure(
                bg="#1C3437" if active else COLORS["surface"],
                fg=COLORS["green"] if active else COLORS["muted"],
            )

    def _set_header(self, title: str, subtitle: str):
        self.header.itemconfigure(self.header_title, text=title)
        self.header.itemconfigure(self.header_subtitle, text=subtitle)

    def _clear_content(self):
        for widget in self.content.winfo_children():
            widget.destroy()

    def _show_overview(self):
        self.current_resource = None
        self._set_active_nav("overview")
        self._set_header("Hospital overview", "A clear view of your hospital operations.")
        self._clear_content()

        intro = tk.Frame(self.content, bg=COLORS["background"])
        intro.pack(fill="x", pady=(0, 16))
        tk.Label(
            intro,
            text="Your workspace",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=("Helvetica Neue", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            intro,
            text="Choose a collection to view, add, update, and manage records.",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(5, 0))

        cards = tk.Frame(self.content, bg=COLORS["background"])
        cards.pack(fill="x")
        for column in range(3):
            cards.grid_columnconfigure(column, weight=1, uniform="cards")
        accents = (COLORS["green"], COLORS["blue"], COLORS["purple"], COLORS["teal"])
        for index, resource in enumerate(RESOURCES):
            row, column = divmod(index, 3)
            card = tk.Frame(
                cards,
                bg=COLORS["surface"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                cursor="hand2",
            )
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 14), pady=(0, 14))
            card.configure(height=152)
            card.grid_propagate(False)
            accent = accents[index % len(accents)]
            tk.Frame(card, bg=accent, width=3).pack(side="left", fill="y")
            inner = tk.Frame(card, bg=COLORS["surface"])
            inner.pack(fill="both", expand=True, padx=18, pady=15)
            top = tk.Frame(inner, bg=COLORS["surface"])
            top.pack(fill="x")
            tk.Label(
                top,
                text=resource.badge,
                bg=COLORS["surface_light"],
                fg=accent,
                font=("Helvetica Neue", 9, "bold"),
                padx=7,
                pady=5,
            ).pack(side="left")
            count_var = tk.StringVar(value="—")
            self.count_vars[resource.key] = count_var
            tk.Label(
                top,
                textvariable=count_var,
                bg=COLORS["surface"],
                fg=COLORS["text"],
                font=("Helvetica Neue", 14, "bold"),
            ).pack(side="right")
            tk.Label(
                inner,
                text=resource.label,
                bg=COLORS["surface"],
                fg=COLORS["text"],
                font=("Helvetica Neue", 13, "bold"),
            ).pack(anchor="w", pady=(13, 4))
            tk.Label(
                inner,
                text="Open collection  →",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Helvetica Neue", 9),
            ).pack(anchor="w")
            self._bind_card(card, resource)

    def _bind_card(self, widget: tk.Widget, resource: Resource):
        widget.bind(
            "<Button-1>",
            lambda _event, selected=resource: self.show_resource(selected),
        )
        for child in widget.winfo_children():
            self._bind_card(child, resource)

        note = tk.Frame(
            self.content,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        note.pack(fill="x", pady=(4, 0))
        tk.Label(
            note,
            text="  DATABASE",
            bg=COLORS["surface"],
            fg=COLORS["teal"],
            font=("Helvetica Neue", 8, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 3))
        tk.Label(
            note,
            text="  Changes are saved directly to your configured MongoDB database.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def show_resource(self, resource: Resource):
        self.current_resource = resource
        self._set_active_nav(resource.key)
        self._set_header(resource.label, f"Manage {resource.label.lower()} in one place.")
        self._clear_content()
        toolbar = tk.Frame(self.content, bg=COLORS["background"])
        toolbar.pack(fill="x", pady=(0, 15))
        search = ttk.Entry(
            toolbar,
            textvariable=self.search_var,
            style="Dark.TEntry",
            width=38,
        )
        search.pack(side="left", fill="x", expand=True, ipady=4)
        search.bind("<KeyRelease>", lambda _event: self._render_rows())
        self.search_var.set("")
        ttk.Button(
            toolbar,
            text="↻  Refresh",
            command=self._load_records,
        ).pack(side="left", padx=(10, 8))
        ttk.Button(
            toolbar,
            text="+  New record",
            style="Accent.TButton",
            command=self._new_record,
        ).pack(side="right")

        table_card = tk.Frame(
            self.content,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        table_card.pack(fill="both", expand=True)
        table_header = tk.Frame(table_card, bg=COLORS["surface"])
        table_header.pack(fill="x", padx=18, pady=(16, 11))
        self.table_count = tk.StringVar(value="Loading records…")
        tk.Label(
            table_header,
            text=resource.label,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Helvetica Neue", 13, "bold"),
        ).pack(side="left")
        tk.Label(
            table_header,
            textvariable=self.table_count,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 9),
        ).pack(side="right")

        columns = resource.fields
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            self.tree.heading(column, text=column.replace("_", " ").upper())
            self.tree.column(column, width=145, minwidth=105, anchor="w", stretch=True)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(0, 12))
        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
        self.tree.bind("<Double-1>", lambda _event: self._edit_selected())

        actions = tk.Frame(self.content, bg=COLORS["background"])
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Edit selected", command=self._edit_selected).pack(side="left")
        ttk.Button(actions, text="Delete selected", command=self._delete_selected).pack(side="left", padx=8)
        tk.Label(
            actions,
            text="Double-click a row to edit",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Helvetica Neue", 9),
        ).pack(side="right", pady=10)
        self.records = []
        self._load_records()

    def _run_background(self, task, on_success, status_text: str):
        self.status_var.set(status_text)

        def worker():
            try:
                result = task()
            except Exception as error:
                self.root.after(0, lambda exc=error: self._show_error(exc))
                return
            self.root.after(0, lambda value=result: on_success(value))

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, error: Exception):
        self.status_var.set("The operation could not be completed.")
        messagebox.showerror(
            "Database operation failed",
            f"{type(error).__name__}: {error}",
            parent=self.root,
        )

    def _refresh_counts(self):
        def fetch_counts():
            database = get_database()
            return {
                resource.key: database[resource.collection].count_documents({})
                for resource in RESOURCES
            }

        def show_counts(counts):
            for key, count in counts.items():
                if key in self.count_vars:
                    self.count_vars[key].set(str(count))
            self.connection_dot.configure(text="●  Connected to MongoDB", fg=COLORS["green"])
            self.status_var.set("Database connected")

        def show_failure(error: Exception):
            self.connection_dot.configure(text="●  Database unavailable", fg=COLORS["red"])
            self._show_error(error)

        def worker():
            try:
                counts = fetch_counts()
            except Exception as error:
                self.root.after(0, lambda exc=error: show_failure(exc))
                return
            self.root.after(0, lambda: show_counts(counts))

        threading.Thread(target=worker, daemon=True).start()

    def _load_records(self):
        resource = self.current_resource
        if resource is None:
            return

        def fetch():
            documents = get_database()[resource.collection].find().limit(500)
            return [self._serialize_document(document) for document in documents]

        def display(records):
            if self.current_resource != resource:
                return
            self.records = records
            self._render_rows()
            self.status_var.set(f"{len(records)} {resource.label.lower()} loaded")

        self._run_background(fetch, display, f"Loading {resource.label.lower()}…")

    @staticmethod
    def _serialize_document(document: dict) -> dict:
        serialized = dict(document)
        if "_id" in serialized:
            serialized["id"] = str(serialized.pop("_id"))
        return serialized

    @staticmethod
    def _display_value(value: Any) -> str:
        text = format_field_value(value).replace("\n", ", ")
        return text if len(text) <= 68 else text[:65] + "…"

    def _render_rows(self):
        if self.current_resource is None or not hasattr(self, "tree"):
            return
        query = self.search_var.get().casefold().strip()
        filtered = [
            record
            for record in self.records
            if not query
            or any(query in str(record.get(field, "")).casefold() for field in self.current_resource.search_fields)
        ]
        for item in self.tree.get_children():
            self.tree.delete(item)
        for record in filtered:
            self.tree.insert(
                "",
                "end",
                iid=record["id"],
                values=[
                    self._display_value(record.get(field))
                    for field in self.current_resource.fields
                ],
            )
        if hasattr(self, "table_count"):
            self.table_count.set(f"{len(filtered)} records")

    def _selected_record(self) -> dict | None:
        if self.current_resource is None or not hasattr(self, "tree"):
            return None
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Select a record", "Choose a record from the table first.", parent=self.root)
            return None
        record_id = selection[0]
        return next((record for record in self.records if record["id"] == record_id), None)

    def _new_record(self):
        if self.current_resource is None:
            return
        dialog = RecordForm(self.root, self.current_resource)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        resource = self.current_resource
        model = dialog.result

        def create():
            payload = record_to_mongo(model)
            result = get_database()[resource.collection].insert_one(payload)
            return result.inserted_id

        def created(_record_id):
            self.status_var.set(f"{resource.singular} created")
            self._load_records()
            self._refresh_counts()

        self._run_background(create, created, f"Creating {resource.singular.lower()}…")

    def _edit_selected(self):
        record = self._selected_record()
        if record is None or self.current_resource is None:
            return
        dialog = RecordForm(self.root, self.current_resource, record)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        resource = self.current_resource
        model = dialog.result
        record_id = record["id"]

        def update():
            result = get_database()[resource.collection].replace_one(
                {"_id": ObjectId(record_id)},
                record_to_mongo(model),
            )
            if result.matched_count == 0:
                raise LookupError(f"{resource.singular} was not found.")

        def updated(_result):
            self.status_var.set(f"{resource.singular} updated")
            self._load_records()

        self._run_background(update, updated, f"Updating {resource.singular.lower()}…")

    def _delete_selected(self):
        record = self._selected_record()
        if record is None or self.current_resource is None:
            return
        resource = self.current_resource
        if not messagebox.askyesno(
            "Delete record",
            f"Delete this {resource.singular.lower()}? This action cannot be undone.",
            parent=self.root,
        ):
            return
        record_id = record["id"]

        def delete():
            result = get_database()[resource.collection].delete_one(
                {"_id": ObjectId(record_id)}
            )
            if result.deleted_count == 0:
                raise LookupError(f"{resource.singular} was not found.")

        def deleted(_result):
            self.status_var.set(f"{resource.singular} deleted")
            self._load_records()
            self._refresh_counts()

        self._run_background(delete, deleted, f"Deleting {resource.singular.lower()}…")


def main():
    root = tk.Tk()
    HospitalDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
