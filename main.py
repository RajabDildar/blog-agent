from graph.main_graph import run


if __name__ == "__main__":
    topic = input("Enter blog topic: ").strip()

    if not topic:
        raise SystemExit("Topic cannot be empty.")

    try:
        result = run(topic)

    except Exception as exc:
        print("\nBlog generation failed.")
        print(f"Error: {exc}")
        raise SystemExit(1)

    print("\nBlog generated successfully.")

    print(f"Title: {result['plan'].blog_title}")

    print(f"Revisions: {result['revision_count']}")

    print(f"Image plans: {len(result['image_specs'])}")

    print(f"Images inserted: {len(result['image_results'])}")

    print(f"Validation repairs: {result['repair_count']}")

    print(f"Saved to: {result['saved_path']}")
