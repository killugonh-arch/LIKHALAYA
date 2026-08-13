from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils.safestring import mark_safe
from .models import Product, Category, ContactMessage, LivelihoodVideo, ProductImage


class ProductImageWidget(forms.ClearableFileInput):
    """A cleaner image upload widget: drag-and-drop style, live preview,
    no 'Clear' checkbox — uploading a new file simply replaces the old one."""
    template_name = None  # we render manually below

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        input_id = attrs.get('id', f'id_{name}')
        has_image = bool(value and hasattr(value, 'url'))
        image_url = value.url if has_image else ''

        return mark_safe(f"""
<div class="product-image-upload" id="wrap_{input_id}">
  <label for="{input_id}" class="image-dropzone{' has-image' if has_image else ''}" id="dropzone_{input_id}">
    <img src="{image_url}" alt="" class="image-dropzone-preview" id="preview_{input_id}" style="{'' if has_image else 'display:none;'}">
    <div class="image-dropzone-placeholder" id="placeholder_{input_id}" style="{'display:none;' if has_image else ''}">
      <i class="fas fa-cloud-upload-alt"></i>
      <div class="fw-semibold small mt-2">Click to upload or drag and drop</div>
      <div class="text-muted" style="font-size:11px;">JPG, PNG, WebP — Max 5MB</div>
    </div>
    <div class="image-dropzone-overlay">
      <i class="fas fa-camera me-1"></i>Change Photo
    </div>
  </label>
  <input type="file" name="{name}" id="{input_id}" class="d-none" accept="image/*"
         onchange="likhalayaPreviewImage(this, '{input_id}')">
</div>
<script>
if (typeof likhalayaPreviewImage !== 'function') {{
  function likhalayaPreviewImage(input, id) {{
    const preview = document.getElementById('preview_' + id);
    const placeholder = document.getElementById('placeholder_' + id);
    const dropzone = document.getElementById('dropzone_' + id);
    if (input.files && input.files[0]) {{
      const reader = new FileReader();
      reader.onload = e => {{
        preview.src = e.target.result;
        preview.style.display = 'block';
        placeholder.style.display = 'none';
        dropzone.classList.add('has-image');
      }};
      reader.readAsDataURL(input.files[0]);
    }}
  }}
}}
</script>
""")

    def value_omitted_from_data(self, data, files, name):
        return name not in files


class ProductSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Search products…'
    }))
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False, empty_label="All Categories",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    sort = forms.ChoiceField(choices=[
        ('newest', 'Newest First'),
        ('price_asc', 'Price: Low to High'),
        ('price_desc', 'Price: High to Low'),
        ('name', 'Name A-Z'),
    ], required=False, widget=forms.Select(attrs={'class': 'form-select'}))

class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Your message…'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'category', 'description', 'price_min', 'price_medium', 'price_max', 'stock',
                  'image', 'is_active']
        labels = {
            'price_min': 'Small Price',
            'price_medium': 'Medium Price',
            'price_max': 'Large Price',
        }
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': 'Describe the product...\n• Materials used\n• Size\n• Production time\n• Other details'
            }),
            'price_min': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Small (lowest price)'}),
            'price_medium': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Medium (optional)'}),
            'price_max': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Large (optional)'}),
            'image': ProductImageWidget(),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price_medium'].required = False
        self.fields['price_medium'].help_text = (
            "Leave blank to auto-set as the midpoint between Small and Large."
        )
        self.fields['price_max'].required = False
        self.fields['price_max'].help_text = (
            "Leave blank to sell at a single price. "
            "If set, buyers choose Small (lowest), Medium (middle) or Large (highest)."
        )
        for field in self.fields.values():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput,
                                         forms.EmailInput, forms.Textarea, forms.Select)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input', 'role': 'switch'})
            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs.update({'class': 'form-control'})


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'size', 'caption', 'order']
        widgets = {
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'size': forms.Select(attrs={'class': 'form-select'}),
            'caption': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Caption (optional)'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'display:none;'}),
        }


class BaseProductImageFormSet(BaseInlineFormSet):
    """Enforces a max of 3 gallery photos per size bucket
    (General / Small / Medium / Large) — server-side backstop for
    the same cap the dashboard JS enforces live."""
    MAX_PER_SIZE = 3
    SIZE_LABELS = {'': 'All sizes (general)', 'S': 'Small', 'M': 'Medium', 'L': 'Large'}

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        counts = {'': 0, 'S': 0, 'M': 0, 'L': 0}
        for form in self.forms:
            cleaned = getattr(form, 'cleaned_data', None)
            if not cleaned or cleaned.get('DELETE'):
                continue
            # Skip untouched blank extra rows (no new image, no existing instance)
            if not cleaned.get('image') and not form.instance.pk:
                continue
            size = cleaned.get('size') or ''
            counts[size] = counts.get(size, 0) + 1
        for size, count in counts.items():
            if count > self.MAX_PER_SIZE:
                raise forms.ValidationError(
                    f'You can only add up to {self.MAX_PER_SIZE} photos for '
                    f'{self.SIZE_LABELS.get(size, size)}.'
                )


ProductImageFormSet = inlineformset_factory(
    Product, ProductImage,
    form=ProductImageForm,
    formset=BaseProductImageFormSet,
    extra=3,
    can_delete=True,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class LivelihoodVideoForm(forms.ModelForm):
    class Meta:
        model = LivelihoodVideo
        fields = ['title', 'description', 'video_url', 'video_file', 'thumbnail', 'order', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Livelihood Skills Training'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Short description of this program...'}),
            'video_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.youtube.com/watch?v=...'}),
            'video_file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'thumbnail': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['video_url'].required = False
        self.fields['video_file'].required = False
        self.fields['thumbnail'].required = False
        self.fields['is_active'].widget.attrs.update({'class': 'form-check-input', 'role': 'switch'})