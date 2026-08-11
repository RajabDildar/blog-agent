def build_image_prompt(
    *,
    purpose: str,
    section_title: str,
    image_type: str,
) -> str:
    base = f"""
Create a clean technical editorial illustration.

Subject:
{purpose}

Article section:
{section_title}

Visual type:
{image_type}

Requirements:
- professional technical publication style
- simple composition
- clear visual hierarchy
- no watermark
- no logos
- no decorative text
- no paragraphs
- no UI screenshot
- no photorealistic people
- visually explain the concept rather than decorate it
"""

    if image_type == "technical_diagram":
        base += """
Prefer a diagram-like composition with simple shapes,
arrows, nodes and relationships.
Keep labels extremely short.
"""

    return base.strip()
