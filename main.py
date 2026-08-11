from graph.main_graph import run


if __name__ == "__main__":
    topic = input("Enter blog topic: ").strip()

    if not topic:
        raise SystemExit("Topic cannot be empty.")

    result = run(topic)

    print("\nBlog generated successfully.")

    print(f"Title: {result['plan'].blog_title}")

    print(f"Revisions: {result['revision_count']}")

    print(f"Images: {len(result['image_specs'])}")
