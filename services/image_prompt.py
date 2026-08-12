def build_image_prompt(
    *,
    purpose: str,
    visual_description: str,
    key_elements: list[str],
    section_title: str,
    image_type: str,
) -> str:
    prompt = f"""
Create a clean technical editorial illustration for a professional
technical blog.

Article section:
{section_title}

Visual type:
{image_type}

Purpose:
{purpose}

Visual description:
{visual_description}

Key visual elements:
{", ".join(key_elements)}

Style requirements:
- clean technical editorial illustration
- clear visual hierarchy
- simple composition
- visually explain the concept
- professional publication quality
- consistent visual language
- no watermark
- no logos
- no UI screenshots
- no photorealistic people
- no decorative filler
- no paragraphs of text
- avoid unnecessary labels
"""

    if image_type == "technical_diagram":
        prompt += """
Technical diagram requirements:
- show relationships clearly
- prefer nodes, boxes, arrows, stages, and flows
- keep labels extremely short
- make the direction of the process obvious
"""

    elif image_type == "conceptual":
        prompt += """
Conceptual illustration requirements:
- communicate one clear idea
- prioritize visual relationships
- avoid decorative symbolism that does not explain the concept
"""

    elif image_type == "illustration":
        prompt += """
Illustration requirements:
- visually represent the specific domain concept
- keep the composition focused on the article's explanation
"""

    return prompt.strip()
