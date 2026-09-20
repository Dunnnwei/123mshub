class SkillRepoError(Exception):
    """Base error with a safe message for CLI and API clients."""


class ValidationError(SkillRepoError):
    """Input cannot be normalized or validated."""


class FetchError(SkillRepoError):
    """A remote repository could not be fetched."""


class ConflictError(SkillRepoError):
    """The requested change conflicts with existing repository state."""


class NotFoundError(SkillRepoError):
    """The requested skill does not exist."""

