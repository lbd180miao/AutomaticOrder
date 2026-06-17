class AutomaticOrderError(Exception):
    """Base exception for project-level business errors."""


class WorkflowTransitionError(AutomaticOrderError):
    """Raised when a workflow state transition is not allowed."""


class DeviceCommunicationError(AutomaticOrderError):
    """Raised when a device adapter cannot complete a request."""


class MesError(AutomaticOrderError):
    """Raised when a MES interaction fails."""


class RecipeValidationError(AutomaticOrderError):
    """Raised when rack measurements do not match the recipe within tolerance."""


class VisionError(AutomaticOrderError):
    """Raised when a vision task fails to produce a usable result."""


class WorkflowLockedError(AutomaticOrderError):
    """Raised when attempting to advance a locked workflow."""
