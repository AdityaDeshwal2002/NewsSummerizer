import openai
import os
from dotenv import load_dotenv
import time
import requests
import streamlit as st
import json

load_dotenv()

openai.api_key = os.environ.get("OPENAI_API_KEY")
news_api_key = os.environ.get("NEWS_API_KEY")
client = openai.OpenAI()
model = "gpt-3.5-turbo-16k"

def get_news(topic):
    url = f"https://newsapi.org/v2/everything?q={topic}&apiKey={news_api_key}&pageSize=5"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            news_json = response.json()

            final_news = []
            articles = news_json.get("articles", [])

            for article in articles:
                source_name = article.get("source", {}).get("name", "Unknown Source")
                author = article.get("author", "Unknown Author")
                title = article.get("title", "No Title")
                description = article.get("description", "No Description")
                url = article.get("url", "#")
                content = article.get("content", "No Content")

                title_description = f"""
Title: {title}
Author: {author}
Source: {source_name}
Description: {description}
URL: {url}
                """
                final_news.append(title_description)
            return final_news
        else:
            print(f"Failed to fetch news. Status code: {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print("Error Occurred during API call:", e)
        return []

class AssistantManager:
    thread_id = "thread_51l6Mg9npXuaLbDZLzo6PtIa"
    assistant_id = "asst_wHBif8FiUReSJTucJKI8JDXB"

    def __init__(self, model: str = model):
        self.client = client
        self.model = model
        self.assistant = None
        self.thread = None
        self.run = None
        self.summary = None

        if AssistantManager.assistant_id: 
            self.assistant = self.client.beta.assistants.retrieve(
                assistant_id=AssistantManager.assistant_id
            )
        if AssistantManager.thread_id:
            self.thread = self.client.beta.threads.retrieve(
                thread_id=AssistantManager.thread_id
            )
            
    def create_assistant(self, name, instructions, tools):
        if not self.assistant:
            assistant_obj = self.client.beta.assistants.create(name=name,
                                                               instructions=instructions,
                                                               tools=tools,
                                                               model=self.model
                                                               )
            AssistantManager.assistant_id = assistant_obj.id
            self.assistant = assistant_obj
            print(f"AssisID:::::::{self.assistant.id}") 
    
    def create_thread(self):
        if not self.thread:
            thread_obj = self.client.beta.threads.create()
            AssistantManager.thread_id = thread_obj.id
            self.thread = thread_obj
            print(f"ThreadID::: {self.thread.id}")

    def add_message_to_thread(self, role, content):
        if self.thread:
            # Check if there is an active run
            if self.run:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=self.run.id
                )
                if run_status.status != "completed":
                    print("Waiting for the active run to complete...")
                    self.wait_for_completion()

            self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role=role,
                content=content
            )

    def run_assistant(self, instructions):
        if self.thread and self.assistant:
            self.run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant.id,
                instructions=instructions
            )

    def process_message(self):
        if self.thread:
            messages = self.client.beta.threads.messages.list(thread_id=self.thread.id)
            summary = []
            last_message = messages.data[0]
            role = last_message.role
            response = last_message.content[0].text.value
            summary.append(response)
            self.summary = "\n".join(summary)
            print(f"SUMMARY ---------> {role.capitalize()}: =====> {response}")

    def call_required_functions(self, required_actions):
        if not self.run:
            return

        tool_outputs = []
        for action in required_actions["tool_calls"]:
            func_name = action["function"]["name"]
            arguments = json.loads(action["function"]["arguments"])

            if func_name == "get_news":
                output = get_news(topic=arguments["topic"])
                print(f"Stuff: {output}")
                final_str = ""
                for item in output:
                    final_str += "".join(item)
                tool_outputs.append({"tool_call_id": action["id"], "output": final_str})

            else:
                raise ValueError(f"Unknown function: {func_name}")

        print("Submitting output back to assistant")
        self.client.beta.threads.runs.submit_tool_outputs(
            thread_id=self.run.id,
            run_id=self.run.id,  # Add this line
            tool_outputs=tool_outputs
        )

    def get_summary(self):
        return self.summary

    def wait_for_completion(self):
        if self.thread and self.run:
            while True:
                time.sleep(5)
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=self.run.id
                )
                print(f"RUN STATUS :: {run_status.model_dump_json(indent=4)}")

                if run_status.status == "completed":
                    self.process_message()
                    break
                elif run_status.status == "requires_action":
                    print("Function CALLING")
                    self.call_required_functions(
                        required_actions=run_status.required_action.submit_tool_outputs.model_dump()
                    )

    def run_steps(self):
        run_steps = self.client.beta.threads.runs.steps.list(
            thread_id=self.thread.id,
            run_id=self.run.id
        )
        print(f"Run Steps ::  {run_steps}")

def main():
    manager = AssistantManager()
    st.title("News Summarizer")

    with st.form(key="user_input_form"):
        instructions = st.text_input("Enter topic")
        submit_button = st.form_submit_button(label="Run Assistant")

        if submit_button:
            manager.create_assistant(
                name="News Summarizer",
                instructions=(
                    "You are a personal article summarizer Assistant who knows how to "
                    "take a list of article titles and descriptions and then write a short summary "
                    "of all the news articles."
                ),
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "get_news",
                            "description": "Get the list of articles/news for the given topic.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "topic": {
                                        "type": "string",
                                        "description": "The topic for the news, e.g., bitcoin."
                                    }
                                },
                                "required": ["topic"],
                            },
                        },
                    }
                ],
            )
            manager.create_thread()

            manager.add_message_to_thread(
                role="user",
                content=f"summarize the news on this topic {instructions}"
            )
            manager.run_assistant(instructions="Summarize the news")

            manager.wait_for_completion()

            summary = manager.get_summary()
            
            st.write(summary)

            st.text("Run Steps:")
            st.code(manager.run_steps(), line_numbers=True)

if __name__ == "__main__":
    print("Executing Main ...")
    main()