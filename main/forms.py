from django import forms
from .models import Activity, Client, Client, Deal, Employee

class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["kind", "duration_min", "notes"]  # user заповнимо в view
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "phone", "email", "notes", "deal_status"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

class DealForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = ["client", "title", "amount", "status", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "first_name", "last_name", "gender", "birth_date", "birth_place",
            "registration_address", "marital_status", "photo", "contract_file",
            "hire_date", "termination_date", "is_active", "absences_count",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "termination_date": forms.DateInput(attrs={"type": "date"}),
        }