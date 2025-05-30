"""
DESCRIPTION:
    This sample demonstrates how to use agent operations with the
    Morningstar OpenAPI tool, from the Azure Agents service using a synchronous client.
    To learn more about OpenAPI specs, visit https://learn.microsoft.com/openapi
    Link to the Morningstar Agent OpenAPI spec: https://developer.morningstar.com/direct-web-services/documentation/intelligence-engine/apps/morningstar-agent-api
    Download the OpenAPI spec and store it as morningstar.json
USAGE:
    python sample_agents_openapi_morningstar.py
    Before running the sample:
    pip install azure-ai-projects azure-identity jsonref
    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - The project endpoint in the format
       "https://<your-ai-services-resource-name>.services.ai.azure.com/api/projects/<your-project-name>"
    2) MODEL - The model deployment name
    3) CONNECTION_ID - The connection id in the format
       "/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-connection-name>"
    You'll also need a JWT token to authorize with the Morningstar service.
    You can fetch this JWT token by using the below code:
    import requests
    from requests.auth import HTTPBasicAuth
    url = "https://www.us-api.morningstar.com/token/oauth"
    response = requests.post(url, auth=auth)
    print(response.text)
    Note: This token expires, please remember to refresh your credentials.
"""

import os
import jsonref
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    OpenApiConnectionAuthDetails,
    OpenApiConnectionSecurityScheme,
    OpenApiTool,
)
from azure.identity import DefaultAzureCredential

# Initialize the project client using the endpoint and default credentials
project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
)

with open("./morningstar.json", "r") as f:
    openapi_spec = jsonref.loads(f.read())

# Create Auth object for the OpenApiTool (note that connection or managed identity auth setup requires additional setup in Azure)
connection_id = os.environ["CONNECTION_ID"]
auth = OpenApiConnectionAuthDetails(
    security_scheme=OpenApiConnectionSecurityScheme(connection_id=connection_id)
)

# Create the OpenAPI tool
openapi = OpenApiTool(
    name="morningstar",
    spec=openapi_spec,
    description="Retrieves information from Morningstar.",
    auth=auth,
)

INSTRUCTIONS = """
You are a helpful assistant that answers questions using Morningstar's data. Only refer to the information found in the **"answer"** and **"sources"** fields of provided responses to generate your answers. If the user asks a complex question, break it down into simpler, more manageable sub-queries to guide your process effectively.
# Guidelines
- **Data Usage**: Strictly rely on the "answer" and "sources" fields for information. Do not infer or assume beyond what is explicitly provided. 
- **Complex Questions**: If the question is challenging or multi-faceted, first decompose it into smaller, simpler queries, ensuring each step aligns with the provided data.
- **Clarity in Explanation**: When delivering the final answer, clearly articulate the reasoning used to arrive at the conclusion based on the Morningstar data provided.
- **Consistency**: Ensure the terminology and phrasing used aligns with the financial and investment language standard for Morningstar.
# Steps
1. Determine if the question is straightforward or complex:
   - If straightforward, proceed directly to formulating an answer based on the "answer" and "sources" fields.
   - If complex, break it into simpler sub-queries, each directly addressable via data from the "answer" and "sources" fields.
2. Reference only the "answer" and "sources" fields to gather information for responding.
3. Construct a clear, concise answer or explanation using the gathered data.
4. If necessary, list the sources referenced to provide users with transparency.
# Output Format
The response should be in plain text, clearly structured, and concise. 
For simple queries:
- A direct, succinct answer based on the given data.
- Include a reference to the sources field if needed.
For complex queries:
- Briefly outline the parallel or sequential reasoning steps taken to address the question.
- Conclude with the final, comprehensive answer.
- Optionally: Cite sources derived from the provided data.
# Example
### Input:
"What are the key financial metrics of XYZ Company? What is my best course of action for diversification?"
### Process:
1. **Simplify the queries**:
   - What are the key financial metrics of XYZ Company?
   - What strategies can be considered for diversification?
2. Consult the "answer" and "sources" fields for data relevant to each sub-query.
### Output:
- XYZ Company's key financial metrics are as follows:
  - Revenue: [Insert data from answer field]
  - Net Income: [Insert data from answer field]
  - P/E Ratio: [Insert data from answer field]
  (Source: [Insert relevant sources here])
- Regarding diversification:
  - Based on provided data, one approach might be to [Insert strategy].
  (Source: [Insert relevant sources here])
# Notes
- Do not speculate or provide opinionsâ€”use only the supplied "answer" and "sources" fields.
- When data from Morningstar is insufficient to form a complete answer, explicitly communicate the limitation in the response."""

# Create agent with OpenApi tool and process assistant run
with project_client:
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL"],
        name="morningstar-agent",
        instructions=INSTRUCTIONS,
        tools=openapi.definitions,
    )

    print(f"Created agent, ID: {agent.id}")

    # Create thread for communication
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create message to thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content="What is value investing according to Morningstar?",
    )
    print(f"Created message, ID: {message.id}")

    # Create and process agent run in thread with tools
    run = project_client.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id,
    )
    print(f"Run finished with status: {run.status}")
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    run_steps = project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id)

    # Loop through each step
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")

        # Check if there are tool calls in the step details
        step_details = step.get("step_details", {})
        tool_calls = step_details.get("tool_calls", [])

        if tool_calls:
            print("  Tool calls:")
            for call in tool_calls:
                print(f"    Tool Call ID: {call.get('id')}")
                print(f"    Type: {call.get('type')}")

                function_details = call.get("function", {})
                if function_details:
                    print(f"    Function name: {function_details.get('name')}")
        print()  # add an extra newline between steps

    # Fetch and log all messages
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages:
        print(
            f"Message ID: {message.id}, Role: {message.role}, Content: {message.content}"
        )

    # Delete the agent when done
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")
