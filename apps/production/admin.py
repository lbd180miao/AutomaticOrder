from django.contrib import admin

from .models import Product, ProductionBatch, Rack, RackRecipe


admin.site.register(ProductionBatch)
admin.site.register(RackRecipe)
admin.site.register(Rack)
admin.site.register(Product)
