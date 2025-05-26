"""
python app.py --windows_host_url localhost:8006 --omniparser_server_url localhost:8000
"""

import os
from datetime import datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import cast
import argparse
import gradio as gr
from anthropic import APIResponse
from anthropic.types import TextBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock
from anthropic.types.tool_use_block import ToolUseBlock

from loop import (
    APIProvider,
    sampling_loop_sync,
)
from agent.ppt_agent import PPTAgent 
from tools import ToolResult
from tools.computer import ComputerTool # Import ComputerTool
import requests
from requests.exceptions import RequestException
import time # Import time
import base64

CONFIG_DIR = Path("~/.anthropic").expanduser()
API_KEY_FILE = CONFIG_DIR / "api_key"

INTRO_TEXT = '''
OmniParser lets you turn any vision-langauge model into an AI agent. We currently support **OpenAI (4o/o1/o3-mini), DeepSeek (R1), Qwen (2.5VL) or Anthropic Computer Use (Sonnet).**

Type a message and press submit to start OmniTool. Press stop to pause, and press the trash icon in the chat to clear the message history.
'''

def parse_arguments():

    parser = argparse.ArgumentParser(description="Gradio App")
    parser.add_argument("--windows_host_url", type=str, default='localhost:8006')
    parser.add_argument("--omniparser_server_url", type=str, default="localhost:8000")
    return parser.parse_args()
args = parse_arguments()


class Sender(StrEnum):
    USER = "user"
    BOT = "assistant"
    TOOL = "tool"


def setup_state(state):
    if "messages" not in state:
        state["messages"] = []
    if "model" not in state:
        state["model"] = "omniparser + gpt-4o"
    if "provider" not in state:
        state["provider"] = "openai"
    if "openai_api_key" not in state:  # Fetch API keys from environment variables
        state["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
    if "anthropic_api_key" not in state:
        state["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
    if "api_key" not in state:
        state["api_key"] = ""
    if "auth_validated" not in state:
        state["auth_validated"] = False
    if "responses" not in state:
        state["responses"] = {}
    if "tools" not in state:
        state["tools"] = {}
    if "only_n_most_recent_images" not in state:
        state["only_n_most_recent_images"] = 2
    if 'chatbot_messages' not in state:
        state['chatbot_messages'] = []
    if 'stop' not in state:
        state['stop'] = False
    if 'agent_type' not in state: # To differentiate between VLM and PPT agent
        state['agent_type'] = "vlm_agent" 
    if 'ppt_filename' not in state:
        state['ppt_filename'] = "GeneratedPPT.pptx"

async def main(state):
    """Render loop for Gradio"""
    setup_state(state)
    return "Setup completed"

def validate_auth(provider: APIProvider, api_key: str | None):
    if provider == APIProvider.ANTHROPIC:
        if not api_key:
            return "Enter your Anthropic API key to continue."
    if provider == APIProvider.BEDROCK:
        import boto3

        if not boto3.Session().get_credentials():
            return "You must have AWS credentials set up to use the Bedrock API."
    if provider == APIProvider.VERTEX:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError

        if not os.environ.get("CLOUD_ML_REGION"):
            return "Set the CLOUD_ML_REGION environment variable to use the Vertex API."
        try:
            google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        except DefaultCredentialsError:
            return "Your google cloud credentials are not set up correctly."

def load_from_storage(filename: str) -> str | None:
    """Load data from a file in the storage directory."""
    try:
        file_path = CONFIG_DIR / filename
        if file_path.exists():
            data = file_path.read_text().strip()
            if data:
                return data
    except Exception as e:
        print(f"Debug: Error loading {filename}: {e}")
    return None

def save_to_storage(filename: str, data: str) -> None:
    """Save data to a file in the storage directory."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        file_path = CONFIG_DIR / filename
        file_path.write_text(data)
        # Ensure only user can read/write the file
        file_path.chmod(0o600)
    except Exception as e:
        print(f"Debug: Error saving {filename}: {e}")

def _api_response_callback(response: APIResponse[BetaMessage], response_state: dict):
    response_id = datetime.now().isoformat()
    response_state[response_id] = response

def _tool_output_callback(tool_output: ToolResult, tool_id: str, tool_state: dict):
    tool_state[tool_id] = tool_output

def chatbot_output_callback(message, chatbot_state, hide_images=False, sender="bot"):
    def _render_message(message: str | BetaTextBlock | BetaToolUseBlock | ToolResult, hide_images=False):
    
        print(f"_render_message: {str(message)[:100]}")
        
        if isinstance(message, str):
            return message
        
        is_tool_result = not isinstance(message, str) and (
            isinstance(message, ToolResult)
            or message.__class__.__name__ == "ToolResult"
        )
        if not message or (
            is_tool_result
            and hide_images
            and not hasattr(message, "error")
            and not hasattr(message, "output")
        ):  # return None if hide_images is True
            return
        # render tool result
        if is_tool_result:
            message = cast(ToolResult, message)
            if message.output:
                return message.output
            if message.error:
                return f"Error: {message.error}"
            if message.base64_image and not hide_images:
                # somehow can't display via gr.Image
                # image_data = base64.b64decode(message.base64_image)
                # return gr.Image(value=Image.open(io.BytesIO(image_data)))
                return f'<img src="data:image/png;base64,{message.base64_image}">'

        elif isinstance(message, BetaTextBlock) or isinstance(message, TextBlock):
            return f"Analysis: {message.text}"
        elif isinstance(message, BetaToolUseBlock) or isinstance(message, ToolUseBlock):
            # return f"Tool Use: {message.name}\nInput: {message.input}"
            return f"Next I will perform the following action: {message.input}"
        else:  
            return message

    def _truncate_string(s, max_length=500):
        """Truncate long strings for concise printing."""
        if isinstance(s, str) and len(s) > max_length:
            return s[:max_length] + "..."
        return s
    # processing Anthropic messages
    message = _render_message(message, hide_images)
    
    if sender == "bot":
        chatbot_state.append((None, message))
    else:
        chatbot_state.append((message, None))
    
    # Create a concise version of the chatbot state for printing
    concise_state = [(_truncate_string(user_msg), _truncate_string(bot_msg))
                        for user_msg, bot_msg in chatbot_state]
    # print(f"chatbot_output_callback chatbot_state: {concise_state} (truncated)")

def valid_params(user_input, state):
    """Validate all requirements and return a list of error messages."""
    errors = []
    agent_type = state.get("agent_type", "vlm_agent")

    if agent_type == "vlm_agent":
        for server_name, url in [('Windows Host', 'localhost:5000'), ('OmniParser Server', args.omniparser_server_url)]:
            try:
                url = f'http://{url}/probe'
                response = requests.get(url, timeout=3)
                if response.status_code != 200:
                    errors.append(f"{server_name} is not responding")
            except RequestException as e:
                errors.append(f"{server_name} is not responding")
    
    # Common validations
    if not state.get("api_key", "").strip():
        # API key might not be needed if PPTAgent uses a local/free model, but current PPTAgent needs one for DeepSeek/Groq
        errors.append("LLM API Key is not set (required for selected model/provider)")

    if not user_input:
        if agent_type == "ppt_generator":
            errors.append("PPT Topic is not provided")
        else: # vlm_agent
            errors.append("No computer use request provided")
    
    return errors

def process_input(user_input, state):
    # Reset the stop flag
    if state["stop"]:
        state["stop"] = False

    errors = valid_params(user_input, state)
    if errors:
        raise gr.Error("Validation errors: " + ", ".join(errors))
    
    # Append the user's message to chatbot_messages with None for the assistant's reply
    state['chatbot_messages'].append((user_input, None))
    yield state['chatbot_messages']

    agent_type = state.get("agent_type", "vlm_agent")

    if agent_type == "ppt_generator":
        chatbot_output_callback(f"PPT Topic Received: {user_input}", state['chatbot_messages'], sender="bot") 
        yield state['chatbot_messages']

        ppt_agent = PPTAgent(
            model=state["model"], 
            provider=state["provider"], 
            api_key=state["api_key"],
            output_callback=partial(chatbot_output_callback, chatbot_state=state['chatbot_messages'], sender="bot"),
            api_response_callback=partial(_api_response_callback, response_state=state["responses"])
        )
        
        ppt_topic = user_input
        ppt_filename = state.get("ppt_filename", "GeneratedPPT.pptx")
        
        chatbot_output_callback(f"Generating PPT content and actions for topic: '{ppt_topic}' (filename: '{ppt_filename}')...", state['chatbot_messages'], sender="bot")
        yield state['chatbot_messages']

        try:
            result = ppt_agent.generate_ppt_content_and_actions(topic=ppt_topic, ppt_filename=ppt_filename)
            generated_slides = result.get("generated_slides", [])
            powerpoint_actions = result.get("powerpoint_actions", [])

            summary_message = f"PPT Content Generation Complete:\nGenerated {len(generated_slides)} slides.\n"
            # for i, slide in enumerate(generated_slides):
            #     summary_message += f"  Slide {i+1}: {slide.get('title', 'No Title')}\n"
            summary_message += f"Found {len(powerpoint_actions)} PowerPoint creation actions. Starting execution..."
            chatbot_output_callback(summary_message, state['chatbot_messages'], sender="bot")
            yield state['chatbot_messages']

            # Initialize ComputerTool
            # The 'messages' state for ComputerTool might need careful handling if PPTAgent modifies it.
            # For now, we pass the main state["messages"], which might have the initial user prompt.
            computer_tool = ComputerTool(
                output_callback=partial(chatbot_output_callback, chatbot_state=state['chatbot_messages'], sender="tool_raw_output"), # For raw output from tool if any
                omniparser_url=args.omniparser_server_url,
                messages=state["messages"] # Pass messages for context if ComputerTool uses it
            )

            for action_step in powerpoint_actions:
                if state.get("stop"):
                    chatbot_output_callback("PPT Action execution stopped by user.", state['chatbot_messages'], sender="bot_info")
                    yield state['chatbot_messages']
                    break
                
                action_type_display = action_step.get('action_type', 'Unknown Action')
                action_details_display = ""
                if action_type_display == "TYPE_TEXT":
                    action_details_display = f" (Placeholder: {action_step.get('target_placeholder', '')}, Text: {action_step.get('text', '')[:30]}...)"
                
                chatbot_output_callback(f"Executing planned action: {action_type_display}{action_details_display}", state['chatbot_messages'], sender="bot_info")
                yield state['chatbot_messages']

                # Screen Capture
                parsed_screen_result = None
                try:
                    parsed_screen_result = computer_tool.capture_screen_uri_and_elements_v2()
                    if not parsed_screen_result or parsed_screen_result.get("error"):
                        raise Exception(parsed_screen_result.get('error', 'Unknown screen capture error'))
                    # Display screenshot in chat - ComputerTool's capture_screen_uri_and_elements_v2 already does this via its output_callback
                    # For example: chatbot_output_callback(ToolResult(tool_id="screen_capture", base64_image=parsed_screen_result.get('screenshot_base64')), state['chatbot_messages'], sender="tool_result")
                    # yield state['chatbot_messages']
                except Exception as e:
                    chatbot_output_callback(f"Error capturing screen: {str(e)}", state['chatbot_messages'], sender="bot_error")
                    yield state['chatbot_messages']
                    continue # Skip to next action or break

                # Get Executable Action from PPTAgent
                beta_message: Optional[BetaMessage] = None
                vlm_response_json: Optional[Dict] = None
                try:
                    beta_message, vlm_response_json = ppt_agent.get_next_executable_action(action_step, parsed_screen_result)
                except Exception as e:
                    chatbot_output_callback(f"Error in get_next_executable_action: {str(e)}", state['chatbot_messages'], sender="bot_error")
                    yield state['chatbot_messages']
                    continue

                # Handle Meta-Actions or errors from get_next_executable_action
                if beta_message is None:
                    status = vlm_response_json.get("status") if vlm_response_json else "unknown_error"
                    details = vlm_response_json.get("details", {}) if vlm_response_json else {}
                    
                    if status == "meta_action":
                        meta_action_type = details.get('action_type', 'UNKNOWN_META_ACTION')
                        chatbot_output_callback(f"Meta action: {meta_action_type}. Details: {details}. Attempting direct handling.", state['chatbot_messages'], sender="bot_info")
                        yield state['chatbot_messages']
                        try:
                            if meta_action_type == "OPEN_APPLICATION":
                                computer_tool.open_application(details.get("application_name", "PowerPoint"))
                                chatbot_output_callback(f"Opened {details.get('application_name', 'PowerPoint')}", state['chatbot_messages'], sender="tool_result")
                            elif meta_action_type == "CLOSE_APPLICATION":
                                computer_tool.close_application(details.get("application_name", "PowerPoint"))
                                chatbot_output_callback(f"Closed {details.get('application_name', 'PowerPoint')}", state['chatbot_messages'], sender="tool_result")
                            # SAVE_PRESENTATION and CREATE_NEW_PRESENTATION are more complex UI tasks,
                            # get_next_executable_action should ideally convert them to VLM-guided steps.
                            # If they still arrive here as meta_actions, it means they need more specific UI sequences.
                            elif meta_action_type in ["SAVE_PRESENTATION", "CREATE_NEW_PRESENTATION"]:
                                chatbot_output_callback(f"Meta action '{meta_action_type}' requires complex UI interaction not yet fully implemented as direct call. It should be broken down by VLM.", state['chatbot_messages'], sender="bot_warning")

                            time.sleep(3) # Give time for app to open/close
                        except Exception as e:
                            chatbot_output_callback(f"Error handling meta action {meta_action_type}: {str(e)}", state['chatbot_messages'], sender="bot_error")
                        yield state['chatbot_messages']
                        continue
                    else:
                        error_msg = vlm_response_json.get('error', 'No BetaMessage returned and not a meta_action') if vlm_response_json else 'Agent failed to produce BetaMessage'
                        chatbot_output_callback(f"Could not determine executable action: {error_msg}", state['chatbot_messages'], sender="bot_error")
                        yield state['chatbot_messages']
                        continue
                
                # Execute BetaMessage
                if beta_message:
                    reasoning = next((c.text for c in beta_message.content if isinstance(c, BetaTextBlock)), "No reasoning provided.")
                    chatbot_output_callback(f"VLM Reasoning: {reasoning}", state['chatbot_messages'], sender="bot_info")
                    yield state['chatbot_messages']
                    
                    has_executed_tool_in_betamsg = False
                    for content_block in beta_message.content:
                        if isinstance(content_block, BetaToolUseBlock):
                            has_executed_tool_in_betamsg = True
                            chatbot_output_callback(f"Attempting to execute tool: {content_block.name}, Input: {content_block.input}", state['chatbot_messages'], sender="bot_info")
                            yield state['chatbot_messages']
                            try:
                                tool_result: ToolResult = computer_tool.execute_tool(tool_use_block=content_block, messages=state["messages"])
                            except Exception as e:
                                tool_result = ToolResult(tool_id=content_block.id, error=f"FATAL: Tool execution failed: {str(e)}") # Ensure tool_id is populated
                            
                            chatbot_output_callback(tool_result, state['chatbot_messages'], sender="tool_result") # Assuming callback can handle ToolResult
                            yield state['chatbot_messages']
                            if tool_result.error:
                                chatbot_output_callback(f"Error executing tool {content_block.name}: {tool_result.error}", state['chatbot_messages'], sender="bot_error")
                                yield state['chatbot_messages']
                                break # Stop processing this BetaMessage if a tool fails
                    
                    if not has_executed_tool_in_betamsg:
                        chatbot_output_callback("No tool use block found in BetaMessage to execute.", state['chatbot_messages'], sender="bot_warning")
                        yield state['chatbot_messages']

                time.sleep(2) # Delay between high-level actions

            chatbot_output_callback("PowerPoint action sequence processing complete.", state['chatbot_messages'], sender="bot")
            yield state['chatbot_messages']

        except Exception as e:
            error_msg = f"Error during PPT processing or execution: {str(e)}"
            chatbot_output_callback(error_msg, state['chatbot_messages'], sender="bot_error")
            yield state['chatbot_messages']

    elif agent_type == "vlm_agent":
        # Append the user message to state["messages"] for VLM agent
        state["messages"].append(
            {
                "role": Sender.USER,
                "content": [TextBlock(type="text", text=user_input)],
            }
        )
        print("VLM Agent State:")
        print(state)
        # Run sampling_loop_sync with the chatbot_output_callback
        for loop_msg in sampling_loop_sync(
            model=state["model"],
            provider=state["provider"],
            messages=state["messages"],
            output_callback=partial(chatbot_output_callback, chatbot_state=state['chatbot_messages'], hide_images=False),
            tool_output_callback=partial(_tool_output_callback, tool_state=state["tools"]),
            api_response_callback=partial(_api_response_callback, response_state=state["responses"]),
            api_key=state["api_key"],
            only_n_most_recent_images=state["only_n_most_recent_images"],
            max_tokens=16384,
            omniparser_url=args.omniparser_server_url
        ):  
            if loop_msg is None or state.get("stop"):
                yield state['chatbot_messages']
                print("End of task. Close the loop.")
                break
                
            yield state['chatbot_messages']
    else:
        chatbot_output_callback(f"Error: Unknown agent type '{agent_type}'.", state['chatbot_messages'], sender="bot_error")
        yield state['chatbot_messages']

def stop_app(state):
    state["stop"] = True
    return "App stopped"

def get_header_image_base64():
    try:
        # Get the absolute path to the image relative to this script
        script_dir = Path(__file__).parent
        image_path = script_dir.parent.parent / "imgs" / "header_bar_thin.png"
        
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            return f'data:image/png;base64,{encoded_string}'
    except Exception as e:
        print(f"Failed to load header image: {e}")
        return None

with gr.Blocks(theme=gr.themes.Default()) as demo:
    gr.HTML("""
        <style>
        .no-padding {
            padding: 0 !important;
        }
        .no-padding > div {
            padding: 0 !important;
        }
        .markdown-text p {
            font-size: 18px;  /* Adjust the font size as needed */
        }
        </style>
    """)
    state = gr.State({})
    
    setup_state(state.value)
    
    header_image = get_header_image_base64()
    if header_image:
        gr.HTML(f'<img src="{header_image}" alt="OmniTool Header" width="100%">', elem_classes="no-padding")
        gr.HTML('<h1 style="text-align: center; font-weight: normal;">Omni<span style="font-weight: bold;">Tool</span></h1>')
    else:
        gr.Markdown("# OmniTool")

    if not os.getenv("HIDE_WARNING", False):
        gr.Markdown(INTRO_TEXT, elem_classes="markdown-text")


    with gr.Accordion("Settings", open=True): 
        with gr.Row():
            with gr.Column():
                model = gr.Dropdown(
                    label="Model",
                    choices=["omniparser + gpt-4o", "omniparser + o1", "omniparser + o3-mini", "omniparser + R1", "omniparser + qwen2.5vl", "claude-3-5-sonnet-20241022", "omniparser + gpt-4o-orchestrated", "omniparser + o1-orchestrated", "omniparser + o3-mini-orchestrated", "omniparser + R1-orchestrated", "omniparser + qwen2.5vl-orchestrated"],
                    value="omniparser + gpt-4o",
                    interactive=True,
                )
            with gr.Column():
                only_n_images = gr.Slider(
                    label="N most recent screenshots",
                    minimum=0,
                    maximum=10,
                    step=1,
                    value=2,
                    interactive=True
                )
        with gr.Row():
            with gr.Column(1):
                provider = gr.Dropdown(
                    label="API Provider",
                    choices=[option.value for option in APIProvider],
                    value="openai",
                    interactive=False,
                )
            with gr.Column(2):
                api_key = gr.Textbox(
                    label="API Key",
                    type="password",
                    value=state.value.get("api_key", ""),
                    placeholder="Paste your API key here",
                    interactive=True,
                )

    with gr.Row():
        with gr.Column(scale=8):
            chat_input = gr.Textbox(show_label=False, placeholder="Type a message to send to Omniparser + X ...", container=False)
        with gr.Column(scale=1, min_width=50):
            submit_button = gr.Button(value="Send", variant="primary")
        with gr.Column(scale=1, min_width=50):
            stop_button = gr.Button(value="Stop", variant="secondary")

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(label="Chatbot History", autoscroll=True, height=580)
        with gr.Column(scale=3):
            iframe = gr.HTML(
                f'<iframe src="http://{args.windows_host_url}/vnc.html?view_only=1&autoconnect=1&resize=scale" width="100%" height="580" allow="fullscreen"></iframe>',
                container=False,
                elem_classes="no-padding"
            )

    def update_model(model_selection, state):
        state["model"] = model_selection
        print(f"Model updated to: {state['model']}")
        
        if model_selection == "claude-3-5-sonnet-20241022":
            provider_choices = [option.value for option in APIProvider if option.value != "openai"]
        elif model_selection in set(["omniparser + gpt-4o", "omniparser + o1", "omniparser + o3-mini", "omniparser + gpt-4o-orchestrated", "omniparser + o1-orchestrated", "omniparser + o3-mini-orchestrated"]):
            provider_choices = ["openai"]
        elif model_selection == "omniparser + R1":
            provider_choices = ["groq"]
        elif model_selection == "omniparser + qwen2.5vl":
            provider_choices = ["dashscope"]
        else:
            provider_choices = [option.value for option in APIProvider]
        default_provider_value = provider_choices[0]

        provider_interactive = len(provider_choices) > 1
        api_key_placeholder = f"{default_provider_value.title()} API Key"

        # Update state
        state["provider"] = default_provider_value
        state["api_key"] = state.get(f"{default_provider_value}_api_key", "")

        # Calls to update other components UI
        provider_update = gr.update(
            choices=provider_choices,
            value=default_provider_value,
            interactive=provider_interactive
        )
        api_key_update = gr.update(
            placeholder=api_key_placeholder,
            value=state["api_key"]
        )

        return provider_update, api_key_update

    def update_only_n_images(only_n_images_value, state):
        state["only_n_most_recent_images"] = only_n_images_value
   
    def update_provider(provider_value, state):
        # Update state
        state["provider"] = provider_value
        state["api_key"] = state.get(f"{provider_value}_api_key", "")
        
        # Calls to update other components UI
        api_key_update = gr.update(
            placeholder=f"{provider_value.title()} API Key",
            value=state["api_key"]
        )
        return api_key_update
                
    def update_api_key(api_key_value, state):
        state["api_key"] = api_key_value
        state[f'{state["provider"]}_api_key'] = api_key_value

    def clear_chat(state):
        # Reset message-related state
        state["messages"] = []
        state["responses"] = {}
        state["tools"] = {}
        state['chatbot_messages'] = []
        return state['chatbot_messages']

    model.change(fn=update_model, inputs=[model, state], outputs=[provider, api_key])
    only_n_images.change(fn=update_only_n_images, inputs=[only_n_images, state], outputs=None)
    provider.change(fn=update_provider, inputs=[provider, state], outputs=api_key)
    api_key.change(fn=update_api_key, inputs=[api_key, state], outputs=None)
    chatbot.clear(fn=clear_chat, inputs=[state], outputs=[chatbot])

    submit_button.click(process_input, [chat_input, state], chatbot)
    stop_button.click(stop_app, [state], None)
    
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7888)