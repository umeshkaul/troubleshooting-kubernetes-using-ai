# The code below demonstrates using OpenAI function calling

# Step-1: Set your openai api key
#         export OPENAI_API_KEY=your-openai-api-key-goes-here
# Step-2 : Install dependencies
#         pip3 install -r requirements.txt
# Step-3 : Set the name of the city for which you want to get weather in line 44 below e.g  and run the program   

# $python test-openai-function.py
# ######
# DEBUG:  get_current_weather function being called with location:  Paris, France unit:  None
# ######
# ChatCompletion(id='chatcmpl-BO3HheyTWgT3lWOI6kGCWjJl5ZiLe', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content='The current temperature in Paris is 22°C. If you need more details about the weather conditions, feel free to ask!', role='assistant', function_call=None, tool_calls=None, refusal=None, annotations=[]))], created=1745072197, model='gpt-4o-mini-2024-07-18', object='chat.completion', service_tier='default', system_fingerprint='fp_f7d56a8a2c', usage=CompletionUsage(completion_tokens=26, prompt_tokens=57, total_tokens=83, prompt_tokens_details={'cached_tokens': 0, 'audio_tokens': 0}, completion_tokens_details={'reasoning_tokens': 0, 'audio_tokens': 0, 'accepted_prediction_tokens': 0, 'rejected_prediction_tokens': 0}))


from openai import OpenAI
import json

client = OpenAI()

# Example dummy function hard coded to return the same weather
# In production, this could be your backend API or an external API

def get_current_weather(location, unit="fahrenheit"):
    """Get the current weather in a given location"""
    print("######")
    print("DEBUG:  get_current_weather function being called with location: ",location, "unit: ", unit)
    print("######")

    if "tokyo" in location.lower():
        return json.dumps({"location": "Tokyo", "temperature": "10", "unit": unit})
    elif "san francisco" in location.lower():
        return json.dumps({"location": "San Francisco", "temperature": "72", "unit": unit})
    elif "paris" in location.lower():
        return json.dumps({"location": "Paris", "temperature": "22", "unit": unit})
    else:
        return json.dumps({"location": location, "temperature": "unknown"})


def run_conversation():
    # Step 1: send the conversation and available functions to the model

    #messages = [{"role": "user", "content": "What's the weather like in San Francisco, Tokyo, and Paris?"}]

    messages = [{"role": "user", "content": "What's the weather like in Paris?"}]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the current weather in a given location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA",
                        },
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto",  # auto is default, but we'll be explicit
    )

    response_message = response.choices[0].message

    tool_calls = response_message.tool_calls

    # Step 2: check if the model wanted to call a function

    if tool_calls:

        # Step 3: call the function
        # Note: the JSON response may not always be valid; be sure to handle errors

        available_functions = {
            "get_current_weather": get_current_weather,
        }  # only one function in this example, but you can have multiple
        messages.append(response_message)  # extend conversation with assistant's reply

        # Step 4: send the info for each function call and function response to the model

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(
                location=function_args.get("location"),
                unit=function_args.get("unit"),
            )
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )  # extend conversation with function response
        second_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )  # get a new response from the model where it can see the function response
        return second_response

print(run_conversation())
