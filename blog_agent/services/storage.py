"""Article and image artifact storage service supporting PostgreSQL and Cloudinary."""
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Any, List, Dict
from uuid import uuid4

from blog_agent.services.cloudinary_storage import (
    is_cloudinary_configured,
    upload_run_image,
    delete_cloudinary_assets,
)
from blog_agent.services.markdown import safe_blog_filename
from blog_agent.services.protocols import ArticleRepository, ImageStorage
from blog_agent.services.run_paths import (
    published_images_dir,
    run_images_dir,
)

logger = logging.getLogger("blog_agent.storage")


def extract_article_excerpt(markdown: str, max_chars: int = 250) -> str:
    """
    Extracts deterministically the first non-heading plain-text paragraph from markdown
    to use as a card excerpt without calling an extra LLM.
    """
    lines = markdown.splitlines()
    paragraph_lines: List[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            if paragraph_lines:
                break
            continue
        # Skip headings, images, horizontal rules, blockquotes
        if (
            stripped.startswith("#")
            or stripped.startswith("![")
            or stripped.startswith("---")
            or stripped.startswith(">")
        ):
            if paragraph_lines:
                break
            continue
        paragraph_lines.append(stripped)

    excerpt = " ".join(paragraph_lines).strip()
    if not excerpt:
        clean_text = "\n".join(l for l in lines if not l.strip().startswith("#") and not l.strip().startswith("```")).strip()
        excerpt = clean_text[:max_chars] if clean_text else markdown.strip()[:max_chars]
    elif len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "..."

    return excerpt


def convert_markdown_asset_routes(
    markdown: str,
    run_id: str,
    image_results: list[dict],
) -> str:
    """
    Transforms local markdown image references to application asset route references:
    /articles/{run_id}/assets/{filename}
    """
    final_markdown = markdown
    for result in image_results:
        filename = result.get("filename")
        if not filename:
            continue
        asset_route = f"/articles/{run_id}/assets/{filename}"
        markdown_path_str = result.get("markdown_path", "")
        if markdown_path_str and markdown_path_str in final_markdown:
            final_markdown = final_markdown.replace(markdown_path_str, asset_route)
        elif f"images/{filename}" in final_markdown:
            final_markdown = final_markdown.replace(f"images/{filename}", asset_route)
        elif f"/images/{filename}" in final_markdown:
            final_markdown = final_markdown.replace(f"/images/{filename}", asset_route)
        elif f"../images/{filename}" in final_markdown:
            final_markdown = final_markdown.replace(f"../images/{filename}", asset_route)
        elif filename in final_markdown:
            final_markdown = final_markdown.replace(filename, asset_route)
        else:
            raise ValueError(
                f"Could not find markdown image reference for '{filename}' in final markdown"
            )
    return final_markdown


def _temporary_sibling(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")


def _atomic_copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_sibling(destination)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_sibling(destination)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def publish_blog(
    *,
    title: str,
    markdown: str,
    run_id: str,
    image_results: list[dict],
    article_repo: Optional[ArticleRepository] = None,
    image_storage: Optional[ImageStorage] = None,
    db_session: Optional[Any] = None,
) -> Path:
    """
    Publishes final article Markdown and images across PostgreSQL + Cloudinary and local disk.
    Enforces the stage -> validate -> upload -> persist -> finalize transaction boundary.
    """
    if not markdown.strip():
        raise ValueError("Cannot publish empty Markdown.")

    expected_stage_dir = run_images_dir(run_id).resolve()
    expected_publish_dir = published_images_dir(title=title, run_id=run_id).resolve()

    prepared_images: list[tuple[dict, Path, Path]] = []

    # Validate every staged image before uploading or committing
    for result in image_results:
        if result["status"] != "inserted":
            raise RuntimeError(
                f"Cannot publish image {result['id']} because it was not inserted."
            )

        source = Path(result["staged_path"]).resolve()
        destination = Path(result["published_path"]).resolve()

        if source.parent != expected_stage_dir:
            raise ValueError(
                f"Staged image path is outside this run: {result['staged_path']}"
            )

        if destination.parent != expected_publish_dir:
            raise ValueError(
                f"Published image path is outside this article/run: {result['published_path']}"
            )

        markdown_destination = (
            Path("generated_blogs") / result["markdown_path"]
        ).resolve()

        if destination != markdown_destination:
            raise ValueError(
                f"Published image path does not match Markdown path for image {result['id']}."
            )

        if not source.is_file():
            raise FileNotFoundError(f"Staged image does not exist: {source}")

        if source.stat().st_size == 0:
            raise RuntimeError(f"Staged image is empty: {source}")

        prepared_images.append((result, source, destination))

    # Build asset manifest & upload images if image_storage or Cloudinary is configured
    asset_manifest: List[Dict[str, Any]] = []
    uploaded_pids: List[str] = []
    published_local_files: List[Path] = []

    # Transform markdown image references to application asset route for database persistence
    final_markdown = convert_markdown_asset_routes(markdown, run_id, image_results)

    try:
        use_cloudinary = is_cloudinary_configured()

        for result, source, destination in prepared_images:
            filename = result["filename"]
            image_bytes = source.read_bytes()
            alt_text = result.get("alt_text") or result.get("alt")

            if image_storage is not None:
                upload_res = image_storage.upload_image(
                    run_id=run_id,
                    filename=filename,
                    image_bytes=image_bytes,
                    alt_text=alt_text,
                )
                if not image_storage.verify_image(upload_res):
                    raise RuntimeError(f"Image storage verification failed for {filename}")
                uploaded_pids.append(upload_res["public_id"])
                asset_manifest.append(upload_res)
            elif use_cloudinary:
                upload_res = upload_run_image(
                    run_id=run_id,
                    filename=filename,
                    image_bytes=image_bytes,
                    alt_text=alt_text,
                )
                uploaded_pids.append(upload_res["public_id"])
                asset_manifest.append(upload_res)
            else:
                asset_manifest.append({
                    "filename": filename,
                    "public_id": f"local:{run_id}:{filename}",
                    "format": Path(filename).suffix.lstrip("."),
                    "bytes": len(image_bytes),
                    "alt_text": alt_text,
                })

            # Also maintain local file copy for local CLI/testing
            dest_existed = destination.exists()
            _atomic_copy_file(source, destination)
            if not dest_existed:
                published_local_files.append(destination)

        # Write local Markdown file with local relative image paths
        blog_path = Path("generated_blogs") / safe_blog_filename(title)
        _atomic_write_text(blog_path, markdown)

        excerpt = extract_article_excerpt(final_markdown)

        # Persist through injected article_repo
        if article_repo is not None:
            article_repo.save_article(
                run_id=run_id,
                title=title,
                markdown=final_markdown,
                excerpt=excerpt,
                assets=asset_manifest,
            )
        elif db_session is not None:
            # Backward-compatibility fallback for tests passing raw db_session
            from sqlalchemy import text
            db_session.execute(
                text(
                    "UPDATE runs SET article_title = :title, article_markdown = :markdown, "
                    "article_excerpt = :excerpt, article_assets = :assets, "
                    "status = 'completed', completed_at = NOW() "
                    "WHERE id = :run_id"
                ),
                {
                    "title": title,
                    "markdown": final_markdown,
                    "excerpt": excerpt,
                    "assets": json.dumps(asset_manifest),
                    "run_id": run_id,
                },
            )
            db_session.commit()

        return blog_path

    except Exception:
        # Roll back partial uploads and local file copies on error
        if image_storage is not None and uploaded_pids:
            image_storage.delete_images(uploaded_pids)
        elif uploaded_pids:
            delete_cloudinary_assets(uploaded_pids)
        for dest in reversed(published_local_files):
            dest.unlink(missing_ok=True)
        raise
