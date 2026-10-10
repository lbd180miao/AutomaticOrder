"""Django management command to check ROI quality."""
from django.core.management.base import BaseCommand
from apps.vision.models import RackLocationRecipe, RackLocationResult
from apps.vision.rack_location import RackLocationService
from apps.vision.rack_roi_optimizer import batch_analyze_recipe_rois, print_roi_report


class Command(BaseCommand):
    help = 'Check ROI quality and suggest optimizations for rack locator'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recipe',
            type=int,
            required=True,
            help='Recipe ID to analyze'
        )
        parser.add_argument(
            '--result',
            type=int,
            default=None,
            help='Optional: use specific result ID for pointcloud (default: latest)'
        )

    def handle(self, *args, **options):
        recipe_id = options['recipe']
        result_id = options.get('result')
        
        try:
            recipe = RackLocationRecipe.objects.get(pk=recipe_id)
            service = RackLocationService()
            
            # Get pointcloud token
            if result_id:
                result = RackLocationResult.objects.get(pk=result_id, recipe_id=recipe_id)
                token = result.raw_data_path
            else:
                # Use latest result
                result = RackLocationResult.objects.filter(recipe_id=recipe_id).order_by('-id').first()
                if not result:
                    self.stdout.write(self.style.ERROR(f"No results found for recipe #{recipe_id}"))
                    return
                token = result.raw_data_path
                self.stdout.write(f"Using latest result #{result.pk}")
            
            # Analyze
            report = batch_analyze_recipe_rois(service, recipe, token)
            
            if 'error' in report:
                self.stdout.write(self.style.ERROR(f"Error: {report['error']}"))
                return
            
            # Print report
            print_roi_report(report)
            
            # Summary
            if report['overall_score'] >= 80:
                self.stdout.write(self.style.SUCCESS("✓ ROI 质量良好"))
            elif report['overall_score'] >= 60:
                self.stdout.write(self.style.WARNING("⚠ ROI 质量一般，建议优化"))
            else:
                self.stdout.write(self.style.ERROR("✗ ROI 质量差，需要重新框选"))
            
        except RackLocationRecipe.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Recipe #{recipe_id} not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            import traceback
            traceback.print_exc()
