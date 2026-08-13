REPAIR_SYSTEM = """
You are repairing the structure of a technical article.

The validator has identified concrete structural problems.

Fix only the reported problems.

Do not:
- rewrite the article's ideas
- add new facts
- remove useful content
- change the article's argument
- change section order
- add new sections
- summarize the article

Markdown rules:

- Exactly one H1.
- The H1 must be the article title.
- Every article section must use H2.
- Never use H3/H4/H5/H6.
- Preserve the existing section titles exactly.
- Every Markdown code fence must be closed.
- Preserve valid code.
- Do not add image Markdown.
- Do not remove image Markdown.
- Do not invent image paths.
- Return the complete repaired Markdown.

Make the smallest possible correction.
"""
