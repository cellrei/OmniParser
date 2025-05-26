import json
from collections.abc import Callable
from typing import List, Dict, Any, Optional, Tuple # Updated typing
import time
import uuid # For BetaMessage
import re # For extract_data

from agent.llm_utils.groqclient import run_groq_interleaved
# from agent.llm_utils.oaiclient import run_oai_interleaved # Placeholder
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock, BetaUsage # For BetaMessage construction

# Utility function similar to VLMAgent's extract_data, if not available from utils
def extract_data(input_string: str, data_type: str) -> str:
    # Regular expression to extract content starting from f"```{data_type}"
    pattern = f"```{data_type}" + r"(.*?)(```|$)"
    matches = re.findall(pattern, input_string, re.DOTALL)
    return matches[0][0].strip() if matches else input_string

class PPTAgent:
    def __init__(
        self,
        model: str,
        provider: str,
        api_key: str,
        output_callback: Callable,
        api_response_callback: Callable,
        max_tokens: int = 4096,
        print_usage: bool = True,
    ):
        if model.lower() == "r1" or "deepseek" in model.lower(): # Assuming R1 is a VLM or suitable for UI grounding
            self.model_name = "deepseek-r1-distill-llama-70b" 
            if provider.lower() != "groq":
                self.output_callback(f"Warning: Model '{model}' is typically used with Groq for VLM tasks. Provider set to '{provider}'.", sender="agent_warning")
        # Example for GPT-4o if it's preferred for VLM tasks
        # elif "gpt-4o" in model.lower():
        #     self.model_name = "gpt-4o-2024-05-13" # Or the latest version
        #     if provider.lower() != "openai":
        #          self.output_callback(f"Warning: Model '{model}' is typically used with OpenAI. Provider set to '{provider}'.", sender="agent_warning")
        else:
            self.output_callback(f"Warning: Model {model} has no specific UI grounding mapping. Using as is. Ensure it's a VLM and compatible with the provider.", sender="agent_warning")
            self.model_name = model

        self.provider = provider.lower()
        self.api_key = api_key
        self.output_callback = output_callback
        self.api_response_callback = api_response_callback
        self.max_tokens = max_tokens
        
        self.print_usage = print_usage
        self.total_token_usage = 0
        self.total_cost = 0
        self.step_count = 0 
        self.ui_interaction_step_count = 0 

        self.system_prompt_outline = """You are an AI assistant specialized in generating PowerPoint presentation outlines.
Given a topic, you must generate a list of slide titles or key themes for the presentation.
The output should be a JSON formatted list of strings. Each string in the list represents a slide title or a major section.
For example, if the topic is "Renewable Energy", the output should be:
["Title: The Future is Renewable", "Introduction: What is Renewable Energy?", "Types of Renewable Energy (Solar, Wind, Hydro)", "Benefits of Renewable Energy", "Challenges and Solutions", "Conclusion: Transitioning to a Green Future"]
Ensure the output is ONLY the JSON list of strings. Do not include any other text, explanations, or markdown formatting outside the JSON structure.
"""
        self.system_prompt_content = """You are an AI assistant specialized in generating detailed content for PowerPoint presentation slides.
Given a slide title, you should provide relevant information to be displayed on that slide.
The content should be informative, concise, and well-structured. Use bullet points or short paragraphs.
Avoid overly long sentences. Focus on key takeaways for the audience.
Do NOT output JSON or Markdown. Output plain text suitable for direct inclusion in a slide.
For example, if the slide title is "Benefits of Solar Energy", your output could be:
- Reduces electricity bills
- Low maintenance costs
- Environmentally friendly, reduces carbon footprint
- Can increase property value
- Versatile installation options (rooftop, ground-mounted)
"""

    def _generate_outline(self, topic: str) -> List[str]:
        """
        Generates a PPT outline (list of slide titles/themes) for a given topic using an LLM.
        This is an internal method.
        """
        self.output_callback(f"--- Generating Outline for topic: '{topic}' ---", sender="agent_internal")
        user_message_content = f"Generate a PowerPoint presentation outline for the topic: '{topic}'. Follow the format instructions precisely."
        
        messages = [
            {"role": "user", "content": user_message_content}
        ]

        llm_response_text = ""
        token_usage = 0
        
        start_time = time.time()
        try:
            if self.provider == "groq":
                llm_response, token_usage_from_call = run_groq_interleaved(
                    messages=messages,
                    system=self.system_prompt_outline, # Use outline prompt
                    model_name=self.model_name,
                    api_key=self.api_key,
                    max_tokens=self.max_tokens,
                )
                llm_response_text = llm_response
                token_usage = token_usage_from_call or 0
            # elif self.provider == "openai": # Placeholder for other providers
            #     # Similar call to run_oai_interleaved
            #     pass
            else:
                self.output_callback(f"Error: Provider '{self.provider}' is not supported by PPTAgent for outline generation.", sender="agent_error")
                return [f"Error: Provider '{self.provider}' not supported for outline generation."]

            latency_llm = time.time() - start_time
            self.output_callback(f"LLM call for outline completed in {latency_llm:.2f}s. Tokens: {token_usage}", sender="agent_metrics")
            
            if self.api_response_callback:
                self.api_response_callback({"step": "outline", "topic": topic, "response": llm_response_text, "tokens": token_usage})

            if token_usage:
                self.total_token_usage += token_usage
                if self.provider == "groq": 
                    cost = (token_usage * 0.7 / 1000000) 
                    self.total_cost += cost
                    if self.print_usage:
                        self.output_callback(f"Token usage for outline: {token_usage}. Cost: ${cost:.6f}", sender="agent_metrics")

        except Exception as e:
            self.output_callback(f"Error during LLM call for outline: {str(e)}", sender="agent_error")
            return [f"Error generating outline: {str(e)}"]

        if not llm_response_text:
            self.output_callback("LLM response for outline was empty.", sender="agent_warning")
            return ["Error: No response from LLM for outline."]

        # Attempt to parse the LLM response as JSON
        try:
            # The prompt asks for a JSON list directly.
            # Sometimes the response might be wrapped in ```json ... ```, try to extract if so.
            if llm_response_text.strip().startswith("```json"):
                llm_response_text = llm_response_text.split("```json")[1].split("```")[0].strip()
            
            parsed_outline = json.loads(llm_response_text)
            if isinstance(parsed_outline, list) and all(isinstance(item, str) for item in parsed_outline):
                self.output_callback(f"Successfully parsed PPT outline: {parsed_outline}", sender="agent_internal")
                return parsed_outline
            else: # Fallback parsing if not list of strings
                self.output_callback("LLM response for outline was not a list of strings as expected, attempting fallback.", sender="agent_warning")
                if isinstance(parsed_outline, list): return [str(item) for item in parsed_outline]
                return [line.strip() for line in llm_response_text.split('\n') if line.strip()]
        except json.JSONDecodeError:
            self.output_callback(f"Failed to decode JSON for outline: {llm_response_text}", sender="agent_warning")
            outline = [item.lstrip('-* ').rstrip(',') for item in llm_response_text.split('\n') if item.strip()]
            return [o for o in outline if o] # Filter out empty strings
        except Exception as e:
            self.output_callback(f"Error parsing outline response: {str(e)}", sender="agent_error")
            return [f"Error parsing outline: {str(e)}"]

    def generate_powerpoint_creation_steps(self, ppt_data: List[Dict[str, str]], filename: str = "GeneratedPPT.pptx") -> List[Dict[str, Any]]:
        """
        Generates a list of high-level actions to create a PowerPoint presentation.
        """
        action_steps: List[Dict[str, Any]] = []

        # Start PowerPoint and create a new presentation
        action_steps.append({"action_type": "OPEN_APPLICATION", "application_name": "PowerPoint"})
        action_steps.append({"action_type": "CREATE_NEW_PRESENTATION"}) # Assumes default template, first slide is often title slide

        if not ppt_data:
            self.output_callback("Warning: PPT data is empty. Generating minimal actions.", sender="agent_warning")
            action_steps.append({"action_type": "SAVE_PRESENTATION", "filename": filename})
            action_steps.append({"action_type": "CLOSE_APPLICATION", "application_name": "PowerPoint"})
            return action_steps

        for i, slide_data in enumerate(ppt_data):
            slide_title = slide_data.get("title", f"Slide {i+1}")
            slide_content = slide_data.get("content", "")

            if i == 0:
                # First slide: often a title slide. Actions depend on assumed template.
                # If the first slide from LLM is "Title: Overall Presentation Title", it fits title slide layout.
                # Otherwise, it might go into a "TITLE_AND_CONTENT" first slide.
                # For simplicity, we'll assume the first slide uses a "TITLE_SLIDE" layout if it's a main title,
                # or "TITLE_AND_CONTENT" if it's more like a regular slide.
                # This heuristic can be improved.
                if "Introduction" in slide_title or i > 0 : # Crude check, can be refined
                     action_steps.append({"action_type": "ADD_NEW_SLIDE", "layout": "TITLE_AND_CONTENT"})
                # else:
                    # action_steps.append({"action_type": "SET_SLIDE_LAYOUT", "layout": "TITLE_SLIDE"}) # Or assume first slide is already title
                    # For now, let's assume CREATE_NEW_PRESENTATION gives us a usable first slide (often title or title_and_content)
                    pass


            else: # For slides other than the first one
                action_steps.append({"action_type": "ADD_NEW_SLIDE", "layout": "TITLE_AND_CONTENT"})
            
            action_steps.append({"action_type": "TYPE_TEXT", "target_placeholder": "TITLE", "text": slide_title})
            if slide_content: # Only add content typing if content exists
                 action_steps.append({"action_type": "TYPE_TEXT", "target_placeholder": "CONTENT", "text": slide_content})

        # Save and close
        action_steps.append({"action_type": "SAVE_PRESENTATION", "filename": filename})
        action_steps.append({"action_type": "CLOSE_APPLICATION", "application_name": "PowerPoint"})
        
        self.output_callback(f"Generated {len(action_steps)} PowerPoint creation steps.", sender="agent_internal")
        return action_steps

    def generate_ppt_content_and_actions(self, topic: str, ppt_filename: str = "GeneratedPPT.pptx") -> Dict[str, Any]:
        """
        Generates PPT slide data (titles and content) and a list of PowerPoint creation actions.
        This is the main method to be called.
        """
        self.step_count += 1
        self.output_callback(f"-- PPT Generation Task {self.step_count}: Starting for topic '{topic}' --", sender="agent")

        # 1. Generate outline
        outline = self._generate_outline(topic)

        if not outline or any("Error:" in item for item in outline):
            error_message = f"Outline generation failed for topic: {topic}. Outline response: {str(outline)}"
            self.output_callback(error_message, sender="agent_error")
            return {
                "generated_slides": [{"title": "Error", "content": error_message}],
                "powerpoint_actions": [
                    {"action_type": "ERROR", "message": "Outline generation failed."}
                ]
            }

        ppt_slides_data: List[Dict[str, str]] = []
        
        # 2. Generate content for each slide in the outline
        for i, slide_title in enumerate(outline):
            self.output_callback(f"--- Generating content for slide {i+1}/{len(outline)}: '{slide_title}' ---", sender="agent_internal")
            
            user_message_content = f"Generate detailed content for a PowerPoint slide titled '{slide_title}'. The content should be suitable for a presentation slide, using bullet points or concise paragraphs. Focus on key information related to this specific slide title within the broader topic of '{topic}'."
            messages = [{"role": "user", "content": user_message_content}]
            
            slide_content_text = ""
            token_usage = 0
            start_time = time.time()

            try:
                if self.provider == "groq":
                    llm_response, token_usage_from_call = run_groq_interleaved(
                        messages=messages,
                        system=self.system_prompt_content, # Use content prompt
                        model_name=self.model_name,
                        api_key=self.api_key,
                        max_tokens=self.max_tokens, # Consider if max_tokens needs adjustment for content
                    )
                    slide_content_text = llm_response.strip()
                    token_usage = token_usage_from_call or 0
                # elif self.provider == "openai":
                #     pass # Placeholder for other providers
                else:
                    self.output_callback(f"Error: Provider '{self.provider}' not supported for slide content generation.", sender="agent_error")
                    slide_content_text = f"Error: Provider '{self.provider}' not supported."

                latency_llm = time.time() - start_time
                self.output_callback(f"LLM call for slide '{slide_title}' completed in {latency_llm:.2f}s. Tokens: {token_usage}", sender="agent_metrics")

                if self.api_response_callback:
                     self.api_response_callback({"step": "content", "slide_title": slide_title, "response": slide_content_text, "tokens": token_usage})

                if token_usage:
                    self.total_token_usage += token_usage
                    if self.provider == "groq": 
                        cost = (token_usage * 0.7 / 1000000)
                        self.total_cost += cost
                        if self.print_usage:
                             self.output_callback(f"Token usage for slide '{slide_title}': {token_usage}. Cost: ${cost:.6f}", sender="agent_metrics")
                
                # Basic cleaning: remove potential markdown code block fences if LLM mistakenly adds them
                if slide_content_text.startswith("```") and slide_content_text.endswith("```"):
                    lines = slide_content_text.splitlines()
                    if len(lines) > 2: # Ensure there's content between fences
                        slide_content_text = "\n".join(lines[1:-1]).strip()


            except Exception as e:
                self.output_callback(f"Error during LLM call for slide '{slide_title}': {str(e)}", sender="agent_error")
                slide_content_text = f"Error: Could not generate content for this slide due to: {str(e)}"
            
            if not slide_content_text:
                 slide_content_text = "No content generated for this slide."
                 self.output_callback(f"Warning: LLM response for slide '{slide_title}' was empty.", sender="agent_warning")

            ppt_slides_data.append({"title": slide_title, "content": slide_content_text})
        
        # 3. Generate PowerPoint creation actions
        action_steps = self.generate_powerpoint_creation_steps(ppt_slides_data, filename=ppt_filename)

        if self.print_usage:
            self.output_callback(f"--- PPT Generation and Action Planning for '{topic}' Complete ---", sender="agent")
            self.output_callback(f"Total token usage for task: {self.total_token_usage}. Total estimated cost: ${self.total_cost:.6f}", sender="agent_metrics")
        
        return {
            "generated_slides": ppt_slides_data,
            "powerpoint_actions": action_steps
        }
