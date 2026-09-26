from django import forms

INVALID_EMAIL_MESSAGE = 'Informe um endereço de e-mail válido.'


class StyledFormMixin:
    """Design system tweaks shared by every form of the project.

    - Widgets of fields with errors get the ``input-error`` class (only
      those styled with ``input``) and ``aria-invalid="true"``.
    - E-mail fields use the pt-BR "e-mail" spelling in their message.
    """

    error_class_name = 'input-error'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.EmailField):
                field.error_messages['invalid'] = INVALID_EMAIL_MESSAGE

    def add_error(self, field, error):
        # Every field, clean() and model validation error goes through
        # add_error(), so the widgets are marked in a single place.
        super().add_error(field, error)
        for name in self._errors:
            if name in self.fields:
                self._mark_widget_invalid(self.fields[name].widget)

    def _mark_widget_invalid(self, widget):
        # RadioSelect copies its attrs to the wrapper <div> too, so the
        # radio groups (color, transaction type) are left untouched.
        if isinstance(widget, forms.RadioSelect) or widget.is_hidden:
            return
        widget.attrs['aria-invalid'] = 'true'
        classes = widget.attrs.get('class', '').split()
        if 'input' in classes and self.error_class_name not in classes:
            classes.append(self.error_class_name)
            widget.attrs['class'] = ' '.join(classes)


class PasswordErrorsOnFirstFieldMixin:
    """Show password strength errors under the first password field.

    Django validates the strength against ``password2``/``new_password2``;
    the mismatch error stays on the confirmation field.
    """

    password_error_fields = {
        'password2': 'password1',
        'new_password2': 'new_password1',
    }

    def validate_password_for_user(
        self, user, password_field_name='password2'
    ):
        password_field_name = self.password_error_fields.get(
            password_field_name, password_field_name
        )
        super().validate_password_for_user(user, password_field_name)
