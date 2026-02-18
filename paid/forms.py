from django import forms

from .models import EsCfgForm


class PaidPrescriptionForm(forms.Form):
    PRICE_CHOICES = [
        ("INR_499", "₹499"),
        ("INR_100", "₹100"),
        ("INR_20", "₹20"),
        ("INR_1", "₹1"),
        ("INR_0", "₹0"),
    ]

    form_code = forms.ModelChoiceField(queryset=EsCfgForm.objects.filter(is_active=True), to_field_name="form_code")
    price_variant = forms.ChoiceField(choices=PRICE_CHOICES)
    patient_name = forms.CharField(max_length=255)
    patient_whatsapp = forms.CharField(max_length=20)
    patient_email = forms.EmailField(required=False)
    discount_rupees = forms.IntegerField(min_value=0, required=False, initial=0)


class PatientEmailForm(forms.Form):
    patient_email = forms.EmailField()


class DemographicsForm(forms.Form):
    child_name = forms.CharField(max_length=255)
    child_dob = forms.DateField(required=True)
    assessment_date = forms.DateField(required=True)
    gender = forms.ChoiceField(choices=[("male", "Male"), ("female", "Female"), ("other", "Other")])
    completed_by = forms.CharField(max_length=255)
    consent_given = forms.BooleanField(required=True)
