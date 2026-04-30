from django.core.management.base import BaseCommand

from service_builder.models import BusinessActionVariant, ScenarioStep, WorkflowStep


def extract_argument_names(arguments):
    names = set()
    for arg in arguments or []:
        if isinstance(arg, dict):
            name = arg.get("name")
            if name:
                names.add(name)
        elif isinstance(arg, str) and arg:
            names.add(arg)
    return names


def extract_output_names(output_variables):
    names = set()
    for item in output_variables or []:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                names.add(name)
        elif isinstance(item, str) and item:
            names.add(item)
    return names


def prune_mapping(mapping, allowed_keys):
    mapping = mapping or {}
    if not isinstance(mapping, dict):
        return {}, []
    cleaned = {}
    removed = []
    for key, value in mapping.items():
        if key in allowed_keys:
            cleaned[key] = value
        else:
            removed.append(key)
    return cleaned, removed


class Command(BaseCommand):
    help = "Remove stale mapping keys that are not in current argument/output contracts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply cleanup. Without this flag command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        apply_changes = options.get("apply", False)
        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"[cleanup_mappings] Mode: {mode}"))

        summary = {
            "workflow_steps_checked": 0,
            "workflow_steps_changed": 0,
            "variant_input_checked": 0,
            "variant_input_changed": 0,
            "variant_output_checked": 0,
            "variant_output_changed": 0,
            "scenario_steps_checked": 0,
            "scenario_steps_changed": 0,
            "removed_keys": 0,
        }

        # 1) WorkflowStep.input_mapping
        for step in WorkflowStep.objects.select_related("business_action", "scenario").all():
            if step.business_action_id:
                allowed = extract_argument_names(step.business_action.arguments)
            elif step.scenario_id:
                allowed = extract_argument_names(step.scenario.arguments)
            else:
                continue
            summary["workflow_steps_checked"] += 1
            cleaned, removed = prune_mapping(step.input_mapping, allowed)
            if not removed:
                continue
            summary["workflow_steps_changed"] += 1
            summary["removed_keys"] += len(removed)
            self.stdout.write(
                f"WorkflowStep id={step.id} removed={sorted(removed)}"
            )
            if apply_changes:
                step.input_mapping = cleaned
                step.save(update_fields=["input_mapping"])

        # 2) BusinessActionVariant mappings
        for variant in BusinessActionVariant.objects.select_related("business_action", "scenario").all():
            # input_mapping: keys must match Scenario arguments
            allowed_input = extract_argument_names(variant.scenario.arguments)
            summary["variant_input_checked"] += 1
            cleaned_input, removed_input = prune_mapping(variant.input_mapping, allowed_input)
            if removed_input:
                summary["variant_input_changed"] += 1
                summary["removed_keys"] += len(removed_input)
                self.stdout.write(
                    f"BusinessActionVariant id={variant.id} input_mapping removed={sorted(removed_input)}"
                )
                if apply_changes:
                    variant.input_mapping = cleaned_input

            # output_mapping: keys must match BusinessAction output variables
            allowed_output = extract_output_names(variant.business_action.output_variables)
            summary["variant_output_checked"] += 1
            cleaned_output, removed_output = prune_mapping(variant.output_mapping, allowed_output)
            if removed_output:
                summary["variant_output_changed"] += 1
                summary["removed_keys"] += len(removed_output)
                self.stdout.write(
                    f"BusinessActionVariant id={variant.id} output_mapping removed={sorted(removed_output)}"
                )
                if apply_changes:
                    variant.output_mapping = cleaned_output

            if apply_changes and (removed_input or removed_output):
                variant.save(update_fields=["input_mapping", "output_mapping"])

        # 3) ScenarioStep.argument_mapping
        for step in ScenarioStep.objects.select_related("method").all():
            if not step.method_id:
                continue
            allowed = set(step.method.arguments or [])
            summary["scenario_steps_checked"] += 1
            cleaned, removed = prune_mapping(step.argument_mapping, allowed)
            if not removed:
                continue
            summary["scenario_steps_changed"] += 1
            summary["removed_keys"] += len(removed)
            self.stdout.write(
                f"ScenarioStep id={step.id} removed={sorted(removed)}"
            )
            if apply_changes:
                step.argument_mapping = cleaned
                step.save(update_fields=["argument_mapping"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("[cleanup_mappings] Summary"))
        for key in sorted(summary.keys()):
            self.stdout.write(f"  - {key}: {summary[key]}")

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING("Dry-run only. Re-run with --apply to persist changes.")
            )
