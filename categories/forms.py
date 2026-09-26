from django import forms

from categories.models import Category
from core.forms import StyledFormMixin

COLOR_CHOICES = (
    ('#8B5CF6', 'Violeta'),
    ('#6366F1', 'Índigo'),
    ('#22D3EE', 'Ciano'),
    ('#10B981', 'Verde'),
    ('#F59E0B', 'Âmbar'),
    ('#F43F5E', 'Rosa'),
    ('#EC4899', 'Rosa-choque'),
    ('#84CC16', 'Lima'),
)


class CategoryForm(StyledFormMixin, forms.ModelForm):
    # Declared explicitly so the submitted color is validated against
    # COLOR_CHOICES (the model field is a plain CharField). The
    # model default ('#8B5CF6') is reused as the initial value on creation;
    # on update the saved color comes from the instance.
    color = forms.ChoiceField(
        label='Cor',
        choices=COLOR_CHOICES,
        initial=Category._meta.get_field('color').default,
        widget=forms.RadioSelect,
        error_messages={
            'required': 'Selecione uma cor.',
            'invalid_choice': 'Selecione uma cor válida.',
        },
    )

    class Meta:
        model = Category
        fields = ('name', 'category_type', 'color')
        labels = {
            'name': 'Nome',
            'category_type': 'Tipo',
        }
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'input', 'placeholder': 'Ex.: Alimentação'}
            ),
            'category_type': forms.Select(attrs={'class': 'input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        # Django 6.1 has no pt-BR translation for the blank choice label.
        self.fields['category_type'].choices = [
            ('', 'Selecione o tipo'),
            *Category.CategoryType.choices,
        ]

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        category_type = cleaned_data.get('category_type')
        if self.user is None or not name or not category_type:
            return cleaned_data

        # name__iexact is ASCII-only on SQLite ('SAÚDE' != 'Saúde'), so
        # the case-insensitive comparison is done with casefold().
        existing_names = Category.objects.filter(
            user=self.user, category_type=category_type
        )
        if self.instance.pk:
            existing_names = existing_names.exclude(pk=self.instance.pk)
        normalized = name.strip().casefold()
        existing_names = existing_names.values_list('name', flat=True)
        if any(n.strip().casefold() == normalized for n in existing_names):
            raise forms.ValidationError(
                'Já existe uma categoria com este nome para este tipo.'
            )
        return cleaned_data
