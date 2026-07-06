# accounts/forms.py

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import UserProfile


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label="Nom d'utilisateur",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class UserCreateForm(forms.ModelForm):
    """Admin creates a new user account with role assignment."""

    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        label="Rôle",
    )
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput,
        validators=[validate_password],
    )
    password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput,
    )
    phone = forms.CharField(
        max_length=50,
        label="Téléphone",
        required=False,
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {
            "username": "Nom d'utilisateur",
            "first_name": "Prénom",
            "last_name": "Nom",
            "email": "Email",
        }

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        role = self.cleaned_data["role"]
        if role == UserProfile.ROLE_ADMIN:
            user.is_staff = True
            user.is_superuser = True
        if commit:
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": role,
                    "phone": self.cleaned_data.get("phone", ""),
                },
            )
        return user


class UserEditForm(forms.ModelForm):
    """Admin edits an existing user — no password change here."""

    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, label="Rôle")
    phone = forms.CharField(max_length=50, label="Téléphone", required=False)
    is_active_profile = forms.BooleanField(
        label="Compte actif",
        required=False,
        initial=True,
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "email": "Email",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, "profile"):
            profile = self.instance.profile
            self.fields["role"].initial = profile.role
            self.fields["phone"].initial = profile.phone
            self.fields["is_active_profile"].initial = profile.is_active

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        role = self.cleaned_data["role"]
        user.is_staff = role == UserProfile.ROLE_ADMIN
        user.is_superuser = role == UserProfile.ROLE_ADMIN
        if commit:
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": role,
                    "phone": self.cleaned_data.get("phone", ""),
                    "is_active": self.cleaned_data.get("is_active_profile", True),
                },
            )
        return user


class PasswordChangeForm(forms.Form):
    """User changes their own password."""

    current_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput,
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput,
        validators=[validate_password],
    )
    new_password2 = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pwd = self.cleaned_data.get("current_password")
        if not self.user.check_password(pwd):
            raise ValidationError("Le mot de passe actuel est incorrect.")
        return pwd

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "Les mots de passe ne correspondent pas.")
        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save()


class AdminPasswordResetForm(forms.Form):
    """Admin force-resets another user's password."""

    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput,
        validators=[validate_password],
    )
    new_password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "Les mots de passe ne correspondent pas.")
        return cleaned_data


class ProfileEditForm(forms.ModelForm):
    """User edits their own display name / contact info (not role)."""

    first_name = forms.CharField(max_length=150, label="Prénom", required=False)
    last_name = forms.CharField(max_length=150, label="Nom", required=False)
    email = forms.EmailField(label="Email", required=False)

    class Meta:
        model = UserProfile
        fields = ["phone", "avatar", "language"]
        labels = {
            "phone": "Téléphone",
            "avatar": "Photo de profil",
            "language": "Langue",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            user = self.instance.user
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            qs = User.objects.filter(email=email).exclude(pk=self.instance.user.pk)
            if qs.exists():
                raise ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
            profile.save()
        return profile
