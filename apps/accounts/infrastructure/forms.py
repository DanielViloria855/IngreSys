"""Infraestructura: formularios de gestión de personal."""
from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password

from apps.accounts.infrastructure.models import Profile
from apps.core.permissions import ensure_roles
from apps.core.roles import get_role
from shared.domain.roles import Role


class StaffForm(forms.Form):
    """Crea o edita un empleado: User + Profile + rol (Group)."""

    username = forms.CharField(label="Usuario", max_length=150)
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo", required=False)
    role = forms.ChoiceField(label="Rol", choices=[(r.value, r.value) for r in Role])
    document_id = forms.CharField(label="Documento", max_length=20, required=False)
    position = forms.CharField(label="Cargo", max_length=80, required=False)
    phone = forms.CharField(label="Teléfono", max_length=20, required=False)
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput(render_value=False), required=False)
    is_active = forms.BooleanField(label="Usuario activo", required=False, initial=True)

    def __init__(self, *args, instance: User | None = None, **kwargs):
        self.instance = instance
        if instance is not None and not args and "initial" not in kwargs:
            profile = getattr(instance, "profile", None)
            role = get_role(instance)
            kwargs["initial"] = {
                "username": instance.username,
                "first_name": instance.first_name,
                "last_name": instance.last_name,
                "email": instance.email,
                "role": role.value if role else Role.OPERATOR.value,
                "document_id": getattr(profile, "document_id", ""),
                "position": getattr(profile, "position", ""),
                "phone": getattr(profile, "phone", ""),
                "is_active": instance.is_active,
            }
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
        self.fields["username"].widget.attrs.update({"autocomplete": "off"})
        self.fields["password"].widget.attrs.update({"autocomplete": "new-password"})
        if instance is None:
            self.fields["password"].required = True
        else:
            self.fields["password"].help_text = "Déjala vacía para conservar la actual."

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        qs = User.objects.filter(username__iexact=username)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self) -> User:
        data = self.cleaned_data
        user = self.instance or User()
        user.username = data["username"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.email = data["email"]
        user.is_active = data["is_active"]
        user.is_staff = data["role"] == Role.ADMIN.value  # el administrador puede entrar al admin de Django
        if data["password"]:
            user.set_password(data["password"])
        user.save()
        ensure_roles()  # garantiza que el grupo exista con sus permisos
        group = Group.objects.get(name=data["role"])
        user.groups.set([group])
        Profile.objects.update_or_create(
            user=user,
            defaults={k: data[k] for k in ("document_id", "position", "phone")},
        )
        return user
