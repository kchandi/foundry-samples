# Sample for using Azure Functions with agents in Azure.AI.Agents

## Prerequisites
To make a function call we need to create and deploy the Azure function. In the code snippet below, we have an example of function on C# which can be used by the code above.

```C#
namespace FunctionProj
{
    public class Response
    {
        public required string Value { get; set; }
        public required string CorrelationId { get; set; }
    }

    public class Arguments
    {
        public required string OutputQueueUri { get; set; }
        public required string CorrelationId { get; set; }
    }

    public class Foo
    {
        private readonly ILogger<Foo> _logger;

        public Foo(ILogger<Foo> logger)
        {
            _logger = logger;
        }

        [Function("Foo")]
        public void Run([QueueTrigger("azure-function-foo-input")] Arguments input, FunctionContext executionContext)
        {
            var logger = executionContext.GetLogger("Foo");
            logger.LogInformation("C# Queue function processed a request.");

            // We have to provide the Managed identity for function resource
            // and allow this identity a Queue Data Contributor role on the storage account.
            var cred = new DefaultAzureCredential();
            var queueClient = new QueueClient(new Uri(input.OutputQueueUri), cred,
                    new QueueClientOptions { MessageEncoding = QueueMessageEncoding.Base64 });

            var response = new Response
            {
                Value = "Bar",
                // Important! Correlation ID must match the input correlation ID.
                CorrelationId = input.CorrelationId
            };

            var jsonResponse = JsonSerializer.Serialize(response);
            queueClient.SendMessage(jsonResponse);
        }
    }
}
```

In this code we define function input and output class: `Arguments` and `Response` respectively. These two data classes will be serialized in JSON. It is important that these both contain field `CorrelationId`, which is the same between input and output.

In our example the function will be stored in the storage account, created with the AI hub. For that we need to allow key access to that storage. In Azure portal go to Storage account > Settings > Configuration and set "Allow storage account key access" to Enabled. If it is not done, the error will be displayed "The remote server returned an error: (403) Forbidden." To create the function resource that will host our function, install azure-cli python package and run the next command:

```shell
pip install -U azure-cli
az login
az functionapp create --resource-group your-resource-group --consumption-plan-location region --runtime dotnet-isolated --functions-version 4 --name function_name --storage-account storage_account_already_present_in_resource_group --app-insights existing_or_new_application_insights_name
```

This function writes data to the output queue and hence needs to be authenticated to Azure, so we will need to assign the function system identity and provide it `Storage Queue Data Contributor`. To do that in Azure portal select the function, located in `your-resource-group` resource group and in Settings>Identity, switch it on and click Save. After that assign the `Storage Queue Data Contributor` permission on storage account used by our function (`storage_account_already_present_in_resource_group` in the script above) for just assigned System Managed identity.

Now we will create the function itself. Install [.NET](https://dotnet.microsoft.com/download) and [Core Tools](https://go.microsoft.com/fwlink/?linkid=2174087) and create the function project using next commands.
```
func init FunctionProj --worker-runtime dotnet-isolated --target-framework net8.0
cd FunctionProj
func new --name foo --template "HTTP trigger" --authlevel "anonymous"
dotnet add package Azure.Identity
dotnet add package Microsoft.Azure.Functions.Worker.Extensions.Storage.Queues --prerelease
```

**Note:** There is a "Azure Queue Storage trigger", however the attempt to use it results in error for now.
We have created a project, containing HTTP-triggered azure function with the logic in `Foo.cs` file. As far as we need to trigger Azure function by a new message in the queue, we will replace the content of a Foo.cs by the C# sample code above.
To deploy the function run the command from dotnet project folder:

```
func azure functionapp publish function_name
```

In the `storage_account_already_present_in_resource_group` select the `Queue service` and create two queues: `azure-function-foo-input` and `azure-function-tool-output`. Note that the same queues are used in our sample. To check that the function is working, place the next message into the `azure-function-foo-input` and replace `storage_account_already_present_in_resource_group` by the actual resource group name, or just copy the output queue address.
```json
{
  "OutputQueueUri": "https://storage_account_already_present_in_resource_group.queue.core.windows.net/azure-function-tool-output",
  "CorrelationId": "42"
}
```

Next, we will monitor the output queue or the message. You should receive the next message.
```json
{
  "Value": "Bar",
  "CorrelationId": "42"
}
```
Please note that the input `CorrelationId` is the same as output.
*Hint:* Place multiple messages to input queue and keep second internet browser window with the output queue open and hit the refresh button on the portal user interface, so that you will not miss the message. If the message instead went to `azure-function-foo-input-poison` queue, the function completed with error, please check your setup.
After we have tested the function and made sure it works, please make sure that the Azure AI Project have the next roles for the storage account: `Storage Account Contributor`, `Storage Blob Data Contributor`, `Storage File Data Privileged Contributor`, `Storage Queue Data Contributor` and `Storage Table Data Contributor`. Now the function is ready to be used by the agent.

In the example below we are calling function "foo", which responds "Bar".

## Azure.AI.Agents Sample Code

1. First, we set up the necessary configuration, initialize the `PersistentAgentsClient`, define the `AzureFunctionToolDefinition` for our Azure Function, and then create the agent. This step includes all necessary `using` directives.

    Common setup:

    ```C# Snippet:AzureFunctionStep1CommonSetup
    using Azure;
    using Azure.AI.Agents.Persistent;
    using Azure.Identity;
    using Microsoft.Extensions.Configuration;
    using System.Text.Json;

    IConfigurationRoot configuration = new ConfigurationBuilder()
        .SetBasePath(AppContext.BaseDirectory)
        .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
        .Build();

    var projectEndpoint = configuration["ProjectEndpoint"];
    var modelDeploymentName = configuration["ModelDeploymentName"];
    var storageQueueUri = configuration["StorageQueueURI"];
    PersistentAgentsClient client = new(projectEndpoint, new DefaultAzureCredential());

    AzureFunctionToolDefinition azureFnTool = new(
        name: "foo",
        description: "Get answers from the foo bot.",
        inputBinding: new AzureFunctionBinding(
            new AzureFunctionStorageQueue(
                queueName: "azure-function-foo-input",
                storageServiceEndpoint: storageQueueUri
            )
        ),
        outputBinding: new AzureFunctionBinding(
            new AzureFunctionStorageQueue(
                queueName: "azure-function-tool-output",
                storageServiceEndpoint: storageQueueUri
            )
        ),
        parameters: BinaryData.FromObjectAsJson(
                new
                {
                    Type = "object",
                    Properties = new
                    {
                        query = new
                        {
                            Type = "string",
                            Description = "The question to ask.",
                        },
                        outputqueueuri = new
                        {
                            Type = "string",
                            Description = "The full output queue uri."
                        }
                    },
                },
            new JsonSerializerOptions() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }
        )
    );
    ```

    Synchronous sample:

    ```C# Snippet:AzureFunctionStep1CreateAgentSync
    PersistentAgent agent = client.Administration.CreateAgent(
        model: modelDeploymentName,
        name: "azure-function-agent-foo",
        instructions: "You are a helpful support agent. Use the provided function any "
        + "time the prompt contains the string 'What would foo say?'. When you invoke "
        + "the function, ALWAYS specify the output queue uri parameter as "
        + $"'{storageQueueUri}/azure-function-tool-output'. Always responds with "
        + "\"Foo says\" and then the response from the tool.",
        tools: [azureFnTool]
    );
    ```

    Asynchronous sample:

    ```C# Snippet:AzureFunctionStep1CreateAgentAsync
    PersistentAgent agent = await client.Administration.CreateAgentAsync(
        model: modelDeploymentName,
        name: "azure-function-agent-foo",
        instructions: "You are a helpful support agent. Use the provided function any "
        + "time the prompt contains the string 'What would foo say?'. When you invoke "
        + "the function, ALWAYS specify the output queue uri parameter as "
        + $"'{storageQueueUri}/azure-function-tool-output'. Always responds with "
        + "\"Foo says\" and then the response from the tool.",
        tools: [azureFnTool]
    );
    ```

2. Next, we create a new persistent agent thread and add an initial user message to it.

    Synchronous sample:

    ```C# Snippet:AzureFunctionStep2CreateThreadMessageSync
    PersistentAgentThread thread = client.Threads.CreateThread();

    client.Messages.CreateMessage(
        thread.Id,
        MessageRole.User,
        "What is the most prevalent element in the universe? What would foo say?");
    ```

    Asynchronous sample:

    ```C# Snippet:AzureFunctionStep2CreateThreadMessageAsync
    PersistentAgentThread thread = await client.Threads.CreateThreadAsync();

    await client.Messages.CreateMessageAsync(
        thread.Id,
        MessageRole.User,
        "What is the most prevalent element in the universe? What would foo say?");
    ```

3. Then, we create a run for the agent on the thread and poll its status until it completes or requires action.

    Synchronous sample:

    ```C# Snippet:AzureFunctionStep3RunAndPollSync
    ThreadRun run = client.Runs.CreateRun(thread.Id, agent.Id);

    do
    {
        Thread.Sleep(TimeSpan.FromMilliseconds(500));
        run = client.Runs.GetRun(thread.Id, run.Id);
    }
    while (run.Status == RunStatus.Queued
        || run.Status == RunStatus.InProgress
        || run.Status == RunStatus.RequiresAction);
    ```

    Asynchronous sample:

    ```C# Snippet:AzureFunctionStep3RunAndPollAsync
    ThreadRun run = await client.Runs.CreateRunAsync(thread.Id, agent.Id);

    do
    {
        await Task.Delay(TimeSpan.FromMilliseconds(500));
        run = await client.Runs.GetRunAsync(thread.Id, run.Id);
    }
    while (run.Status == RunStatus.Queued
        || run.Status == RunStatus.InProgress
        || run.Status == RunStatus.RequiresAction);
    ```

4. After the run is complete, we retrieve and process the messages from the thread.

    Synchronous sample:

    ```C# Snippet:AzureFunctionStep4ProcessResultsSync
    Pageable<ThreadMessage> messages = client.Messages.GetMessages(
        threadId: thread.Id,
        order: ListSortOrder.Ascending
    );

    foreach (ThreadMessage threadMessage in messages)
    {
        foreach (MessageContent content in threadMessage.ContentItems)
        {
            switch (content)
            {
                case MessageTextContent textItem:
                    Console.WriteLine($"[{threadMessage.Role}]: {textItem.Text}");
                    break;
            }
        }
    }
    ```

    Asynchronous sample:

    ```C# Snippet:AzureFunctionStep4ProcessResultsAsync
    AsyncPageable<ThreadMessage> messages = client.Messages.GetMessagesAsync(
        threadId: thread.Id,
        order: ListSortOrder.Ascending
    );

    await foreach (ThreadMessage threadMessage in messages)
    {
        foreach (MessageContent content in threadMessage.ContentItems)
        {
            switch (content)
            {
                case MessageTextContent textItem:
                    Console.WriteLine($"[{threadMessage.Role}]: {textItem.Text}");
                    break;
            }
        }
    }
    ```

5. Finally, we clean up the created resources by deleting the thread and the agent.

    Synchronous sample:

    ```C# Snippet:AzureFunctionStep5CleanupSync
    client.Threads.DeleteThread(thread.Id);
    client.Administration.DeleteAgent(agent.Id);
    ```

    Asynchronous sample:

    ```C# Snippet:AzureFunctionStep5CleanupAsync
    await client.Threads.DeleteThreadAsync(thread.Id);
    await client.Administration.DeleteAgentAsync(agent.Id);
    ```
