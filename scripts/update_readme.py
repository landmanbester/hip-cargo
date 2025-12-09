from pathlib import Path


def update_readme():
    readme = Path("README.md")
    content = readme.read_text()

    # Define your code snippets with markers
    snippets = {
        "generate-cabs": Path("src/hip_cargo/cli/generate_cabs.py").read_text(),
    }

    # Replace content between markers
    for name, code in snippets.items():
        start_marker = f"<!-- CODE:{name}:START -->"
        end_marker = f"<!-- CODE:{name}:END -->"

        if start_marker in content and end_marker in content:
            before = content.split(start_marker)[0]
            after = content.split(end_marker)[1]
            content = f"{before}{start_marker}\n```python\n{code}```\n{end_marker}{after}"

    readme.write_text(content)
    return 0


if __name__ == "__main__":
    update_readme()
