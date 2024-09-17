import azure.functions as func
from base64 import b64encode
from datetime import datetime
import json
import os
from requests import get, post, patch
from pydantic import BaseModel
from openai import OpenAI


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
    github_token = os.getenv("GITHUB_TOKEN")
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
        "The file should be named 'index.html'."
        "The favicon file should be named 'favicon.ico'."
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[{"role": "user", "content": user_input}],
        response_format=indexHTML,
        temperature=1,
    )

    code = completion.choices[0].message.parsed.code

    new_content = code

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

    index_url = f"{base_url}/contents/index.html"
    index_response = get(index_url, headers=headers)
    index_response.raise_for_status()
    current_index_content = index_response.json()["content"]
    decoded_content = b64encode(current_index_content.encode("utf-8")).decode("utf-8")
    archive_blob_sha = create_blob(decoded_content)

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
