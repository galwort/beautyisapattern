import azure.functions as func

from base64 import b64encode
from openai import OpenAI
from os import getenv
from pydantic import BaseModel
from requests import get, put


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
    url = "https://api.github.com/repos/galwort/beautyisapattern/contents/index.html"
    github_response = get(url, headers=headers)
    sha = github_response.json()["sha"]

    quote_response = get("https://api.quotable.io/random")
    data = quote_response.json()
    quote = data["content"]

    user_input = (
        "Please create an HTML file using p5, "
        "drawing inspiration from the following quote: "
        f'"{quote}"\n'
        "Do not reference the quote in the output."
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[{"role": "user", "content": user_input}],
        response_format=indexHTML,
        temperature=1,
    )

    code = completion.choices[0].message.parsed.code

    new_content = b64encode(code.encode("utf-8")).decode("utf-8")

    commit_data = {
        "message": "Daily p5 index generation - test",
        "content": new_content,
        "sha": sha,
        "branch": "main",
    }

    put(url, json=commit_data, headers=headers)
