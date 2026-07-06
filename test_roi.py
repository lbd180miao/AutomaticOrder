import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationRecipe
from apps.vision.rack_location import Rack3DLocator, RackLocationService
import numpy as np

r = RackLocationRecipe.objects.first()
svc = Rack3DLocator()
pointcloud = svc.frame_provider.capture(r, 1, 1)['organized_pointcloud']

ps = RackLocationService(frame_provider=svc.frame_provider, estimator=svc.estimator, plc_writer=svc.plc_writer)
res1 = ps.project_recipe_roi_to_pixels(pointcloud, r)
print("Original:", res1)

config = dict(getattr(r, 'roi_config', None) or {})
camera_roi = config.get('camera_roi')
bounds = ps.estimator.processor._normalized_roi_3d(camera_roi)

cloud = np.asarray(pointcloud, dtype=float)
z = cloud[:, :, 2]
valid = np.isfinite(z) & (np.abs(z) > 1e-9)
x = cloud[:, :, 0]
y = cloud[:, :, 1]

in_roi = (
    valid
    & (x >= bounds['x_min']) & (x <= bounds['x_max'])
    & (y >= bounds['y_min']) & (y <= bounds['y_max'])
    & (z >= bounds['z_min']) & (z <= bounds['z_max'])
)
rows, cols = np.where(in_roi)
if len(rows) > 0:
    x1 = int(cols.min())
    x2 = int(cols.max()) + 1
    y1 = int(rows.min())
    y2 = int(rows.max()) + 1
    print("Point-based:", {'x': x1, 'y': y1, 'w': x2 - x1, 'h': y2 - y1})
else:
    print("No points inside!")
