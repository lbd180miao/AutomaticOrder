"""Read-only deployment preflight for standards that still require raw clouds."""
from django.core.management.base import BaseCommand, CommandError
from apps.vision.models import RackLocationRecipe, RackLocationResult
from apps.vision.rack_location import RackLocationService


class Command(BaseCommand):
    help = '检查旧标准依赖的点云；打包前运行，不修改配方或记录'

    def handle(self, *args, **options):
        service = RackLocationService()
        failures = []
        for recipe in RackLocationRecipe.objects.filter(enabled=True):
            standard = recipe.local_template_std or {}
            source_id = standard.get('source_result_id')
            if not source_id or standard.get('dual_axis_standard'):
                continue
            try:
                record = RackLocationResult.objects.get(pk=source_id, recipe_id=recipe.pk)
                service._load_workbench_pointcloud(record.raw_data_path)
            except (RackLocationResult.DoesNotExist, ValueError, OSError) as exc:
                failures.append(f'配方 #{recipe.pk} / 标准 #{source_id}: {exc}')
        if failures:
            raise CommandError('\n'.join(failures))
        self.stdout.write(self.style.SUCCESS('旧标准点云引用检查通过'))
