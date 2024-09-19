import azure.functions as func
from base64 import b64decode
from datetime import datetime
from requests import get, post, patch
from pydantic import BaseModel
from openai import OpenAI
from os import getenv


class indexHTML(BaseModel):
    code: str


app = func.FunctionApp()
client = OpenAI()


@app.timer_trigger(
    schedule="0 0 3 * * *",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=False,
)
def refresh(myTimer: func.TimerRequest) -> None:
    github_token = getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {github_token}"}
    repo_owner = "galwort"
    repo_name = "beautyisapattern"
    base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    current_date = datetime.now().strftime("%Y-%m-%d")
    archive_path = f"archive/index_{current_date}.html"

    quote_response = get("https://api.quotable.io/random", verify=False)
    data = quote_response.json()
    quote = data["content"]
    author = data["author"]

    user_input = (
        "Please create an HTML file using p5, "
        "drawing inspiration from the following quote: "
        f'"{quote}"\n'
        "The output should be animated. "
        "Do not add text in the output. "
        "Avoid making the output interactive. "
        "The file should be named 'index.html'. "
        "The favicon is available at https://www.beautyisapattern.com/favicon.ico. "
        "The title of the page should not mention p5, "
        "but should more reference the theme of the quote. "
        "Somewhere on the page, there should be a link to "
        "the archive at https://www.beautyisapattern.com/archive"
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[{"role": "user", "content": user_input}],
        response_format=indexHTML,
        temperature=1,
    )

    new_content = completion.choices[0].message.parsed.code

    ref_url = f"{base_url}/git/ref/heads/main"
    ref_response = get(ref_url, headers=headers)
    ref_response.raise_for_status()
    commit_sha = ref_response.json()["object"]["sha"]

    commit_url = f"{base_url}/git/commits/{commit_sha}"
    commit_response = get(commit_url, headers=headers)
    commit_response.raise_for_status()
    tree_sha = commit_response.json()["tree"]["sha"]

    def create_blob(content):
        blob_url = f"{base_url}/git/blobs"
        blob_data = {"content": content, "encoding": "utf-8"}
        blob_response = post(blob_url, json=blob_data, headers=headers)
        blob_response.raise_for_status()
        return blob_response.json()["sha"]

    index_blob_sha = create_blob(new_content)
    archive_blob_sha = create_blob(new_content)

    archive_csv_url = f"{base_url}/contents/archive.csv"
    archive_csv_response = get(archive_csv_url, headers=headers)

    if archive_csv_response.status_code == 200:
        archive_csv_content_encoded = archive_csv_response.json()["content"]
        archive_csv_content = b64decode(archive_csv_content_encoded).decode("utf-8")
        archive_csv_sha = archive_csv_response.json()["sha"]

        lines = archive_csv_content.splitlines()
        header = lines[0]
        data_lines = lines[1:]

        data_lines = [
            line for line in data_lines if not line.startswith(f'"{current_date}"')
        ]

        new_row = f'"{current_date}","{quote}","{author}"'
        updated_csv_content = (
            header + "\n" + new_row + "\n" + "\n".join(data_lines) + "\n"
        )
    elif archive_csv_response.status_code == 404:
        updated_csv_content = "Date,Quote,Author\n"
        new_row = f'"{current_date}","{quote}","{author}"\n'
        updated_csv_content += new_row
        archive_csv_sha = None
    else:
        archive_csv_response.raise_for_status()

    archive_csv_blob_sha = create_blob(updated_csv_content)

    tree_url = f"{base_url}/git/trees"
    tree_data = {
        "base_tree": tree_sha,
        "tree": [
            {
                "path": "index.html",
                "mode": "100644",
                "type": "blob",
                "sha": index_blob_sha,
            },
            {
                "path": archive_path,
                "mode": "100644",
                "type": "blob",
                "sha": archive_blob_sha,
            },
            {
                "path": "archive.csv",
                "mode": "100644",
                "type": "blob",
                "sha": archive_csv_blob_sha,
            },
        ],
    }
    tree_response = post(tree_url, json=tree_data, headers=headers)
    tree_response.raise_for_status()
    new_tree_sha = tree_response.json()["sha"]

    commit_message = "Generate new art"
    commit_data = {
        "message": commit_message,
        "tree": new_tree_sha,
        "parents": [commit_sha],
    }
    new_commit_url = f"{base_url}/git/commits"
    new_commit_response = post(new_commit_url, json=commit_data, headers=headers)
    new_commit_response.raise_for_status()
    new_commit_sha = new_commit_response.json()["sha"]

    update_ref_url = f"{base_url}/git/refs/heads/main"
    ref_data = {"sha": new_commit_sha}
    update_response = patch(update_ref_url, json=ref_data, headers=headers)
    update_response.raise_for_status()
