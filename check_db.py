from apps.vision.models import RackLocationRecipe
for r in RackLocationRecipe.objects.filter(enabled=True):
    print(f"ID={r.id}, ROI={r.roi_config}")
