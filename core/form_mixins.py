# core/form_mixins.py
# =============================================================================
# ISIFormMixin — Auto-applies Bootstrap 5 CSS classes to every Django widget.
#
# Usage:
#   class MyForm(ISIFormMixin, forms.ModelForm): ...
#   class MyForm(ISIFormMixin, forms.Form): ...
#
# Must be listed BEFORE forms.ModelForm / forms.Form in the MRO so that
# __init__ runs first and patches the widgets before render.
# =============================================================================

from django import forms


class ISIFormMixin:
    """
    Injects Bootstrap 5 + ISI-design-system CSS classes into every widget
    declared on the form, without requiring explicit widget definitions.

    Widget → class mapping
    ──────────────────────
    TextInput, EmailInput, URLInput, PasswordInput,
    NumberInput, DateInput, DateTimeInput, TimeInput  →  form-control
    Textarea                                           →  form-control
    Select                                             →  form-select
    SelectMultiple                                     →  form-select
    CheckboxInput                                      →  form-check-input
    FileInput, ClearableFileInput                      →  form-control
    HiddenInput, MultipleHiddenInput                   →  (untouched)
    """

    # Widget types that take "form-control"
    _CONTROL_TYPES = (
        forms.TextInput,
        forms.EmailInput,
        forms.URLInput,
        forms.PasswordInput,
        forms.NumberInput,
        forms.DateInput,
        forms.DateTimeInput,
        forms.TimeInput,
        forms.Textarea,
        forms.FileInput,
        forms.ClearableFileInput,
    )

    # Widget types that take "form-select"
    _SELECT_TYPES = (
        forms.Select,
        forms.SelectMultiple,
    )

    # Widget types that take "form-check-input"
    _CHECK_TYPES = (forms.CheckboxInput,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget

            # Handle MultiWidget (e.g. SplitDateTimeWidget) recursively
            if isinstance(widget, forms.MultiWidget):
                for sub in widget.widgets:
                    self._apply_class(sub)
            else:
                self._apply_class(widget)

    @staticmethod
    def _apply_class(widget):
        """Add the appropriate Bootstrap class to a single widget instance."""
        if isinstance(widget, ISIFormMixin._CHECK_TYPES):
            _add_class(widget, "form-check-input")
        elif isinstance(widget, ISIFormMixin._SELECT_TYPES):
            _add_class(widget, "form-select")
        elif isinstance(widget, ISIFormMixin._CONTROL_TYPES):
            _add_class(widget, "form-control")
        # HiddenInput and others → no class added


def _add_class(widget, css_class):
    """Append css_class to the widget's existing class list (idempotent)."""
    existing = widget.attrs.get("class", "")
    classes = existing.split() if existing else []
    if css_class not in classes:
        classes.append(css_class)
    widget.attrs["class"] = " ".join(classes)
