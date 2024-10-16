from fasthtml.common import *
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Dict, List
from openai import OpenAI
from textwrap import dedent
from dotenv import load_dotenv
import uuid
import json
from datetime import datetime

load_dotenv()
MODEL = "gpt-4o-mini-2024-07-18"
client = OpenAI()

css = Style("""
    :root { --pico-font-size: 100%; --pico-font-family: Pacifico, cursive; }
    .form-list { list-style-type: none; padding: 0; }
    .form-list li { margin-bottom: 10px; }
    .analytics { margin-top: 20px; }
    .preview-form { border: 1px solid #ccc; padding: 20px; margin-bottom: 20px; }
""")
app = FastHTML(hdrs=(picolink, css))

rt = app.route


class TypeEnum(str, Enum):
    text = "text"
    number = "number"
    date = "date"
    radio = "radio"
    checkbox = "checkbox"
    select = "select"
    textarea = "textarea"


class Options(BaseModel):
    label: str = Field(description="unique label for the option")
    value: str = Field(description="unique value for the option")


class FormField(BaseModel):
    label: str = Field(description="Title of the field")
    type: TypeEnum = Field(description="Type of the field")
    name: str = Field(description="unique name to access the field")
    required: bool = Field(description="Whether the field is required")
    placeholder: Optional[str] = Field(
        description="Placeholder for the field. only applicable for the type text and text area"
    )
    options: Optional[List[Options]] = Field(
        description="Options for the field. only applicable for the type radio, checkbox and select"
    )


class DynamicForm(BaseModel):
    title: str = Field(description="Title of the form")
    fields: List[FormField] = Field(description="List of fields")


class FormResponse(BaseModel):
    response_id: str
    form_id: str
    data: Dict[str, str]
    timestamp: datetime


form_prompt = ""
dynamic_form_data: DynamicForm = None
generated_forms: Dict[str, DynamicForm] = {}
form_responses: Dict[str, List[FormResponse]] = {}


def get_form_response(prompt):
    system_prompt = """
        You are a helpful dynamic html form creator. You will be provided with a dynamic form requirement,
        and your goal will be to output form fields.
        For each field, just provide the correct configuration.
    """
    completion = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": dedent(system_prompt)},
            {"role": "user", "content": prompt},
        ],
        response_format=DynamicForm,
    )
    return completion.choices[0].message


def create_dynamic_form(form_data: DynamicForm | None, form_id: str, is_preview: bool = False):
    if form_data is None:
        return None

    fields = []

    for field in form_data.fields:
        field_type = field.type
        if field_type in ["text", "number", "date"]:
            fields.append(
                Div(
                    Label(field.label, _for=field.name),
                    Input(
                        type=field_type,
                        name=field.name,
                        placeholder=field.placeholder,
                        required=field.required,
                    ),
                    style="margin-bottom: 15px;",
                )
            )
        elif field_type == "select":
            options = [
                Option(value=opt.value, label=opt.label) for opt in field.options
            ]
            fields.append(
                Div(
                    Label(field.label, _for=field.label),
                    Select(*options, name=field.name, required=field.required),
                    style="margin-bottom: 15px;",
                )
            )
        elif field_type == "checkbox":
            checkboxes = [
                Div(
                    Input(
                        type="checkbox",
                        name=field.name,
                        value=opt.value,
                        id=f"{field.name}_{opt.value}",
                    ),
                    Label(opt.label, _for=f"{field.name}_{opt.value}"),
                )
                for opt in field.options
            ]
            fields.append(
                Div(Label(field.label), Div(*checkboxes), style="margin-bottom: 15px;")
            )
        elif field_type == "radio":
            radios = [
                Div(
                    Input(
                        type="radio",
                        name=field.name,
                        value=opt.value,
                        id=f"{field.name}_{opt.value}",
                        required=field.required,
                    ),
                    Label(opt.label, _for=f"{field.name}_{opt.label}"),
                )
                for opt in field.options
            ]
            fields.append(
                Div(Label(field.label), Div(*radios), style="margin-bottom: 15px;")
            )
        elif field_type == "textarea":
            fields.append(
                Div(
                    Label(field.label, _for=field.name),
                    Textarea(
                        name=field.name,
                        placeholder=field.placeholder,
                        required=field.required,
                    ),
                    style="margin-bottom: 15px;",
                )
            )

    if is_preview:
        form = Div(*fields, _class="preview-form")
    else:
        form = Form(
            *fields,
            Button("Submit", type="submit", style="margin-top: 20px;"),
            method="post",
            action=f"/submit/{form_id}",
        )

    return Container(H1(form_data.title), form)


@app.get("/")
def home():
    create_form_button = A("Create Form", href="/create-form", role="button")
    form_list = Ul(*[Li(A(form.title, href=f"/analytics/{form_id}")) for form_id, form in generated_forms.items()],
                   _class="form-list")
    return Container(
        H1("Dynamic Form Creator"),
        create_form_button,
        H2("Created Forms:"),
        form_list if generated_forms else P("No forms created yet.")
    )


@app.get("/create-form")
def create_form():
    return Container(
        H1("Create a New Form"),
        Form(
            Textarea(
                name="prompt",
                placeholder="Enter your prompt to create a dynamic form...",
                style="width: 100%; margin-bottom: 5px;",
            ),
            Button(
                "Generate Form",
                type="submit",
            ),
            method="post",
            action="/generate-form",
        )
    )


@app.post("/generate-form")
async def generate_form(request):
    form_data = await request.form()
    prompt = form_data.get("prompt", "")
    if prompt:
        dynamic_form_data = get_form_response(prompt)
        form_id = str(uuid.uuid4())
        generated_forms[form_id] = dynamic_form_data.parsed
        form_responses[form_id] = []
        share_link = f"/share/{form_id}"

        # Create a preview of the form
        preview_form = create_dynamic_form(dynamic_form_data.parsed, form_id, is_preview=True)

        return Container(
            H1("Form Generated Successfully"),
            H2("Form Preview:"),
            preview_form,
            P(f"Share this form: ", A(share_link, href=share_link, target="_blank")),
            A("Back to Home", href="/", role="button")
        )
    return Container(H1("Error generating form. Please try again."))


@app.get("/share/{form_id}")
def share_form(form_id: str):
    if form_id in generated_forms:
        form_data = generated_forms[form_id]
        return Container(
            create_dynamic_form(form_data, form_id)
        )
    else:
        return Container(H1("Form not found"))


@app.post("/submit/{form_id}")
async def submit_form(request, form_id: str):
    if form_id not in generated_forms:
        return Container(H1("Form not found"))

    form_data = await request.form()
    response_id = str(uuid.uuid4())
    response = FormResponse(
        response_id=response_id,
        form_id=form_id,
        data=dict(form_data),
        timestamp=datetime.now()
    )
    form_responses[form_id].append(response)

    return Container(
        H1("Form Submitted Successfully"),
        H2("Your Responses:"),
        Ul(*[Li(f"{key}: {value}") for key, value in form_data.items()]),
        P("Thank you for your submission!")
    )


@app.get("/analytics/{form_id}")
def show_analytics(form_id: str):
    if form_id not in generated_forms:
        return Container(H1("Form not found"))

    form = generated_forms[form_id]
    responses = form_responses.get(form_id, [])

    analytics = Div(_class="analytics")
    for field in form.fields:
        field_responses = [response.data.get(field.name, "") for response in responses]
        if field.type in ["text", "textarea"]:
            analytics.append(
                Div(
                    H3(f"Responses for {field.label}:"),
                    Ul(*[Li(response) for response in field_responses])
                )
            )
        elif field.type in ["number", "date"]:
            analytics.append(
                Div(
                    H3(f"Statistics for {field.label}:"),
                    P(f"Average: {sum(float(r) for r in field_responses if r) / len(field_responses) if field_responses else 0}"),
                    P(f"Min: {min(field_responses, default='N/A')}"),
                    P(f"Max: {max(field_responses, default='N/A')}")
                )
            )
        elif field.type in ["radio", "select", "checkbox"]:
            option_counts = {option.value: field_responses.count(option.value) for option in field.options}
            analytics.append(
                Div(
                    H3(f"Response distribution for {field.label}:"),
                    Ul(*[Li(f"{option}: {count}") for option, count in option_counts.items()])
                )
            )

    return Container(
        H1(f"Analytics for {form.title}"),
        P(f"Total Responses: {len(responses)}"),
        analytics,
        A("Back to Home", href="/", role="button")
    )


serve()