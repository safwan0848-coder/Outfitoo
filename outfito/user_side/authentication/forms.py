from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class SignupForm(UserCreationForm):
    class Meta:
        model=User
        fields=['username','email','password1','password2']

class ResetPasswordForm(forms.Form):
    password1=forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Enter new password'}))
    password2=forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirm new password'}))

    def clean(self):
        cleaned_data=super().clean()
        password1=cleaned_data.get('password1')
        password2=cleaned_data.get('password2')

        if password1!=password2:
            raise forms.ValidationError("Passwords do not match.")
        if password1 and len(password1)<6:
            raise forms.ValidationError("Password must be at least 6 characters.")
        return cleaned_data

    