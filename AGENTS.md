# Agent Instructions

## Progress Log

Log is stale, read only `docs/progress.md`.

## Mantine
- prefer mantine tokens over styles
- prefer module css pattern over basic css

## Upload event images to the VPS

- Run `bash copy-files.sh` from the repository root to upload `.pino/media/` WebP covers to `ops@204.168.143.13:/var/lib/pino/media/`. The script also works from other directories when invoked by path.
- This is the working ops-based upload path: no remote sudo or ownership mapping. It requires existing server-side group write access and uses `-O` to avoid changing timestamps on directories owned by another user. Preserve `--chmod=D2775,F664` and never add `--delete` for live media.
- Source PNG/JPG images are normalized to WebP during ingestion. To fetch missing covers for stored events locally, run `uv run pino sources backfill-media`, then upload with the script.
- The infrastructure contract describes the intended `pino-deploy` account; use this ops-based script for current manual uploads.
