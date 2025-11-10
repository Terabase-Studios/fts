"""
FTS AI Chat Plugin (Novelty)

Description:
This plugin adds a chat AI into FTS, It uses a self-hosted GPT4All model to generate responses
without relying on the internet.

How it works:
- Adds a new command `!ai` that sends messages to the AI and returns a short,
  concise response (max 20 words for prompt recommended).
- Each prompt creates a temporary chat session and does not preserve memory.

Why use it:
- Adds a fun or experimental AI assistant directly inside FTS TUI chat.
- Completely self-contained: no API keys or external servers are required.
- This should be used as a novelty, this is not a very good chatbot.

Usage:
- Place this plugin in your FTS plugin directory.
- Use the `!ai <message>` command in the FTS console to interact with the AI.
- Note: Running `!ai` will temporarily pause the TUI until the AI finishes generating a response.
"""

from gpt4all import GPT4All

import fts.app.backend.commands as commands

SYSTEM_PROMPT = (
    "You are FTS Assistant, a concise and practical AI built into a developer tool. "
    "Answer clearly and directly without fluff. "
    "If unsure, admit it briefly. Keep answers under 20 words."
)

model = None

def _query(cmd: str):
    global model
    if not model:
        return "Model not initialized"

    query = " ".join(cmd.split(" ")[1:])
    if not query:
        return "Usage: !ai <message>"

    with model.chat_session(system_prompt=SYSTEM_PROMPT):
        # Generate using chat session (preserves context automatically)
        reply = model.generate(query, temp=0.7, max_tokens=40)
        reply = reply.strip().replace("\n", " ")

    return f"[blue]You:[/blue] {query}\n[blue]AI[/blue]: {reply}"

def setup():
    global model
    print("[AI Command] (Downloading and) loading model into memory...")
    model = GPT4All("Phi-3-mini-4k-instruct.Q4_0.gguf")

    commands.COMMANDS["!ai"] = ("\tUsage: !ai <message>\n\tSend message to AI model", _query)
    commands.COMMAND_KEYS.append("!ai")

    print("[AI Command] Model ready. Note: running !ai will pause TUI until response completes.")
