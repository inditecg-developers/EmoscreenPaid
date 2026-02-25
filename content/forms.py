import re
from django import forms
from .models import RegisteredProfessional
from .utils import normalize_phone
from .state_districts import state_choices, district_choices, is_valid_pair

SALUTATIONS = [("Dr", "Dr."), ("Mr", "Mr."), ("Ms", "Ms."), ("Mrs", "Mrs.")]


def _validate_gmail_address(email: str) -> str:
    email = (email or "").strip()
    if not re.fullmatch(r"[^@\s]+@(gmail\.com|googlemail\.com)", email, flags=re.I):
        raise forms.ValidationError("Please enter a valid Gmail address (…@gmail.com).")
    return email.lower()


class PediatricianForm(forms.ModelForm):
    class Meta:
        model = RegisteredProfessional
        fields = [
            "salutation", "first_name", "last_name", "email", "whatsapp",
            "imc_registration_number", "appointment_booking_number",
            "clinic_address", "state", "district",
            "receptionist_whatsapp", "photo_url"
        ]
        widgets = {
            "salutation": forms.Select(choices=[("Dr", "Dr.")]),
            "clinic_address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = name not in ("receptionist_whatsapp", "photo_url")
        self.fields["photo_url"].label = "Upload your Photo"
        self.fields["appointment_booking_number"].label = "Appointment Booking Number"

        sel_state = (self.data.get("state") or self.initial.get("state") or "")
        self.fields["state"].widget = forms.Select(choices=state_choices())
        self.fields["district"].widget = forms.Select(choices=district_choices(sel_state))
        self.fields["district"].required = True

    def clean_email(self):
        return _validate_gmail_address(self.cleaned_data["email"])

    def clean_whatsapp(self):
        return normalize_phone(self.cleaned_data["whatsapp"])

    def clean_appointment_booking_number(self):
        return normalize_phone(self.cleaned_data["appointment_booking_number"])

    def clean_receptionist_whatsapp(self):
        val = self.cleaned_data.get("receptionist_whatsapp")
        return normalize_phone(val) if val else val

    def clean(self):
        data = super().clean()
        if not data.get("receptionist_whatsapp"):
            data["receptionist_whatsapp"] = data.get("whatsapp")

        state = (data.get("state") or "").strip()
        district = (data.get("district") or "").strip()
        if state == "NULL":
            data["district"] = "NULL"
        elif not is_valid_pair(state, district):
            self.add_error("district", "Please choose a district that belongs to the selected state.")
        return data


class CaregiverForm(forms.ModelForm):
    name = forms.CharField(label="Name of Caregiver")

    class Meta:
        model = RegisteredProfessional
        fields = [
            "salutation", "email", "whatsapp", "appointment_booking_number",
            "clinic_address", "state", "district", "receptionist_whatsapp", "photo_url"
        ]
        widgets = {
            "salutation": forms.Select(choices=SALUTATIONS),
            "clinic_address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        for name, field in self.fields.items():
            field.required = name not in ("receptionist_whatsapp", "photo_url")
        self.fields["photo_url"].label = "Upload your Photo"
        self.fields["appointment_booking_number"].label = "Appointment Booking Number"

        sel_state = (self.data.get("state") or self.initial.get("state") or "")
        self.fields["state"].widget = forms.Select(choices=state_choices())
        self.fields["district"].widget = forms.Select(choices=district_choices(sel_state))
        self.fields["district"].required = True

    def clean_email(self):
        return _validate_gmail_address(self.cleaned_data["email"])

    def clean_whatsapp(self):
        return normalize_phone(self.cleaned_data["whatsapp"])

    def clean_appointment_booking_number(self):
        return normalize_phone(self.cleaned_data["appointment_booking_number"])

    def clean_receptionist_whatsapp(self):
        val = self.cleaned_data.get("receptionist_whatsapp")
        return normalize_phone(val) if val else val

    def clean(self):
        data = super().clean()
        if not data.get("receptionist_whatsapp"):
            data["receptionist_whatsapp"] = data.get("whatsapp")

        state = (data.get("state") or "").strip()
        district = (data.get("district") or "").strip()
        if state == "NULL":
            data["district"] = "NULL"
        elif not is_valid_pair(state, district):
            self.add_error("district", "Please choose a district that belongs to the selected state.")
        return data


class ClinicSendForm(forms.Form):
    parent_whatsapp = forms.CharField(
        label="Enter Parent's WhatsApp No.",
        max_length=20
    )
    language = forms.ChoiceField(choices=[], label="Select Language")
    share_form = forms.ChoiceField(choices=[], label="Select Form")
    patient_name = forms.CharField(label="Patient Name (for paid form)", max_length=255, required=False)
    price_variant = forms.ChoiceField(
        label="Paid Price",
        required=False,
        choices=[
            ("INR_499", "₹499"),
            ("INR_100", "₹100"),
            ("INR_20", "₹20"),
            ("INR_1", "₹1"),
            ("INR_0", "₹0"),
        ],
        initial="INR_0",
    )

    def __init__(self, *args, **kwargs):
        lang_choices = kwargs.pop("lang_choices", [])
        form_choices = kwargs.pop("form_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["language"].choices = lang_choices
        self.fields["share_form"].choices = form_choices

    def clean_parent_whatsapp(self):
        return normalize_phone(self.cleaned_data["parent_whatsapp"])


class BulkDoctorUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="Upload CSV (max 100 rows)",
        help_text="CSV must include Doctor Name, WhatsApp Number, Email ID, IMC Registration Number. "
                  "Optional: Clinic Appointment Booking Number, Clinic Address with Postal Code, "
                  "State, District, Receptionist WhatsApp Number, Receptionist Email ID, Doctor’s Photo."
    )

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file")
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("CSV too large (limit ~2MB)")
        return f

# content/forms.py  (append at bottom)
from django import forms
from django.utils import timezone

class ReportFilterForm(forms.Form):
    
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to   = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        df, dt = data.get("date_from"), data.get("date_to")
        if df and dt and df > dt:
            raise forms.ValidationError("Start date must be on or before end date.")
        return data
