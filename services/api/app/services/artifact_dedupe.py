from app import schemas


def dedupe_discovered_artifacts(artifacts: list[schemas.Artifact]) -> list[schemas.Artifact]:
    deduped: list[schemas.Artifact] = []
    seen: set[str] = set()
    for artifact in artifacts:
        metadata = artifact.metadata or {}
        keys = [
            artifact.id,
            str(metadata.get("contentHash") or ""),
            str(metadata.get("normalizedPath") or ""),
            str(metadata.get("originalNormalizedPath") or ""),
            str(metadata.get("path") or ""),
            str(metadata.get("originalPath") or ""),
        ]
        present_keys = {item for item in keys if item}
        if present_keys & seen:
            continue
        seen.update(present_keys)
        deduped.append(artifact)
    return deduped
