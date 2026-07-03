import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'automatic_order.settings')
django.setup()

from django.template.loader import render_to_string
from apps.vision.models import RackLocationRecipe
import re

try:
    recipes = RackLocationRecipe.objects.all()
    content = render_to_string('vision/rack_location_recipes.html', {'recipes': recipes})
    print('Template rendered successfully, length:', len(content))
    matches = re.findall(r'<div class=\"recipe-card-row\">.*?</div>', content, re.DOTALL)
    for i, m in enumerate(matches):
        print(f'Match {i}: {m.strip()[:200]}...')
except Exception as e:
    print('Template error:', e)
