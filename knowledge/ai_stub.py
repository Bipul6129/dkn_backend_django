from .models import AIFlag, KnowledgeResource, KnowledgeResourceVersion

def run_ai_check(resource: KnowledgeResource, version: KnowledgeResourceVersion | None = None):
    """
    Creates AIFlag rows for the given resource/version.
    If version is None, defaults to resource.latest_version.
    """
    version = version or getattr(resource, "latest_version", None)

    flags = []
    title = (resource.title or "").lower()
    desc = (resource.description or "").strip()
    meta = resource.metadata or {}

    if "draft" in title or "v0" in title:
        flags.append((AIFlag.FlagType.OUTDATED, AIFlag.Severity.HIGH, "Title suggests draft/outdated content."))

    if not resource.tags.exists():
        flags.append((AIFlag.FlagType.METADATA, AIFlag.Severity.MEDIUM, "Missing tags; improves search and recommendations."))

    if "confidentiality" not in meta:
        flags.append((AIFlag.FlagType.METADATA, AIFlag.Severity.HIGH, "Missing confidentiality in metadata (needed for compliance)."))

    if 0 < len(desc) < 30:
        flags.append((AIFlag.FlagType.QUALITY, AIFlag.Severity.LOW, "Description is very short; may reduce usefulness."))

    created = []
    for flag_type, severity, message in flags:
        created.append(
            AIFlag.objects.create(
                resource=resource,
                version=version,   # ✅ attach to version (can be None if no latest yet)
                flag_type=flag_type,
                severity=severity,
                message=message,
            )
        )

    return created
