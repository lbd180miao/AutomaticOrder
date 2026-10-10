"""Django management command to diagnose rack locator repeatability."""
import json
from django.core.management.base import BaseCommand
from apps.vision.models import RackLocationRecipe
from apps.vision.rack_location import RackLocationService
from apps.vision.rack_repeatability_diagnostics import generate_repeatability_report


class Command(BaseCommand):
    help = 'Diagnose repeatability issues for rack locator results'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recipe',
            type=int,
            required=True,
            help='Recipe ID'
        )
        parser.add_argument(
            '--results',
            type=str,
            required=True,
            help='Comma-separated result IDs (e.g., 361,362,363,364,365)'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='',
            help='Optional output JSON file path'
        )

    def handle(self, *args, **options):
        recipe_id = options['recipe']
        result_ids = [int(x.strip()) for x in options['results'].split(',')]
        
        try:
            recipe = RackLocationRecipe.objects.get(pk=recipe_id)
            service = RackLocationService()
            
            self.stdout.write(f"Analyzing repeatability for Recipe #{recipe_id}")
            self.stdout.write(f"Comparing {len(result_ids)} results: {result_ids}")
            
            report = generate_repeatability_report(service, recipe, result_ids)
            
            if 'error' in report:
                self.stdout.write(self.style.ERROR(f"Error: {report['error']}"))
                return
            
            # Print summary
            self.stdout.write(self.style.SUCCESS("\n=== REPEATABILITY REPORT ===\n"))
            
            self.stdout.write("Point Cloud Diagnostics:")
            for key, diag in report['point_cloud_diagnostics'].items():
                if 'error' in diag:
                    self.stdout.write(f"  {key}: {self.style.WARNING(diag['error'])}")
                else:
                    self.stdout.write(f"  {key}:")
                    self.stdout.write(f"    Coverage: {diag['coverage_ratio']*100:.1f}%")
                    self.stdout.write(f"    Depth noise: {diag['depth_noise_mm']:.3f} mm")
                    self.stdout.write(f"    Systematic shift: {[f'{x:.3f}' for x in diag['systematic_shift_mm']]} mm")
            
            self.stdout.write("\nAxis Diagnostics:")
            for key, diag in report['axis_diagnostics'].items():
                self.stdout.write(f"  {key}:")
                self.stdout.write(f"    Angular drift: {diag['angular_drift_deg']:.4f}°")
                self.stdout.write(f"    Perpendicular shift: {diag['perpendicular_shift_mm']:.3f} mm")
                self.stdout.write(f"    Quality ratio: {diag['quality_ratio_1']:.2f} → {diag['quality_ratio_2']:.2f}")
            
            self.stdout.write("\nFrame Diagnostics (Robot Groups):")
            for key, diag in report['frame_diagnostics'].items():
                self.stdout.write(f"  {key}:")
                trans = diag['translation_error_mm']
                self.stdout.write(f"    Translation error: X={trans['x']:.3f}, Y={trans['y']:.3f}, Z={trans['z']:.3f} mm")
                rot = diag['rotation_error_deg']
                self.stdout.write(f"    Rotation error: RX={rot['rx']:.4f}, RY={rot['ry']:.4f}, RZ={rot['rz']:.4f}°")
            
            if report['suggestions']:
                self.stdout.write(self.style.WARNING("\n=== SUGGESTIONS ==="))
                for suggestion in report['suggestions']:
                    self.stdout.write(f"  • {suggestion}")
            else:
                self.stdout.write(self.style.SUCCESS("\n✓ No major issues detected"))
            
            # Save to file if specified
            if options['output']:
                with open(options['output'], 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                self.stdout.write(self.style.SUCCESS(f"\nFull report saved to: {options['output']}"))
            
        except RackLocationRecipe.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Recipe #{recipe_id} not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            import traceback
            traceback.print_exc()
