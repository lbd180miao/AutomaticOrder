"""rack_3d REST API 路由，挂载前缀 /vision/rack-3d/。"""

from django.urls import path

from . import api

app_name = 'rack_3d'

urlpatterns = [
    path('', api.page, name='page'),
    path('recipes/', api.recipes, name='recipes'),
    path('recipes/<int:recipe_id>/rois/', api.recipe_rois, name='recipe_rois'),
    path('recipes/<int:recipe_id>/coordinates/', api.update_coordinates, name='update_coordinates'),
    path('rois/', api.upsert_roi, name='upsert_roi'),
    path('capture/', api.capture, name='capture'),
    path('calculate/', api.calculate, name='calculate'),
    path('results/', api.results, name='results'),
]
