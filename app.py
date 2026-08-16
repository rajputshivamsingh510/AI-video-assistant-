import os
import shutil

# Whisper calls ffmpeg directly via subprocess, using whatever's on PATH.
# On HF Spaces, packages.txt installs ffmpeg via apt and it lands on PATH
# automatically. Locally on Windows it usually isn't on PATH, so add it
# manually there only.
if os.name == "nt" and shutil.which("ffmpeg") is None:
    FFMPEG_LOCATION = r"C:\Users\rajpu\ffmpeg\bin"
    os.environ["PATH"] = FFMPEG_LOCATION + os.pathsep + os.environ["PATH"]

import gradio as gr
from dotenv import load_dotenv

from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarizer import summarize, generate_title
from core.extractor import extract_action_items, extract_key_decisions, extract_questions
from core.rag_engine import build_rag_chain, ask_question

load_dotenv()

# Holds the RAG chain for the current session between the "Analyse" run
# and later chat questions. Gradio state per-browser-session is handled
# via gr.State below, but the chain object itself isn't JSON-serialisable
# in a simple textbox, so we keep it in this dict keyed by session id.
_rag_chains = {}


def run_pipeline(source: str, language: str, progress=gr.Progress()):
    if not source or not source.strip():
        raise gr.Error("Please enter a YouTube URL or file path.")

    source = source.strip()

    progress(0.02, desc="Downloading / processing audio")
    chunks = process_input(source)

    progress(0.15, desc="Transcribing")

    def on_chunk_progress(pct: int):
        # Transcription gets the biggest slice of the bar: 15% → 70%
        progress(0.15 + (pct / 100) * 0.55, desc=f"Transcribing ({pct}%)")

    transcript = transcribe_all(chunks, language, progress_callback=on_chunk_progress)

    progress(0.72, desc="Generating title")
    title = generate_title(transcript)

    progress(0.78, desc="Summarising")
    summary = summarize(transcript)

    progress(0.86, desc="Extracting action items / decisions / questions")
    action_items = extract_action_items(transcript)
    decisions = extract_key_decisions(transcript)
    questions = extract_questions(transcript)

    progress(0.94, desc="Building RAG index")
    rag_chain = build_rag_chain(transcript)

    progress(1.0, desc="Done")

    # Store the chain for this run so the chat tab can use it.
    session_key = "current"
    _rag_chains[session_key] = rag_chain

    return (
        f"## 📌 {title}",
        summary,
        transcript,
        action_items,
        decisions,
        questions,
        session_key,        # fed into the hidden state used by the chat fn
        gr.update(visible=True),   # reveal the chat section
    )


def chat_with_transcript(message: str, history, session_key: str):
    if not session_key or session_key not in _rag_chains:
        return "Please run **Analyse** on a video/meeting first."
    return ask_question(_rag_chains[session_key], message)


with gr.Blocks(title="AI Video Assistant", theme=gr.themes.Soft(primary_hue="purple")) as demo:
    gr.Markdown("# 🎬 AI Video Assistant")
    gr.Markdown("Transcribe · Summarise · Chat with your meetings and videos")

    with gr.Row():
        with gr.Column(scale=3):
            source_input = gr.Textbox(
                label="YouTube URL or local file path",
                placeholder="https://youtube.com/watch?v=... or /path/to/file.mp4",
            )
        with gr.Column(scale=1):
            language_input = gr.Dropdown(
                choices=["english", "hinglish"], value="english", label="Language"
            )
    run_btn = gr.Button("⚡ Analyse", variant="primary")

    title_out = gr.Markdown()

    with gr.Row():
        with gr.Column(scale=3):
            summary_out = gr.Textbox(label="📋 Summary", lines=8)
        with gr.Column(scale=2):
            transcript_out = gr.Textbox(label="📝 Full Transcript", lines=8)

    with gr.Row():
        action_items_out = gr.Textbox(label="✅ Action Items", lines=6)
        decisions_out = gr.Textbox(label="🔑 Key Decisions", lines=6)
        questions_out = gr.Textbox(label="❓ Open Questions", lines=6)

    session_state = gr.State(value=None)

    with gr.Column(visible=False) as chat_section:
        gr.Markdown("## 💬 Chat with your meeting")
        chatbot = gr.ChatInterface(
            fn=chat_with_transcript,
            additional_inputs=[session_state],
            type="messages",
        )

    run_btn.click(
        fn=run_pipeline,
        inputs=[source_input, language_input],
        outputs=[
            title_out,
            summary_out,
            transcript_out,
            action_items_out,
            decisions_out,
            questions_out,
            session_state,
            chat_section,
        ],
    )

if __name__ == "__main__":
    demo.launch()
